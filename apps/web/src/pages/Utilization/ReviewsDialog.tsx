import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import dialog from '../../components/FormDialog.module.css';
import styles from './Utilization.module.css';

// Read-only modal listing every review for one technician. Same scrim,
// head and close button as FormDialog; Escape / backdrop close it and
// focus returns to the opener.

interface Props {
  lang: Lang;
  technician: string;
  /** Rating summary under the name (stars, average, count). */
  summary: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

export default function ReviewsDialog({ lang, technician, summary, onClose, children }: Props) {
  const titleId = useId();
  const closeBtn = useRef<HTMLButtonElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current(); };
    document.addEventListener('keydown', onKey);
    document.body.classList.add('modal-open');
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.classList.remove('modal-open');
      opener?.focus?.();
    };
  }, []);

  return (
    <div className={dialog.scrim} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <section className={`${dialog.dialog} ${styles.reviewsDialog}`} role="dialog" aria-modal="true"
        aria-labelledby={titleId} data-testid="reviews-dialog">
        <header className={dialog.head}>
          <div>
            <p className={dialog.eyebrow}>{t(lang, 'Avis clients', 'Customer reviews')}</p>
            <h2 id={titleId} className={dialog.title}>{technician}</h2>
            <div className={styles.reviewsDialogSummary}>{summary}</div>
          </div>
          <button ref={closeBtn} type="button" className={dialog.close} onClick={onClose}
            aria-label={t(lang, 'Fermer', 'Close')}>
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>
        <div className={styles.reviewsDialogBody}>{children}</div>
      </section>
    </div>
  );
}
