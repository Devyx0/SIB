import { useEffect, useRef, useState } from 'react';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import type { SectorLookup, EmployeeLookup } from '../../api/schema.d.ts';
import StatusSelect from './StatusSelect';
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
  dateNote?: string;
  redispatch?: boolean;
  onRedispatch?: (v: boolean) => void;
  /** True when any filter differs from the page defaults. */
  hasActiveFilters?: boolean;
  onReset?: () => void;
}

export default function FilterBar({
  lang = 'fr',
  startDate, endDate, status, sourceCalendar, q, total,
  sectors = [], sectorId = null, urgency = '',
  employees = [], assignedEmployeeId = null,
  showAllCols = false,
  dateNote,
  redispatch = false,
  onStartDate, onEndDate, onStatus, onSourceCalendar, onQ,
  onSectorId = () => {},
  onUrgency = () => {},
  onAssignedEmployeeId = () => {},
  onToggleCols = () => {},
  onRedispatch = () => {},
  hasActiveFilters = false,
  onReset,
}: Props) {
  const [draft, setDraft] = useState(q);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Local draft state for date inputs — only propagate complete valid dates.
  const [draftStart, setDraftStart] = useState(startDate);
  const [draftEnd, setDraftEnd] = useState(endDate);
  const startTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const endTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { setDraft(q); }, [q]);
  useEffect(() => { setDraftStart(startDate); }, [startDate]);
  useEffect(() => { setDraftEnd(endDate); }, [endDate]);

  function handleSearch(v: string) {
    setDraft(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onQ(v || null), 500);
  }

  function isCompleteDate(v: string): boolean {
    return /^\d{4}-\d{2}-\d{2}$/.test(v) && v >= '2000-01-01' && v <= '2100-12-31';
  }

  function handleStartDate(v: string) {
    // Complete-format dates with years outside [2000, 2100] are ignored entirely — no state change.
    if (/^\d{4}-\d{2}-\d{2}$/.test(v) && !isCompleteDate(v)) return;
    setDraftStart(v);
    if (startTimer.current) clearTimeout(startTimer.current);
    if (isCompleteDate(v)) {
      startTimer.current = setTimeout(() => onStartDate(v), 400);
    }
  }

  function handleEndDate(v: string) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(v) && !isCompleteDate(v)) return;
    setDraftEnd(v);
    if (endTimer.current) clearTimeout(endTimer.current);
    if (isCompleteDate(v)) {
      endTimer.current = setTimeout(() => onEndDate(v), 400);
    }
  }

  const SOURCE_OPTS = [
    { value: '', label: t(lang, 'Toutes', 'All') },
    { value: 'main', label: t(lang, 'Principal', 'Main') },
    { value: 'st_maj', label: t(lang, 'Butler/Majordome', 'Butler') },
    { value: 'unrouted', label: t(lang, 'À router', 'To route') },
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

  const dateRangeError = (() => {
    if (!draftStart || !draftEnd) return null;
    if (!isCompleteDate(draftStart) || !isCompleteDate(draftEnd)) return null;
    const days = (new Date(draftEnd).getTime() - new Date(draftStart).getTime()) / 86400000;
    if (days < 0) return t(lang, 'La date de fin doit être après la date de début.', 'End date must be after start date.');
    if (days > 31) return t(lang, 'La plage de dates ne peut pas dépasser 31 jours.', 'Date range cannot exceed 31 days.');
    return null;
  })();

  const searchRef = useRef<HTMLInputElement>(null);

  // "/" jumps to the search field (unless already typing somewhere).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement;
      if (el.closest('input, textarea, select, [contenteditable="true"]')) return;
      e.preventDefault();
      searchRef.current?.focus();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className={styles.bar}>
      {/* Row 1: search + the filters people change most */}
      <div className={styles.row}>
        <div className={styles.searchGroup}>
          <label className={styles.label} htmlFor="board-search">{t(lang, 'Recherche', 'Search')}</label>
          <input
            id="board-search"
            ref={searchRef}
            type="search"
            className={styles.searchInput}
            placeholder={t(lang, 'ASNU, unité, immeuble, employé…', 'ASNU, unit, building, employee…')}
            value={draft}
            onChange={(e) => handleSearch(e.target.value)}
            data-testid="search-input"
          />
        </div>

        <div className={styles.fieldGroup}>
          <span className={styles.label} id="board-period">{t(lang, 'Période', 'Period')}</span>
          <div className={styles.dateRange} role="group" aria-labelledby="board-period">
            <input
              type="date"
              className={styles.dateInput}
              value={draftStart}
              disabled={!!dateNote}
              aria-label={t(lang, 'Du', 'From')}
              data-testid="start-date-input"
              onChange={(e) => handleStartDate(e.target.value)}
            />
            <span className={styles.dateSep} aria-hidden="true">→</span>
            <input
              type="date"
              className={styles.dateInput}
              value={draftEnd}
              disabled={!!dateNote}
              aria-label={t(lang, 'Au', 'To')}
              data-testid="end-date-input"
              onChange={(e) => handleEndDate(e.target.value)}
            />
          </div>
        </div>

        <div className={styles.fieldGroup}>
          <span className={styles.label}>{t(lang, 'Statut', 'Status')}</span>
          <StatusSelect lang={lang} value={status} onChange={onStatus} />
        </div>

        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="board-urgency">{t(lang, 'Urgence', 'Urgency')}</label>
          <select
            id="board-urgency"
            className={`${styles.input} ${urgency ? styles.inputActive : ''}`}
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
            <label className={styles.label} htmlFor="board-employee">{t(lang, 'Employé', 'Employee')}</label>
            <select
              id="board-employee"
              className={`${styles.input} ${styles.employeeSelect} ${assignedEmployeeId != null ? styles.inputActive : ''}`}
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

        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="board-source">{t(lang, 'Source', 'Source')}</label>
          <select
            id="board-source"
            className={`${styles.input} ${sourceCalendar ? styles.inputActive : ''}`}
            value={sourceCalendar}
            onChange={(e) => onSourceCalendar(e.target.value)}
          >
            {SOURCE_OPTS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      {(dateNote || dateRangeError) && (
        <div className={styles.notes}>
          {dateNote && <span className={styles.dateNote}>{dateNote}</span>}
          {dateRangeError && <span className={styles.dateError} data-testid="date-range-error">{dateRangeError}</span>}
        </div>
      )}

      {/* Row 2: territory chips · quick toggles · result count */}
      <div className={styles.subRow}>
        {sectors.length > 0 && (
          <div className={styles.chipGroup} role="group" aria-label={t(lang, 'Territoire', 'Territory')}>
            <button
              type="button"
              className={styles.chip + (sectorId === null ? ' ' + styles.chipActive : '')}
              aria-pressed={sectorId === null}
              onClick={() => onSectorId(null)}
            >
              {t(lang, 'Tous les territoires', 'All territories')}
            </button>
            {sectors.map((s) => (
              <button
                type="button"
                key={s.sector_id}
                className={styles.chip + (sectorId === s.sector_id ? ' ' + styles.chipActive : '')}
                aria-pressed={sectorId === s.sector_id}
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
        )}

        <div className={styles.tools}>
          <label
            className={`${styles.toggleChip} ${redispatch ? styles.toggleChipActive : ''}`}
            data-testid="redispatch-filter"
          >
            <input
              type="checkbox"
              checked={redispatch}
              onChange={(e) => onRedispatch(e.target.checked)}
            />
            {t(lang, 'À redispatcher', 'To re-dispatch')}
          </label>

          <button
            type="button"
            className={styles.colsBtn + (showAllCols ? ' ' + styles.colsBtnActive : '')}
            onClick={onToggleCols}
            aria-pressed={showAllCols}
            title={t(lang, 'Afficher toutes les colonnes', 'Toggle all columns')}
          >
            {showAllCols ? t(lang, 'Moins de colonnes', 'Fewer columns') : t(lang, 'Plus de colonnes', 'More columns')}
          </button>

          <span className={styles.divider} aria-hidden="true" />

          <span className={styles.count} aria-live="polite">{countLabel}</span>

          {hasActiveFilters && onReset && (
            <button type="button" className={styles.linkBtn} onClick={onReset} data-testid="reset-filters">
              {t(lang, 'Réinitialiser', 'Reset')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
