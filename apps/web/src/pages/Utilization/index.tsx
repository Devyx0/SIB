import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchUtilization } from '../../api/client';
import type { UtilizationResponse } from '../../api/schema.d.ts';
import { closeoutOutcomeLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './Utilization.module.css';
import Select from '../../components/Select';
import RangeCalendar from '../../components/RangeCalendar';
import ReviewsDialog from './ReviewsDialog';

type Row = UtilizationResponse['rows'][number];
type OutcomeKey = keyof Row['outcome_mix'];
type Review = Row['reviews'][number];
type SortKey ='name' | 'assigned' | 'closed' | 'rate' | 'planned' | 'visit' | 'rating';

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

/** Read-only 5-star display; rounds to the nearest whole star. */
function Stars({ value, label }: { value: number; label: string }) {
  const full = Math.round(value);
  return (
    <span className={styles.stars} role="img" aria-label={label}>
      {'★'.repeat(full)}
      <span className={styles.starsOff}>{'★'.repeat(5 - full)}</span>
    </span>
  );
}

function fmtRating(n: number, lang: Lang): string {
  return lang === 'fr' ? n.toFixed(1).replace('.', ',') : n.toFixed(1);
}

function YesNoChip({ lang, value, label }: { lang: Lang; value: boolean | null; label: readonly [string, string] }) {
  if (value == null) return null;
  return (
    <span className={`${styles.chip} ${value ? styles.chipYes : styles.chipNo}`}>
      {t(lang, label[0], label[1])} : {value ? t(lang, 'oui', 'yes') : t(lang, 'non', 'no')}
    </span>
  );
}

function ReviewItem({ lang, review, technician }: { lang: Lang; review: Review; technician?: string }) {
  const when = new Date(review.submitted_at).toLocaleDateString(lang === 'fr' ? 'fr-CA' : 'en-CA', {
    day: 'numeric', month: 'short', year: 'numeric',
  });
  return (
    <li className={styles.review}>
      <div className={styles.reviewHead}>
        {technician && <span className={styles.reviewTech}>{technician}</span>}
        {review.rating != null
          ? <Stars value={review.rating} label={t(lang, `${review.rating} sur 5`, `${review.rating} out of 5`)} />
          : <span className={styles.muted}>{t(lang, 'Sans note', 'No rating')}</span>}
        <YesNoChip lang={lang} value={review.polite} label={['Poli', 'Polite']} />
        <YesNoChip lang={lang} value={review.problem_solved} label={['Résolu', 'Solved']} />
        <span className={styles.reviewMeta}>
          {when} · #{review.request_id}{review.building_address ? ` · ${review.building_address}` : ''}
        </span>
      </div>
      {review.comments
        ? <p className={styles.reviewText}>{review.comments}</p>
        : <span className={styles.muted}>{t(lang, 'Aucun commentaire', 'No comment')}</span>}
    </li>
  );
}

const newestFirst = (reviews: Review[]) =>
  [...reviews].sort((a, b) => b.submitted_at.localeCompare(a.submitted_at));

const closeRate = (r: Row) => (r.calls_assigned > 0 ? r.calls_closed / r.calls_assigned : 0);
const outcomeTotal = (r: Row) => OUTCOMES.reduce((n, o) => n + r.outcome_mix[o.key], 0);

export default function Utilization({ lang = 'fr' }: { lang?: Lang }) {
  const [start, setStart] = useState(() => isoDaysAgo(6));
  const [end, setEnd] = useState(() => isoDaysAgo(0));
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('assigned');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [showAllReviews, setShowAllReviews] = useState(false);
  // Technician whose reviews are open in the modal.
  const [dialogFor, setDialogFor] = useState<number | null>(null);
  // Phone: the period's calendar popover and the sort menu.
  const [calOpen, setCalOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const calRef = useRef<HTMLDivElement>(null);
  const sortRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!calOpen && !sortOpen) return;
    const onDown = (e: MouseEvent) => {
      if (calOpen && calRef.current && !calRef.current.contains(e.target as Node)) setCalOpen(false);
      if (sortOpen && sortRef.current && !sortRef.current.contains(e.target as Node)) setSortOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setCalOpen(false); setSortOpen(false); } };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [calOpen, sortOpen]);

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
        case 'rating': return r.avg_rating ?? -1;
      }
    };
    return [...filtered].sort((a, b) => {
      // Unrated people always sink to the bottom when sorting by rating.
      if (sortKey === 'rating' && (a.avg_rating == null) !== (b.avg_rating == null)) {
        return a.avg_rating == null ? 1 : -1;
      }
      const va = val(a);
      const vb = val(b);
      const cmp = va < vb ? -1 : va > vb ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [data, search, sortKey, sortDir]);

  const totals = useMemo(() => {
    const all = data?.rows ?? [];
    const sum = (f: (r: Row) => number) => all.reduce((n, r) => n + f(r), 0);
    const ratingCount = sum((r) => r.rating_count);
    // Weighted by review count; avg_rating is already rounded, so sum raw ratings.
    const ratingSum = sum((r) => r.reviews.reduce((n, rv) => n + (rv.rating ?? 0), 0));
    return {
      ratingCount,
      avgRating: ratingCount > 0 ? ratingSum / ratingCount : null,
      people: all.length,
      assigned: sum((r) => r.calls_assigned),
      closed: sum((r) => r.calls_closed),
      planned: sum((r) => r.planned_minutes),
      visit: sum((r) => r.visit_minutes),
      visits: sum((r) => r.visits_count),
    };
  }, [data]);

  // Every review in the range across the team, newest first.
  const dialogRow = dialogFor == null ? undefined : data?.rows.find((r) => r.employee_id === dialogFor);

  const allReviews = useMemo(
    () => (data?.rows ?? [])
      .flatMap((r) => r.reviews.map((review) => ({ review, technician: r.nom_employe })))
      .sort((a, b) => b.review.submitted_at.localeCompare(a.review.submitted_at)),
    [data],
  );

  // Bars are scaled against the busiest person so rows compare at a glance.
  const maxMinutes = Math.max(1, ...rows.map((r) => Math.max(r.planned_minutes, r.visit_minutes)));

  const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
    { key: 'assigned', label: t(lang, 'Appels assignés', 'Calls assigned') },
    { key: 'closed', label: t(lang, 'Appels clôturés', 'Calls closed') },
    { key: 'rate', label: t(lang, 'Taux de clôture', 'Close rate') },
    { key: 'visit', label: t(lang, 'Temps sur place', 'Time on site') },
    { key: 'planned', label: t(lang, 'Temps planifié', 'Planned time') },
    { key: 'rating', label: t(lang, 'Note client', 'Customer rating') },
    { key: 'name', label: t(lang, 'Nom', 'Name') },
  ];

  function changeSort(key: SortKey) {
    setSortKey(key);
    setSortDir(key === 'name' ? 'asc' : 'desc');
  }

  // Which column the current sort belongs to — that header gets a marker.
  const sortedCol =
    sortKey === 'name' ? 'person'
      : sortKey === 'planned' || sortKey === 'visit' ? 'time'
        : sortKey === 'rating' ? 'rating' : 'calls';
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
          <div className={styles.periodRow} ref={calRef}>
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
            {/* Phone: the custom range opens a calendar instead of two date fields. */}
            <button
              type="button"
              className={`${styles.preset} ${styles.calBtn} ${!activePreset ? styles.presetActive : ''}`}
              aria-haspopup="dialog"
              aria-expanded={calOpen}
              aria-label={t(lang, `Période personnalisée : ${start} au ${end}`, `Custom range: ${start} to ${end}`)}
              onClick={() => setCalOpen((o) => !o)}
              data-testid="util-cal-btn"
            >
              <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4.5" width="14" height="12" rx="2" /><path d="M3 8.5h14M7 3v3M13 3v3" />
              </svg>
              {!activePreset && <span className={styles.calLabel}>{`${start.slice(8)}/${start.slice(5, 7)} → ${end.slice(8)}/${end.slice(5, 7)}`}</span>}
            </button>
          </div>
          {calOpen && (
            <div className={styles.calPopover} role="dialog" aria-label={t(lang, 'Période personnalisée', 'Custom range')}>
              <RangeCalendar
                lang={lang}
                start={start}
                end={end}
                maxDays={92}
                onChange={(a, b) => { setStart(a); setEnd(b); setCalOpen(false); }}
              />
            </div>
          )}
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
              <button
                type="button"
                className={`${styles.kpi} ${styles.kpiBtn}`}
                data-testid="kpi-rating"
                disabled={allReviews.length === 0}
                aria-expanded={showAllReviews && allReviews.length > 0}
                aria-controls="util-all-reviews"
                onClick={() => setShowAllReviews((v) => !v)}
              >
                <span className={styles.kpiLabel}>
                  {t(lang, 'Note client moyenne', 'Avg customer rating')}
                  {allReviews.length > 0 && (
                    <span className={styles.kpiAction}>
                      {showAllReviews ? t(lang, 'Masquer ▴', 'Hide ▴') : t(lang, 'Voir les avis ▾', 'View reviews ▾')}
                    </span>
                  )}
                </span>
                <span className={styles.kpiValue}>
                  {totals.avgRating != null ? (
                    <>
                      {fmtRating(totals.avgRating, lang)}
                      <span className={styles.kpiSub}>
                        <Stars value={totals.avgRating}
                          label={t(lang, `${fmtRating(totals.avgRating, lang)} sur 5`, `${fmtRating(totals.avgRating, lang)} out of 5`)} />
                        {' '}{totals.ratingCount} {t(lang, 'avis', totals.ratingCount === 1 ? 'review' : 'reviews')}
                      </span>
                    </>
                  ) : '—'}
                </span>
              </button>
            </section>

            {showAllReviews && allReviews.length > 0 && (
              <section className={styles.allReviews} id="util-all-reviews" data-testid="util-all-reviews"
                aria-label={t(lang, 'Tous les avis clients', 'All customer reviews')}>
                <div className={styles.allReviewsHead}>
                  <h2 className={styles.allReviewsTitle}>
                    {t(lang, 'Avis clients', 'Customer reviews')}
                    <span className={styles.note}> · {allReviews.length}</span>
                  </h2>
                  <button type="button" className={styles.dirBtn} onClick={() => setShowAllReviews(false)}
                    aria-label={t(lang, 'Fermer', 'Close')} title={t(lang, 'Fermer', 'Close')}>
                    ×
                  </button>
                </div>
                <ul className={styles.reviewList}>
                  {allReviews.map(({ review, technician }) => (
                    <ReviewItem key={review.survey_id} lang={lang} review={review} technician={technician} />
                  ))}
                </ul>
              </section>
            )}

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
                {/* Phone: one sort button beside the search; its menu has the options and the order. */}
                <div className={styles.sortMenuWrap} ref={sortRef}>
                  <button
                    type="button"
                    className={styles.sortIconBtn}
                    aria-haspopup="menu"
                    aria-expanded={sortOpen}
                    aria-label={t(lang, 'Trier', 'Sort')}
                    onClick={() => setSortOpen((o) => !o)}
                    data-testid="util-sort-btn"
                  >
                    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M6 4v12M3 13l3 3 3-3M14 16V4M11 7l3-3 3 3" />
                    </svg>
                  </button>
                  {sortOpen && (
                    <div className={styles.sortMenu} role="menu" data-testid="util-sort-menu">
                      <p className={styles.sortMenuLabel}>{t(lang, 'Trier par', 'Sort by')}</p>
                      {SORT_OPTIONS.map((o) => (
                        <button
                          key={o.key}
                          type="button"
                          role="menuitemradio"
                          aria-checked={sortKey === o.key}
                          className={`${styles.sortMenuItem} ${sortKey === o.key ? styles.sortMenuOn : ''}`}
                          onClick={() => { changeSort(o.key); setSortOpen(false); }}
                        >
                          {o.label}
                          {sortKey === o.key && <span aria-hidden="true">✓</span>}
                        </button>
                      ))}
                      <div className={styles.sortMenuDir} role="group" aria-label={t(lang, 'Ordre', 'Order')}>
                        {(['desc', 'asc'] as const).map((d) => (
                          <button
                            key={d}
                            type="button"
                            role="menuitemradio"
                            aria-checked={sortDir === d}
                            className={`${styles.sortDirOpt} ${sortDir === d ? styles.sortDirOn : ''}`}
                            onClick={() => { setSortDir(d); setSortOpen(false); }}
                          >
                            {d === 'desc' ? t(lang, '↓ Décroissant', '↓ Descending') : t(lang, '↑ Croissant', '↑ Ascending')}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <div className={styles.sortControl}>
                  <label htmlFor="util-sort">{t(lang, 'Trier par', 'Sort by')}</label>
                  <Select
                    id="util-sort"
                    value={sortKey}
                    onChange={(e) => changeSort(e.target.value as SortKey)}
                    data-testid="util-sort"
                  >
                    {SORT_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                  </Select>
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

              {/* Phone: a compact colour key above the cards (the full one is below on desktop). */}
              <ul className={styles.legendTop} aria-label={t(lang, 'Légende des résultats', 'Outcome legend')}>
                {OUTCOMES.map((o) => (
                  <li key={o.key} title={closeoutOutcomeLabel(lang, o.key)}>
                    <span className={`${styles.dot} ${styles[o.cls]}`} aria-hidden="true" />
                    {t(lang, o.short[0], o.short[1])}
                  </li>
                ))}
              </ul>

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
                      <th scope="col">
                        <span className={styles.colTitle}>
                          {t(lang, 'Avis clients', 'Customer reviews')}{sortedCol === 'rating' && sortMark}
                        </span>
                        <span className={styles.colHint}>{t(lang, 'note moyenne sur 5', 'average out of 5')}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 && (
                      <tr>
                        <td colSpan={5} className={styles.empty}>
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

                          <td className={styles.cellCalls} data-label={t(lang, 'Appels', 'Calls')}>
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

                          <td className={styles.cellTime} data-label={t(lang, 'Temps', 'Time')}>
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

                          <td className={styles.cellOutcomes} data-label={t(lang, 'Résultats de clôture', 'Closeout outcomes')}>
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

                          <td className={styles.cellRating} data-label={t(lang, 'Avis clients', 'Customer reviews')}>
                            {r.reviews.length === 0 ? (
                              <span className={styles.muted}>{t(lang, 'Aucun avis', 'No reviews')}</span>
                            ) : (
                              <button
                                type="button"
                                className={styles.ratingBtn}
                                aria-haspopup="dialog"
                                onClick={() => setDialogFor(r.employee_id)}
                                data-testid={`util-rating-${r.employee_id}`}
                              >
                                {r.avg_rating != null ? (
                                  <span className={styles.ratingTop}>
                                    <Stars value={r.avg_rating}
                                      label={t(lang, `${fmtRating(r.avg_rating, lang)} sur 5`, `${fmtRating(r.avg_rating, lang)} out of 5`)} />
                                    <span className={styles.ratingValue}>{fmtRating(r.avg_rating, lang)}</span>
                                  </span>
                                ) : (
                                  <span className={styles.muted}>{t(lang, 'Sans note', 'No rating')}</span>
                                )}
                                <span className={styles.ratingCount}>
                                  {r.reviews.length} {t(lang, 'avis', r.reviews.length === 1 ? 'review' : 'reviews')}
                                  {' '}›
                                </span>
                              </button>
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

      {dialogRow && (
        <ReviewsDialog
          lang={lang}
          technician={dialogRow.nom_employe}
          onClose={() => setDialogFor(null)}
          summary={
            <>
              {dialogRow.avg_rating != null && (
                <>
                  <Stars value={dialogRow.avg_rating}
                    label={t(lang, `${fmtRating(dialogRow.avg_rating, lang)} sur 5`, `${fmtRating(dialogRow.avg_rating, lang)} out of 5`)} />
                  <strong>{fmtRating(dialogRow.avg_rating, lang)}</strong>
                </>
              )}
              <span>
                {dialogRow.reviews.length} {t(lang, 'avis', dialogRow.reviews.length === 1 ? 'review' : 'reviews')}
                {dialogRow.territoire ? ` · ${dialogRow.territoire}` : ''}
              </span>
            </>
          }
        >
          <ul className={styles.reviewList} data-testid="reviews-dialog-list">
            {newestFirst(dialogRow.reviews).map((rv) =>
              <ReviewItem key={rv.survey_id} lang={lang} review={rv} />)}
          </ul>
        </ReviewsDialog>
      )}
    </div>
  );
}
