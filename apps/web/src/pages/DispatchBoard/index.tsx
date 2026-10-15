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
import Pagination from '../../components/Pagination';
import styles from './index.module.css';

interface Props {
  lang: Lang;
  employeeId: string | null;
}

const PAGE_SIZE = 50;
const DEFAULT_START = '2026-09-01';
const DEFAULT_END = '2026-09-25';

export default function DispatchBoard({ lang, employeeId }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showAllCols, setShowAllCols] = useState(false);

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

  const { data, isPending, isError, error } = useRequests(params, employeeId);

  const { data: sectors } = useQuery({
    queryKey: ['sectors', employeeId],
    queryFn: () => fetchSectors(employeeId),
    staleTime: 5 * 60 * 1000,
  });

  const { data: employees } = useQuery({
    queryKey: ['employees', employeeId],
    queryFn: () => fetchEmployees(employeeId),
    staleTime: 5 * 60 * 1000,
  });

  // Changing a filter resets to page 1.
  function setFilter(key: string, value: string | null) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value === null || value === '') next.delete(key);
      else next.set(key, value);
      next.delete('offset');
      return next;
    });
  }

  // For page navigation only — does NOT reset offset.
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

  const errorMsg = is403
    ? t(lang, 'Choisissez un utilisateur', 'Choose a user')
    : undefined;

  const total = data?.total ?? 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>{t(lang, 'Répartition', 'Dispatch')}</h1>
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
        onToggleCols={() => setShowAllCols((b) => !b)}
      />

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
          employeeId={employeeId}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}
