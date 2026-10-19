import { Link } from 'react-router-dom';
import { useRequests } from '../../hooks/useRequests';
import { STATUS_VALUES } from '../../api/statusValues';
import type { MeResponse, ListRow } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t, statusLabel } from '../../i18n';
import TechHeader from './TechHeader';
import { elapsedLabel } from './elapsed';
import styles from './TechPortal.module.css';

interface Props {
  lang: Lang;
  me: MeResponse | null;
  onSignOut: () => void;
}

// Every open status — the list shows all my non-closed calls, any date.
const OPEN_STATUSES = STATUS_VALUES.filter((s) => s !== 'closed');

function todayToronto(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
}

function CallRow({ row, lang }: { row: ListRow; lang: Lang }) {
  return (
    <Link to={`/tech/appels/${row.request_id}`} className={styles.callRow}>
      <div className={styles.callRowTop}>
        <span className={styles.callDate}>{row.start_date ?? t(lang, 'Sans date', 'No date')}</span>
        <span className={styles.statusBadge} data-status={row.status}>
          {statusLabel(lang, row.status)}
        </span>
        {row.urgency_tier && row.urgency_tier !== 'none' && (
          <span className={styles.urgencyBadge}>{row.urgency_tier}</span>
        )}
      </div>
      <div className={styles.callTitle}>{row.raw_title ?? `#${row.request_id}`}</div>
      <div className={styles.callAddress}>
        {row.building_address ?? '—'}
        {row.unit_label ? `, app. ${row.unit_label}` : ''}
      </div>
    </Link>
  );
}

function Section({ title, rows, lang }: { title: string; rows: ListRow[]; lang: Lang }) {
  if (rows.length === 0) return null;
  return (
    <>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {rows.map((r) => <CallRow key={r.request_id} row={r} lang={lang} />)}
    </>
  );
}

export default function TechList({ lang, me, onSignOut }: Props) {
  const params = me
    ? {
        assigned_employee_id: me.employee_id,
        status: [...OPEN_STATUSES],
        sort_by: 'start_date',
        sort_dir: 'asc' as const,
        limit: 200,
      }
    : null;
  const { data, isPending, isError } = useRequests(params);

  const today = todayToronto();
  // Defensive: drop anything closed even if the API returned it.
  const all = data
    ? [...data.items, ...data.unscheduled_items].filter((r) => r.status !== 'closed')
    : [];
  const enRoute = all.filter((r) => r.status === 'en_route');
  const rest = all.filter((r) => r.status !== 'en_route');
  const overdue = rest.filter((r) => r.start_date != null && r.start_date < today);
  const dueToday = rest.filter((r) => r.start_date === today);
  const upcoming = rest.filter((r) => r.start_date != null && r.start_date > today);
  const undated = rest.filter((r) => r.start_date == null);

  return (
    <div className={styles.page}>
      <TechHeader lang={lang} me={me} onSignOut={onSignOut} />
      <main className={styles.main}>
        {isPending && <p className={styles.muted}>{t(lang, 'Chargement…', 'Loading…')}</p>}
        {isError && <p className={styles.error}>{t(lang, 'Erreur de chargement', 'Failed to load')}</p>}

        {enRoute.length > 0 && (
          <section className={styles.openCall}>
            <div className={styles.openCallBanner}>
              {t(lang, 'Appel en cours — à clôturer avant le prochain', 'Open call — close it before the next one')}
              {elapsedLabel(enRoute[0].en_route_at) && (
                <> · {t(lang, 'En route depuis', 'En route for')} {elapsedLabel(enRoute[0].en_route_at)}</>
              )}
            </div>
            {enRoute.map((r) => <CallRow key={r.request_id} row={r} lang={lang} />)}
          </section>
        )}

        {data && all.length === 0 && (
          <p className={styles.muted}>{t(lang, 'Aucun appel assigné', 'No assigned calls')}</p>
        )}

        <Section title={t(lang, 'En retard', 'Overdue')} rows={overdue} lang={lang} />
        <Section title={t(lang, "Aujourd'hui", 'Today')} rows={dueToday} lang={lang} />
        <Section title={t(lang, 'À venir', 'Upcoming')} rows={upcoming} lang={lang} />
        <Section title={t(lang, 'Sans date', 'No date')} rows={undated} lang={lang} />
      </main>
    </div>
  );
}
