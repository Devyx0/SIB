import { useState } from 'react';
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
import styles from './index.module.css';

import type { MeResponse } from '../../api/schema.d.ts';

interface Props {
  lang: Lang;
  me?: MeResponse | null;
}

const PAGE_SIZE = 50;
const DEFAULT_START = '2026-09-01';
const DEFAULT_END = '2026-09-25';

export default function DispatchBoard({ lang, me }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showAllCols, setShowAllCols] = useState(false);
  const [showNewCall, setShowNewCall] = useState(false);
  const isCoordOrDir = !!(me?.roles.includes('coordinator') || me?.roles.includes('director'));

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
  };

  const isDateRangeValid = (() => {
    if (!startDate || !endDate) return true;
    const days = (new Date(endDate).getTime() - new Date(startDate).getTime()) / 86400000;
    return days >= 0 && days <= 31;
  })();

  const { data, isPending, isError, error } = useRequests(isDateRangeValid ? params : null);

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

  const total = data?.total ?? 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>{t(lang, 'Répartition', 'Dispatch')}</h1>
        {isCoordOrDir && (
          <button
            data-testid="nouvel-appel-btn"
            onClick={() => setShowNewCall(true)}
            style={{ fontWeight: 700, padding: '6px 16px', background: 'var(--color-accent)', color: '#fff', border: 'none', borderRadius: 'var(--r-md)', cursor: 'pointer', fontSize: 13 }}
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
      />

      {(data?.unscheduled_items?.length ?? 0) > 0 && (
        <div className={styles.tableWrap} data-testid="unscheduled-group">
          <h2 style={{ fontSize: 13, fontWeight: 600, padding: '8px 12px 4px', margin: 0, background: 'var(--color-bg-alt, #f5f5f5)' }}>
            {t(lang, `À planifier (${data!.unscheduled_items.length})`, `To schedule (${data!.unscheduled_items.length})`)}
          </h2>
          <RequestTable
            lang={lang}
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
          rows={data?.items ?? []}
          selectedId={selectedId}
          sortBy={sortBy}
          sortDir={sortDir}
          onSort={handleSort}
          onSelect={setSelectedId}
          isLoading={isPending}
          isError={isError}
          total={total}
          showAllCols={showAllCols}
          errorMsg={errorMsg}
        />
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
        onClose={() => setShowNewCall(false)}
        lang={lang}
      />
    </div>
  );
}
