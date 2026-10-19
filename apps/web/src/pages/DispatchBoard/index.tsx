import { useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useRequests } from '../../hooks/useRequests';
import { fetchSectors, fetchEmployees, ApiError } from '../../api/client';
import type { Lang } from '../../i18n';
import { t } from '../../i18n';
import FilterBar from './FilterBar';
import RequestTable from './RequestTable';
import DetailPanel from './DetailPanel';
import NouvelAppelModal from './NouvelAppelModal';
import Pagination from '../../components/Pagination';
import { DEMO_ROW, isDemoEnabled } from '../../dev/demoRequest';
import styles from './index.module.css';

import type { MeResponse } from '../../api/schema.d.ts';

interface Props {
  lang: Lang;
  me?: MeResponse | null;
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

export default function DispatchBoard({ lang, me }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showAllCols, setShowAllCols] = useState(false);
  const [showNewCall, setShowNewCall] = useState(false);
  const isCoordOrDir = !!(me?.roles.includes('coordinator') || me?.roles.includes('director'));

  // Side-menu entry point: ?nouvel-appel=1 opens the modal. The param is
  // stripped on close/save so a refresh afterwards does not reopen it.
  const newCallParam = searchParams.get('nouvel-appel') === '1';
  useEffect(() => {
    if (newCallParam) setShowNewCall(true);
  }, [newCallParam]);

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

  const startDate = searchParams.get('start_date') ?? DEFAULT_START;
  const endDate = searchParams.get('end_date') ?? DEFAULT_END;
  const statusParam = searchParams.getAll('status');
  const sourceCalendar = searchParams.get('source_calendar') ?? undefined;
  const q = searchParams.get('q') ?? undefined;
  const sortBy = searchParams.get('sort_by') ?? 'start_date';
  const sortDir = (searchParams.get('sort_dir') ?? 'asc') as 'asc' | 'desc';
  const offset = Number(searchParams.get('offset') ?? '0');
  const sectorId = searchParams.get('sector_id')
    ? Number(searchParams.get('sector_id'))
    : undefined;
  const urgency = searchParams.get('urgency') ?? undefined;
  const assignedEmployeeId = searchParams.get('assigned_employee_id')
    ? Number(searchParams.get('assigned_employee_id'))
    : undefined;
  const redispatch = searchParams.get('redispatch') === '1';

  const params = {
    start_date: startDate,
    end_date: endDate,
    status: statusParam.length ? statusParam : undefined,
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
  };

  const isDateRangeValid = (() => {
    if (!startDate || !endDate) return true;
    const days = (new Date(endDate).getTime() - new Date(startDate).getTime()) / 86400000;
    return days >= 0 && days <= 31;
  })();

  // Keep last valid params so the table retains its data while the range error is shown.
  const lastValidParamsRef = useRef(params);
  if (isDateRangeValid) lastValidParamsRef.current = params;

  const { data, isPending, isError, error } = useRequests(lastValidParamsRef.current);

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
    'start_date', 'end_date', 'status', 'source_calendar', 'q',
    'sector_id', 'urgency', 'assigned_employee_id', 'redispatch',
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
      values.forEach((v) => next.append('status', v));
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
  const total = (data?.total ?? 0) + (demo ? 1 : 0);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleBlock}>
          <h1>{t(lang, 'Répartition', 'Dispatch')}</h1>
          <p className={styles.subtitle}>{t(lang, 'Appels de service et assignations', 'Service calls and assignments')}</p>
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
        startDate={startDate}
        endDate={endDate}
        status={statusParam}
        sourceCalendar={sourceCalendar ?? ''}
        q={q ?? ''}
        total={total}
        sectors={sectors ?? []}
        sectorId={sectorId ?? null}
        urgency={urgency ?? ''}
        employees={employees ?? []}
        assignedEmployeeId={assignedEmployeeId ?? null}
        showAllCols={showAllCols}
        redispatch={redispatch}
        onRedispatch={(v) => setFilter('redispatch', v ? '1' : null)}
        onStartDate={(v) => setFilter('start_date', v)}
        onEndDate={(v) => setFilter('end_date', v)}
        onStatus={setStatusFilter}
        onSourceCalendar={(v) => setFilter('source_calendar', v)}
        onQ={(v) => setFilter('q', v || null)}
        onSectorId={(v) => setFilter('sector_id', v !== null ? String(v) : null)}
        onUrgency={(v) => setFilter('urgency', v || null)}
        onAssignedEmployeeId={(v) =>
          setFilter('assigned_employee_id', v !== null ? String(v) : null)
        }
        dateNote={sourceCalendar === 'unrouted'
          ? t(lang, 'dates ignorées — 90 derniers jours', 'dates ignored — last 90 days')
          : undefined}
        onToggleCols={() => setShowAllCols((b) => !b)}
        hasActiveFilters={hasActiveFilters}
        onReset={resetFilters}
      />

      {/* Only this area scrolls; header, filters and paging stay put. */}
      <div className={styles.scrollArea} data-testid="board-scroll">
        {(data?.unscheduled_items?.length ?? 0) > 0 && (
          <div className={styles.tableWrap} data-testid="unscheduled-group">
            <h2 className={styles.groupHeading}>
              {t(
                lang,
                `À traiter — sans date (${data!.unscheduled_items.length})`,
                `Needs attention — no date yet (${data!.unscheduled_items.length})`,
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

        <div className={styles.tableWrap}>
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
      </div>

      <Pagination
        offset={offset}
        pageSize={PAGE_SIZE}
        total={total}
        lang={lang}
        onPrev={() => setPage(Math.max(0, offset - PAGE_SIZE))}
        onNext={() => setPage(offset + PAGE_SIZE)}
      />

      {selectedId !== null && (
        <DetailPanel
          lang={lang}
          requestId={selectedId}
          onClose={() => setSelectedId(null)}
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
