import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { fetchPortfolioSector, fetchPortfolioSectors, fetchPortfolioUnits } from '../../api/client';
import Pagination from '../../components/Pagination';
import Select from '../../components/Select';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { fmtDate } from './format';
import { Breadcrumbs, Empty, Header, LevelState, portfolioPath, rootCrumb, sectorName } from './shared';
import styles from './Portfolio.module.css';

// Every unit of the portfolio in one list, narrowed by filters that live in
// the URL (?secteur=&projet=&occupation=&grandeur=&bail=&q=&page=) so a
// filtered view survives a refresh and can be shared as a link.

const PAGE_SIZE = 50;
const LEASE_END_DAYS = [30, 60, 90];

export type UnitsFilter = {
  secteur?: number;
  projet?: number;
  occupation?: 'vacant' | 'occupe';
};

/** Link to the unit list with these filters, e.g. from a « N vacants » total. */
export function unitsPath(f: UnitsFilter = {}): string {
  const q = new URLSearchParams();
  if (f.secteur != null) q.set('secteur', String(f.secteur));
  if (f.projet != null) q.set('projet', String(f.projet));
  if (f.occupation) q.set('occupation', f.occupation);
  const s = q.toString();
  return `/portfolio/logements${s ? `?${s}` : ''}`;
}

const num = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null);

export default function UnitsListView({ lang }: { lang: Lang }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const sectorId = num(params.get('secteur'));
  const projectId = num(params.get('projet'));
  const occupation = params.get('occupation');
  const occupancy = occupation === 'vacant' ? 'vacant' : occupation === 'occupe' ? 'occupied' : null;
  const grandeur = params.get('grandeur') ?? '';
  const leaseDays = num(params.get('bail'));
  const q = params.get('q') ?? '';
  const page = Math.max(1, num(params.get('page')) ?? 1);

  // Changing any filter goes back to page 1.
  const set = (key: string, value: string | number | null) =>
    setParams((prev) => {
      const n = new URLSearchParams(prev);
      if (value === null || value === '') n.delete(key); else n.set(key, String(value));
      if (key !== 'page') n.delete('page');
      if (key === 'secteur') n.delete('projet');
      return n;
    });

  const [draft, setDraft] = useState(q);
  useEffect(() => { setDraft(q); }, [q]);
  useEffect(() => {
    if (draft === q) return;
    const id = setTimeout(() => set('q', draft.trim() || null), 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const { data: sectors } = useQuery({ queryKey: ['portfolio', 'sectors'], queryFn: fetchPortfolioSectors });
  const { data: sector } = useQuery({
    queryKey: ['portfolio', 'sector', sectorId],
    queryFn: () => fetchPortfolioSector(sectorId as number),
    enabled: sectorId != null,
  });
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['portfolio', 'units', { sectorId, projectId, occupancy, grandeur, leaseDays, q, page }],
    queryFn: () => fetchPortfolioUnits({
      sector_id: sectorId, project_id: projectId, occupancy,
      grandeur: grandeur || null, lease_ending_within_days: leaseDays, q: q || null,
      page, page_size: PAGE_SIZE,
    }),
    placeholderData: keepPreviousData,
  });

  const active = [sectorId, projectId, occupancy, grandeur || null, leaseDays, q || null]
    .some((v) => v != null);
  const n = (v: number) => v.toLocaleString(lang === 'fr' ? 'fr-CA' : 'en-CA');
  const occChips: { value: string | null; label: string }[] = [
    { value: null, label: t(lang, 'Tous', 'All') },
    { value: 'vacant', label: t(lang, 'Vacants', 'Vacant') + (data ? ` (${n(data.vacant_total)})` : '') },
    { value: 'occupe', label: t(lang, 'Occupés', 'Occupied') },
  ];

  return (
    <>
      <Breadcrumbs items={[rootCrumb(lang), { label: t(lang, 'Logements', 'Units') }]} lang={lang} />
      <Header
        eyebrow={t(lang, 'Parc immobilier', 'Property portfolio')}
        title={t(lang, 'Logements', 'Units')}
        subtitle={t(lang, 'Tous les logements, filtrés selon vos critères.', 'Every unit, narrowed by your filters.')}
      />

      <div className={styles.filters} data-testid="units-filters">
        <div className={styles.filterRow}>
          <label className={styles.filterField}>
            <span className={styles.filterLabel}>{t(lang, 'Recherche', 'Search')}</span>
            <input type="search" className={styles.search} value={draft}
                   placeholder={t(lang, 'Adresse, logement, locataire…', 'Address, unit, tenant…')}
                   onChange={(e) => setDraft(e.target.value)} data-testid="units-q" />
          </label>
          <div className={styles.filterField}>
            <label className={styles.filterLabel} htmlFor="units-sector">{t(lang, 'Secteur', 'Sector')}</label>
            <Select id="units-sector" className={`${styles.select} ${sectorId != null ? styles.selectActive : ''}`}
                    value={sectorId ?? ''} onChange={(e) => set('secteur', e.target.value || null)}
                    data-testid="units-sector">
              <option value="">{t(lang, 'Tous les secteurs', 'All sectors')}</option>
              {sectors?.map((s) => (
                <option key={s.sector_id} value={s.sector_id}>{sectorName(lang, s.territoire, s.sector_id)}</option>
              ))}
            </Select>
          </div>
          <div className={styles.filterField}>
            <label className={styles.filterLabel} htmlFor="units-project">{t(lang, 'Projet', 'Project')}</label>
            <Select id="units-project" className={`${styles.select} ${projectId != null ? styles.selectActive : ''}`}
                    value={projectId ?? ''} disabled={sectorId == null}
                    onChange={(e) => set('projet', e.target.value || null)} data-testid="units-project">
              <option value="">
                {sectorId == null ? t(lang, 'Choisir un secteur', 'Pick a sector') : t(lang, 'Tous les projets', 'All projects')}
              </option>
              {sector?.projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>{p.nom_unique_projet ?? `#${p.project_id}`}</option>
              ))}
            </Select>
          </div>
          <div className={styles.filterField}>
            <label className={styles.filterLabel} htmlFor="units-size">{t(lang, 'Grandeur', 'Size')}</label>
            <Select id="units-size" className={`${styles.select} ${grandeur ? styles.selectActive : ''}`}
                    value={grandeur} onChange={(e) => set('grandeur', e.target.value || null)}
                    data-testid="units-size">
              <option value="">{t(lang, 'Toutes', 'Any')}</option>
              {grandeur && !data?.grandeur_options.includes(grandeur) && <option value={grandeur}>{grandeur}</option>}
              {data?.grandeur_options.map((g) => <option key={g} value={g}>{g}</option>)}
            </Select>
          </div>
          <div className={styles.filterField}>
            <label className={styles.filterLabel} htmlFor="units-lease">{t(lang, 'Fin de bail', 'Lease ends')}</label>
            <Select id="units-lease" className={`${styles.select} ${leaseDays != null ? styles.selectActive : ''}`}
                    value={leaseDays ?? ''} onChange={(e) => set('bail', e.target.value || null)}
                    data-testid="units-lease">
              <option value="">{t(lang, 'Peu importe', 'Any time')}</option>
              {LEASE_END_DAYS.map((d) => (
                <option key={d} value={d}>{t(lang, `D'ici ${d} jours`, `Within ${d} days`)}</option>
              ))}
            </Select>
          </div>
        </div>
        <div className={styles.filterRow}>
          <div className={styles.chipGroup} role="group" aria-label={t(lang, 'Occupation', 'Occupancy')}>
            {occChips.map((c) => (
              <button key={c.label} type="button" data-testid={`occ-${c.value ?? 'all'}`}
                      className={`${styles.filterChip} ${occupation === c.value || (!occupation && !c.value) ? styles.filterChipActive : ''}`}
                      aria-pressed={occupation === c.value || (!occupation && !c.value)}
                      onClick={() => set('occupation', c.value)}>
                {c.label}
              </button>
            ))}
          </div>
          <span className={styles.filterCount} aria-live="polite" data-testid="units-count">
            {data && t(lang, `${n(data.total)} logement${data.total === 1 ? '' : 's'}`,
                             `${n(data.total)} unit${data.total === 1 ? '' : 's'}`)}
          </span>
          {active && (
            <button type="button" className={styles.linkBtn} onClick={() => setParams(new URLSearchParams())}
                    data-testid="units-reset">
              {t(lang, 'Réinitialiser', 'Reset')}
            </button>
          )}
        </div>
      </div>

      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && data.items.length === 0 && (
        <Empty>{t(lang, 'Aucun logement ne correspond à ces filtres.', 'No unit matches these filters.')}</Empty>
      )}
      {data && data.items.length > 0 && (
        <div className={`${styles.tableWrap} ${isFetching ? styles.refreshing : ''}`}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t(lang, 'Logement', 'Unit')}</th>
                <th>{t(lang, 'Bâtiment', 'Building')}</th>
                <th className={styles.hideNarrow}>{t(lang, 'Secteur', 'Sector')}</th>
                <th>{t(lang, 'Grandeur', 'Size')}</th>
                <th>{t(lang, 'Locataires', 'Tenants')}</th>
                <th className={styles.hideNarrow}>{t(lang, 'Fin du bail', 'Lease end')}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((u) => (
                <tr key={u.unit_id} className={styles.row} tabIndex={0} data-testid="units-row"
                    onClick={() => navigate(portfolioPath.unit(u.unit_id))}
                    onKeyDown={(e) => { if (e.key === 'Enter') navigate(portfolioPath.unit(u.unit_id)); }}>
                  <td><strong>{u.numero_appartement ?? `#${u.unit_id}`}</strong></td>
                  <td>
                    <Link to={portfolioPath.building(u.building_id)} onClick={(e) => e.stopPropagation()}>
                      {u.building_adresse ?? `#${u.building_id}`}
                    </Link>
                    {u.nom_unique_projet && <div className={styles.cellSub}>{u.nom_unique_projet}</div>}
                  </td>
                  <td className={`${styles.nowrap} ${styles.hideNarrow}`}>{sectorName(lang, u.territoire, u.sector_id)}</td>
                  <td className={styles.nowrap}>{u.grandeur ?? '—'}</td>
                  <td>{u.tenant_names.length > 0
                    ? u.tenant_names.join(', ')
                    : <span className={styles.vacant}>{t(lang, 'Vacant', 'Vacant')}</span>}</td>
                  <td className={`${styles.nowrap} ${styles.hideNarrow}`}>{fmtDate(u.fin_bail, lang) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && (
        <Pagination offset={(page - 1) * PAGE_SIZE} pageSize={PAGE_SIZE} total={data.total} lang={lang}
                    onPrev={() => set('page', page - 1 > 1 ? page - 1 : null)}
                    onNext={() => set('page', page + 1)} />
      )}
    </>
  );
}
