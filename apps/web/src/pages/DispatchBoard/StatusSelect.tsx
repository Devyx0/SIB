import { useEffect, useId, useRef, useState } from 'react';
import { STATUS_VALUES } from '../../api/statusValues';
import { statusLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './FilterBar.module.css';

interface Props {
  lang: Lang;
  value: string[];
  onChange: (v: string[]) => void;
}

// Multi-select dropdown for the status filter: a trigger summarising the
// selection and a popover of checkboxes. Closes on outside click / Escape.
export default function StatusSelect({ lang, value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popId = useId();

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
    onChange(value.includes(s) ? value.filter((v) => v !== s) : [...value, s]);
  }

  const summary =
    value.length === 0
      ? t(lang, 'Tous les statuts', 'All statuses')
      : value.length === 1
        ? statusLabel(lang, value[0])
        : t(lang, `${value.length} statuts`, `${value.length} statuses`);

  return (
    <div className={styles.dropdown} ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.input} ${styles.dropdownTrigger} ${value.length > 0 ? styles.dropdownTriggerActive : ''}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={popId}
        data-testid="status-select"
        onClick={() => setOpen((o) => !o)}
      >
        <span className={styles.dropdownSummary}>{summary}</span>
        {value.length > 1 && <span className={styles.dropdownCount}>{value.length}</span>}
      </button>

      {open && (
        <div id={popId} className={styles.popover} role="group" aria-label={t(lang, 'Statut', 'Status')}>
          <div className={styles.popoverList}>
            {STATUS_VALUES.map((s) => (
              <label key={s} className={styles.popoverOption}>
                <input
                  type="checkbox"
                  checked={value.includes(s)}
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
              disabled={value.length === 0}
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
