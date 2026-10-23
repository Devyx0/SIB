// Every current occupant in the portfolio, narrowed by filters that live in
// the URL (?secteur=&projet=&capacite=&bail=&q=&page=) so a filtered view
// survives a refresh and can be shared as a link — same pattern as UnitsList.

import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { fetchPortfolioSector, fetchPortfolioSectors, fetchPortfolioTenants } from '../../api/client';
import type { TenancyCapacity } from '../../api/client';
import Pagination from '../../components/Pagination';
import Select from '../../components/Select';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { formatPhone, telHref } from '../../lib/phone';
import { fmtDate } from './format';
import { FilterIcon } from './icons';
import { CAPACITE_OPTIONS, capaciteOptionLabel } from './occupancy';
import { Breadcrumbs, Empty, Header, LevelState, portfolioPath, rootCrumb, sectorName } from './shared';
import styles from './Portfolio.module.css';

const PAGE_SIZE = 50;
const LEASE_END_DAYS = [30, 60, 90];

export type TenantsFilter = {
  secteur?: number;
  projet?: number;
  capacite?: TenancyCapacity;
};

/** Link to the tenant list with these filters. */
export function tenantsPath(f: TenantsFilter = {}): string {
  const q = new URLSearchParams();
  if (f.secteur != null) q.set('secteur', String(f.secteur));
  if (f.projet != null) q.set('projet', String(f.projet));
  if (f.capacite) q.set('capacite', f.capacite);
  const s = q.toString();
  return `/portfolio/locataires${s ? `?${s}` : ''}`;
}

const num = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null);

const isCapacite = (v: string): v is TenancyCapacity =>
  CAPACITE_OPTIONS.some((c) => c.value === v);

export default function TenantsListView({ lang }: { lang: Lang }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const sectorId = num(params.get('secteur'));
  const projectId = num(params.get('projet'));
  const capaciteRaw = params.get('capacite') ?? '';
  const capacite = isCapacite(capaciteRaw) ? capaciteRaw : null;
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
  const [filtersOpen, setFiltersOpen] = useState(false);
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
      capacite,
      lease_ending_within_days: leaseDays,
      q: q || null,
      page,
      page_size: PAGE_SIZE,
    }),
    placeholderData: keepPreviousData,
  });

  const advancedCount = [sectorId, projectId, capacite, leaseDays].filter((v) => v != null).length;
  const active = advancedCount > 0 || !!q;
  const n = (v: number) => v.toLocaleString(lang === 'fr' ? 'fr-CA' : 'en-CA');
  const openTenant = (unitId: number, tenantId: number) =>
    navigate(`${portfolioPath.unit(unitId)}?locataire=${tenantId}`);

  const capaciteChips: { value: TenancyCapacity | null; label: string }[] = [
    { value: null, label: t(lang, 'Tous', 'All') },
    ...CAPACITE_OPTIONS.map((c) => ({ value: c.value, label: t(lang, c.fr, c.en) })),
  ];

  const searchField = (key: string) => (
    <label key={key} className={`${styles.filterField} ${styles.filterFieldSearch}`}>
      <span className={styles.filterLabel}>{t(lang, 'Recherche', 'Search')}</span>
      <input
        type="search"
        className={styles.search}
        value={draft}
        placeholder={t(lang, 'Nom, téléphone, courriel, adresse…', 'Name, phone, email, address…')}
        onChange={(e) => setDraft(e.target.value)}
        data-testid={key === 'compact' ? 'tenants-q' : undefined}
        aria-label={t(lang, 'Recherche', 'Search')}
      />
    </label>
  );

  return (
    <>
      <Breadcrumbs items={[rootCrumb(lang), { label: t(lang, 'Locataires', 'Tenants') }]} lang={lang} />
      <Header
        lang={lang}
        eyebrow={t(lang, 'Parc immobilier', 'Property portfolio')}
        title={t(lang, 'Locataires', 'Tenants')}
        subtitle={t(
          lang,
          'Tous les occupants actuels, filtrés selon vos critères.',
          'Every current occupant, narrowed by your filters.',
        )}
      />

      <div className={styles.filters} data-testid="tenants-filters">
        <div className={styles.filterCompact}>
          {searchField('compact')}
          <button
            type="button"
            className={`${styles.filterToggle} ${filtersOpen || advancedCount > 0 ? styles.filterToggleActive : ''}`}
            aria-expanded={filtersOpen}
            aria-controls="tenants-filter-panel"
            data-testid="tenants-filter-toggle"
            onClick={() => setFiltersOpen((o) => !o)}
          >
            <FilterIcon size={16} />
            <span>{t(lang, 'Filtres', 'Filters')}</span>
            {advancedCount > 0 && <span className={styles.filterBadge}>{advancedCount}</span>}
          </button>
        </div>

        <div
          id="tenants-filter-panel"
          className={`${styles.filterFull} ${filtersOpen ? styles.filterFullOpen : ''}`}
        >
          <div className={`${styles.filterGrid} ${styles.filterGridTenants}`}>
            {searchField('full')}
            <div className={styles.filterField}>
              <label className={styles.filterLabel} htmlFor="tenants-sector">{t(lang, 'Secteur', 'Sector')}</label>
              <Select
                id="tenants-sector"
                className={`${styles.select} ${sectorId != null ? styles.selectActive : ''}`}
                value={sectorId ?? ''}
                onChange={(e) => set('secteur', e.target.value || null)}
                data-testid="tenants-sector"
              >
                <option value="">{t(lang, 'Tous les secteurs', 'All sectors')}</option>
                {sectors?.map((s) => (
                  <option key={s.sector_id} value={s.sector_id}>{sectorName(lang, s.territoire, s.sector_id)}</option>
                ))}
              </Select>
            </div>
            <div className={styles.filterField}>
              <label className={styles.filterLabel} htmlFor="tenants-project">{t(lang, 'Projet', 'Project')}</label>
              <Select
                id="tenants-project"
                className={`${styles.select} ${projectId != null ? styles.selectActive : ''}`}
                value={projectId ?? ''}
                disabled={sectorId == null}
                onChange={(e) => set('projet', e.target.value || null)}
                data-testid="tenants-project"
              >
                <option value="">
                  {sectorId == null
                    ? t(lang, 'Choisir un secteur', 'Pick a sector')
                    : t(lang, 'Tous les projets', 'All projects')}
                </option>
                {sector?.projects.map((p) => (
                  <option key={p.project_id} value={p.project_id}>{p.nom_unique_projet ?? `#${p.project_id}`}</option>
                ))}
              </Select>
            </div>
            <div className={styles.filterField}>
              <label className={styles.filterLabel} htmlFor="tenants-lease">{t(lang, 'Fin de bail', 'Lease ends')}</label>
              <Select
                id="tenants-lease"
                className={`${styles.select} ${leaseDays != null ? styles.selectActive : ''}`}
                value={leaseDays ?? ''}
                onChange={(e) => set('bail', e.target.value || null)}
                data-testid="tenants-lease"
              >
                <option value="">{t(lang, 'Peu importe', 'Any time')}</option>
                {LEASE_END_DAYS.map((d) => (
                  <option key={d} value={d}>{t(lang, `D'ici ${d} jours`, `Within ${d} days`)}</option>
                ))}
              </Select>
            </div>
          </div>
          <div className={styles.filterRow}>
            <div className={styles.chipGroup} role="group" aria-label={t(lang, 'Capacité', 'Capacity')}>
              {capaciteChips.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  data-testid={`capacite-${c.value ?? 'all'}`}
                  className={`${styles.filterChip} ${capacite === c.value || (!capacite && !c.value) ? styles.filterChipActive : ''}`}
                  aria-pressed={capacite === c.value || (!capacite && !c.value)}
                  onClick={() => set('capacite', c.value)}
                >
                  {c.label}
                </button>
              ))}
            </div>
            <span className={styles.filterCount} aria-live="polite" data-testid="tenants-count">
              {data && t(
                lang,
                `${n(data.total)} locataire${data.total === 1 ? '' : 's'}`,
                `${n(data.total)} tenant${data.total === 1 ? '' : 's'}`,
              )}
            </span>
            {active && (
              <button
                type="button"
                className={styles.linkBtn}
                onClick={() => setParams(new URLSearchParams())}
                data-testid="tenants-reset"
              >
                {t(lang, 'Réinitialiser', 'Reset')}
              </button>
            )}
          </div>
        </div>
      </div>

      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && data.items.length === 0 && (
        <Empty>{t(lang, 'Aucun locataire ne correspond à ces filtres.', 'No tenant matches these filters.')}</Empty>
      )}
      {data && data.items.length > 0 && (
        <div className={`${styles.tableWrap} ${styles.listTableWrap} ${isFetching ? styles.refreshing : ''}`}>
          <table className={`${styles.table} ${styles.listTable}`}>
            <thead>
              <tr>
                <th>{t(lang, 'Locataire', 'Tenant')}</th>
                <th>{t(lang, 'Logement', 'Unit')}</th>
                <th>{t(lang, 'Bâtiment', 'Building')}</th>
                <th>{t(lang, 'Secteur', 'Sector')}</th>
                <th>{t(lang, 'Capacité', 'Capacity')}</th>
                <th>{t(lang, 'Fin du bail', 'Lease end')}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => {
                const phone = row.telephone_international || row.telephone;
                const role = capaciteOptionLabel(lang, row.capacite);
                return (
                  <tr
                    key={`${row.tenant_id}-${row.unit_id}`}
                    className={styles.row}
                    tabIndex={0}
                    data-testid="tenants-row"
                    onClick={() => openTenant(row.unit_id, row.tenant_id)}
                    onKeyDown={(e) => { if (e.key === 'Enter') openTenant(row.unit_id, row.tenant_id); }}
                  >
                    <td>
                      <strong>{row.nom_complet ?? `#${row.tenant_id}`}</strong>
                      {row.has_turnover && (
                        <div className={styles.cellSub}>
                          <span className={styles.turnoverFlag}>{t(lang, 'Historover', 'Turnover')}</span>
                        </div>
                      )}
                      {(phone || row.courriel) && (
                        <div className={styles.cellSub}>
                          {phone && (
                            <a href={telHref(phone)} onClick={(e) => e.stopPropagation()}>
                              {formatPhone(row.telephone) || phone}
                            </a>
                          )}
                          {phone && row.courriel ? ' · ' : null}
                          {row.courriel && (
                            <a href={`mailto:${row.courriel}`} onClick={(e) => e.stopPropagation()}>
                              {row.courriel}
                            </a>
                          )}
                        </div>
                      )}
                    </td>
                    <td>
                      <Link to={portfolioPath.unit(row.unit_id)} onClick={(e) => e.stopPropagation()}>
                        <strong>{row.numero_appartement ?? `#${row.unit_id}`}</strong>
                      </Link>
                    </td>
                    <td>
                      <Link to={portfolioPath.building(row.building_id)} onClick={(e) => e.stopPropagation()}>
                        {row.building_adresse ?? `#${row.building_id}`}
                      </Link>
                      {row.nom_unique_projet && <div className={styles.cellSub}>{row.nom_unique_projet}</div>}
                    </td>
                    <td className={styles.nowrap}>{sectorName(lang, row.territoire, row.sector_id)}</td>
                    <td className={styles.nowrap}>{role ?? '—'}</td>
                    <td className={styles.nowrap}>{fmtDate(row.fin_bail, lang) ?? '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {data && (
        <Pagination
          offset={(page - 1) * PAGE_SIZE}
          pageSize={PAGE_SIZE}
          total={data.total}
          lang={lang}
          onPrev={() => set('page', page - 1 > 1 ? page - 1 : null)}
          onNext={() => set('page', page + 1)}
        />
      )}
    </>
  );
}
