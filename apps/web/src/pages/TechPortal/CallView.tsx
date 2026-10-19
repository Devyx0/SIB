import { useParams } from 'react-router-dom';
import { useRequest } from '../../hooks/useRequest';
import type { MeResponse } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t, statusLabel } from '../../i18n';
import TechHeader from './TechHeader';
import styles from './TechPortal.module.css';

interface Props {
  lang: Lang;
  me: MeResponse | null;
  onSignOut: () => void;
}

export default function TechCallView({ lang, me, onSignOut }: Props) {
  const { id } = useParams();
  const requestId = Number(id);
  const { data: req, isPending, isError } = useRequest(Number.isFinite(requestId) ? requestId : null);

  return (
    <div className={styles.page}>
      <TechHeader lang={lang} me={me} onSignOut={onSignOut} backTo="/tech" />
      <main className={styles.main}>
        {isPending && <p className={styles.muted}>{t(lang, 'Chargement…', 'Loading…')}</p>}
        {isError && (
          <p className={styles.error}>{t(lang, 'Appel introuvable', 'Call not found')}</p>
        )}

        {req && (
          <>
            <div className={styles.callRowTop}>
              <span className={styles.callDate}>{req.start_date ?? t(lang, 'Sans date', 'No date')}</span>
              <span className={styles.statusBadge} data-status={req.status}>
                {statusLabel(lang, req.status)}
              </span>
              {req.urgency_tier && req.urgency_tier !== 'none' && (
                <span className={styles.urgencyBadge}>{req.urgency_tier}</span>
              )}
            </div>
            <h1 className={styles.callViewTitle}>{req.raw_title ?? `#${req.request_id}`}</h1>

            <section className={styles.card}>
              <h2 className={styles.cardTitle}>{t(lang, 'Adresse', 'Address')}</h2>
              <p>
                {req.building_address ?? '—'}
                {req.unit_label ? `, app. ${req.unit_label}` : ''}
              </p>
              {req.building_name && <p className={styles.muted}>{req.building_name}</p>}
            </section>

            <section className={styles.card}>
              <h2 className={styles.cardTitle}>{t(lang, 'Problème', 'Problem')}</h2>
              <p className={styles.preWrap}>{req.problem_summary ?? req.problems ?? '—'}</p>
            </section>

            {req.ft_link && (
              <section className={styles.card}>
                <h2 className={styles.cardTitle}>{t(lang, 'Fiche technique', 'Technical sheet')}</h2>
                <a href={req.ft_link} target="_blank" rel="noreferrer" className={styles.ftLink}>
                  {req.ft_name ?? t(lang, 'Ouvrir la fiche', 'Open the sheet')}
                </a>
              </section>
            )}

            <section className={styles.card}>
              <h2 className={styles.cardTitle}>{t(lang, 'Contact locataire', 'Tenant contact')}</h2>
              {req.caller_name || req.caller_phone || req.caller_email ? (
                <>
                  {req.caller_name && <p>{req.caller_name}</p>}
                  {req.caller_phone && (
                    <p><a href={`tel:${req.caller_phone}`} className={styles.contactLink}>{req.caller_phone}</a></p>
                  )}
                  {req.caller_email && (
                    <p><a href={`mailto:${req.caller_email}`} className={styles.contactLink}>{req.caller_email}</a></p>
                  )}
                </>
              ) : (
                <p className={styles.muted}>—</p>
              )}
            </section>

            <section className={styles.card}>
              <h2 className={styles.cardTitle}>{t(lang, 'Suivis', 'Follow-ups')}</h2>
              {req.followup_log.length === 0 && <p className={styles.muted}>—</p>}
              {req.followup_log.map((f) => (
                <div key={f.followup_id} className={styles.followupEntry}>
                  <span className={styles.muted}>
                    {f.entry_date ?? '—'} {f.entered_by_initials ? `· ${f.entered_by_initials}` : ''}
                  </span>
                  <p className={styles.preWrap}>{f.entry_text}</p>
                </div>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
