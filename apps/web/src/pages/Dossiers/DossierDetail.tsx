// Read-only dossier view: call summary and its history timeline (visits,
// follow-up notes, decisions, status changes). No write actions.
import { Link, useParams } from 'react-router-dom';
import { useRequest } from '../../hooks/useRequest';
import { closeoutOutcomeLabel, statusLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import HistoryTimeline from '../../components/HistoryTimeline';
import styles from './Dossiers.module.css';

export default function DossierDetail({ lang = 'fr' }: { lang?: Lang }) {
  const { id } = useParams();
  const requestId = Number(id);
  const validId = Number.isFinite(requestId);
  const { data, isError } = useRequest(validId ? requestId : null);

  if (isError || !validId) {
    return (
      <div className={styles.page}>
        <Link to="/dossiers" className={styles.backLink}>← {t(lang, 'Dossiers', 'Cases')}</Link>
        <p className={styles.error}>{t(lang, 'Erreur de chargement', 'Failed to load')}</p>
      </div>
    );
  }
  if (!data) return null;

  const facts: Array<[string, string | null | undefined]> = [
    [t(lang, 'Statut', 'Status'), statusLabel(lang, data.status)],
    [t(lang, 'Immeuble', 'Building'), data.building_address],
    [t(lang, 'Unité', 'Unit'), data.unit_label],
    [t(lang, 'Territoire', 'Territory'), data.territoire],
    [t(lang, 'Assigné', 'Assigned'), data.assigned_employee_name],
    [t(lang, 'Dernier résultat', 'Last outcome'),
      data.closeout_outcome ? closeoutOutcomeLabel(lang, data.closeout_outcome) : null],
    [t(lang, 'Travail effectué', 'Work performed'), data.work_performed],
  ];

  return (
    <div className={styles.page}>
      <Link to="/dossiers" className={styles.backLink}>
        ← {t(lang, 'Dossiers', 'Cases')}
      </Link>
      <h1 className={styles.title}>{data.raw_title ?? `#${data.request_id}`}</h1>

      <dl className={styles.facts}>
        {facts.filter(([, v]) => v).map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
        ))}
      </dl>

      <div className={styles.sections}>
        <HistoryTimeline
          requestId={data.request_id}
          visits={data.visits ?? []}
          followups={data.followup_log}
          decisions={data.justification_log}
          statusChanges={data.status_history ?? []}
          lang={lang}
        />
      </div>
    </div>
  );
}
