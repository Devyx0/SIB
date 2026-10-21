import { useEffect, useRef, useState } from 'react';
import type { BoardMode } from '../../api/boardModes';
import { statusesForMode } from '../../api/boardModes';
import { statusLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import type { SectorLookup, EmployeeLookup } from '../../api/schema.d.ts';
import StatusSelect from './StatusSelect';
import RangeCalendar from '../../components/RangeCalendar';
import styles from './FilterBar.module.css';
import Select from '../../components/Select';

interface Props {
  lang?: Lang;
  /** triage = no date period; tasks = dates + escalated filter. */
  mode?: BoardMode;
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
  hasSubcontractor?: boolean | null;
  showAllCols?: boolean;
  onStartDate: (v: string) => void;
  onEndDate: (v: string) => void;
  /** Set both dates at once (quick ranges). */
  onDateRange?: (start: string, end: string) => void;
  onStatus: (v: string[]) => void;
  onSourceCalendar: (v: string) => void;
  onQ: (v: string | null) => void;
  onSectorId?: (v: number | null) => void;
  onUrgency?: (v: string) => void;
  onAssignedEmployeeId?: (v: number | null) => void;
  onHasSubcontractor?: (v: boolean | null) => void;
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
  mode = 'tasks',
  startDate, endDate, status, sourceCalendar, q, total,
  sectors = [], sectorId = null, urgency = '',
  employees = [], assignedEmployeeId = null,
  hasSubcontractor = null,
  showAllCols = false,
  dateNote,
  redispatch = false,
  onStartDate, onEndDate, onDateRange, onStatus, onSourceCalendar, onQ,
  onSectorId = () => {},
  onUrgency = () => {},
  onAssignedEmployeeId = () => {},
  onHasSubcontractor = () => {},
  onToggleCols = () => {},
  onRedispatch = () => {},
  hasActiveFilters = false,
  onReset,
}: Props) {
  const showDates = mode === 'tasks';
  const statusOptions = statusesForMode(mode);
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
    { value: 'URGENT', label: t(lang, 'Urgent', 'Urgent') },
    { value: 'Intermédiaire', label: t(lang, 'Intermédiaire', 'Medium') },
    { value: 'Faible', label: t(lang, 'Faible', 'Low') },
  ];

  const SUB_OPTS = [
    { value: '', label: t(lang, 'Tous', 'All') },
    { value: 'true', label: t(lang, 'Avec sous-traitant', 'With subcontractor') },
    { value: 'false', label: t(lang, 'Sans sous-traitant', 'No subcontractor') },
  ];

  const countLabel = total === 1
    ? `1 ${t(lang, 'appel', 'call')}`
    : `${total} ${t(lang, 'appels', 'calls')}`;

  // Quick ranges end today (America/Toronto, like the board's default) and
  // count today as one of the days: « 7 derniers jours » = today + 6 before.
  const todayYmd = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
  function daysBefore(ymd: string, n: number): string {
    const [y, m, d] = ymd.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, d - n)).toISOString().slice(0, 10);
  }
  const QUICK_RANGES = [7, 14, 30].map((days) => ({ days, start: daysBefore(todayYmd, days - 1) }));
  const activeQuick = draftEnd === todayYmd
    ? QUICK_RANGES.find((r) => r.start === draftStart)?.days
    : undefined;
  const shortDay = (v: string) => (v && v.length === 10 ? `${v.slice(8)}/${v.slice(5, 7)}` : '—');
  const customLabel = `${shortDay(draftStart)} → ${shortDay(draftEnd)}`;

  const [calOpen, setCalOpen] = useState(false);
  const periodRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!calOpen) return;
    function onDown(e: MouseEvent) {
      if (periodRef.current && !periodRef.current.contains(e.target as Node)) setCalOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [calOpen]);

  function applyRange(start: string, end: string) {
    if (startTimer.current) clearTimeout(startTimer.current);
    if (endTimer.current) clearTimeout(endTimer.current);
    setDraftStart(start);
    setDraftEnd(end);
    if (onDateRange) onDateRange(start, end);
    else { onStartDate(start); onEndDate(end); }
  }

  function applyQuickRange(start: string) {
    if (startTimer.current) clearTimeout(startTimer.current);
    if (endTimer.current) clearTimeout(endTimer.current);
    setDraftStart(start);
    setDraftEnd(todayYmd);
    if (onDateRange) onDateRange(start, todayYmd);
    else { onStartDate(start); onEndDate(todayYmd); }
  }

  const dateRangeError = (() => {
    if (!draftStart || !draftEnd) return null;
    if (!isCompleteDate(draftStart) || !isCompleteDate(draftEnd)) return null;
    const days = (new Date(draftEnd).getTime() - new Date(draftStart).getTime()) / 86400000;
    if (days < 0) return t(lang, 'La date de fin doit être après la date de début.', 'End date must be after start date.');
    if (days > 31) return t(lang, 'La plage de dates ne peut pas dépasser 31 jours.', 'Date range cannot exceed 31 days.');
    return null;
  })();

  // ── Phone/tablet: the filters fold away behind a « Filtres » bar ───────
  const OPEN_KEY = 'sib.board.filtersOpen';
  const [filtersOpen, setFiltersOpen] = useState<boolean>(() => {
    try { return localStorage.getItem(OPEN_KEY) === '1'; } catch { return false; }
  });
  function toggleFilters() {
    setFiltersOpen((o) => {
      try { localStorage.setItem(OPEN_KEY, o ? '0' : '1'); } catch { /* private mode */ }
      return !o;
    });
  }
  const fmtDay = (ymd: string) => {
    const [, m, d] = ymd.split('-');
    return `${d}/${m}`;
  };
  const activeSummary = [
    activeQuick
      ? t(lang, `${activeQuick} jours`, `${activeQuick} days`)
      : (draftStart && draftEnd ? `${fmtDay(draftStart)} → ${fmtDay(draftEnd)}` : null),
    status.length === 1 ? statusLabel(lang, status[0])
      : status.length > 1 ? t(lang, `${status.length} statuts`, `${status.length} statuses`) : null,
    urgency ? URGENCY_OPTS.find((o) => o.value === urgency)?.label ?? urgency : null,
    assignedEmployeeId != null ? employees.find((e) => e.employee_id === assignedEmployeeId)?.nom_employe ?? null : null,
    sourceCalendar ? SOURCE_OPTS.find((o) => o.value === sourceCalendar)?.label ?? null : null,
    hasSubcontractor != null ? SUB_OPTS.find((o) => o.value === String(hasSubcontractor))?.label ?? null : null,
    sectorId != null ? sectors.find((x) => x.sector_id === sectorId)?.territoire ?? null : null,
    redispatch ? t(lang, 'À redispatcher', 'To re-dispatch') : null,
  ].filter(Boolean) as string[];
  // Everything except the period counts as "active" (the period is always set).
  const activeCount = activeSummary.length - (activeSummary[0] ? 1 : 0);

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
    <div className={`${styles.bar} ${filtersOpen ? '' : styles.mobileCollapsed}`}>
      {/* Row 1: search + the filters people change most */}
      <div className={styles.row} id="board-filter-fields">
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

        {/* Phone/tablet only: fold the filters away once they are set. */}
        <button
          type="button"
          className={styles.mobileToggle}
          aria-expanded={filtersOpen}
          aria-controls="board-filter-fields"
          onClick={toggleFilters}
          data-testid="filters-toggle"
        >
          <span className={styles.mobileToggleMain}>
            <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M3 5h14M6 10h8M8.5 15h3" />
            </svg>
            {t(lang, 'Filtres', 'Filters')}
            {activeCount > 0 && <span className={styles.mobileBadge}>{activeCount}</span>}
            <span className={styles.mobileToggleAction}>
              {filtersOpen ? t(lang, 'Masquer', 'Hide') : t(lang, 'Afficher', 'Show')}
              <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                className={filtersOpen ? styles.chevronUp : ''}>
                <path d="M6 8l4 4 4-4" />
              </svg>
            </span>
          </span>
          {!filtersOpen && activeSummary.length > 0 && (
            <span className={styles.mobileSummary} data-testid="filters-summary">{activeSummary.join(' · ')}</span>
          )}
        </button>

        {showDates && <div className={styles.fieldGroup}>
          <span className={styles.label} id="board-period">{t(lang, 'Période', 'Period')}</span>
          <div
            className={styles.periodWrap}
            ref={periodRef}
            onKeyDown={(e) => {
              if (e.key === 'Escape' && calOpen) { e.stopPropagation(); setCalOpen(false); }
            }}
          >
            <div className={styles.period} role="group" aria-labelledby="board-period">
              {QUICK_RANGES.map((r) => (
                <button
                  key={r.days}
                  type="button"
                  className={`${styles.periodBtn} ${activeQuick === r.days ? styles.periodBtnActive : ''}`}
                  aria-pressed={activeQuick === r.days}
                  disabled={!!dateNote}
                  title={t(lang, `${r.days} derniers jours`, `Last ${r.days} days`)}
                  aria-label={t(lang, `${r.days} derniers jours`, `Last ${r.days} days`)}
                  onClick={() => { applyQuickRange(r.start); setCalOpen(false); }}
                  data-testid={`quick-range-${r.days}`}
                >
                  {t(lang, `${r.days} jours`, `${r.days} days`)}
                </button>
              ))}
              <button
                type="button"
                className={`${styles.periodBtn} ${styles.calBtn} ${!activeQuick ? styles.periodBtnActive : ''}`}
                aria-haspopup="dialog"
                aria-expanded={calOpen}
                aria-controls="board-period-cal"
                aria-label={activeQuick
                  ? t(lang, 'Choisir une période personnalisée', 'Pick a custom range')
                  : t(lang, `Période personnalisée : ${customLabel}. Modifier`, `Custom range: ${customLabel}. Change`)}
                disabled={!!dateNote}
                onClick={() => setCalOpen((o) => !o)}
                data-testid="custom-range-btn"
              >
                <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4.5" width="14" height="12" rx="2" /><path d="M3 8.5h14M7 3v3M13 3v3" />
                </svg>
                {!activeQuick && <span className={styles.customLabel}>{customLabel}</span>}
              </button>
            </div>

            {/* Custom range: calendar + exact dates. Kept mounted (hidden) so
                typing a date keeps its debounce while the popover is closed. */}
            <div
              id="board-period-cal"
              className={styles.calPopover}
              role="dialog"
              aria-label={t(lang, 'Période personnalisée', 'Custom range')}
              hidden={!calOpen}
            >
              {calOpen && (
                <RangeCalendar
                  lang={lang}
                  start={draftStart}
                  end={draftEnd}
                  maxDays={31}
                  onChange={(a, b) => { applyRange(a, b); setCalOpen(false); }}
                />
              )}
              <div className={styles.calInputs}>
                <label className={styles.calInputLabel}>
                  {t(lang, 'Du', 'From')}
                  <input
                    type="date"
                    className={styles.dateInput}
                    value={draftStart}
                    disabled={!!dateNote}
                    data-testid="start-date-input"
                    onChange={(e) => handleStartDate(e.target.value)}
                  />
                </label>
                <label className={styles.calInputLabel}>
                  {t(lang, 'Au', 'To')}
                  <input
                    type="date"
                    className={styles.dateInput}
                    value={draftEnd}
                    disabled={!!dateNote}
                    data-testid="end-date-input"
                    onChange={(e) => handleEndDate(e.target.value)}
                  />
                </label>
              </div>
            </div>
          </div>
        </div>}

        <div className={styles.fieldGroup}>
          <span className={styles.label}>{t(lang, 'Statut', 'Status')}</span>
          <StatusSelect
            lang={lang}
            value={status}
            onChange={onStatus}
            allowedStatuses={statusOptions}
          />
        </div>

        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="board-urgency">{t(lang, 'Urgence', 'Urgency')}</label>
          <Select
            id="board-urgency"
            className={`${styles.input} ${urgency ? styles.inputActive : ''}`}
            value={urgency}
            onChange={(e) => onUrgency(e.target.value)}
          >
            {URGENCY_OPTS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>
        </div>

        {employees.length > 0 && (
          <div className={styles.fieldGroup}>
            <label className={styles.label} htmlFor="board-employee">{t(lang, 'Employé', 'Employee')}</label>
            <Select
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
            </Select>
          </div>
        )}

        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="board-source">{t(lang, 'Source', 'Source')}</label>
          <Select
            id="board-source"
            className={`${styles.input} ${sourceCalendar ? styles.inputActive : ''}`}
            value={sourceCalendar}
            onChange={(e) => onSourceCalendar(e.target.value)}
          >
            {SOURCE_OPTS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>
        </div>

        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="board-subcontractor">
            {t(lang, 'Sous-traitant', 'Subcontractor')}
          </label>
          <Select
            id="board-subcontractor"
            className={`${styles.input} ${hasSubcontractor != null ? styles.inputActive : ''}`}
            value={hasSubcontractor == null ? '' : String(hasSubcontractor)}
            onChange={(e) => {
              const v = e.target.value;
              onHasSubcontractor(v === '' ? null : v === 'true');
            }}
            data-testid="subcontractor-filter"
          >
            {SUB_OPTS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>
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
          {mode === 'tasks' && (
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
          )}

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
