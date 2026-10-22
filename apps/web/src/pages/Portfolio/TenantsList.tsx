/**
 * TEMP — scratch page to exercise GET /portfolio/tenants.
 * Revert when the real locataires portal lands.
 */
import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { fetchPortfolioSector, fetchPortfolioSectors, fetchPortfolioTenants } from '../../api/client';
import Pagination from '../../components/Pagination';
import Select from '../../components/Select';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { fmtDate } from './format';
import { Breadcrumbs, Empty, Header, LevelState, portfolioPath, rootCrumb, sectorName } from './shared';
import styles from './Portfolio.module.css';

const PAGE_SIZE = 50;
const LEASE_END_DAYS = [30, 60, 90];
const CAPACITE = [
  { value: 'named_on_lease', fr: 'Titulaire', en: 'Named on lease' },
  { value: 'added_occupant', fr: 'Occupant ajouté', en: 'Added occupant' },
  { value: 'took_over', fr: 'Reprise', en: 'Took over' },
] as const;

const num = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null);

export default function TenantsListView({ lang }: { lang: Lang }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const sectorId = num(params.get('secteur'));
  const projectId = num(params.get('projet'));
  const capacite = params.get('capacite') ?? '';
  const leaseDays = num(params.get('bail'));
  const q = params.get('q') ?? '';
  const page = Math.max(1, num(params.get('page')) ?? 1);

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
    queryKey: ['portfolio', 'tenants', { sectorId, projectId, capacite, leaseDays, q, page }],
    queryFn: () => fetchPortfolioTenants({
      sector_id: sectorId,
      project_id: projectId,
      capacite: (CAPACITE.some((c) => c.value === capacite) ? capacite : null) as
        | 'named_on_lease' | 'added_occupant' | 'took_over' | null,
      lease_ending_within_days: leaseDays,
      q: q || null,
      page,
      page_size: PAGE_SIZE,
    }),
    placeholderData: keepPreviousData,
  });

  const active = [sectorId, projectId, capacite || null, leaseDays, q || null].some((v) => v != null);
  const n = (v: number) => v.toLocaleString(lang === 'fr' ? 'fr-CA' : 'en-CA');
  const capaciteLabel = (v: string | null) => {
    const hit = CAPACITE.find((c) => c.value === v);
    return hit ? t(lang, hit.fr, hit.en) : (v ?? '—');
  };

  return (
    <>
      <Breadcrumbs items={[rootCrumb(lang), { label: t(lang, 'Locataires (test)', 'Tenants (test)') }]} lang={lang} />
      <Header
        lang={lang}
        eyebrow={t(lang, 'TEMP — à retirer', 'TEMP — revert later')}
        title={t(lang, 'Locataires', 'Tenants')}
        subtitle={t(lang, 'Page de test pour GET /portfolio/tenants.', 'Scratch page for GET /portfolio/tenants.')}
      />

      <div className={styles.filters} data-testid="tenants-filters">
        <div className={styles.filterGrid}>
          <label className={styles.filterField}>
            <span className={styles.filterLabel}>{t(lang, 'Recherche', 'Search')}</span>
            <input type="search" className={styles.search} value={draft}
                   placeholder={t(lang, 'Nom, téléphone, courriel, adresse…', 'Name, phone, email, address…')}
                   onChange={(e) => setDraft(e.target.value)} data-testid="tenants-q" />
          </label>
          <div className={styles.filterField}>
            <label className={styles.filterLabel} htmlFor="tenants-sector">{t(lang, 'Secteur', 'Sector')}</label>
            <Select id="tenants-sector" className={`${styles.select} ${sectorId != null ? styles.selectActive : ''}`}
                    value={sectorId ?? ''} onChange={(e) => set('secteur', e.target.value || null)}
                    data-testid="tenants-sector">
              <option value="">{t(lang, 'Tous les secteurs', 'All sectors')}</option>
              {sectors?.map((s) => (
                <option key={s.sector_id} value={s.sector_id}>{sectorName(lang, s.territoire, s.sector_id)}</option>
              ))}
            </Select>
          </div>
          <div className={styles.filterField}>
            <label className={styles.filterLabel} htmlFor="tenants-project">{t(lang, 'Projet', 'Project')}</label>
            <Select id="tenants-project" className={`${styles.select} ${projectId != null ? styles.selectActive : ''}`}
                    value={projectId ?? ''} disabled={sectorId == null}
                    onChange={(e) => set('projet', e.target.value || null)} data-testid="tenants-project">
              <option value="">
                {sectorId == null ? t(lang, 'Choisir un secteur', 'Pick a sector') : t(lang, 'Tous les projets', 'All projects')}
              </option>
              {sector?.projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>{p.nom_unique_projet ?? `#${p.project_id}`}</option>
              ))}
            </Select>
          </div>
          <div className={styles.filterField}>
            <label className={styles.filterLabel} htmlFor="tenants-capacite">{t(lang, 'Capacité', 'Capacity')}</label>
            <Select id="tenants-capacite" className={`${styles.select} ${capacite ? styles.selectActive : ''}`}
                    value={capacite} onChange={(e) => set('capacite', e.target.value || null)}
                    data-testid="tenants-capacite">
              <option value="">{t(lang, 'Toutes', 'Any')}</option>
              {CAPACITE.map((c) => (
                <option key={c.value} value={c.value}>{t(lang, c.fr, c.en)}</option>
              ))}
            </Select>
          </div>
          <div className={styles.filterField}>
            <label className={styles.filterLabel} htmlFor="tenants-lease">{t(lang, 'Fin de bail', 'Lease ends')}</label>
            <Select id="tenants-lease" className={`${styles.select} ${leaseDays != null ? styles.selectActive : ''}`}
                    value={leaseDays ?? ''} onChange={(e) => set('bail', e.target.value || null)}
                    data-testid="tenants-lease">
              <option value="">{t(lang, 'Peu importe', 'Any time')}</option>
              {LEASE_END_DAYS.map((d) => (
                <option key={d} value={d}>{t(lang, `D'ici ${d} jours`, `Within ${d} days`)}</option>
              ))}
            </Select>
          </div>
        </div>
        <div className={styles.filterRow}>
          <span className={styles.filterCount} aria-live="polite" data-testid="tenants-count">
            {data && t(lang, `${n(data.total)} locataire${data.total === 1 ? '' : 's'}`,
                             `${n(data.total)} tenant${data.total === 1 ? '' : 's'}`)}
          </span>
          {active && (
            <button type="button" className={styles.linkBtn} onClick={() => setParams(new URLSearchParams())}
                    data-testid="tenants-reset">
              {t(lang, 'Réinitialiser', 'Reset')}
            </button>
          )}
        </div>
      </div>

      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && data.items.length === 0 && (
        <Empty>{t(lang, 'Aucun locataire ne correspond à ces filtres.', 'No tenant matches these filters.')}</Empty>
      )}
      {data && data.items.length > 0 && (
        <div className={`${styles.tableWrap} ${isFetching ? styles.refreshing : ''}`}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t(lang, 'Locataire', 'Tenant')}</th>
                <th>{t(lang, 'Contact', 'Contact')}</th>
                <th>{t(lang, 'Logement', 'Unit')}</th>
                <th className={styles.hideNarrow}>{t(lang, 'Bâtiment', 'Building')}</th>
                <th className={styles.hideNarrow}>{t(lang, 'Capacité', 'Capacity')}</th>
                <th className={styles.hideNarrow}>{t(lang, 'Fin du bail', 'Lease end')}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={`${row.tenant_id}-${row.unit_id}`} className={styles.row} tabIndex={0}
                    data-testid="tenants-row"
                    onClick={() => navigate(`${portfolioPath.unit(row.unit_id)}?locataire=${row.tenant_id}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') navigate(`${portfolioPath.unit(row.unit_id)}?locataire=${row.tenant_id}`);
                    }}>
                  <td>
                    <strong>{row.nom_complet ?? `#${row.tenant_id}`}</strong>
                    {row.has_turnover && (
                      <div className={styles.cellSub}>{t(lang, 'Historover', 'Turnover')}</div>
                    )}
                  </td>
                  <td>
                    {row.telephone || row.courriel ? (
                      <>
                        {row.telephone && <div>{row.telephone}</div>}
                        {row.courriel && <div className={styles.cellSub}>{row.courriel}</div>}
                      </>
                    ) : '—'}
                  </td>
                  <td>
                    <Link to={portfolioPath.unit(row.unit_id)} onClick={(e) => e.stopPropagation()}>
                      {row.numero_appartement ?? `#${row.unit_id}`}
                    </Link>
                  </td>
                  <td className={styles.hideNarrow}>
                    <Link to={portfolioPath.building(row.building_id)} onClick={(e) => e.stopPropagation()}>
                      {row.building_adresse ?? `#${row.building_id}`}
                    </Link>
                    {row.nom_unique_projet && <div className={styles.cellSub}>{row.nom_unique_projet}</div>}
                  </td>
                  <td className={`${styles.nowrap} ${styles.hideNarrow}`}>{capaciteLabel(row.capacite)}</td>
                  <td className={`${styles.nowrap} ${styles.hideNarrow}`}>{fmtDate(row.fin_bail, lang) ?? '—'}</td>
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
