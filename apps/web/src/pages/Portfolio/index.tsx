import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, Navigate, Route, Routes, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  fetchPortfolioBuilding,
  fetchPortfolioProject,
  fetchPortfolioSector,
  fetchPortfolioSectors,
  fetchPortfolioUnit,
} from '../../api/client';
import type { PortfolioLease } from '../../api/client';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import TurnoverDialog, { capaciteLabel } from './TurnoverDialog';
import { fmtDate, matches, parseDate, plural } from './format';
import styles from './Portfolio.module.css';

// Sector → project → building → unit → tenant. Each level has its own URL so
// back/forward, refresh and shared links all land on the same view.
export const portfolioPath = {
  root: () => '/portfolio',
  sector: (sectorId: number) => `/portfolio/secteurs/${sectorId}`,
  project: (sectorId: number, projectId: number) => `/portfolio/secteurs/${sectorId}/projets/${projectId}`,
  building: (buildingId: number) => `/portfolio/batiments/${buildingId}`,
  unit: (unitId: number) => `/portfolio/unites/${unitId}`,
};

const PROJECT_FR: [string, string] = ['projet', 'projets'];
const PROJECT_EN: [string, string] = ['project', 'projects'];
const BUILDING_FR: [string, string] = ['bâtiment', 'bâtiments'];
const BUILDING_EN: [string, string] = ['building', 'buildings'];
const UNIT_FR: [string, string] = ['logement', 'logements'];
const UNIT_EN: [string, string] = ['unit', 'units'];

type Crumb = { label: string; to?: string };

function Breadcrumbs({ items, lang }: { items: Crumb[]; lang: Lang }) {
  return (
    <nav aria-label={t(lang, "Fil d'Ariane", 'Breadcrumb')}>
      <ol className={styles.crumbs} data-testid="breadcrumbs">
        {items.map((c, i) => (
          <li key={i}>
            {c.to && i < items.length - 1
              ? <Link to={c.to}>{c.label}</Link>
              : <span aria-current="page">{c.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function Header({ eyebrow, title, subtitle, chips, search }: {
  eyebrow: string;
  title: string;
  subtitle?: string | null;
  chips?: (string | null)[];
  search?: React.ReactNode;
}) {
  return (
    <header className={styles.header}>
      <div>
        <p className={styles.eyebrow}>{eyebrow}</p>
        <h1 className={styles.title}>{title}</h1>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        {chips && chips.some(Boolean) && (
          <div className={styles.chips}>
            {chips.filter(Boolean).map((c) => <span key={c} className={styles.chip}>{c}</span>)}
          </div>
        )}
      </div>
      {search}
    </header>
  );
}

function SearchBox({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder: string;
}) {
  return (
    <input type="search" className={styles.search} value={value} placeholder={placeholder}
           aria-label={placeholder} data-testid="portfolio-search"
           onChange={(e) => onChange(e.target.value)} />
  );
}

/** Loading / error / not-found for a level; renders children once data is there. */
function LevelState({ isLoading, error, lang, onRetry, rows = 6 }: {
  isLoading: boolean; error: unknown; lang: Lang; onRetry: () => void; rows?: number;
}) {
  if (isLoading) {
    return (
      <div className={styles.grid} aria-busy="true">
        {Array.from({ length: rows }, (_, i) => <div key={i} className={styles.skeleton} />)}
      </div>
    );
  }
  if (error) {
    const notFound = (error as { code?: string }).code === 'NOT_FOUND'
      || (error as { code?: string }).code === 'HTTP_404';
    return (
      <div className={styles.error} role="alert">
        {notFound
          ? t(lang, 'Introuvable ou hors de votre secteur.', 'Not found or outside your sector.')
          : t(lang, 'Erreur de chargement', 'Failed to load')}
        {notFound
          ? <Link className={styles.btn} to={portfolioPath.root()}>{t(lang, 'Retour au portfolio', 'Back to portfolio')}</Link>
          : <button className={styles.btn} onClick={onRetry}>{t(lang, 'Réessayer', 'Retry')}</button>}
      </div>
    );
  }
  return null;
}

function Arrow() {
  return (
    <svg className={styles.arrow} viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"
         fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 5l5 5-5 5" />
    </svg>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className={styles.empty}>{children}</p>;
}

const rootCrumb = (lang: Lang): Crumb => ({ label: t(lang, 'Portfolio', 'Portfolio'), to: portfolioPath.root() });
const sectorName = (lang: Lang, name: string | null | undefined, id: number) =>
  name ?? t(lang, `Secteur ${id}`, `Sector ${id}`);
const projectName = (lang: Lang, name: string | null | undefined, id: number) =>
  name ?? t(lang, `Projet ${id}`, `Project ${id}`);
// Address first: the web name often repeats the project name for every building.
const buildingName = (lang: Lang, b: { web_building_name?: string | null; adresse?: string | null; building_adresse?: string | null; building_id: number }) =>
  b.adresse ?? b.building_adresse ?? b.web_building_name ?? t(lang, `Bâtiment ${b.building_id}`, `Building ${b.building_id}`);
const buildingPlace = (b: { web_building_name: string | null; ville: string | null; code_postal: string | null }) =>
  [b.web_building_name, b.ville, b.code_postal].filter(Boolean).join(' · ');
const unitName = (lang: Lang, u: { numero_appartement: string | null; unit_id: number }) =>
  u.numero_appartement ? t(lang, `Logement ${u.numero_appartement}`, `Unit ${u.numero_appartement}`)
    : t(lang, `Logement #${u.unit_id}`, `Unit #${u.unit_id}`);

// ── Level 1: sectors ─────────────────────────────────────────────────────────

function pct(part: number, whole: number): number {
  return whole > 0 ? Math.round((part / whole) * 100) : 0;
}

function SectorsView({ lang }: { lang: Lang }) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'sectors'],
    queryFn: fetchPortfolioSectors,
  });
  // « Inconnu » (unknown territory) goes last, after the named sectors.
  const sorted = data && [...data].sort((a, b) =>
    Number(a.territoire === 'Inconnu' || !a.territoire) - Number(b.territoire === 'Inconnu' || !b.territoire));
  const sum = (k: 'project_count' | 'building_count' | 'unit_count' | 'occupied_unit_count') =>
    data?.reduce((n, s) => n + s[k], 0) ?? 0;
  const units = sum('unit_count');
  const occupied = sum('occupied_unit_count');
  const n = (v: number) => v.toLocaleString(lang === 'fr' ? 'fr-CA' : 'en-CA');

  return (
    <>
      <Breadcrumbs items={[{ label: t(lang, 'Portfolio', 'Portfolio') }]} lang={lang} />
      <Header
        eyebrow={t(lang, 'Parc immobilier', 'Property portfolio')}
        title={t(lang, 'Secteurs', 'Sectors')}
        subtitle={t(lang, 'Choisissez un secteur pour voir ses projets, bâtiments et logements.',
                          'Pick a sector to browse its projects, buildings and units.')}
      />
      {data && data.length > 0 && (
        <dl className={styles.totals} data-testid="portfolio-totals">
          <div><dt>{t(lang, 'Secteurs', 'Sectors')}</dt><dd>{n(data.length)}</dd></div>
          <div><dt>{t(lang, 'Projets', 'Projects')}</dt><dd>{n(sum('project_count'))}</dd></div>
          <div><dt>{t(lang, 'Bâtiments', 'Buildings')}</dt><dd>{n(sum('building_count'))}</dd></div>
          <div><dt>{t(lang, 'Logements', 'Units')}</dt><dd>{n(units)}</dd></div>
          <div>
            <dt>{t(lang, 'Occupation', 'Occupancy')}</dt>
            <dd>{pct(occupied, units)} %</dd>
            <span className={styles.totalsNote}>
              {t(lang, `${n(units - occupied)} vacants`, `${n(units - occupied)} vacant`)}
            </span>
          </div>
        </dl>
      )}
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} />
      {data && data.length === 0 && <Empty>{t(lang, 'Aucun secteur accessible.', 'No sector available to you.')}</Empty>}
      {data && data.length > 0 && (
        <div className={`${styles.grid} ${styles.sectorGrid}`}>
          {sorted?.map((s) => {
            const more = s.project_count - s.top_projects.length;
            return (
              <Link key={s.sector_id} to={portfolioPath.sector(s.sector_id)} className={styles.card}
                    data-testid="sector-card">
                <Arrow />
                <h2 className={styles.cardTitle}>{sectorName(lang, s.territoire, s.sector_id)}</h2>
                <dl className={styles.miniStats}>
                  <div><dd>{n(s.project_count)}</dd><dt>{s.project_count === 1 ? t(lang, 'projet', 'project') : t(lang, 'projets', 'projects')}</dt></div>
                  <div><dd>{n(s.building_count)}</dd><dt>{s.building_count === 1 ? t(lang, 'bâtiment', 'building') : t(lang, 'bâtiments', 'buildings')}</dt></div>
                  <div><dd>{n(s.unit_count)}</dd><dt>{s.unit_count === 1 ? t(lang, 'logement', 'unit') : t(lang, 'logements', 'units')}</dt></div>
                </dl>
                {s.top_projects.length > 0 && (
                  <div className={styles.topProjects}>
                    <span className={styles.topLabel}>{t(lang, 'Principaux projets', 'Largest projects')}</span>
                    <div className={styles.tags}>
                      {s.top_projects.map((p) => <span key={p} className={styles.tag}>{p}</span>)}
                      {more > 0 && <span className={`${styles.tag} ${styles.tagMore}`}>+{more}</span>}
                    </div>
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}

// ── Level 2: projects of a sector ────────────────────────────────────────────

function SectorView({ lang }: { lang: Lang }) {
  const sectorId = Number(useParams().sectorId);
  const [q, setQ] = useState('');
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'sector', sectorId],
    queryFn: () => fetchPortfolioSector(sectorId),
  });
  const projects = data?.projects.filter((p) =>
    matches(q, p.nom_unique_projet, p.adresse_quickbooks, p.accounting_project_number)) ?? [];
  const name = data ? sectorName(lang, data.territoire, data.sector_id) : '…';

  return (
    <>
      <Breadcrumbs items={[rootCrumb(lang), { label: name }]} lang={lang} />
      <Header
        eyebrow={t(lang, 'Secteur', 'Sector')}
        title={name}
        chips={data ? [
          plural(data.project_count, lang, PROJECT_FR, PROJECT_EN),
          plural(data.building_count, lang, BUILDING_FR, BUILDING_EN),
        ] : []}
        search={data && data.projects.length > 6 && (
          <SearchBox value={q} onChange={setQ}
                     placeholder={t(lang, 'Rechercher un projet…', 'Search projects…')} />
        )}
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} />
      {data && projects.length === 0 && (
        <Empty>{q ? t(lang, 'Aucun projet ne correspond.', 'No matching project.')
                  : t(lang, 'Aucun projet dans ce secteur.', 'No project in this sector.')}</Empty>
      )}
      {projects.length > 0 && (
        <div className={styles.grid}>
          {projects.map((p) => (
            <Link key={p.project_id} to={portfolioPath.project(sectorId, p.project_id)}
                  className={styles.card} data-testid="project-card">
              <Arrow />
              <h2 className={styles.cardTitle}>{projectName(lang, p.nom_unique_projet, p.project_id)}</h2>
              {p.adresse_quickbooks && <p className={styles.cardSub}>{p.adresse_quickbooks}</p>}
              <div className={styles.cardMeta}>
                <span><strong>{p.building_count}</strong> {p.building_count === 1 ? t(lang, 'bâtiment', 'building') : t(lang, 'bâtiments', 'buildings')}</span>
                {p.accounting_project_number && <span>{t(lang, 'No', 'No.')} {p.accounting_project_number}</span>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}

// ── Level 3: buildings of a project (within the sector it was opened from) ───

function ProjectView({ lang }: { lang: Lang }) {
  const params = useParams();
  const sectorId = Number(params.sectorId);
  const projectId = Number(params.projectId);
  const { data: sector } = useQuery({
    queryKey: ['portfolio', 'sector', sectorId],
    queryFn: () => fetchPortfolioSector(sectorId),
  });
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'project', projectId, sectorId],
    queryFn: () => fetchPortfolioProject(projectId, sectorId),
  });
  const name = data ? projectName(lang, data.nom_unique_projet, data.project_id) : '…';

  return (
    <>
      <Breadcrumbs items={[
        rootCrumb(lang),
        { label: sector ? sectorName(lang, sector.territoire, sectorId) : '…', to: portfolioPath.sector(sectorId) },
        { label: name },
      ]} lang={lang} />
      <Header
        eyebrow={t(lang, 'Projet', 'Project')}
        title={name}
        subtitle={data?.adresse_quickbooks}
        chips={data ? [
          plural(data.building_count, lang, BUILDING_FR, BUILDING_EN),
          data.accounting_project_number ? `${t(lang, 'No', 'No.')} ${data.accounting_project_number}` : null,
        ] : []}
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && data.buildings.length === 0 && (
        <Empty>{t(lang, 'Aucun bâtiment dans ce projet.', 'No building in this project.')}</Empty>
      )}
      {data && data.buildings.length > 0 && (
        <div className={styles.grid}>
          {data.buildings.map((b) => (
            <Link key={b.building_id} to={portfolioPath.building(b.building_id)}
                  className={styles.card} data-testid="building-card">
              <Arrow />
              <h2 className={styles.cardTitle}>{buildingName(lang, b)}</h2>
              <p className={styles.cardSub}>
                {buildingPlace(b)}
              </p>
              <div className={styles.cardMeta}>
                <span><strong>{b.unit_count}</strong> {b.unit_count === 1 ? t(lang, 'logement', 'unit') : t(lang, 'logements', 'units')}</span>
                {b.actif_inactif && (
                  <span className={`${styles.badge} ${styles.badgeEnd} ${b.actif_inactif === 'Actif' ? '' : styles.badgeMuted}`}>
                    {b.actif_inactif === 'Actif' ? t(lang, 'Actif', 'Active') : b.actif_inactif}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}

// ── Level 4: units of a building ─────────────────────────────────────────────

function BuildingView({ lang }: { lang: Lang }) {
  const buildingId = Number(useParams().buildingId);
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'building', buildingId],
    queryFn: () => fetchPortfolioBuilding(buildingId),
  });
  const units = data?.units.filter((u) =>
    matches(q, u.numero_appartement, u.rue, u.grandeur, u.tenant_name)) ?? [];
  const occupied = data?.units.filter((u) => u.occupant_count > 0).length ?? 0;
  const name = data ? buildingName(lang, data) : '…';
  const open = (unitId: number) => navigate(portfolioPath.unit(unitId));

  return (
    <>
      <Breadcrumbs items={data ? [
        rootCrumb(lang),
        { label: sectorName(lang, data.territoire, data.sector_id), to: portfolioPath.sector(data.sector_id) },
        { label: projectName(lang, data.nom_unique_projet, data.project_id), to: portfolioPath.project(data.sector_id, data.project_id) },
        { label: name },
      ] : [rootCrumb(lang), { label: '…' }]} lang={lang} />
      <Header
        eyebrow={t(lang, 'Bâtiment', 'Building')}
        title={name}
        subtitle={data && buildingPlace(data)}
        chips={data ? [
          plural(data.unit_count, lang, UNIT_FR, UNIT_EN),
          t(lang, `${occupied} occupé${occupied === 1 ? '' : 's'}`, `${occupied} occupied`),
          data.nb_etages ? t(lang, `${data.nb_etages} étages`, `${data.nb_etages} floors`) : null,
          data.annee_construction ? t(lang, `Construit en ${data.annee_construction}`, `Built ${data.annee_construction}`) : null,
        ] : []}
        search={data && data.units.length > 8 && (
          <SearchBox value={q} onChange={setQ}
                     placeholder={t(lang, 'Logement, locataire, grandeur…', 'Unit, tenant, size…')} />
        )}
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && units.length === 0 && (
        <Empty>{q ? t(lang, 'Aucun logement ne correspond.', 'No matching unit.')
                  : t(lang, 'Aucun logement dans ce bâtiment.', 'No unit in this building.')}</Empty>
      )}
      {units.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t(lang, 'Logement', 'Unit')}</th>
                <th className={styles.hideNarrow}>{t(lang, 'Adresse', 'Address')}</th>
                <th>{t(lang, 'Grandeur', 'Size')}</th>
                <th>{t(lang, 'Locataire', 'Tenant')}</th>
                <th className={`${styles.num} ${styles.fit}`}>{t(lang, 'Occupants', 'Occupants')}</th>
                <th>{t(lang, 'Bail', 'Lease')}</th>
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <tr key={u.unit_id} className={styles.row} tabIndex={0} data-testid="unit-row"
                    onClick={() => open(u.unit_id)}
                    onKeyDown={(e) => { if (e.key === 'Enter') open(u.unit_id); }}>
                  <td><strong>{u.numero_appartement ?? '—'}</strong></td>
                  <td className={`${styles.nowrap} ${styles.hideNarrow}`}>{u.rue ?? '—'}</td>
                  <td className={styles.nowrap}>{u.grandeur ?? '—'}</td>
                  <td>{u.tenant_name ?? <span className={styles.vacant}>{t(lang, 'Aucun locataire', 'No tenant')}</span>}</td>
                  <td className={`${styles.num} ${styles.fit}`}>{u.occupant_count}</td>
                  <td className={styles.nowrap}>{u.lease_statut ?? (u.occupant_count > 0 ? t(lang, 'En cours', 'Current') : '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// ── Level 5: the unit, its lease and tenants (tenant → turnover window) ──────

function LeaseProgress({ lease, lang }: { lease: PortfolioLease; lang: Lang }) {
  if (!lease.debut_bail || !lease.fin_bail) return null;
  const start = parseDate(lease.debut_bail).getTime();
  const end = parseDate(lease.fin_bail).getTime();
  const now = Date.now();
  if (end <= start) return null;
  const pct = Math.min(100, Math.max(0, ((now - start) / (end - start)) * 100));
  const months = Math.max(0, Math.round((end - now) / (30.44 * 24 * 3600 * 1000)));
  return (
    <div className={styles.progress}>
      <div className={styles.progressTrack} role="progressbar" aria-valuenow={Math.round(pct)}
           aria-valuemin={0} aria-valuemax={100} aria-label={t(lang, 'Avancement du bail', 'Lease progress')}>
        <div className={styles.progressFill} style={{ width: `${pct}%` }} />
      </div>
      <p className={styles.progressLabel}>
        {months === 0
          ? t(lang, 'Se termine ce mois-ci', 'Ends this month')
          : t(lang, `${months} mois restant${months === 1 ? '' : 's'}`, `${months} month${months === 1 ? '' : 's'} left`)}
      </p>
    </div>
  );
}

function UnitView({ lang }: { lang: Lang }) {
  const unitId = Number(useParams().unitId);
  const [searchParams, setSearchParams] = useSearchParams();
  const tenantParam = searchParams.get('locataire');
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'unit', unitId],
    queryFn: () => fetchPortfolioUnit(unitId),
  });

  // The open tenant lives in the URL (?locataire=) so the panel survives a
  // refresh and the browser's back button closes it.
  const openTenant = (tenantId: number) =>
    setSearchParams((prev) => { const n = new URLSearchParams(prev); n.set('locataire', String(tenantId)); return n; });
  const closeTenant = useCallback(() =>
    setSearchParams((prev) => { const n = new URLSearchParams(prev); n.delete('locataire'); return n; }),
  [setSearchParams]);

  const name = data ? unitName(lang, data) : '…';
  const lease = data?.lease;

  return (
    <>
      <Breadcrumbs items={data ? [
        rootCrumb(lang),
        { label: sectorName(lang, data.territoire, data.sector_id), to: portfolioPath.sector(data.sector_id) },
        { label: projectName(lang, data.nom_unique_projet, data.project_id), to: portfolioPath.project(data.sector_id, data.project_id) },
        { label: buildingName(lang, data), to: portfolioPath.building(data.building_id) },
        { label: name },
      ] : [rootCrumb(lang), { label: '…' }]} lang={lang} />
      <Header
        eyebrow={t(lang, 'Logement', 'Unit')}
        title={name}
        subtitle={data?.rue}
        chips={data ? [
          data.grandeur,
          plural(data.tenants.length, lang, ['occupant', 'occupants'], ['occupant', 'occupants']),
        ] : []}
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={2} />
      {data && (
        <div className={styles.unitLayout}>
          <section className={styles.panel} aria-labelledby="lease-title">
            <h2 id="lease-title" className={styles.panelTitle}>{t(lang, 'Bail en cours', 'Current lease')}</h2>
            {lease ? (
              <>
                <dl className={styles.facts}>
                  <dt>{t(lang, 'Début', 'Start')}</dt><dd>{fmtDate(lease.debut_bail, lang) ?? '—'}</dd>
                  <dt>{t(lang, 'Fin', 'End')}</dt><dd>{fmtDate(lease.fin_bail, lang) ?? '—'}</dd>
                  {lease.statut && <><dt>{t(lang, 'Statut', 'Status')}</dt><dd>{lease.statut}</dd></>}
                  {lease.langue_bail && <><dt>{t(lang, 'Langue', 'Language')}</dt><dd>{lease.langue_bail}</dd></>}
                </dl>
                <LeaseProgress lease={lease} lang={lang} />
              </>
            ) : (
              <p className={styles.cardSub}>{t(lang, 'Aucun bail en cours pour ce logement.', 'No current lease for this unit.')}</p>
            )}
          </section>

          <section aria-labelledby="tenants-title">
            <h2 id="tenants-title" className={styles.panelTitle}>
              {t(lang, 'Locataires', 'Tenants')}
            </h2>
            {data.tenants.length === 0 ? (
              <Empty>{t(lang, 'Aucun locataire actuel.', 'No current tenant.')}</Empty>
            ) : (
              <ul className={styles.tenantList}>
                {data.tenants.map((tn) => (
                  <li key={tn.tenant_id} className={styles.tenantRow} data-testid="tenant-row">
                    <div className={styles.tenantName}>
                      <span className={styles.nameLine}>
                        <button className={styles.tenantOpen} onClick={() => openTenant(tn.tenant_id)}
                                aria-haspopup="dialog"
                                title={t(lang, 'Voir le roulement', 'View turnover')}>
                          {tn.nom_complet ?? t(lang, 'Locataire sans nom', 'Unnamed tenant')}
                        </button>
                        {tn.has_turnover && (
                          <span className={styles.turnoverFlag} data-testid="turnover-flag">
                            <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" fill="none"
                                 stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M3 5h9l-2.5-2.5M13 11H4l2.5 2.5" />
                            </svg>
                            {t(lang, 'Roulement', 'Turnover')}
                          </span>
                        )}
                      </span>
                      {capaciteLabel(lang, tn.capacite) && (
                        <span className={styles.tenantRole}>{capaciteLabel(lang, tn.capacite)}</span>
                      )}
                    </div>
                    {tn.telephone
                      ? <a className={styles.contact} href={`tel:${tn.telephone_international ?? tn.telephone}`}>{tn.telephone}</a>
                      : <span className={styles.muted}>—</span>}
                    {tn.courriel
                      ? <a className={styles.contact} href={`mailto:${tn.courriel}`}>{tn.courriel}</a>
                      : <span className={styles.muted}>—</span>}
                    <svg className={styles.rowArrow} viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"
                         fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M8 5l5 5-5 5" />
                    </svg>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {tenantParam && Number(tenantParam) > 0 && (
        <TurnoverDialog
          unitId={unitId}
          tenantId={Number(tenantParam)}
          tenant={data?.tenants.find((tn) => tn.tenant_id === Number(tenantParam))}
          lang={lang}
          onClose={closeTenant}
        />
      )}
    </>
  );
}

export default function Portfolio({ lang = 'fr' }: { lang?: Lang }) {
  return (
    <div className={styles.page}>
      <Routes>
        <Route index element={<SectorsView lang={lang} />} />
        <Route path="secteurs/:sectorId" element={<SectorView lang={lang} />} />
        <Route path="secteurs/:sectorId/projets/:projectId" element={<ProjectView lang={lang} />} />
        <Route path="batiments/:buildingId" element={<BuildingView lang={lang} />} />
        <Route path="unites/:unitId" element={<UnitView lang={lang} />} />
        <Route path="*" element={<Navigate to="/portfolio" replace />} />
      </Routes>
    </div>
  );
}
