import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { fetchDashboard } from '../../api/client';
import { statusLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import { urgencyLabel } from '../../lib/urgencyLevels';
import styles from './Dashboard.module.css';
import { PersonName } from '../../components/Avatar';

export default function Dashboard({ lang = 'fr' }: { lang?: Lang }) {
  const navigate = useNavigate();
  const { data, isError, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
  });

  if (isLoading) return <div className={styles.page}>{t(lang, 'Chargement…', 'Loading…')}</div>;
  if (isError || !data) {
    return (
      <div className={styles.page}>
        <p className={styles.error}>{t(lang, 'Erreur de chargement', 'Failed to load')}</p>
      </div>
    );
  }

  const untriagedTip = [...new Set(data.untriaged_statuses.map((s) => statusLabel(lang, s)))]
    .join(', ');

  return (
    <div className={styles.page} data-testid="dashboard-page">
      <h1 className={styles.title}>{t(lang, 'Tableau de bord', 'Dashboard')}</h1>
      <p className={styles.meta}>
        {t(lang, 'Au', 'As of')} {data.as_of_date}
      </p>

      <div className={styles.grid}>
        <Link
          to={data.queue_counts.a_router_link}
          className={styles.linkTile}
          data-testid="link-a-router"
        >
          <h2>{t(lang, 'À router', 'To route')}</h2>
          <div className={styles.bigCount} data-testid="count-a-router">{data.queue_counts.a_router}</div>
          <div className={styles.cta}>{t(lang, 'Ouvrir le tableau →', 'Open board →')}</div>
        </Link>
        <Link
          to={data.queue_counts.a_redispatcher_link}
          className={styles.linkTile}
          data-testid="link-a-redispatcher"
        >
          <h2>{t(lang, 'À redispatcher', 'To redispatch')}</h2>
          <div className={styles.bigCount} data-testid="count-a-redispatcher">{data.queue_counts.a_redispatcher}</div>
          <div className={styles.cta}>{t(lang, 'Ouvrir le tableau →', 'Open board →')}</div>
        </Link>
      </div>

      <section className={styles.tile}>
        <h2>{t(lang, "Appels d'aujourd'hui par statut", "Today's calls by status")}</h2>
        {data.today_by_status.length === 0 ? (
          <p className={styles.statRow} data-testid="today-status-empty">
            <span>{t(lang, 'Aucun appel aujourd’hui', 'No calls today')}</span>
            <span className={styles.statCount}>0</span>
          </p>
        ) : (
          data.today_by_status.map((row) => (
            <div key={row.status} className={styles.statRow} data-testid={`status-${row.status}`}>
              <span>{statusLabel(lang, row.status)}</span>
              <span className={styles.statCount}>{row.count}</span>
            </div>
          ))
        )}
      </section>

      <section className={styles.tile}>
        <h2>{t(lang, "Charge par employé aujourd'hui", "Load per employee today")}</h2>
        {data.load_today.length === 0 ? (
          <p className={styles.statRow} data-testid="load-empty">
            <span>{t(lang, 'Aucune charge aujourd’hui', 'No load today')}</span>
            <span className={styles.statCount}>0</span>
          </p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t(lang, 'Employé', 'Employee')}</th>
                  <th className={styles.num}>{t(lang, 'Assignés', 'Assigned')}</th>
                  <th className={styles.num}>{t(lang, 'En route', 'En route')}</th>
                  <th className={styles.num}>{t(lang, 'Minutes', 'Minutes')}</th>
                </tr>
              </thead>
              <tbody>
                {data.load_today.map((r) => (
                  <tr key={r.employee_id}>
                    <td><PersonName name={r.nom_employe} size="xs" /></td>
                    <td className={styles.num}>{r.assigned_count}</td>
                    <td className={styles.num}>{r.en_route_count}</td>
                    <td className={styles.num}>{r.minutes_worked}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={styles.tile}>
        <h2>{t(lang, 'Par territoire', 'By territory')}</h2>
        <div className={styles.tableWrap}>
          <table className={`${styles.table} ${styles.territoryTable}`} data-testid="territory-table">
            <thead>
              <tr>
                <th>{t(lang, 'Territoire', 'Territory')}</th>
                <th className={styles.num}>{t(lang, 'Actifs', 'Active')}</th>
                <th className={`${styles.num} ${styles.urgencyCase}`}>{urgencyLabel(lang, 'URGENT')}</th>
                <th className={`${styles.num} ${styles.urgencyCase}`}>{urgencyLabel(lang, 'Intermédiaire')}</th>
                <th
                  className={styles.num}
                  title={untriagedTip}
                  data-testid="untriaged-header"
                >
                  {t(lang, 'Non triés', 'Untriaged')}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.by_territory.length === 0 ? (
                <tr>
                  <td colSpan={5} data-testid="territory-empty">
                    {t(lang, 'Aucun appel actif', 'No active calls')}
                  </td>
                </tr>
              ) : (
                data.by_territory.map((row) => (
                  <tr
                    key={row.sector_id}
                    data-testid={`territory-row-${row.sector_id}`}
                    onClick={() => navigate(row.board_link)}
                    onKeyDown={(e) => { if (e.key === 'Enter') navigate(row.board_link); }}
                    tabIndex={0}
                    role="link"
                  >
                    <td>{row.territoire}</td>
                    <td className={styles.num}>{row.active}</td>
                    <td className={styles.num}>{row.urgent}</td>
                    <td className={styles.num}>{row.medium}</td>
                    <td className={styles.num}>{row.untriaged}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <p className={styles.hint}>
          {t(lang, 'Cliquez une ligne pour ouvrir le tableau filtré.', 'Click a row to open the filtered board.')}
        </p>
      </section>
    </div>
  );
}
