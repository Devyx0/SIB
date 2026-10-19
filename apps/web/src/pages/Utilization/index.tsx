import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchUtilization } from '../../api/client';
import type { UtilizationResponse } from '../../api/schema.d.ts';
import { closeoutOutcomeLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './Utilization.module.css';

type Row = UtilizationResponse['rows'][number];
type OutcomeKey = keyof Row['outcome_mix'];
type SortKey = 'name' | 'assigned' | 'closed' | 'rate' | 'planned' | 'visit';

const OUTCOMES: Array<{ key: OutcomeKey; short: readonly [string, string]; cls: string }> = [
  { key: 'complete', short: ['Terminé', 'Done'], cls: 'oComplete' },
  { key: 'partial_reschedule', short: ['À revenir', 'Return'], cls: 'oReschedule' },
  { key: 'partial_expertise', short: ['Expertise', 'Expertise'], cls: 'oExpertise' },
  { key: 'failed', short: ['Non fait', 'Not done'], cls: 'oFailed' },
];

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

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

const closeRate = (r: Row) => (r.calls_assigned > 0 ? r.calls_closed / r.calls_assigned : 0);
const outcomeTotal = (r: Row) => OUTCOMES.reduce((n, o) => n + r.outcome_mix[o.key], 0);

export default function Utilization({ lang = 'fr' }: { lang?: Lang }) {
  const [start, setStart] = useState(() => isoDaysAgo(6));
  const [end, setEnd] = useState(() => isoDaysAgo(0));
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('assigned');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const { data, isError, isLoading } = useQuery({
    queryKey: ['utilization', start, end],
    queryFn: () => fetchUtilization(start, end),
    enabled: Boolean(start && end),
  });

  const presets = [
    { label: t(lang, '7 jours', '7 days'), days: 6 },
    { label: t(lang, '14 jours', '14 days'), days: 13 },
    { label: t(lang, '30 jours', '30 days'), days: 29 },
  ];
  const activePreset = end === isoDaysAgo(0) ? presets.find((p) => start === isoDaysAgo(p.days)) : undefined;

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const needle = search.trim().toLowerCase();
    const filtered = needle
      ? all.filter((r) => `${r.nom_employe} ${r.territoire ?? ''}`.toLowerCase().includes(needle))
      : all;
    const val = (r: Row): number | string => {
      switch (sortKey) {
        case 'name': return r.nom_employe.toLowerCase();
        case 'assigned': return r.calls_assigned;
        case 'closed': return r.calls_closed;
        case 'rate': return closeRate(r);
        case 'planned': return r.planned_minutes;
        case 'visit': return r.visit_minutes;
      }
    };
    return [...filtered].sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      const cmp = va < vb ? -1 : va > vb ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [data, search, sortKey, sortDir]);

  const totals = useMemo(() => {
    const all = data?.rows ?? [];
    const sum = (f: (r: Row) => number) => all.reduce((n, r) => n + f(r), 0);
    return {
      people: all.length,
      assigned: sum((r) => r.calls_assigned),
      closed: sum((r) => r.calls_closed),
      planned: sum((r) => r.planned_minutes),
      visit: sum((r) => r.visit_minutes),
      visits: sum((r) => r.visits_count),
    };
  }, [data]);

  // Bars are scaled against the busiest person so rows compare at a glance.
  const maxMinutes = Math.max(1, ...rows.map((r) => Math.max(r.planned_minutes, r.visit_minutes)));

  const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
    { key: 'assigned', label: t(lang, 'Appels assignés', 'Calls assigned') },
    { key: 'closed', label: t(lang, 'Appels clôturés', 'Calls closed') },
    { key: 'rate', label: t(lang, 'Taux de clôture', 'Close rate') },
    { key: 'visit', label: t(lang, 'Temps sur place', 'Time on site') },
    { key: 'planned', label: t(lang, 'Temps planifié', 'Planned time') },
    { key: 'name', label: t(lang, 'Nom', 'Name') },
  ];

  function changeSort(key: SortKey) {
    setSortKey(key);
    setSortDir(key === 'name' ? 'asc' : 'desc');
  }

  // Which column the current sort belongs to — that header gets a marker.
  const sortedCol =
    sortKey === 'name' ? 'person' : sortKey === 'planned' || sortKey === 'visit' ? 'time' : 'calls';
  const sortMark = <span className={styles.sortMark} aria-hidden="true">{sortDir === 'asc' ? '↑' : '↓'}</span>;

  const pct = (n: number) => `${Math.round(n * 100)} %`;

  return (
    <div className={styles.page} data-testid="utilization-page">
      <header className={styles.header}>
        <div className={styles.titleBlock}>
          <h1 className={styles.title}>{t(lang, 'Utilisation', 'Utilization')}</h1>
          <p className={styles.subtitle}>
            {t(lang, 'Charge et résultats par employé', 'Workload and outcomes per employee')}
          </p>
        </div>

        <div className={styles.controls}>
          <div className={styles.presets} role="group" aria-label={t(lang, 'Période rapide', 'Quick range')}>
            {presets.map((p) => (
              <button
                key={p.days}
                type="button"
                className={`${styles.preset} ${activePreset === p ? styles.presetActive : ''}`}
                aria-pressed={activePreset === p}
                onClick={() => { setStart(isoDaysAgo(p.days)); setEnd(isoDaysAgo(0)); }}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className={styles.dateRange}>
            <label className={styles.srOnly} htmlFor="util-start">{t(lang, 'Du', 'From')}</label>
            <input id="util-start" type="date" value={start} onChange={(e) => setStart(e.target.value)}
              data-testid="util-start" />
            <span aria-hidden="true" className={styles.dateSep}>→</span>
            <label className={styles.srOnly} htmlFor="util-end">{t(lang, 'Au', 'To')}</label>
            <input id="util-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)}
              data-testid="util-end" />
          </div>
        </div>
      </header>

      <div className={styles.body}>
        {isLoading && <p className={styles.muted}>{t(lang, 'Chargement…', 'Loading…')}</p>}
        {isError && <p className={styles.error}>{t(lang, 'Erreur de chargement', 'Failed to load')}</p>}

        {data && (
          <>
            {/* Team totals */}
            <section className={styles.kpis} aria-label={t(lang, 'Totaux', 'Totals')}>
              <div className={styles.kpi}>
                <span className={styles.kpiLabel}>{t(lang, 'Employés', 'Employees')}</span>
                <span className={styles.kpiValue}>{totals.people}</span>
              </div>
              <div className={styles.kpi}>
                <span className={styles.kpiLabel}>{t(lang, 'Appels assignés', 'Calls assigned')}</span>
                <span className={styles.kpiValue}>{totals.assigned}</span>
              </div>
              <div className={styles.kpi}>
                <span className={styles.kpiLabel}>{t(lang, 'Appels clôturés', 'Calls closed')}</span>
                <span className={styles.kpiValue}>
                  {totals.closed}
                  {totals.assigned > 0 && (
                    <span className={styles.kpiSub}>{pct(totals.closed / totals.assigned)}</span>
                  )}
                </span>
              </div>
              <div className={styles.kpi}>
                <span className={styles.kpiLabel}>{t(lang, 'Temps de visite', 'Visit time')}</span>
                <span className={styles.kpiValue}>
                  {fmtMinutes(totals.visit)}
                  <span className={styles.kpiSub}>
                    {totals.visits} {t(lang, 'visite(s)', 'visit(s)')}
                  </span>
                </span>
              </div>
              <div className={styles.kpi}>
                <span className={styles.kpiLabel}>{t(lang, 'Temps planifié', 'Planned time')}</span>
                <span className={styles.kpiValue}>{fmtMinutes(totals.planned)}</span>
              </div>
            </section>

            <section className={styles.card}>
              <div className={styles.toolbar}>
                <input
                  type="search"
                  className={styles.search}
                  placeholder={t(lang, 'Filtrer par employé ou territoire…', 'Filter by employee or territory…')}
                  aria-label={t(lang, 'Filtrer', 'Filter')}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <div className={styles.sortControl}>
                  <label htmlFor="util-sort">{t(lang, 'Trier par', 'Sort by')}</label>
                  <select
                    id="util-sort"
                    value={sortKey}
                    onChange={(e) => changeSort(e.target.value as SortKey)}
                    data-testid="util-sort"
                  >
                    {SORT_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                  </select>
                  <button
                    type="button"
                    className={styles.dirBtn}
                    onClick={() => setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))}
                    aria-label={sortDir === 'asc'
                      ? t(lang, 'Ordre croissant — inverser', 'Ascending — reverse')
                      : t(lang, 'Ordre décroissant — inverser', 'Descending — reverse')}
                    title={t(lang, "Inverser l'ordre", 'Reverse order')}
                  >
                    {sortDir === 'asc' ? '↑' : '↓'}
                  </button>
                </div>
              </div>

              <div className={styles.tableWrap}>
                <table className={styles.table} data-testid="util-table">
                  <thead>
                    <tr>
                      <th scope="col" className={styles.stickyCol}>
                        <span className={styles.colTitle}>
                          {t(lang, 'Employé', 'Employee')}{sortedCol === 'person' && sortMark}
                        </span>
                        <span className={styles.colHint}>{t(lang, 'et territoire', 'and territory')}</span>
                      </th>
                      <th scope="col">
                        <span className={styles.colTitle}>
                          {t(lang, 'Appels', 'Calls')}{sortedCol === 'calls' && sortMark}
                        </span>
                        <span className={styles.colHint}>{t(lang, 'clôturés sur assignés', 'closed out of assigned')}</span>
                      </th>
                      <th scope="col">
                        <span className={styles.colTitle}>
                          {t(lang, 'Temps', 'Time')}{sortedCol === 'time' && sortMark}
                        </span>
                        <span className={styles.colHint}>{t(lang, 'sur place et planifié', 'on site and planned')}</span>
                      </th>
                      <th scope="col">
                        <span className={styles.colTitle}>{t(lang, 'Résultats de clôture', 'Closeout outcomes')}</span>
                        <span className={styles.colHint}>{t(lang, 'par type de résultat', 'by outcome type')}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 && (
                      <tr>
                        <td colSpan={4} className={styles.empty}>
                          {search
                            ? t(lang, 'Aucun employé ne correspond au filtre.', 'No employee matches the filter.')
                            : t(lang, 'Aucune activité sur cette période.', 'No activity in this period.')}
                        </td>
                      </tr>
                    )}
                    {rows.map((r) => {
                      const rate = closeRate(r);
                      const oTotal = outcomeTotal(r);
                      return (
                        <tr key={r.employee_id} data-testid={`util-row-${r.employee_id}`}>
                          <th scope="row" className={styles.stickyCol}>
                            <div className={styles.person}>
                              <span className={styles.avatar} aria-hidden="true">{initials(r.nom_employe)}</span>
                              <span className={styles.personText}>
                                <span className={styles.personName}>{r.nom_employe}</span>
                                <span className={styles.territory}>{r.territoire ?? '—'}</span>
                              </span>
                            </div>
                          </th>

                          <td>
                            <div className={styles.calls}>
                              <span className={styles.callsFig}>
                                <span className={styles.big}>{r.calls_closed}</span>
                                <span className={styles.of}> / {r.calls_assigned}</span>
                              </span>
                              <div className={styles.meter}>
                                <div className={styles.meterTrack}>
                                  <div className={styles.meterFill} style={{ width: `${rate * 100}%` }} />
                                </div>
                                <span className={styles.meterLabel}>
                                  {r.calls_assigned > 0 ? pct(rate) : '—'}
                                </span>
                              </div>
                            </div>
                          </td>

                          <td>
                            <div className={styles.time}>
                              <span className={styles.timeLabel}>{t(lang, 'Sur place', 'On site')}</span>
                              <div className={styles.timeBar}>
                                <span className={styles.barVisit} style={{ width: `${(r.visit_minutes / maxMinutes) * 100}%` }} />
                              </div>
                              <span className={styles.timeValue}>
                                {fmtMinutes(r.visit_minutes)}
                                <span className={styles.note}> · {r.visits_count} {t(lang, 'visite(s)', 'visit(s)')}</span>
                              </span>

                              <span className={styles.timeLabel}>{t(lang, 'Planifié', 'Planned')}</span>
                              <div className={styles.timeBar}>
                                <span className={styles.barPlanned} style={{ width: `${(r.planned_minutes / maxMinutes) * 100}%` }} />
                              </div>
                              <span className={styles.timeValue}>
                                {fmtMinutes(r.planned_minutes)}
                                {r.planned_unknown_count > 0 && (
                                  <span className={styles.note}>
                                    {' '}· +{r.planned_unknown_count} {t(lang, 'sans estimation', 'unestimated')}
                                  </span>
                                )}
                              </span>
                            </div>
                          </td>

                          <td>
                            {oTotal === 0 ? (
                              <span className={styles.muted}>{t(lang, 'Aucune clôture', 'No closeouts')}</span>
                            ) : (
                              <div className={styles.outcomes}>
                                <div className={styles.stack} role="img"
                                  aria-label={OUTCOMES.map((o) => `${closeoutOutcomeLabel(lang, o.key)}: ${r.outcome_mix[o.key]}`).join(', ')}>
                                  {OUTCOMES.map((o) => r.outcome_mix[o.key] > 0 && (
                                    <span
                                      key={o.key}
                                      className={styles[o.cls]}
                                      style={{ flexGrow: r.outcome_mix[o.key] }}
                                      title={`${closeoutOutcomeLabel(lang, o.key)} : ${r.outcome_mix[o.key]}`}
                                    />
                                  ))}
                                </div>
                                <div className={styles.outcomeCounts}>
                                  {OUTCOMES.map((o) => (
                                    <span key={o.key} className={r.outcome_mix[o.key] === 0 ? styles.zero : ''}
                                      title={closeoutOutcomeLabel(lang, o.key)}>
                                      <span className={`${styles.dot} ${styles[o.cls]}`} aria-hidden="true" />
                                      {r.outcome_mix[o.key]} {t(lang, o.short[0], o.short[1])}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <div className={styles.footer}>
              <ul className={styles.legend} aria-label={t(lang, 'Légende des résultats', 'Outcome legend')}>
                {OUTCOMES.map((o) => (
                  <li key={o.key}>
                    <span className={`${styles.swatch} ${styles[o.cls]}`} aria-hidden="true" />
                    <strong>{t(lang, o.short[0], o.short[1])}</strong>
                    <span className={styles.legendFull}>{closeoutOutcomeLabel(lang, o.key)}</span>
                  </li>
                ))}
              </ul>
              <p className={styles.footnote} data-testid="planned-footnote">
                {t(lang, 'Temps planifié', 'Planned time')} — {data.planned_footnote}
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
