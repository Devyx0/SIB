import { useEffect, useId, useRef } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { t } from '../i18n';
import type { Lang } from '../i18n';
import styles from './FormDialog.module.css';

// A modal form: scrim, Escape / backdrop to close, focus on the first field
// and back to the opener on close, a busy state and an error line.

interface Props {
  title: string;
  eyebrow?: string;
  lang: Lang;
  submitting: boolean;
  error?: string | null;
  submitLabel?: string;
  onSubmit: () => void;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
}

export default function FormDialog({
  title, eyebrow, lang, submitting, error, submitLabel, onSubmit, onClose, children, testId,
}: Props) {
  const titleId = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    formRef.current?.querySelector<HTMLElement>('input, select, textarea')?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current(); };
    document.addEventListener('keydown', onKey);
    document.body.classList.add('modal-open');
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.classList.remove('modal-open');
      opener?.focus?.();
    };
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!submitting) onSubmit();
  }

  return (
    <div className={styles.scrim} onMouseDown={(e) => { if (e.target === e.currentTarget && !submitting) onClose(); }}>
      <section className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby={titleId}
               data-testid={testId}>
        <header className={styles.head}>
          <div>
            {eyebrow && <p className={styles.eyebrow}>{eyebrow}</p>}
            <h2 id={titleId} className={styles.title}>{title}</h2>
          </div>
          <button type="button" className={styles.close} onClick={onClose} disabled={submitting}
                  aria-label={t(lang, 'Fermer', 'Close')}>
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none"
                 stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <form ref={formRef} className={styles.form} onSubmit={submit}>
          <div className={styles.body}>{children}</div>
          <footer className={styles.foot}>
            {error && <p className={styles.error} role="alert">{error}</p>}
            <div className={styles.buttons}>
              <button type="button" className={styles.secondary} onClick={onClose} disabled={submitting}>
                {t(lang, 'Annuler', 'Cancel')}
              </button>
              <button type="submit" className={styles.primary} disabled={submitting} data-testid="form-submit">
                {submitting ? t(lang, 'Enregistrement…', 'Saving…') : submitLabel ?? t(lang, 'Enregistrer', 'Save')}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
}

/** A labelled field for FormDialog bodies. */
export function Field({ label, hint, wide, children }: {
  label: string; hint?: string; wide?: boolean; children: ReactNode;
}) {
  return (
    <label className={`${styles.field} ${wide ? styles.wide : ''}`}>
      <span className={styles.label}>{label}</span>
      {children}
      {hint && <span className={styles.hint}>{hint}</span>}
    </label>
  );
}

export function FieldGroup({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <fieldset className={styles.group}>
      {title && <legend className={styles.legend}>{title}</legend>}
      <div className={styles.grid}>{children}</div>
    </fieldset>
  );
}

export const inputClass = styles.input;
