import { useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useRequests } from '../../hooks/useRequests';
import { useTasks } from '../../hooks/useTasks';
import { fetchSectors, fetchEmployees, ApiError } from '../../api/client';
import type { BoardMode } from '../../api/boardModes';
import { clampStatusesToMode, defaultStatusesForMode } from '../../api/boardModes';
import { expandStatusFilter } from '../../api/statusValues';
import type { TaskListItem } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t } from '../../i18n';
import FilterBar from './FilterBar';
import RequestTable from './RequestTable';
import TaskTable, { sortTasks, taskUrgency, type TaskSortKey } from './TaskTable';
import DetailPanel from './DetailPanel';
import NouvelAppelModal from './NouvelAppelModal';
import TaskDayStrip from './TaskDayStrip';
import Pagination from '../../components/Pagination';
import { DEMO_ROW, isDemoEnabled } from '../../dev/demoRequest';
import styles from './index.module.css';

import type { MeResponse } from '../../api/schema.d.ts';

interface Props {
  lang: Lang;
  me?: MeResponse | null;
  mode: BoardMode;
}

const PAGE_SIZE = 50;

/** Local calendar dates in America/Toronto (matches backend today_local). */
function torontoYmd(d: Date = new Date()): string {
  return d.toLocaleDateString('en-CA', { timeZone: 'America/Toronto' }); // YYYY-MM-DD
}

function defaultDateRange(): { start: string; end: string } {
  const end = torontoYmd();
  const start = `${end.slice(0, 7)}-01`; // first day of current month
  return { start, end };
}

const { start: DEFAULT_START, end: DEFAULT_END } = defaultDateRange();

const TASK_SORT_KEYS: readonly string[] = [
  'due_at', 'urgency_tier', 'description', 'territoire',
  'building_address', 'assigned_employee_name', 'status',
] satisfies TaskSortKey[];

/** Board filters GET /tasks does not take — applied to the returned window. */
function matchesTaskFilters(
  row: TaskListItem,
  f: { sectorId?: number; urgency?: string; q?: string; hasSubcontractor?: boolean },
): boolean {
  if (f.sectorId != null && row.sector_id !== f.sectorId) return false;
  if (f.urgency && taskUrgency(row) !== f.urgency) return false;
  if (f.hasSubcontractor != null && (row.subcontractor_name != null) !== f.hasSubcontractor) return false;
  if (f.q) {
    const needle = f.q.toLowerCase();
    const hay = [
      row.description, row.request_title, row.request_asnu, row.building_address,
      row.unit_label, row.assigned_employee_name, row.territoire, String(row.request_id),
    ].filter(Boolean).join(' ').toLowerCase();
    if (!hay.includes(needle)) return false;
  }
  return true;
}

export default function DispatchBoard({ lang, me, mode }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [showAllCols, setShowAllCols] = useState(false);
  const [showNewCall, setShowNewCall] = useState(false);
  const isCoordOrDir = !!(me?.roles.includes('coordinator') || me?.roles.includes('director'));
  const isTriage = mode === 'triage';

  // Side-menu entry point: ?nouvel-appel=1 opens the modal. The param is
  // stripped on close/save so a refresh afterwards does not reopen it.
  const newCallParam = searchParams.get('nouvel-appel') === '1';
  useEffect(() => {
    if (newCallParam) setShowNewCall(true);
  }, [newCallParam]);

  // Alert bell deep-link: ?request_id=N selects that call in the detail panel.
  const deepRequestId = searchParams.get('request_id');
  useEffect(() => {
    if (deepRequestId) setSelectedId(Number(deepRequestId));
  }, [deepRequestId]);

  function closeNewCall() {
    setShowNewCall(false);
    if (newCallParam) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete('nouvel-appel');
        return next;
      }, { replace: true });
    }
  }

  const rangeStart = searchParams.get('start_date') ?? DEFAULT_START;
  const rangeEnd = searchParams.get('end_date') ?? DEFAULT_END;
  /** Tasks: optional single-day focus within the range. */
  const dayFocus = searchParams.get('day');
  const startDate = isTriage ? '' : (dayFocus && dayFocus >= rangeStart && dayFocus <= rangeEnd ? dayFocus : rangeStart);
  const endDate = isTriage ? '' : (dayFocus && dayFocus >= rangeStart && dayFocus <= rangeEnd ? dayFocus : rangeEnd);
  const statusParam = clampStatusesToMode(mode, searchParams.getAll('status'));
  const sourceCalendar = searchParams.get('source_calendar') ?? undefined;
  const q = searchParams.get('q') ?? undefined;
  const sortParam = searchParams.get('sort_by');
  const sortBy = isTriage
    ? (sortParam ?? 'urgency_tier')
    : (sortParam && TASK_SORT_KEYS.includes(sortParam) ? sortParam : 'due_at');
  const sortDir = (searchParams.get('sort_dir')
    ?? (isTriage ? 'asc' : 'asc')) as 'asc' | 'desc';
  const offset = Number(searchParams.get('offset') ?? '0');
  const sectorId = searchParams.get('sector_id')
    ? Number(searchParams.get('sector_id'))
    : undefined;
  const urgency = searchParams.get('urgency') ?? undefined;
  const assignedEmployeeId = searchParams.get('assigned_employee_id')
    ? Number(searchParams.get('assigned_employee_id'))
    : undefined;
  const redispatch = !isTriage && searchParams.get('redispatch') === '1';
  const hasSubParam = searchParams.get('has_subcontractor');
  const hasSubcontractor = hasSubParam === 'true' ? true
    : hasSubParam === 'false' ? false
    : undefined;

  // Mode default statuses when URL has none; Received expands triage_pending.
  const statusForApi = expandStatusFilter(
    statusParam.length ? statusParam : defaultStatusesForMode(mode),
  );

  const params = {
    status: statusForApi,
    source_calendar: sourceCalendar,
    q: q || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    limit: PAGE_SIZE,
    offset,
    sector_id: sectorId,
    urgency: urgency || undefined,
    assigned_employee_id: assignedEmployeeId,
    redispatch: redispatch || undefined,
    has_subcontractor: hasSubcontractor,
  };

  const isDateRangeValid = (() => {
    if (isTriage || !startDate || !endDate) return true;
    const days = (new Date(endDate).getTime() - new Date(startDate).getTime()) / 86400000;
    return days >= 0 && days <= 31;
  })();

  // Keep last valid params so the table retains its data while the range error is shown.
  const lastValidParamsRef = useRef(params);
  if (isDateRangeValid) lastValidParamsRef.current = params;

  const requestsQuery = useRequests(isTriage ? lastValidParamsRef.current : null);

  // « À redispatcher » = tasks that came back needing expertise or a return
  // visit, any date, until a follow-up task is created for them.
  const taskParams = isTriage ? null : (redispatch
    ? { status: ['needs_expertise', 'return_visit'], assigned_employee_id: assignedEmployeeId }
    : { start_date: startDate, end_date: endDate, status: statusForApi, assigned_employee_id: assignedEmployeeId });
  const lastValidTaskParamsRef = useRef(taskParams);
  if (isDateRangeValid) lastValidTaskParamsRef.current = taskParams;
  const tasksQuery = useTasks(isTriage ? null : lastValidTaskParamsRef.current);
  // Undated tasks are always queued (scheduled needs a date); the range query cannot see them.
  const showUndated = !isTriage && !redispatch && statusForApi.includes('queued');
  const undatedQuery = useTasks(showUndated
    ? { status: ['queued'], assigned_employee_id: assignedEmployeeId }
    : null);

  const { isPending, isError, error } = isTriage ? requestsQuery : tasksQuery;
  const data = requestsQuery.data;
  const taskFilters = { sectorId, urgency, q, hasSubcontractor };
  const taskRows = sortTasks(
    (tasksQuery.data?.items ?? []).filter((r) =>
      matchesTaskFilters(r, taskFilters) && !(redispatch && r.has_followup)),
    sortBy, sortDir,
  );
  const undatedTasks = showUndated
    ? sortTasks(
      (undatedQuery.data?.items ?? []).filter((r) => r.due_at == null && matchesTaskFilters(r, taskFilters)),
      sortBy, sortDir,
    )
    : [];

  function selectTask(row: TaskListItem) {
    setSelectedTaskId(row.task_id);
    setSelectedId(row.request_id);
  }

  const { data: sectors } = useQuery({
    queryKey: ['sectors'],
    queryFn: fetchSectors,
    staleTime: 5 * 60 * 1000,
  });

  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: fetchEmployees,
    staleTime: 5 * 60 * 1000,
  });

  function setFilter(key: string, value: string | null) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value === null || value === '') next.delete(key);
      else next.set(key, value);
      next.delete('offset');
      return next;
    });
  }

  // URL params that narrow the list (sort and paging are not filters).
  const FILTER_KEYS = [
    'start_date', 'end_date', 'day', 'status', 'source_calendar', 'q',
    'sector_id', 'urgency', 'assigned_employee_id', 'redispatch',
    'has_subcontractor', 'sort_by', 'sort_dir',
  ];
  const hasActiveFilters = FILTER_KEYS.some((k) => searchParams.has(k));

  function resetFilters() {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      FILTER_KEYS.forEach((k) => next.delete(k));
      next.delete('offset');
      return next;
    });
  }

  function setDayFocus(day: string | null) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (day) next.set('day', day);
      else next.delete('day');
      next.delete('offset');
      return next;
    });
  }

  function setPage(newOffset: number) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (newOffset > 0) next.set('offset', String(newOffset));
      else next.delete('offset');
      return next;
    });
  }

  function setStatusFilter(values: string[]) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete('status');
      clampStatusesToMode(mode, values).forEach((v) => next.append('status', v));
      next.delete('offset');
      return next;
    });
  }

  function handleSort(key: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (key === sortBy) {
        next.set('sort_dir', sortDir === 'asc' ? 'desc' : 'asc');
      } else {
        next.set('sort_by', key);
        next.set('sort_dir', 'asc');
      }
      next.delete('offset');
      return next;
    });
  }

  const is403 =
    isError &&
    error instanceof ApiError &&
    (error.code === 'PERMISSION_DENIED' || error.code === 'HTTP_403');

  const errorMsg = !isError
    ? undefined
    : is403
      ? t(lang, 'Accès refusé', 'Access denied')
      : error instanceof ApiError && error.code === 'VALIDATION_FAILED' && error.message.includes('31 day')
        ? t(lang, 'La plage de dates ne peut pas dépasser 31 jours', error.message)
        : error instanceof ApiError && error.code === 'VALIDATION_FAILED' && error.message.includes('end_date')
          ? t(lang, 'La date de fin ne peut pas précéder la date de début', error.message)
          : (error instanceof ApiError ? error.message : t(lang, 'Erreur', 'Error'));

  // Dev-only: ?demo=1 puts one fake call at the top of the main table.
  const demo = isDemoEnabled(searchParams);
  const mainRows = demo ? [DEMO_ROW, ...(data?.items ?? [])] : (data?.items ?? []);
  const total = isTriage
    ? (data?.total ?? 0) + (demo ? 1 : 0)
    : taskRows.length + undatedTasks.length;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleBlock}>
          <h1>
            {isTriage
              ? t(lang, 'Triage', 'Triage')
              : t(lang, 'Tâches', 'Tasks')}
          </h1>
          <p className={styles.subtitle}>
            {isTriage
              ? t(lang, 'Nouveaux appels à prioriser et assigner', 'New calls to prioritize and assign')
              : t(lang, 'Travaux à planifier, planifiés et en cours', 'Work to plan, planned and in progress')}
          </p>
        </div>
        {isCoordOrDir && (
          <button
            data-testid="nouvel-appel-btn"
            onClick={() => setShowNewCall(true)}
            className={styles.newCallBtn}
          >
            {t(lang, '+ Nouvel appel', '+ New call')}
          </button>
        )}
      </header>

      <FilterBar
        lang={lang}
        mode={mode}
        startDate={rangeStart}
        endDate={rangeEnd}
        status={statusParam}
        sourceCalendar={sourceCalendar ?? ''}
        q={q ?? ''}
        total={total}
        sectors={sectors ?? []}
        sectorId={sectorId ?? null}
        urgency={urgency ?? ''}
        employees={employees ?? []}
        assignedEmployeeId={assignedEmployeeId ?? null}
        hasSubcontractor={hasSubcontractor ?? null}
        showAllCols={showAllCols}
        redispatch={redispatch}
        onRedispatch={(v) => setFilter('redispatch', v ? '1' : null)}
        onStartDate={(v) => setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          if (v) next.set('start_date', v); else next.delete('start_date');
          next.delete('day');
          next.delete('offset');
          return next;
        })}
        onEndDate={(v) => setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          if (v) next.set('end_date', v); else next.delete('end_date');
          next.delete('day');
          next.delete('offset');
          return next;
        })}
        onDateRange={(start, end) => setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          next.set('start_date', start);
          next.set('end_date', end);
          next.delete('day');
          next.delete('offset');
          return next;
        })}
        onStatus={setStatusFilter}
        onSourceCalendar={(v) => setFilter('source_calendar', v)}
        onQ={(v) => setFilter('q', v || null)}
        onSectorId={(v) => setFilter('sector_id', v !== null ? String(v) : null)}
        onUrgency={(v) => setFilter('urgency', v || null)}
        onAssignedEmployeeId={(v) =>
          setFilter('assigned_employee_id', v !== null ? String(v) : null)
        }
        onHasSubcontractor={(v) =>
          setFilter('has_subcontractor', v == null ? null : String(v))
        }
        onToggleCols={() => setShowAllCols((b) => !b)}
        hasActiveFilters={hasActiveFilters}
        onReset={resetFilters}
        countUnit={isTriage ? 'call' : 'task'}
        showSourceFilter={isTriage}
      />

      {!isTriage && (
        <TaskDayStrip
          lang={lang}
          startDate={rangeStart}
          endDate={rangeEnd}
          selectedDay={dayFocus && dayFocus >= rangeStart && dayFocus <= rangeEnd ? dayFocus : null}
          onSelectDay={setDayFocus}
        />
      )}

      {/* Only the table cards scroll; header, filters and paging stay put. */}
      {!isTriage && (
        <div className={styles.scrollArea} data-testid="board-scroll">
          {undatedTasks.length > 0 && (
            <div className={`${styles.tableWrap} ${styles.unscheduledGroup}`} data-testid="unscheduled-group">
              <h2 className={styles.groupHeading}>
                {t(lang, `Sans date (${undatedTasks.length})`, `No date (${undatedTasks.length})`)}
              </h2>
              <TaskTable
                lang={lang}
                inScroller
                rows={undatedTasks}
                selectedTaskId={selectedTaskId}
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={handleSort}
                onSelect={selectTask}
                isLoading={false}
                isError={false}
              />
            </div>
          )}
          <div className={`${styles.tableWrap} ${styles.mainGroup}`}>
            <TaskTable
              lang={lang}
              inScroller
              rows={taskRows}
              selectedTaskId={selectedTaskId}
              sortBy={sortBy}
              sortDir={sortDir}
              onSort={handleSort}
              onSelect={selectTask}
              isLoading={isPending}
              isError={isError}
              errorMsg={errorMsg}
            />
          </div>
        </div>
      )}

      {isTriage && <div className={styles.scrollArea} data-testid="board-scroll">
        {(data?.unscheduled_items?.length ?? 0) > 0 && (
          <div className={`${styles.tableWrap} ${styles.unscheduledGroup}`} data-testid="unscheduled-group">
            <h2 className={styles.groupHeading}>
              {t(
                lang,
                `Sans date (${data!.unscheduled_items.length})`,
                `No date (${data!.unscheduled_items.length})`,
              )}
            </h2>
            <RequestTable
              lang={lang}
              inScroller
              rows={data!.unscheduled_items}
              selectedId={selectedId}
              sortBy={sortBy}
              sortDir={sortDir}
              onSort={() => {}}
              onSelect={setSelectedId}
              isLoading={false}
              isError={false}
              total={data!.unscheduled_items.length}
              showAllCols={showAllCols}
            />
          </div>
        )}

        <div className={`${styles.tableWrap} ${styles.mainGroup}`}>
          <RequestTable
            lang={lang}
            inScroller
            rows={mainRows}
            selectedId={selectedId}
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={handleSort}
            onSelect={setSelectedId}
            isLoading={isPending && !demo}
            isError={isError && !demo}
            total={total}
            showAllCols={showAllCols}
            errorMsg={errorMsg}
          />
        </div>
      </div>}

      {isTriage && (
        <Pagination
          offset={offset}
          pageSize={PAGE_SIZE}
          total={total}
          lang={lang}
          onPrev={() => setPage(Math.max(0, offset - PAGE_SIZE))}
          onNext={() => setPage(offset + PAGE_SIZE)}
        />
      )}

      {selectedId !== null && (
        <DetailPanel
          lang={lang}
          requestId={selectedId}
          onClose={() => { setSelectedId(null); setSelectedTaskId(null); }}
          onSelectPeer={setSelectedId}
          me={me}
        />
      )}

      <NouvelAppelModal
        open={showNewCall}
        onClose={closeNewCall}
        lang={lang}
      />
    </div>
  );
}
