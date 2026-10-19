import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchUtilization } from '../../api/client';
import { closeoutOutcomeLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './Utilization.module.css';

function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function fmtMinutes(m: number): string {
  if (m <= 0) return '0';
  const h = Math.floor(m / 60);
  const min = m % 60;
  if (h === 0) return `${min} min`;
  return min ? `${h} h ${String(min).padStart(2, '0')}` : `${h} h`;
}

export default function Utilization({ lang = 'fr' }: { lang?: Lang }) {
  const [start, setStart] = useState(() => isoDaysAgo(6));
  const [end, setEnd] = useState(() => isoDaysAgo(0));

  const { data, isError, isLoading } = useQuery({
    queryKey: ['utilization', start, end],
    queryFn: () => fetchUtilization(start, end),
    enabled: Boolean(start && end),
  });

  const outcomeKeys = useMemo(
    () => ['complete', 'partial_reschedule', 'partial_expertise', 'failed'] as const,
    [],
  );

  return (
    <div className={styles.page} data-testid="utilization-page">
      <h1 className={styles.title}>{t(lang, 'Utilisation', 'Utilization')}</h1>

      <div className={styles.filters}>
        <div className={styles.field}>
          <label htmlFor="util-start">{t(lang, 'Du', 'From')}</label>
          <input id="util-start" type="date" value={start} onChange={(e) => setStart(e.target.value)}
            data-testid="util-start" />
        </div>
        <div className={styles.field}>
          <label htmlFor="util-end">{t(lang, 'Au', 'To')}</label>
          <input id="util-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)}
            data-testid="util-end" />
        </div>
      </div>

      {isLoading && <p>{t(lang, 'Chargement…', 'Loading…')}</p>}
      {isError && <p className={styles.error}>{t(lang, 'Erreur de chargement', 'Failed to load')}</p>}

      {data && (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table} data-testid="util-table">
              <thead>
                <tr>
                  <th>{t(lang, 'Employé', 'Employee')}</th>
                  <th>{t(lang, 'Territoire', 'Territory')}</th>
                  <th className={styles.num}>{t(lang, 'Assignés', 'Assigned')}</th>
                  <th className={styles.num}>{t(lang, 'Clôturés', 'Closed')}</th>
                  <th className={styles.num}>{t(lang, 'Planifié', 'Planned')}</th>
                  <th className={styles.num}>{t(lang, 'Visite', 'Visit')}</th>
                  {outcomeKeys.map((k) => (
                    <th key={k} className={styles.num}>{closeoutOutcomeLabel(lang, k)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.employee_id} data-testid={`util-row-${r.employee_id}`}>
                    <td>{r.nom_employe}</td>
                    <td>{r.territoire ?? '—'}</td>
                    <td className={styles.num}>{r.calls_assigned}</td>
                    <td className={styles.num}>{r.calls_closed}</td>
                    <td className={styles.num}>{fmtMinutes(r.planned_minutes)}</td>
                    <td className={styles.num}>{fmtMinutes(r.visit_minutes)}</td>
                    <td className={styles.num}>{r.outcome_mix.complete}</td>
                    <td className={styles.num}>{r.outcome_mix.partial_reschedule}</td>
                    <td className={styles.num}>{r.outcome_mix.partial_expertise}</td>
                    <td className={styles.num}>{r.outcome_mix.failed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.footnote} data-testid="planned-footnote">
            {t(lang, 'Temps planifié', 'Planned time')} — {data.planned_footnote}
          </p>
        </>
      )}
    </div>
  );
}