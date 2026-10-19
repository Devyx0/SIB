import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchDossiers, fetchEmployees } from '../../api/client';
import { closeoutOutcomeLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import { durationLabel } from '../../components/RequestSections';
import Pagination from '../../components/Pagination';
import styles from './Dossiers.module.css';

const PAGE_SIZE = 50;
const OUTCOMES = ['complete', 'partial_reschedule', 'partial_expertise', 'failed'] as const;

function fmtDate(iso: string, lang: Lang): string {
  return new Date(iso).toLocaleDateString(lang === 'fr' ? 'fr-CA' : 'en-CA',
    { timeZone: 'America/Toronto' });
}

export default function DossiersList({ lang = 'fr' }: { lang?: Lang }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const outcome = searchParams.get('outcome') ?? '';
  const employeeId = searchParams.get('employee_id');
  const startDate = searchParams.get('start_date') ?? '';
  const endDate = searchParams.get('end_date') ?? '';
  const q = searchParams.get('q') ?? '';
  const offset = Number(searchParams.get('offset') ?? '0') || 0;

  // Search draft, debounced like the board's FilterBar — one fetch and one
  // (replaced) history entry per pause, not per keystroke.
  const [qDraft, setQDraft] = useState(q);
  const qTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => { setQDraft(q); }, [q]);
  function onQChange(v: string) {
    setQDraft(v);
    if (qTimer.current) clearTimeout(qTimer.current);
    qTimer.current = setTimeout(() => setFilter('q', v || null, { replace: true }), 500);
  }

  // Both-or-neither (like the board): the range is only sent once both
  // bounds are picked, so a half-filled pair never 422s.
  const rangeComplete = startDate !== '' && endDate !== '';

  const params = {
    outcome: outcome || undefined,
    employee_id: employeeId ? Number(employeeId) : undefined,
    start_date: rangeComplete ? startDate : undefined,
    end_date: rangeComplete ? endDate : undefined,
    q: q || undefined,
    limit: PAGE_SIZE,
    offset,
  };
  const { data, isError } = useQuery({
    queryKey: ['dossiers', params],
    queryFn: () => fetchDossiers(params),
  });
  const { data: employees = [] } = useQuery({
    queryKey: ['employees'],
    queryFn: fetchEmployees,
  });

  function setFilter(key: string, value: string | null, opts?: { replace?: boolean }) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value === null || value === '') next.delete(key);
      else next.set(key, value);
      next.delete('offset');
      return next;
    }, opts);
  }
  function setPage(newOffset: number) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (newOffset > 0) next.set('offset', String(newOffset)); else next.delete('offset');
      return next;
    });
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{t(lang, 'Dossiers', 'Cases')}</h1>
        {data && <span className={styles.count}>{data.total}</span>}
      </header>

      <div className={styles.filters}>
        <select data-testid="filter-outcome" value={outcome} aria-label={t(lang, 'Résultat', 'Outcome')}
                onChange={(e) => setFilter('outcome', e.target.value || null)}>
          <option value="">{t(lang, 'Tous les résultats', 'All outcomes')}</option>
          {OUTCOMES.map((o) => (
            <option key={o} value={o}>{closeoutOutcomeLabel(lang, o)}</option>
          ))}
        </select>
        {/* « A fait une visite »: matches any visit by this employee; the
            column still shows the LAST visit's employee. */}
        <select data-testid="filter-employee" value={employeeId ?? ''}
                aria-label={t(lang, 'A fait une visite', 'Made a visit')}
                onChange={(e) => setFilter('employee_id', e.target.value || null)}>
          <option value="">{t(lang, 'A fait une visite', 'Made a visit')}</option>
          {employees.filter((e) => e.role === 'technician' || e.role === 'contractor')
            .map((e) => <option key={e.employee_id} value={e.employee_id}>{e.nom_employe}</option>)}
        </select>
        <input type="date" data-testid="filter-start" value={startDate}
               aria-label={t(lang, 'Du', 'From')}
               onChange={(e) => setFilter('start_date', e.target.value || null)} />
        <input type="date" data-testid="filter-end" value={endDate}
               aria-label={t(lang, 'Au', 'To')}
               onChange={(e) => setFilter('end_date', e.target.value || null)} />
        <input type="search" data-testid="filter-q" value={qDraft}
               placeholder={t(lang, 'Rechercher…', 'Search…')}
               aria-label={t(lang, 'Rechercher', 'Search')}
               onChange={(e) => onQChange(e.target.value)} />
      </div>

      {isError && <p className={styles.error}>{t(lang, 'Erreur de chargement', 'Failed to load')}</p>}

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{t(lang, 'Date', 'Date')}</th>
              <th>{t(lang, 'Unité', 'Unit')}</th>
              <th>{t(lang, 'Appel', 'Call')}</th>
              <th>{t(lang, 'Territoire', 'Territory')}</th>
              <th>{t(lang, 'Assigné', 'Assigned')}</th>
              <th>{t(lang, 'Résultat', 'Outcome')}</th>
              <th className={styles.num}>{t(lang, 'En route → clôture', 'En route → closeout')}</th>
              <th className={styles.num}>{t(lang, 'Photos', 'Photos')}</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((d) => (
              <tr key={d.request_id} className={styles.row} tabIndex={0}
                  onClick={() => navigate(`/dossiers/${d.request_id}`)}
                  onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/dossiers/${d.request_id}`); }}>
                <td>{fmtDate(d.last_en_route_at, lang)}</td>
                <td>{d.unit_label ?? '—'}</td>
                <td>{d.raw_title ?? '—'}</td>
                <td>{d.territoire ?? '—'}</td>
                <td>{d.employee_name ?? '—'}</td>
                <td>
                  {d.last_outcome
                    ? closeoutOutcomeLabel(lang, d.last_outcome)
                    : t(lang, 'En cours', 'In progress')}
                  {d.closeout_urgent && <span className={styles.urgentBadge}>{t(lang, 'Urgent', 'Urgent')}</span>}
                </td>
                <td className={styles.num}>
                  {durationLabel(d.last_en_route_at, d.last_closeout_at) ?? t(lang, 'En cours', 'In progress')}
                </td>
                <td className={styles.num}>{d.photo_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && (
        <Pagination offset={offset} pageSize={PAGE_SIZE} total={data.total} lang={lang}
          onPrev={() => setPage(Math.max(0, offset - PAGE_SIZE))}
          onNext={() => setPage(offset + PAGE_SIZE)} />
      )}
    </div>
  );
}
