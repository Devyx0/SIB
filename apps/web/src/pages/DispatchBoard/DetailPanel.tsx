import { useEffect } from 'react';
import { useRequest } from '../../hooks/useRequest';
import { ApiError } from '../../api/client';
import { statusLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './DetailPanel.module.css';

interface Props {
  requestId: number;
  onClose: () => void;
  lang?: Lang;
}

export default function DetailPanel({ requestId, onClose, lang = 'fr' }: Props) {
  const { data, isPending, isError, error } = useRequest(requestId);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  function errorText() {
    const traceId = error instanceof ApiError ? error.traceId : undefined;
    const base = t(lang, 'Erreur lors du chargement', 'Error loading request');
    return traceId ? `${base} [${traceId}]` : base;
  }

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden />
      <aside className={styles.panel} data-testid="detail-panel" aria-label={t(lang, 'Détails de la demande', 'Request details')}>
        <header className={styles.header}>
          <span className={styles.requestId}>#{requestId}</span>
          <button className={styles.closeBtn} onClick={onClose} aria-label={t(lang, 'Fermer', 'Close')}>✕</button>
        </header>

        <div className={styles.body}>
          {isPending && <p className={styles.loading}>{t(lang, 'Chargement…', 'Loading…')}</p>}

          {isError && (
            <p className={styles.error}>{errorText()}</p>
          )}

          {data && (
            <>
              <h2 className={styles.title}>{data.raw_title ?? '—'}</h2>

              <dl className={styles.dl}>
                <dt>{t(lang, 'Date', 'Date')}</dt>
                <dd>{data.start_date ?? '—'}</dd>

                <dt>ASNU</dt>
                <dd className={styles.mono}>{data.asnu ?? '—'}</dd>

                <dt>{t(lang, 'Urgence', 'Urgency')}</dt>
                <dd>{data.urgency_tier ?? '—'}</dd>

                <dt>{t(lang, 'Statut', 'Status')}</dt>
                <dd>{statusLabel(lang, data.status)}</dd>

                <dt>{t(lang, 'Immeuble', 'Building')}</dt>
                <dd>{data.building_address ?? '—'}</dd>

                <dt>{t(lang, 'Territoire', 'Territory')}</dt>
                <dd>{data.territoire ?? '—'}</dd>

                <dt>{t(lang, 'Employé', 'Employee')}</dt>
                <dd>{data.assigned_employee_name ?? '—'}</dd>

                <dt>{t(lang, 'Sous-traitant', 'Subcontractor')}</dt>
                <dd>{data.subcontractor_name ?? '—'}</dd>

                <dt>{t(lang, 'Estimation', 'Est. time')}</dt>
                <dd>{data.time_estimate_bucket ?? '—'}</dd>

                <dt>Source</dt>
                <dd>{data.source_calendar ?? '—'}</dd>
              </dl>

              {data.followup_log.length > 0 && (
                <section className={styles.followupSection}>
                  <h3 className={styles.followupHeading}>
                    {t(lang, 'Journal de suivi', 'Follow-up log')}
                  </h3>
                  {data.followup_log.map((entry) => (
                    <div key={entry.followup_id} className={styles.followupEntry}>
                      <span className={styles.followupMeta}>
                        {entry.entry_date ?? '—'}
                        {entry.entered_by_initials ? ` · ${entry.entered_by_initials}` : ''}
                      </span>
                      <p className={styles.followupText}>{entry.entry_text ?? '—'}</p>
                    </div>
                  ))}
                </section>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  );
}
