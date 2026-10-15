import { useRef, KeyboardEvent } from 'react';
import type { ListRow } from '../../api/schema.d.ts';
import { statusLabel, t } from '../../i18n';
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
  { key: 'assigned_employee_name',fr: 'Employé',        en: 'Employee',      sortable: true  },
  { key: 'last_followup_date',    fr: 'Dernier suivi',  en: 'Last log',      sortable: true  },
  { key: 'status',                fr: 'Statut',         en: 'Status',        sortable: true  },
];

const OPTIONAL_COLS: ColDef[] = [
  { key: 'subcontractor_name',    fr: 'Sous-traitant',      en: 'Subcontractor', sortable: true  },
  { key: 'time_estimate_bucket',  fr: 'Durée',              en: 'Est. time',     sortable: true  },
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
  return <span className={styles.tagStatus}>{statusLabel(lang, status)}</span>;
}

export default function RequestTable({
  lang = 'fr',
  rows, selectedId, sortBy, sortDir, onSort, onSelect,
  isLoading, isError, showAllCols = false, errorMsg,
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

  function arrow(key: string) {
    if (key !== sortBy) return null;
    return <span className={styles.sortArrow}>{sortDir === 'asc' ? '↑' : '↓'}</span>;
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
            {t(lang, 'Aucun appel dans cette plage.', 'No calls in this range.')}
          </td>
        </tr>
      );
    }

    const showDayHeaders = sortBy === 'start_date';
    const result: JSX.Element[] = [];
    let lastDate: string | null = null;
    let dayGroupIndex = 0;

    rows.forEach((row) => {
      if (showDayHeaders && row.start_date !== lastDate) {
        if (row.start_date !== null) {
          dayGroupIndex++;
          lastDate = row.start_date;
          result.push(
            <tr
              key={`day-${row.start_date}`}
              className={`${styles.dayHeader} ${dayGroupIndex % 2 === 0 ? styles.dayGroupEven : styles.dayGroupOdd}`}
              data-testid="day-header"
            >
              <td colSpan={colCount} className={styles.dayHeaderCell}>
                {row.start_date}
              </td>
            </tr>,
          );
        }
      }

      const isAJD = row.urgency_tier === 'AJD';
      const isSelected = row.request_id === selectedId;

      result.push(
        <tr
          key={row.request_id}
          className={[
            styles.row,
            isAJD ? styles.ajdRow : '',
            isSelected ? styles.selectedRow : '',
          ].join(' ')}
          aria-selected={isSelected}
          onClick={() => onSelect(row.request_id)}
          data-testid="request-row"
          tabIndex={0}
        >
          {/* mandatory cells */}
          <td className={styles.nowrap}>{row.start_date ?? '—'}</td>
          <td className={styles.nowrap + ' ' + styles.mono}>{row.asnu ?? '—'}</td>
          <td className={styles.nowrap}><UrgencyTag tier={row.urgency_tier} /></td>
          <td className={styles.titleCell}>{row.raw_title ?? '—'}</td>
          <td className={styles.nowrap}>{row.territoire ?? '—'}</td>
          <td>{row.building_address ?? '—'}</td>
          <td className={styles.nowrap + ' ' + styles.bold}>{row.assigned_employee_name ?? '—'}</td>
          <td className={styles.nowrap}>{row.last_followup_date ?? '—'}</td>
          <td className={styles.nowrap}><StatusTag status={row.status} lang={lang} /></td>
          {/* optional cells */}
          {showAllCols && <td className={styles.nowrap}>{row.subcontractor_name ?? '—'}</td>}
          {showAllCols && <td className={styles.nowrap}>{row.time_estimate_bucket ?? '—'}</td>}
          {showAllCols && <td className={styles.nowrap + ' ' + styles.muted}>—</td>}
          {showAllCols && <td className={styles.nowrap + ' ' + styles.muted}>—</td>}
          {showAllCols && <td className={styles.muted}>—</td>}
        </tr>,
      );
    });
    return result;
  }

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                key={c.key}
                onClick={c.sortable ? () => onSort(c.key) : undefined}
                className={c.sortable ? styles.sortable : ''}
              >
                {t(lang, c.fr, c.en)}{arrow(c.key)}
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
