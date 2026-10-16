import { useEffect, useRef, useState } from 'react';
import { STATUS_VALUES } from '../../api/statusValues';
import { statusLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import type { SectorLookup, EmployeeLookup } from '../../api/schema.d.ts';
import styles from './FilterBar.module.css';

interface Props {
  lang?: Lang;
  startDate: string;
  endDate: string;
  status: string[];
  sourceCalendar: string;
  q: string;
  total: number;
  sectors?: SectorLookup[];
  sectorId?: number | null;
  urgency?: string;
  employees?: EmployeeLookup[];
  assignedEmployeeId?: number | null;
  showAllCols?: boolean;
  onStartDate: (v: string) => void;
  onEndDate: (v: string) => void;
  onStatus: (v: string[]) => void;
  onSourceCalendar: (v: string) => void;
  onQ: (v: string | null) => void;
  onSectorId?: (v: number | null) => void;
  onUrgency?: (v: string) => void;
  onAssignedEmployeeId?: (v: number | null) => void;
  onToggleCols?: () => void;
}

export default function FilterBar({
  lang = 'fr',
  startDate, endDate, status, sourceCalendar, q, total,
  sectors = [], sectorId = null, urgency = '',
  employees = [], assignedEmployeeId = null,
  showAllCols = false,
  onStartDate, onEndDate, onStatus, onSourceCalendar, onQ,
  onSectorId = () => {},
  onUrgency = () => {},
  onAssignedEmployeeId = () => {},
  onToggleCols = () => {},
}: Props) {
  const [draft, setDraft] = useState(q);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { setDraft(q); }, [q]);

  function handleSearch(v: string) {
    setDraft(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onQ(v || null), 500);
  }

  function toggleStatus(value: string) {
    if (status.includes(value)) {
      onStatus(status.filter((s) => s !== value));
    } else {
      onStatus([...status, value]);
    }
  }

  const SOURCE_OPTS = [
    { value: '', label: t(lang, 'Tous', 'All') },
    { value: 'main', label: t(lang, 'Principal', 'Main') },
    { value: 'st_maj', label: t(lang, 'Butler/Majordome', 'Butler') },
  ];

  const URGENCY_OPTS = [
    { value: '', label: t(lang, 'Tout', 'All') },
    { value: 'AJD', label: 'AJD' },
    { value: 'ajd', label: 'ajd' },
    { value: 'none', label: t(lang, 'Aucune', 'None') },
  ];

  const countLabel = total === 1
    ? `1 ${t(lang, 'appel', 'call')}`
    : `${total} ${t(lang, 'appels', 'calls')}`;

  return (
    <div className={styles.bar}>
      {/* Row 1: date range, source, search, count, column toggle */}
      <div className={styles.row}>
        <div className={styles.fieldGroup}>
          <label className={styles.label}>{t(lang, 'Du', 'From')}</label>
          <input
            type="date"
            className={styles.input}
            value={startDate}
            onChange={(e) => {
              const v = e.target.value;
              onStartDate(v);
              if (endDate && v > endDate) onEndDate(v);
            }}
          />
        </div>
        <div className={styles.fieldGroup}>
          <label className={styles.label}>{t(lang, 'Au', 'To')}</label>
          <input
            type="date"
            className={styles.input}
            value={endDate}
            onChange={(e) => {
              const v = e.target.value;
              onEndDate(v);
              if (startDate && v < startDate) onStartDate(v);
            }}
          />
        </div>

        <div className={styles.fieldGroup}>
          <label className={styles.label}>{t(lang, 'Source', 'Source')}</label>
          <select
            className={styles.input}
            value={sourceCalendar}
            onChange={(e) => onSourceCalendar(e.target.value)}
          >
            {SOURCE_OPTS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        <div className={styles.fieldGroup}>
          <label className={styles.label}>{t(lang, 'Urgence', 'Urgency')}</label>
          <select
            className={styles.input}
            value={urgency}
            onChange={(e) => onUrgency(e.target.value)}
          >
            {URGENCY_OPTS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {employees.length > 0 && (
          <div className={styles.fieldGroup}>
            <label className={styles.label}>{t(lang, 'Employé', 'Employee')}</label>
            <select
              className={styles.input}
              value={assignedEmployeeId ?? ''}
              onChange={(e) => onAssignedEmployeeId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">{t(lang, 'Tous', 'All')}</option>
              {employees.map((emp) => (
                <option key={emp.employee_id} value={emp.employee_id}>
                  {emp.nom_employe}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className={styles.searchGroup}>
          <input
            type="search"
            className={styles.searchInput}
            placeholder={t(lang, 'Rechercher ASNU, unité, immeuble, employé…', 'Search ASNU, unit, building, employee…')}
            value={draft}
            onChange={(e) => handleSearch(e.target.value)}
            data-testid="search-input"
          />
        </div>

        <span className={styles.count}>{countLabel}</span>

        <button
          className={styles.colsBtn + (showAllCols ? ' ' + styles.colsBtnActive : '')}
          onClick={onToggleCols}
          title={t(lang, 'Afficher toutes les colonnes', 'Toggle all columns')}
        >
          {t(lang, 'Colonnes', 'Columns')} {showAllCols ? '−' : '+'}
        </button>
      </div>

      {/* Row 2: territory chips */}
      {sectors.length > 0 && (
        <div className={styles.row}>
          <span className={styles.label}>{t(lang, 'Territoire', 'Territory')}</span>
          <div className={styles.chipGroup}>
            <button
              className={styles.chip + (sectorId === null ? ' ' + styles.chipActive : '')}
              onClick={() => onSectorId(null)}
            >
              {t(lang, 'Tous', 'All')}
            </button>
            {sectors.map((s) => (
              <button
                key={s.sector_id}
                className={styles.chip + (sectorId === s.sector_id ? ' ' + styles.chipActive : '')}
                onClick={() => onSectorId(sectorId === s.sector_id ? null : s.sector_id)}
              >
                {s.color_code && (
                  <span
                    className={styles.colorDot}
                    style={{ background: s.color_code }}
                  />
                )}
                {s.territoire}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Row 3: status checkboxes */}
      <div className={styles.statusRow}>
        <span className={styles.label}>{t(lang, 'Statut', 'Status')}</span>
        <div className={styles.checkGroup}>
          {STATUS_VALUES.map((s) => (
            <label key={s} className={styles.check}>
              <input
                type="checkbox"
                checked={status.includes(s)}
                onChange={() => toggleStatus(s)}
              />
              {statusLabel(lang, s)}
            </label>
          ))}
          {status.length > 0 && (
            <button className={styles.clearBtn} onClick={() => onStatus([])}>
              {t(lang, 'Effacer', 'Clear')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
