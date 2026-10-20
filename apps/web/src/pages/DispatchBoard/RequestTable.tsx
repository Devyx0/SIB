import { useRef, KeyboardEvent } from 'react';
import type { ListRow } from '../../api/schema.d.ts';
import { statusLabel, t, timeEstimateLabel } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './RequestTable.module.css';

interface Props {
  lang?: Lang;
  rows: ListRow[];
  selectedId: number | null;
  sortBy: string;
  sortDir: 'asc' | 'desc';
  onSort: (key: string) => void;
  onSelect: (id: number) => void;
  isLoading: boolean;
  isError: boolean;
  total: number;
  showAllCols?: boolean;
  errorMsg?: string;
  /** Rendered inside a scrolling parent: let the header stick to it. */
  inScroller?: boolean;
}

interface ColDef {
  key: string;
  fr: string;
  en: string;
  sortable: boolean;
}

const MANDATORY_COLS: ColDef[] = [
  { key: 'start_date',            fr: 'Date',           en: 'Date',          sortable: true  },
  { key: 'asnu',                  fr: 'ASNU',           en: 'ASNU',          sortable: true  },
  { key: 'urgency_tier',          fr: 'Urgence',        en: 'Urgency',       sortable: true  },
  { key: 'raw_title',             fr: 'Appel',          en: 'Call',          sortable: true  },
  { key: 'territoire',            fr: 'Territoire',     en: 'Territory',     sortable: true  },
  { key: 'building_address',      fr: 'Immeuble',       en: 'Building',      sortable: true  },
  { key: 'unique_unit_number',    fr: "N° d'unité",     en: 'Unit #',        sortable: true  },
  { key: 'assigned_employee_name',fr: 'Employé',        en: 'Employee',      sortable: true  },
  { key: 'subcontractor_name',    fr: 'Sous-traitant',  en: 'Subcontractor', sortable: true  },
  { key: 'time_estimate_bucket',  fr: 'Durée',          en: 'Est. time',     sortable: true  },
  { key: 'last_followup_date',    fr: 'Dernier suivi',  en: 'Last log',      sortable: true  },
  { key: 'status',                fr: 'Statut',         en: 'Status',        sortable: true  },
];

const OPTIONAL_COLS: ColDef[] = [
  { key: 'estimated_cost',        fr: 'Coût',               en: 'Est. cost',     sortable: false },
  { key: 'next_follow_up_date',   fr: 'Prochain suivi',     en: 'Next follow-up',sortable: false },
  { key: 'next_steps',            fr: 'Prochaines étapes',  en: 'Next steps',    sortable: false },
];

function UrgencyTag({ tier }: { tier: string | null }) {
  if (tier === 'AJD') return <span className={styles.tagAJD}>AJD</span>;
  if (tier === 'ajd') return <span className={styles.tagAjd}>ajd</span>;
  return <span className={styles.muted}>—</span>;
}

function StatusTag({ status, lang = 'fr' }: { status: string; lang?: Lang }) {
  // en_route is highlighted — the calendar's "X" prefix equivalent.
  return <span className={styles.tagStatus} data-status={status}>{statusLabel(lang, status)}</span>;
}

export default function RequestTable({
  lang = 'fr',
  rows, selectedId, sortBy, sortDir, onSort, onSelect,
  isLoading, isError, showAllCols = false, errorMsg, inScroller = false,
}: Props) {
  const tbodyRef = useRef<HTMLTableSectionElement>(null);
  const cols = showAllCols ? [...MANDATORY_COLS, ...OPTIONAL_COLS] : MANDATORY_COLS;
  const colCount = cols.length;

  function handleKeyDown(e: KeyboardEvent<HTMLTableSectionElement>) {
    const idx = rows.findIndex((r) => r.request_id === selectedId);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = rows[idx + 1];
      if (next) onSelect(next.request_id);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = rows[idx - 1];
      if (prev) onSelect(prev.request_id);
    }
  }

  function arrow(c: ColDef) {
    if (!c.sortable) return null;
    if (c.key !== sortBy) return <span className={styles.sortHint} aria-hidden="true">↕</span>;
    return <span className={styles.sortArrow}>{sortDir === 'asc' ? '↑' : '↓'}</span>;
  }

  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
  const dayFmt = new Intl.DateTimeFormat(lang === 'fr' ? 'fr-CA' : 'en-CA', {
    weekday: 'long', day: 'numeric', month: 'long',
  });
  function dayLabel(ymd: string): string {
    const [y, m, d] = ymd.split('-').map(Number);
    const label = dayFmt.format(new Date(y, m - 1, d));
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  function renderRows() {
    if (isLoading) {
      return Array.from({ length: 3 }).map((_, i) => (
        <tr key={i} className={styles.skeleton}>
          {cols.map((c) => <td key={c.key}><span className={styles.skeletonCell} /></td>)}
        </tr>
      ));
    }

    if (isError) {
      const msg = errorMsg ?? t(lang, 'Erreur lors du chargement.', 'Loading error.');
      return (
        <tr>
          <td colSpan={colCount} className={styles.emptyState}>{msg}</td>
        </tr>
      );
    }

    if (rows.length === 0) {
      return (
        <tr>
          <td colSpan={colCount} className={styles.emptyState}>
            <span className={styles.emptyTitle}>
              {t(lang, 'Aucun appel dans cette plage.', 'No calls in this range.')}
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

    const showDayHeaders = sortBy === 'start_date';
    const result: JSX.Element[] = [];
    let lastDate: string | null = null;
    const perDay = new Map<string, number>();
    rows.forEach((r) => {
      if (r.start_date) perDay.set(r.start_date, (perDay.get(r.start_date) ?? 0) + 1);
    });

    rows.forEach((row) => {
      if (showDayHeaders && row.start_date !== lastDate) {
        if (row.start_date !== null) {
          lastDate = row.start_date;
          // Noon local avoids UTC date-shift when reading weekday from YYYY-MM-DD.
          const weekday = new Date(`${row.start_date}T12:00:00`).getDay();
          result.push(
            <tr
              key={`day-${row.start_date}`}
              className={styles.dayHeader}
              data-weekday={weekday}
              data-testid="day-header"
            >
              <td colSpan={colCount} className={styles.dayHeaderCell}>
                <span className={styles.daySwatch} aria-hidden="true" />
                <span className={styles.dayName}>{dayLabel(row.start_date)}</span>
                {row.start_date === today && (
                  <span className={styles.todayTag}>{t(lang, "Aujourd'hui", 'Today')}</span>
                )}
                <span className={styles.dayCount}>
                  {perDay.get(row.start_date) ?? 0} {t(lang, 'appel(s)', 'call(s)')}
                </span>
              </td>
            </tr>,
          );
        }
      }

      const isAJD = row.urgency_tier === 'AJD';
      const isDup = row.duplicate_of_request_id != null;
      const isAdd = row.addition_to_request_id != null;
      const isSelected = row.request_id === selectedId;

      result.push(
        <tr
          key={row.request_id}
          className={[
            styles.row,
            isAJD ? styles.ajdRow : '',
            isDup ? styles.dupRow : '',
            isAdd ? styles.addRow : '',
            isSelected ? styles.selectedRow : '',
          ].join(' ')}
          aria-selected={isSelected}
          onClick={() => onSelect(row.request_id)}
          onKeyDown={(e) => { if (e.key === 'Enter') onSelect(row.request_id); }}
          data-testid="request-row"
          data-duplicate={isDup || undefined}
          data-addition={isAdd || undefined}
          tabIndex={0}
        >
          {/* mandatory cells */}
          <td className={styles.nowrap + ' ' + styles.dateCell}>{row.start_date ?? '—'}</td>
          <td className={styles.nowrap + ' ' + styles.mono}>{row.asnu ?? '—'}</td>
          <td className={styles.nowrap}><UrgencyTag tier={row.urgency_tier} /></td>
          <td className={styles.titleCell}>
            <span className={styles.clamp} title={row.raw_title ?? undefined}>{row.raw_title ?? '—'}</span>
            {isDup && (
              <span className={styles.tagDup} data-testid="dup-badge">
                {t(lang, 'Doublon', 'Duplicate')} #{row.duplicate_of_request_id}
              </span>
            )}
            {isAdd && (
              <span className={styles.tagAdd} data-testid="add-badge">
                {t(lang, 'Ajout', 'Addition')} #{row.addition_to_request_id}
              </span>
            )}
          </td>
          <td className={styles.nowrap}>{row.territoire ?? '—'}</td>
          <td className={styles.buildingCell}>
            <span className={styles.clamp} title={row.building_address ?? undefined}>{row.building_address ?? '—'}</span>
          </td>
          <td className={styles.nowrap + ' ' + styles.mono} title={row.unique_unit_number ?? undefined}>
            {row.unique_unit_number ?? '—'}
          </td>
          <td className={styles.nowrap + ' ' + styles.bold}>{row.assigned_employee_name ?? '—'}</td>
          <td className={styles.titleCell}>
            <span className={styles.clamp} title={row.subcontractor_name ?? undefined}>
              {row.subcontractor_name ?? '—'}
            </span>
          </td>
          <td className={styles.nowrap}>{timeEstimateLabel(lang, row.time_estimate_bucket)}</td>
          <td className={styles.nowrap}>{row.last_followup_date ?? '—'}</td>
          <td className={styles.nowrap}>
            <StatusTag status={row.status} lang={lang} />
            {row.closeout_urgent && (
              <span className={styles.tagCloseoutUrgent} data-testid="closeout-urgent-badge">URGENT</span>
            )}
          </td>
          {/* optional cells */}
          {showAllCols && <td className={styles.nowrap}>{row.estimated_cost != null ? String(row.estimated_cost) : '—'}</td>}
          {showAllCols && <td className={styles.nowrap}>{row.next_follow_up_date ?? '—'}</td>}
          {showAllCols && <td>{row.next_steps ?? '—'}</td>}
        </tr>,
      );
    });
    return result;
  }

  return (
    <div className={`${styles.wrap} ${inScroller ? styles.inScroller : ''}`}>
      <table className={styles.table}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                key={c.key}
                scope="col"
                onClick={c.sortable ? () => onSort(c.key) : undefined}
                onKeyDown={c.sortable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSort(c.key); } } : undefined}
                tabIndex={c.sortable ? 0 : undefined}
                aria-sort={c.key === sortBy ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                className={c.sortable ? styles.sortable : ''}
              >
                {t(lang, c.fr, c.en)}{arrow(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody
          ref={tbodyRef}
          onKeyDown={handleKeyDown}
          tabIndex={rows.length > 0 ? 0 : -1}
        >
          {renderRows()}
        </tbody>
      </table>
    </div>
  );
}
