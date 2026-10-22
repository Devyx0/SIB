/** /tasks board: one row per dispatch_task (accepted), grouped by due day. */
import type { KeyboardEvent } from 'react';
import type { TaskListItem } from '../../api/schema.d.ts';
import { t, type Lang } from '../../i18n';
import { googleMapsUrl } from '../../lib/maps';
import { dueDay } from '../../lib/taskDates';
import { StatusTag, UrgencyTag } from './RequestTable';
import styles from './RequestTable.module.css';

export type TaskSortKey =
  | 'due_at' | 'urgency_tier' | 'description' | 'territoire'
  | 'building_address' | 'assigned_employee_name' | 'status';

interface Props {
  lang?: Lang;
  rows: TaskListItem[];
  selectedTaskId: number | null;
  sortBy: string;
  sortDir: 'asc' | 'desc';
  onSort: (key: string) => void;
  onSelect: (row: TaskListItem) => void;
  isLoading: boolean;
  isError: boolean;
  errorMsg?: string;
  inScroller?: boolean;
}

const COLS: { key: TaskSortKey; fr: string; en: string }[] = [
  { key: 'due_at',                 fr: 'Date',          en: 'Date' },
  { key: 'urgency_tier',           fr: 'Urgence',       en: 'Urgency' },
  { key: 'description',            fr: 'Tâche',         en: 'Task' },
  { key: 'territoire',             fr: 'Territoire',    en: 'Territory' },
  { key: 'building_address',       fr: 'Immeuble',      en: 'Building' },
  { key: 'assigned_employee_name', fr: 'Employé',       en: 'Employee' },
  { key: 'status',                 fr: 'Statut',        en: 'Status' },
];

export function taskUrgency(row: TaskListItem): string | null {
  return row.urgency_tier ?? row.request_urgency_tier;
}

const URGENCY_RANK: Record<string, number> = { URGENT: 0, 'Intermédiaire': 1, Faible: 2 };

function sortValue(row: TaskListItem, key: string): string | number | null {
  switch (key) {
    case 'due_at': return row.due_at;
    case 'urgency_tier': { const u = taskUrgency(row); return u ? URGENCY_RANK[u] ?? 3 : null; }
    case 'description': return row.description.toLowerCase();
    case 'territoire': return row.territoire;
    case 'building_address': return row.building_address;
    case 'assigned_employee_name': return row.assigned_employee_name;
    case 'status': return row.status;
    default: return null;
  }
}

/** Client-side sort (GET /tasks returns the whole window); nulls always last. */
export function sortTasks(rows: TaskListItem[], key: string, dir: 'asc' | 'desc'): TaskListItem[] {
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = sortValue(a, key);
    const vb = sortValue(b, key);
    if (va == null && vb == null) return a.task_id - b.task_id;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (va < vb) return -sign;
    if (va > vb) return sign;
    return a.task_id - b.task_id;
  });
}

export default function TaskTable({
  lang = 'fr', rows, selectedTaskId, sortBy, sortDir, onSort, onSelect,
  isLoading, isError, errorMsg, inScroller = false,
}: Props) {
  const colCount = COLS.length;
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
  const dayFmt = new Intl.DateTimeFormat(lang === 'fr' ? 'fr-CA' : 'en-CA', {
    weekday: 'long', day: 'numeric', month: 'long',
  });
  function dayLabel(ymd: string): string {
    const [y, m, d] = ymd.split('-').map(Number);
    const label = dayFmt.format(new Date(y, m - 1, d));
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTableSectionElement>) {
    const idx = rows.findIndex((r) => r.task_id === selectedTaskId);
    const next = e.key === 'ArrowDown' ? rows[idx + 1] : e.key === 'ArrowUp' ? rows[idx - 1] : undefined;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') e.preventDefault();
    if (next) onSelect(next);
  }

  function renderRows() {
    if (isLoading) {
      return Array.from({ length: 3 }).map((_, i) => (
        <tr key={i} className={styles.skeleton}>
          {COLS.map((c) => <td key={c.key}><span className={styles.skeletonCell} /></td>)}
        </tr>
      ));
    }
    if (isError) {
      return (
        <tr>
          <td colSpan={colCount} className={styles.emptyState}>
            {errorMsg ?? t(lang, 'Erreur lors du chargement.', 'Loading error.')}
          </td>
        </tr>
      );
    }
    if (rows.length === 0) {
      return (
        <tr>
          <td colSpan={colCount} className={styles.emptyState}>
            <span className={styles.emptyTitle}>
              {t(lang, 'Aucune tâche dans cette plage.', 'No tasks in this range.')}
            </span>
            <span className={styles.emptyHint}>
              {t(lang,
                'Élargissez la période ou retirez des filtres pour voir plus de résultats.',
                'Widen the period or remove filters to see more results.')}
            </span>
          </td>
        </tr>
      );
    }

    const showDayHeaders = sortBy === 'due_at';
    const perDay = new Map<string, number>();
    rows.forEach((r) => {
      const d = dueDay(r.due_at);
      if (d) perDay.set(d, (perDay.get(d) ?? 0) + 1);
    });

    const out: JSX.Element[] = [];
    let lastDay: string | null = null;
    rows.forEach((row) => {
      const day = dueDay(row.due_at);
      if (showDayHeaders && day && day !== lastDay) {
        lastDay = day;
        out.push(
          <tr
            key={`day-${day}`}
            className={styles.dayHeader}
            data-weekday={new Date(`${day}T12:00:00`).getDay()}
            data-testid="day-header"
          >
            <td colSpan={colCount} className={styles.dayHeaderCell}>
              <span className={styles.daySwatch} aria-hidden="true" />
              <span className={styles.dayName}>{dayLabel(day)}</span>
              {day === today && <span className={styles.todayTag}>{t(lang, "Aujourd'hui", 'Today')}</span>}
              <span className={styles.dayCount}>
                {perDay.get(day) ?? 0} {t(lang, 'tâche(s)', 'task(s)')}
              </span>
            </td>
          </tr>,
        );
      }

      const urgency = taskUrgency(row);
      const isSelected = row.task_id === selectedTaskId;
      const isEscalated = row.status === 'needs_expertise';
      const address = row.building_address
        ? `${row.building_address}${row.unit_label ? `, app. ${row.unit_label}` : ''}`
        : null;
      out.push(
        <tr
          key={row.task_id}
          className={[
            styles.row,
            urgency === 'URGENT' ? styles.ajdRow : '',
            isEscalated ? styles.escalatedRow : '',
            isSelected ? styles.selectedRow : '',
          ].join(' ')}
          aria-selected={isSelected}
          onClick={() => onSelect(row)}
          onKeyDown={(e) => { if (e.key === 'Enter') onSelect(row); }}
          data-testid="task-row"
          data-escalated={isEscalated || undefined}
          tabIndex={0}
        >
          <td className={`${styles.nowrap} ${styles.dateCell}`}>{day ?? '—'}</td>
          <td className={styles.nowrap}><UrgencyTag tier={urgency} lang={lang} /></td>
          <td className={styles.titleCell}>
            <span className={styles.clamp} title={row.description}>{row.description}</span>
            <span className={`${styles.clamp} ${styles.muted}`} title={row.request_title ?? undefined}>
              #{row.request_id} {row.request_title ?? ''}
            </span>
          </td>
          <td className={styles.nowrap}>{row.territoire ?? '—'}</td>
          <td className={styles.buildingCell}>
            {address ? (
              <a
                className={`${styles.clamp} ${styles.mapLink}`}
                href={googleMapsUrl(row.building_address!)}
                target="_blank"
                rel="noopener noreferrer"
                title={`${address} — ${t(lang, 'Ouvrir dans Google Maps', 'Open in Google Maps')}`}
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                {address}
                <span aria-hidden="true"> ↗</span>
              </a>
            ) : '—'}
          </td>
          <td className={`${styles.nowrap} ${styles.bold}`}>
            {row.assigned_employee_name ?? row.subcontractor_name ?? '—'}
          </td>
          <td className={styles.nowrap}><StatusTag status={row.status} lang={lang} /></td>
        </tr>,
      );
    });
    return out;
  }

  return (
    <div className={`${styles.wrap} ${inScroller ? styles.inScroller : ''}`}>
      <table className={styles.table}>
        <thead>
          <tr>
            {COLS.map((c) => (
              <th
                key={c.key}
                scope="col"
                onClick={() => onSort(c.key)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSort(c.key); } }}
                tabIndex={0}
                aria-sort={c.key === sortBy ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                className={styles.sortable}
              >
                {t(lang, c.fr, c.en)}
                {c.key === sortBy
                  ? <span className={styles.sortArrow}>{sortDir === 'asc' ? '↑' : '↓'}</span>
                  : <span className={styles.sortHint} aria-hidden="true">↕</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody onKeyDown={handleKeyDown} tabIndex={rows.length > 0 ? 0 : -1}>
          {renderRows()}
        </tbody>
      </table>
    </div>
  );
}
