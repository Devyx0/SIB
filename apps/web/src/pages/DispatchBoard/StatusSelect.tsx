import { useEffect, useId, useRef, useState } from 'react';
import { FILTER_STATUS_VALUES } from '../../api/statusValues';
import { statusLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './FilterBar.module.css';

interface Props {
  lang: Lang;
  value: string[];
  onChange: (v: string[]) => void;
}

/** Collapse triage_pending into intake_received for the checkbox UI. */
function uiStatuses(value: string[]): string[] {
  const out = value.filter((s) => s !== 'triage_pending');
  if (value.includes('triage_pending') && !out.includes('intake_received')) {
    out.push('intake_received');
  }
  return out;
}

// Multi-select dropdown for the status filter: a trigger summarising the
// selection and a popover of checkboxes. Closes on outside click / Escape.
export default function StatusSelect({ lang, value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popId = useId();
  const selected = uiStatuses(value);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  function toggle(s: string) {
    onChange(selected.includes(s) ? selected.filter((v) => v !== s) : [...selected, s]);
  }

  const summary =
    selected.length === 0
      ? t(lang, 'Tous les statuts', 'All statuses')
      : selected.length === 1
        ? statusLabel(lang, selected[0])
        : t(lang, `${selected.length} statuts`, `${selected.length} statuses`);

  return (
    <div className={styles.dropdown} ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.input} ${styles.dropdownTrigger} ${selected.length > 0 ? styles.dropdownTriggerActive : ''}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={popId}
        data-testid="status-select"
        onClick={() => setOpen((o) => !o)}
      >
        <span className={styles.dropdownSummary}>{summary}</span>
        {selected.length > 1 && <span className={styles.dropdownCount}>{selected.length}</span>}
      </button>

      {open && (
        <div id={popId} className={styles.popover} role="group" aria-label={t(lang, 'Statut', 'Status')}>
          <div className={styles.popoverList}>
            {FILTER_STATUS_VALUES.map((s) => (
              <label key={s} className={styles.popoverOption}>
                <input
                  type="checkbox"
                  checked={selected.includes(s)}
                  onChange={() => toggle(s)}
                />
                {statusLabel(lang, s)}
              </label>
            ))}
          </div>
          <div className={styles.popoverFooter}>
            <button
              type="button"
              className={styles.linkBtn}
              onClick={() => onChange([])}
              disabled={selected.length === 0}
            >
              {t(lang, 'Effacer', 'Clear')}
            </button>
            <button type="button" className={styles.doneBtn} onClick={() => setOpen(false)}>
              {t(lang, 'Fermer', 'Done')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
