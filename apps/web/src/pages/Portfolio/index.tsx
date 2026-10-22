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
import type { PortfolioBuildingDetail, PortfolioLease, PortfolioUnitDetail } from '../../api/client';
import type { PortfolioSectorSummary, PortfolioUnitSummary } from '../../api/schema.d.ts';
import Select from '../../components/Select';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import BuildingInfo from './BuildingInfo';
import { BuildingDialog, ProjectDialog, UnitDialog } from './forms';
import {
  BuildingIcon, CalendarIcon, CityIcon, DocumentIcon, EyeIcon, GridIcon, ListIcon, FolderIcon, HashIcon, HomeIcon, LayersIcon, MailIcon, MapPinIcon,
  PencilIcon, PhoneIcon, PieIcon, PlusIcon, UsersIcon,
} from './icons';
import TurnoverDialog, { capaciteLabel } from './TurnoverDialog';
import UnitsListView, { unitsPath } from './UnitsList';
import { fmtDate, matches, parseDate, plural, sentenceCase } from './format';
import type { Fact } from './shared';
import {
  Arrow, BUILDING_EN, BUILDING_FR, Breadcrumbs, Empty, Header, LevelState, PROJECT_EN, PROJECT_FR,
  SearchBox, useIsPhone, TenantNames, UNIT_EN, UNIT_FR, buildingName, buildingPlace, portfolioPath, projectName, rootCrumb,
  sectorName, unitName,
} from './shared';
import styles from './Portfolio.module.css';

export { portfolioPath } from './shared';

/** A project / building card: the title links to it; eye and pencil sit top right.
 *  `viewTo` sends the eye somewhere else (a building's information page). */
function ItemCard({ to, viewTo, viewLabel, title, testId, lang, onEdit, children, top }: {
  to: string; viewTo?: string; viewLabel?: string; title: string; testId: string; lang: Lang;
  onEdit: () => void; children: React.ReactNode;
  /** A line above the title (a project's accounting number). */
  top?: React.ReactNode;
}) {
  return (
    <div className={`${styles.card} ${styles.itemCard}`} data-testid={testId}>
      <div className={styles.cardTools}>
        <Link to={viewTo ?? to} className={styles.toolBtn} data-testid={`${testId}-view`}
              aria-label={viewLabel ? `${viewLabel} — ${title}` : t(lang, `Voir ${title}`, `View ${title}`)}
              title={viewLabel ?? t(lang, 'Voir', 'View')}>
          <EyeIcon />
        </Link>
        <button type="button" className={styles.toolBtn} onClick={onEdit} data-testid={`${testId}-edit`}
                aria-label={t(lang, `Modifier ${title}`, `Edit ${title}`)} title={t(lang, 'Modifier', 'Edit')}>
          <PencilIcon />
        </button>
      </div>
      {top && <p className={styles.cardTop}>{top}</p>}
      <h2 className={styles.cardTitle}><Link to={to} className={styles.cardLink}>{title}</Link></h2>
      {children}
    </div>
  );
}

/** A project on its sector's page: number, name, address; then a footer with
 *  the building count, edit, and a chevron that opens it. */
function ProjectCard({ to, number, title, address, buildings, lang, onEdit }: {
  to: string; number: string | null; title: string; address: string | null; buildings: number;
  lang: Lang; onEdit: () => void;
}) {
  return (
    <div className={`${styles.card} ${styles.itemCard} ${styles.projectCard}`} data-testid="project-card">
      {number && <p className={styles.projectNo}>{t(lang, 'N°', 'No.')} {number}</p>}
      <h2 className={styles.cardTitle}><Link to={to} className={styles.cardLink}>{title}</Link></h2>
      {address && <p className={`${styles.cardSub} ${styles.projectAddr}`}>{address}</p>}
      <div className={styles.projectFoot}>
        <span className={styles.projectCount}>
          <BuildingIcon size={24} />
          {plural(buildings, lang, BUILDING_FR, BUILDING_EN)}
        </span>
        <button type="button" className={styles.toolBtn} onClick={onEdit} data-testid="project-card-edit"
                aria-label={t(lang, `Modifier ${title}`, `Edit ${title}`)} title={t(lang, 'Modifier', 'Edit')}>
          <PencilIcon size={19} />
        </button>
        <Link to={to} className={styles.toolBtn} data-testid="project-card-view"
              aria-label={t(lang, `Voir ${title}`, `View ${title}`)} title={t(lang, 'Ouvrir', 'Open')}>
          <svg viewBox="0 0 20 20" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 5l5 5-5 5" /></svg>
        </Link>
      </div>
    </div>
  );
}

function AddButton({ label, onClick, testId }: { label: string; onClick: () => void; testId?: string }) {
  return (
    <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} onClick={onClick} data-testid={testId}>
      <PlusIcon size={14} /> {label}
    </button>
  );
}

/** « Modifier » on screen (the page title says what); the full label is for screen readers. */
function EditButton({ lang, label, onClick, testId }: { lang: Lang; label: string; onClick: () => void; testId?: string }) {
  return (
    <button type="button" className={`${styles.btn} ${styles.btnIcon}`} onClick={onClick} data-testid={testId}
            aria-label={label} title={label}>
      <PencilIcon /> <span className={styles.btnText}>{t(lang, 'Modifier', 'Edit')}</span>
    </button>
  );
}

const unitFields = (u: Pick<PortfolioUnitSummary, 'numero_appartement' | 'rue' | 'grandeur' | 'unique_unit_number'>) => ({
  numero_appartement: u.numero_appartement, rue: u.rue, grandeur: u.grandeur, unique_unit_number: u.unique_unit_number,
});

// ── Level 1: sectors ─────────────────────────────────────────────────────────

function pct(part: number, whole: number): number {
  return whole > 0 ? Math.round((part / whole) * 100) : 0;
}

/** A sector: name and chevron, then projects / buildings / units, then its largest projects. */
function SectorCard({ sector: s, lang }: { sector: PortfolioSectorSummary; lang: Lang }) {
  const n = (v: number) => v.toLocaleString(lang === 'fr' ? 'fr-CA' : 'en-CA');
  const more = s.project_count - s.top_projects.length;
  return (
    <Link to={portfolioPath.sector(s.sector_id)} className={`${styles.card} ${styles.sectorCard}`}
          data-testid="sector-card">
      <div className={styles.sectorHead}>
        <h3 className={styles.cardTitle}>{sectorName(lang, s.territoire, s.sector_id)}</h3>
        <Arrow />
      </div>
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
            {more > 0 && <span className={`${styles.tag} ${styles.tagMore}`}>{t(lang, `+${more} autres`, `+${more} more`)}</span>}
          </div>
        </div>
      )}
    </Link>
  );
}

function SectorsView({ lang }: { lang: Lang }) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'sectors'],
    queryFn: fetchPortfolioSectors,
  });
  // « Inconnu » (unknown territory) goes last, after the named sectors.
  const isUnknown = (s: PortfolioSectorSummary) => Number(s.territoire === 'Inconnu' || !s.territoire);
  const sorted = data && [...data].sort((a, b) => isUnknown(a) - isUnknown(b));
  const sum = (k: 'project_count' | 'building_count' | 'unit_count' | 'occupied_unit_count') =>
    data?.reduce((n, s) => n + s[k], 0) ?? 0;
  const units = sum('unit_count');
  const occupied = sum('occupied_unit_count');
  const n = (v: number) => v.toLocaleString(lang === 'fr' ? 'fr-CA' : 'en-CA');

  return (
    <>
      <Breadcrumbs items={[{ label: t(lang, 'Portfolio', 'Portfolio') }]} lang={lang} />
      <Header
        lang={lang}
        eyebrow={t(lang, 'Parc immobilier', 'Property portfolio')}
        title={t(lang, 'Secteurs', 'Sectors')}
        subtitle={t(lang, 'Choisissez un secteur pour voir ses projets, bâtiments et logements.',
                          'Pick a sector to browse its projects, buildings and units.')}
        globalSearch
        actions={
          <div className={styles.headerActions}>
            <Link className={styles.btn} to={unitsPath()} data-testid="all-units-link">
              {t(lang, 'Tous les logements', 'All units')}
            </Link>
          </div>
        }
      />
      {data && data.length > 0 && (
        <dl className={styles.totals} data-testid="portfolio-totals">
          <div><dt><span className={`${styles.totalIcon} ${styles.totalIconLg}`}><CityIcon size={32} /></span>{t(lang, 'Secteurs', 'Sectors')}</dt><dd>{n(data.length)}</dd></div>
          <div><dt><span className={`${styles.totalIcon} ${styles.totalIconLg}`}><DocumentIcon size={32} /></span>{t(lang, 'Projets', 'Projects')}</dt><dd>{n(sum('project_count'))}</dd></div>
          <div><dt><span className={`${styles.totalIcon} ${styles.totalIconLg}`}><BuildingIcon size={32} /></span>{t(lang, 'Bâtiments', 'Buildings')}</dt><dd>{n(sum('building_count'))}</dd></div>
          <div><dt><span className={styles.totalIcon}><UsersIcon size={24} /></span>{t(lang, 'Logements', 'Units')}</dt><dd>{n(units)}</dd></div>
          <div>
            <dt><span className={styles.totalIcon}><PieIcon /></span>{t(lang, 'Occupation', 'Occupancy')}</dt>
            <dd className={styles.occLine}>
              <span>{pct(occupied, units)} %</span>
              <Link className={`${styles.totalsNote} ${styles.vacantLink}`} to={unitsPath({ occupation: 'vacant' })}
                    data-testid="vacant-link">
                {t(lang, `${n(units - occupied)} vacants`, `${n(units - occupied)} vacant`)}
              </Link>
            </dd>
            <span className={styles.occBar} aria-hidden="true">
              <span style={{ width: `${pct(occupied, units)}%` }} />
            </span>
          </div>
        </dl>
      )}
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} />
      {data && data.length === 0 && <Empty>{t(lang, 'Aucun secteur accessible.', 'No sector available to you.')}</Empty>}
      {data && data.length > 0 && (
        <section aria-labelledby="all-sectors-title">
          <h2 id="all-sectors-title" className={styles.allSectorsTitle} data-testid="all-sectors-title">
            {t(lang, 'Tous les secteurs', 'All sectors')} <span className={styles.sectionCount}>({n(data.length)})</span>
          </h2>
          <div className={`${styles.grid} ${styles.sectorGrid}`}>
            {sorted?.map((s) => <SectorCard key={s.sector_id} sector={s} lang={lang} />)}
          </div>
        </section>
      )}
    </>
  );
}

// ── Level 2: projects of a sector ────────────────────────────────────────────

function SectorView({ lang }: { lang: Lang }) {
  const sectorId = Number(useParams().sectorId);
  const [q, setQ] = useState('');
  const phone = useIsPhone();
  const [dialog, setDialog] = useState<{ edit: number } | 'new' | null>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'sector', sectorId],
    queryFn: () => fetchPortfolioSector(sectorId),
  });
  const editing = dialog && dialog !== 'new' ? data?.projects.find((p) => p.project_id === dialog.edit) : null;
  const [size, setSize] = useState<'all' | '1' | '2-3' | '4+'>('all');
  const [sort, setSort] = useState<'name' | 'number' | 'buildings'>('name');
  const [view, setView] = useState<'grid' | 'list'>(() => {
    try { return localStorage.getItem('portfolio.projectView') === 'list' ? 'list' : 'grid'; } catch { return 'grid'; }
  });
  const pickView = (v: 'grid' | 'list') => {
    setView(v);
    try { localStorage.setItem('portfolio.projectView', v); } catch { /* private mode */ }
  };
  const inSize = (n: number) => size === 'all' || (size === '1' ? n === 1 : size === '2-3' ? n >= 2 && n <= 3 : n >= 4);
  const collator = new Intl.Collator(lang === 'fr' ? 'fr-CA' : 'en-CA', { numeric: true, sensitivity: 'base' });
  const projects = (data?.projects.filter((p) =>
    inSize(p.building_count) && matches(q, p.nom_unique_projet, p.adresse_quickbooks, p.accounting_project_number)) ?? [])
    .sort((a, b) => sort === 'buildings' ? b.building_count - a.building_count
      : sort === 'number' ? collator.compare(a.accounting_project_number ?? '\uffff', b.accounting_project_number ?? '\uffff')
      : collator.compare(projectName(lang, a.nom_unique_projet, a.project_id), projectName(lang, b.nom_unique_projet, b.project_id)));
  const name = data ? sectorName(lang, data.territoire, data.sector_id) : '…';
  const addProject = <AddButton label={t(lang, 'Nouveau projet', 'New project')} onClick={() => setDialog('new')} testId="add-project" />;
  const viewUnits = (
    <Link className={styles.btn} to={unitsPath({ secteur: sectorId })}>{t(lang, 'Voir les logements', 'View units')}</Link>
  );

  return (
    <>
      <Breadcrumbs items={[rootCrumb(lang), { label: name }]} lang={lang}
                   action={phone && data && addProject} />
      <Header
        lang={lang}
        eyebrow={t(lang, 'Secteur', 'Sector')}
        title={name}
        facts={data && [
          { key: 'projects', icon: <FolderIcon />, label: plural(data.project_count, lang, PROJECT_FR, PROJECT_EN) },
          { key: 'buildings', icon: <BuildingIcon />, label: plural(data.building_count, lang, BUILDING_FR, BUILDING_EN) },
        ]}
        actions={!phone && data && <div className={styles.headerActions}>{viewUnits}{addProject}</div>}
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} />
      {data && (
        <div className={styles.unitTools}>
          {data.projects.length > 0 && (
            <SearchBox value={q} onChange={setQ}
                       placeholder={t(lang, 'Rechercher un projet…', 'Search projects…')} />
          )}
          {phone && <div className={styles.headerActions}>{viewUnits}</div>}
          {data.projects.length > 0 && (
            <div className={styles.listControls}>
              <Select className={`${styles.select} ${size !== 'all' ? styles.selectActive : ''}`} value={size}
                      aria-label={t(lang, 'Nombre de bâtiments', 'Building count')} data-testid="project-size"
                      onChange={(e) => setSize(e.target.value as typeof size)}>
                <option value="all">{t(lang, 'Bâtiments : tous', 'Buildings: all')}</option>
                <option value="1">{t(lang, '1 bâtiment', '1 building')}</option>
                <option value="2-3">{t(lang, '2 à 3 bâtiments', '2–3 buildings')}</option>
                <option value="4+">{t(lang, '4 bâtiments et plus', '4+ buildings')}</option>
              </Select>
              <Select className={styles.select} value={sort} data-testid="project-sort"
                      aria-label={t(lang, 'Trier les projets', 'Sort projects')}
                      onChange={(e) => setSort(e.target.value as typeof sort)}>
                <option value="name">{t(lang, 'Tri : nom', 'Sort: name')}</option>
                <option value="number">{t(lang, 'Tri : numéro', 'Sort: number')}</option>
                <option value="buildings">{t(lang, 'Tri : bâtiments', 'Sort: buildings')}</option>
              </Select>
              {!phone && (
                <div className={styles.viewToggle} role="group" aria-label={t(lang, 'Affichage', 'View')}>
                  <button type="button" aria-pressed={view === 'grid'} onClick={() => pickView('grid')}
                          aria-label={t(lang, 'Cartes', 'Cards')} title={t(lang, 'Cartes', 'Cards')} data-testid="view-grid">
                    <GridIcon />
                  </button>
                  <button type="button" aria-pressed={view === 'list'} onClick={() => pickView('list')}
                          aria-label={t(lang, 'Liste', 'List')} title={t(lang, 'Liste', 'List')} data-testid="view-list">
                    <ListIcon />
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {data && projects.length === 0 && (
        <Empty>{q || size !== 'all' ? t(lang, 'Aucun projet ne correspond.', 'No matching project.')
                  : t(lang, 'Aucun projet dans ce secteur.', 'No project in this sector.')}</Empty>
      )}
      {projects.length > 0 && (
        <>
          {view === 'list' && !phone ? (
            <div className={styles.tableWrap}>
              <table className={styles.table} data-testid="project-table">
                <thead>
                  <tr>
                    <th className={styles.fit}>{t(lang, 'N°', 'No.')}</th>
                    <th>{t(lang, 'Projet', 'Project')}</th>
                    <th>{t(lang, 'Adresse', 'Address')}</th>
                    <th className={styles.num}>{t(lang, 'Bâtiments', 'Buildings')}</th>
                    <th className={styles.fit}><span className={styles.srOnly}>{t(lang, 'Actions', 'Actions')}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((p) => {
                    const title = projectName(lang, p.nom_unique_projet, p.project_id);
                    const to = portfolioPath.project(sectorId, p.project_id);
                    return (
                      <tr key={p.project_id} data-testid="project-row">
                        <td className={styles.fit}><strong>{p.accounting_project_number ?? '—'}</strong></td>
                        <td><Link to={to} className={styles.rowLink}>{title}</Link></td>
                        <td className={styles.addrCell}>{p.adresse_quickbooks ?? '—'}</td>
                        <td className={styles.num}>{p.building_count}</td>
                        <td className={`${styles.fit} ${styles.rowActions}`}>
                          <button type="button" className={styles.toolBtn} onClick={() => setDialog({ edit: p.project_id })}
                                  aria-label={t(lang, `Modifier ${title}`, `Edit ${title}`)} title={t(lang, 'Modifier', 'Edit')}>
                            <PencilIcon />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className={`${styles.grid} ${styles.projectGrid}`}>
              {projects.map((p) => (
                <ProjectCard key={p.project_id} to={portfolioPath.project(sectorId, p.project_id)}
                             number={p.accounting_project_number} address={p.adresse_quickbooks}
                             title={projectName(lang, p.nom_unique_projet, p.project_id)}
                             buildings={p.building_count} lang={lang}
                             onEdit={() => setDialog({ edit: p.project_id })} />
              ))}
            </div>
          )}
          <p className={styles.listCount} data-testid="project-count" aria-live="polite">
            {projects.length === data!.projects.length
              ? t(lang, `${plural(projects.length, lang, PROJECT_FR, PROJECT_EN)} au total.`,
                        `Showing all ${plural(projects.length, lang, PROJECT_FR, PROJECT_EN)}.`)
              : t(lang, `${projects.length} sur ${plural(data!.projects.length, lang, PROJECT_FR, PROJECT_EN)}.`,
                        `${projects.length} of ${plural(data!.projects.length, lang, PROJECT_FR, PROJECT_EN)}.`)}
          </p>
        </>
      )}
      {dialog === 'new' && <ProjectDialog mode="create" sectorId={sectorId} lang={lang} onClose={() => setDialog(null)} />}
      {editing && (
        <ProjectDialog mode="edit" projectId={editing.project_id} lang={lang} onClose={() => setDialog(null)}
                       initial={{
                         nom_unique_projet: editing.nom_unique_projet,
                         adresse_quickbooks: editing.adresse_quickbooks,
                         accounting_project_number: editing.accounting_project_number,
                       }} />
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
  const [dialog, setDialog] = useState<'project' | 'new' | { edit: number } | null>(null);
  const [q, setQ] = useState('');
  const name = data ? projectName(lang, data.nom_unique_projet, data.project_id) : '…';
  const buildings = data?.buildings.filter((b) =>
    matches(q, b.adresse, b.web_building_name, b.ville, b.code_postal)) ?? [];

  const phone = useIsPhone();
  const addBuilding = <AddButton label={t(lang, 'Bâtiment', 'Building')} onClick={() => setDialog('new')} testId="add-building" />;
  const editProject = <EditButton lang={lang} label={t(lang, 'Modifier le projet', 'Edit project')} testId="edit-project"
                                  onClick={() => setDialog('project')} />;

  return (
    <>
      <Breadcrumbs items={[
        rootCrumb(lang),
        { label: sector ? sectorName(lang, sector.territoire, sectorId) : '…', to: portfolioPath.sector(sectorId) },
        { label: name },
      ]} lang={lang} action={phone && data && addBuilding} />
      <Header
        lang={lang}
        eyebrow={t(lang, 'Projet', 'Project')}
        title={name}
        subtitle={data?.adresse_quickbooks}
        facts={data && [
          data.accounting_project_number && { key: 'number', icon: <HashIcon />, label: t(lang, `Projet N° ${data.accounting_project_number}`, `Project No. ${data.accounting_project_number}`) },
          { key: 'buildings', icon: <BuildingIcon />, label: plural(data.building_count, lang, BUILDING_FR, BUILDING_EN) },
          sector && { key: 'sector', icon: <MapPinIcon />, label: sectorName(lang, sector.territoire, sectorId), to: portfolioPath.sector(sectorId) },
        ]}
        actions={data && (phone ? <div className={styles.headerActions}>{editProject}</div> : (
          <div className={styles.headerActions}>
            <Link className={styles.btn} to={unitsPath({ secteur: sectorId, projet: projectId })}>
              {t(lang, 'Voir les logements', 'View units')}
            </Link>
            {editProject}{addBuilding}
          </div>
        ))}
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && (
        <div className={styles.unitTools}>
          {data.buildings.length > 0 && (
            <SearchBox value={q} onChange={setQ}
                       placeholder={t(lang, 'Rechercher un bâtiment…', 'Search buildings…')} />
          )}
          {phone && (
            <div className={styles.headerActions}>
              <Link className={styles.btn} to={unitsPath({ secteur: sectorId, projet: projectId })}>
                {t(lang, 'Voir les logements', 'View units')}
              </Link>
            </div>
          )}
        </div>
      )}
      {data && buildings.length === 0 && (
        <Empty>{q ? t(lang, 'Aucun bâtiment ne correspond.', 'No matching building.')
                  : t(lang, 'Aucun bâtiment dans ce projet.', 'No building in this project.')}</Empty>
      )}
      {buildings.length > 0 && (
        <div className={styles.grid}>
          {buildings.map((b) => (
            <ItemCard key={b.building_id} to={portfolioPath.building(b.building_id)}
                      viewTo={portfolioPath.buildingInfo(b.building_id)}
                      viewLabel={t(lang, 'Informations du bâtiment', 'Building information')}
                      title={buildingName(lang, b)} testId="building-card"
                      lang={lang} onEdit={() => setDialog({ edit: b.building_id })}>
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
            </ItemCard>
          ))}
        </div>
      )}
      {dialog === 'project' && data && (
        <ProjectDialog mode="edit" projectId={projectId} lang={lang} onClose={() => setDialog(null)}
                       initial={{
                         nom_unique_projet: data.nom_unique_projet,
                         adresse_quickbooks: data.adresse_quickbooks,
                         accounting_project_number: data.accounting_project_number,
                       }} />
      )}
      {dialog === 'new' && (
        <BuildingDialog mode="create" projectId={projectId} sectorId={sectorId} lang={lang}
                        onClose={() => setDialog(null)} />
      )}
      {dialog && typeof dialog === 'object' && (
        <BuildingDialog mode="edit" buildingId={dialog.edit} lang={lang} onClose={() => setDialog(null)} />
      )}
    </>
  );
}

// ── Level 4: units of a building ─────────────────────────────────────────────

function BuildingView({ lang }: { lang: Lang }) {
  const buildingId = Number(useParams().buildingId);
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [occ, setOcc] = useState<'all' | 'vacant' | 'occupied'>('all');
  const [dialog, setDialog] = useState<'building' | 'new' | { edit: number } | null>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'building', buildingId],
    queryFn: () => fetchPortfolioBuilding(buildingId),
  });
  const occupied = data?.units.filter((u) => u.occupant_count > 0).length ?? 0;
  const vacant = (data?.units.length ?? 0) - occupied;
  const units = data?.units.filter((u) =>
    (occ === 'all' || (occ === 'vacant') === (u.occupant_count === 0))
    && matches(q, u.numero_appartement, u.rue, u.grandeur, ...u.tenant_names)) ?? [];
  const name = data ? buildingName(lang, data) : '…';
  const open = (unitId: number) => navigate(portfolioPath.unit(unitId));
  // One street for every unit: the column would repeat it on each row.
  const showStreet = new Set(data?.units.map((u) => u.rue ?? '')).size > 1;

  const phone = useIsPhone();
  const addUnit = <AddButton label={t(lang, 'Logement', 'Unit')} onClick={() => setDialog('new')} testId="add-unit" />;
  // Building information (eye) and edit (pencil): beside the title on a phone.
  const buildingButtons = (
    <>
      <Link className={`${styles.btn} ${styles.btnIcon}`} to={portfolioPath.buildingInfo(buildingId)}
            data-testid="building-info-link" title={t(lang, 'Informations du bâtiment', 'Building information')}
            aria-label={t(lang, 'Informations du bâtiment', 'Building information')}>
        <EyeIcon /> <span className={styles.btnText}>{t(lang, 'Informations', 'Information')}</span>
      </Link>
      <EditButton lang={lang} label={t(lang, 'Modifier le bâtiment', 'Edit building')} testId="edit-building"
                  onClick={() => setDialog('building')} />
    </>
  );

  return (
    <>
      <Breadcrumbs items={data ? [
        rootCrumb(lang),
        { label: sectorName(lang, data.territoire, data.sector_id), to: portfolioPath.sector(data.sector_id) },
        { label: projectName(lang, data.nom_unique_projet, data.project_id), to: portfolioPath.project(data.sector_id, data.project_id) },
        { label: name },
      ] : [rootCrumb(lang), { label: '…' }]} lang={lang} action={phone && data && addUnit} />
      <Header
        lang={lang}
        eyebrow={t(lang, 'Bâtiment', 'Building')}
        title={name}
        subtitle={data && buildingPlace(data)}
        facts={data && buildingFacts(data, lang, occupied)}
        actionsBelow={phone}
        actions={data && <div className={styles.headerActions}>{buildingButtons}{!phone && addUnit}</div>}
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && (
        <div className={styles.unitTools}>
          {data.units.length > 0 && (
            <SearchBox value={q} onChange={setQ}
                       placeholder={t(lang, 'Rechercher : logement, locataire, grandeur…', 'Search: unit, tenant, size…')} />
          )}
          {data.units.length > 0 && (
            <div className={styles.chipGroup} role="group" aria-label={t(lang, 'Occupation', 'Occupancy')}>
              {([
                ['all', t(lang, `Tous (${data.units.length})`, `All (${data.units.length})`)],
                ['vacant', t(lang, `Vacants (${vacant})`, `Vacant (${vacant})`)],
                ['occupied', t(lang, `Occupés (${occupied})`, `Occupied (${occupied})`)],
              ] as const).map(([value, label]) => (
                <button key={value} type="button" data-testid={`building-occ-${value}`}
                        className={`${styles.filterChip} ${occ === value ? styles.filterChipActive : ''}`}
                        aria-pressed={occ === value} onClick={() => setOcc(value)}>
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {data && units.length === 0 && (
        <Empty>{q || occ !== 'all' ? t(lang, 'Aucun logement ne correspond.', 'No matching unit.')
                  : t(lang, 'Aucun logement dans ce bâtiment.', 'No unit in this building.')}</Empty>
      )}
      {units.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t(lang, 'Logement', 'Unit')}</th>
                {showStreet && <th className={styles.hideNarrow}>{t(lang, 'Adresse', 'Address')}</th>}
                <th>{t(lang, 'Grandeur', 'Size')}</th>
                <th>{t(lang, 'Locataire', 'Tenant')}</th>
                <th className={`${styles.num} ${styles.fit} ${styles.hideNarrow}`}>{t(lang, 'Occupants', 'Occupants')}</th>
                <th>{t(lang, 'Bail', 'Lease')}</th>
                <th className={`${styles.fit} ${styles.hideNarrow}`}><span className={styles.srOnly}>{t(lang, 'Actions', 'Actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <tr key={u.unit_id} className={styles.row} tabIndex={0} data-testid="unit-row"
                    onClick={() => open(u.unit_id)}
                    onKeyDown={(e) => { if (e.key === 'Enter') open(u.unit_id); }}>
                  <td><strong>{u.numero_appartement ?? '—'}</strong></td>
                  {showStreet && <td className={`${styles.nowrap} ${styles.hideNarrow}`}>{u.rue ?? '—'}</td>}
                  <td className={styles.nowrap}>{u.grandeur ?? '—'}</td>
                  <td>{u.tenant_names.length > 0
                    ? <TenantNames names={u.tenant_names} />
                    : <span className={styles.vacant}>{t(lang, 'Aucun locataire', 'No tenant')}</span>}</td>
                  <td className={`${styles.num} ${styles.fit} ${styles.hideNarrow}`}>{u.occupant_count}</td>
                  <td className={styles.nowrap}>{u.lease_statut ?? (u.occupant_count > 0
                    ? t(lang, 'En cours', 'Current')
                    : <span className={styles.vacantBadge}>{t(lang, 'Vacant', 'Vacant')}</span>)}</td>
                  <td className={`${styles.fit} ${styles.rowActions} ${styles.hideNarrow}`} onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.stopPropagation()}>
                    <Link to={portfolioPath.unit(u.unit_id)} className={styles.toolBtn}
                          aria-label={t(lang, `Voir le logement ${u.numero_appartement ?? ''}`, `View unit ${u.numero_appartement ?? ''}`)}
                          title={t(lang, 'Voir', 'View')}>
                      <EyeIcon />
                    </Link>
                    <button type="button" className={styles.toolBtn} data-testid="unit-row-edit"
                            onClick={() => setDialog({ edit: u.unit_id })} title={t(lang, 'Modifier', 'Edit')}
                            aria-label={t(lang, `Modifier le logement ${u.numero_appartement ?? ''}`, `Edit unit ${u.numero_appartement ?? ''}`)}>
                      <PencilIcon />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {dialog === 'building' && (
        <BuildingDialog mode="edit" buildingId={buildingId} lang={lang} onClose={() => setDialog(null)} />
      )}
      {dialog === 'new' && (
        <UnitDialog mode="create" buildingId={buildingId} lang={lang} onClose={() => setDialog(null)}
                    defaultRue={data?.units[0]?.rue ?? data?.adresse} />
      )}
      {dialog && typeof dialog === 'object' && (() => {
        const u = data?.units.find((x) => x.unit_id === dialog.edit);
        return u && (
          <UnitDialog mode="edit" unitId={u.unit_id} initial={unitFields(u)} lang={lang}
                      onClose={() => setDialog(null)} />
        );
      })()}
    </>
  );
}

// ── Level 4b: the building's information (eye icon on a building card) ──────

/** Units, occupied, floors and year built, then the project it belongs to. */
function buildingFacts(b: PortfolioBuildingDetail, lang: Lang, occupied?: number): (Fact | null)[] {
  const floors = b.nb_etages || null;
  return [
    { key: 'units', icon: <HomeIcon />, label: plural(b.unit_count, lang, UNIT_FR, UNIT_EN) },
    occupied != null
      ? { key: 'occupied', icon: <UsersIcon />, label: t(lang, `${occupied} occupé${occupied === 1 ? '' : 's'}`, `${occupied} occupied`) }
      : null,
    floors
      ? { key: 'floors', icon: <LayersIcon />, label: t(lang, `${floors} étage${Number(floors) === 1 ? '' : 's'}`, `${floors} floor${Number(floors) === 1 ? '' : 's'}`) }
      : null,
    b.annee_construction
      ? { key: 'built', icon: <CalendarIcon />, label: t(lang, `Construit en ${b.annee_construction}`, `Built in ${b.annee_construction}`) }
      : null,
    { key: 'project', icon: <FolderIcon />, label: projectName(lang, b.nom_unique_projet, b.project_id), to: portfolioPath.project(b.sector_id, b.project_id) },
  ];
}

function BuildingInfoView({ lang }: { lang: Lang }) {
  const buildingId = Number(useParams().buildingId);
  const [editing, setEditing] = useState(false);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'building', buildingId],
    queryFn: () => fetchPortfolioBuilding(buildingId),
  });
  const name = data ? buildingName(lang, data) : '…';
  const infoLabel = t(lang, 'Informations', 'Information');

  return (
    <>
      <Breadcrumbs items={data ? [
        rootCrumb(lang),
        { label: sectorName(lang, data.territoire, data.sector_id), to: portfolioPath.sector(data.sector_id) },
        { label: projectName(lang, data.nom_unique_projet, data.project_id), to: portfolioPath.project(data.sector_id, data.project_id) },
        { label: name, to: portfolioPath.building(buildingId) },
        { label: infoLabel },
      ] : [rootCrumb(lang), { label: '…' }]} lang={lang} />
      <Header
        lang={lang}
        eyebrow={t(lang, 'Bâtiment', 'Building')}
        title={name}
        subtitle={data && buildingPlace(data)}
        facts={data && buildingFacts(data, lang)}
        actions={data && (
          <div className={styles.headerActions}>
            <Link className={styles.btn} to={portfolioPath.building(buildingId)} data-testid="building-units-link">
              {t(lang, 'Voir les logements', 'View units')}
            </Link>
            <EditButton lang={lang} label={t(lang, 'Modifier le bâtiment', 'Edit building')} testId="edit-building"
                        onClick={() => setEditing(true)} />
          </div>
        )}
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && <BuildingInfo building={data} lang={lang} />}
      {editing && (
        <BuildingDialog mode="edit" buildingId={buildingId} lang={lang} onClose={() => setEditing(false)} />
      )}
    </>
  );
}

// ── Level 5: the unit, its lease and tenants (tenant → turnover window) ──────

/** The unit's current lease: months left up front, then the timeline. */
function LeaseCard({ lease, lang }: { lease: PortfolioLease | null | undefined; lang: Lang }) {
  const title = <h2 id="lease-title" className={styles.panelTitle}>{t(lang, 'Bail en cours', 'Current lease')}</h2>;
  if (!lease) {
    return (
      <section className={styles.panel} aria-labelledby="lease-title" data-testid="lease-card">
        {title}
        <p className={styles.cardSub}>{t(lang, 'Aucun bail en cours pour ce logement.', 'No current lease for this unit.')}</p>
      </section>
    );
  }

  const start = lease.debut_bail ? parseDate(lease.debut_bail).getTime() : null;
  const end = lease.fin_bail ? parseDate(lease.fin_bail).getTime() : null;
  const now = Date.now();
  const hasSpan = start != null && end != null && end > start;
  const pct = hasSpan ? Math.min(100, Math.max(0, ((now - start!) / (end! - start!)) * 100)) : null;
  const months = end != null ? Math.round((end - now) / (30.44 * 24 * 3600 * 1000)) : null;
  const endText = fmtDate(lease.fin_bail, lang);

  const headline = months == null
    ? t(lang, 'Fin du bail inconnue', 'Lease end unknown')
    : end! < now
      ? t(lang, 'Bail terminé', 'Lease ended')
      : months <= 0
        ? t(lang, 'Se termine ce mois-ci', 'Ends this month')
        : t(lang, `${months} mois restant${months === 1 ? '' : 's'}`, `${months} month${months === 1 ? '' : 's'} left`);
  const sub = endText && (end! < now
    ? t(lang, `Terminé le ${endText}`, `Ended ${endText}`)
    : t(lang, `Expire le ${endText}`, `Expires ${endText}`));

  return (
    <section className={styles.panel} aria-labelledby="lease-title" data-testid="lease-card">
      {title}
      <div className={styles.leaseSummary}>
        <div>
          <p className={styles.leaseBig} data-testid="lease-remaining">{headline}</p>
          {sub && <p className={styles.leaseSub}>{sub}</p>}
        </div>
        <svg className={styles.leaseIcon} viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" fill="none"
             stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3.5" y="5" width="17" height="15.5" rx="2" /><path d="M3.5 9.5h17M8 3v4M16 3v4" />
          <path d="M8 13h.01M12 13h.01M16 13h.01M8 16.5h.01M12 16.5h.01M16 16.5h.01" strokeWidth="2.4" />
        </svg>
      </div>
      {pct != null && (
        <div className={styles.progressTrack} role="progressbar" aria-valuenow={Math.round(pct)}
             aria-valuemin={0} aria-valuemax={100} aria-label={t(lang, 'Avancement du bail', 'Lease progress')}>
          <div className={styles.progressFill} style={{ width: `${pct}%` }} />
        </div>
      )}
      <dl className={styles.leaseDates}>
        <div><dt>{t(lang, 'Début', 'Start')}</dt><dd>{fmtDate(lease.debut_bail, lang) ?? '—'}</dd></div>
        <div><dt>{t(lang, 'Fin', 'End')}</dt><dd>{endText ?? '—'}</dd></div>
        <div><dt>{t(lang, 'Langue', 'Language')}</dt><dd data-testid="lease-language">{lease.langue_bail ?? '—'}</dd></div>
      </dl>
    </section>
  );
}

type PaintSpec = PortfolioUnitDetail['paint_specs'][number];


/** The building's paint codes, grouped by zone. The units' own zone comes
 *  first: it is what staff need on a unit page. */
function UnitPaint({ unit, lang }: { unit: PortfolioUnitDetail; lang: Lang }) {
  const none = unit.paint_specs.length === 0 && unit.paint_notes.length === 0;
  const groups = new Map<string, PaintSpec[]>();
  for (const p of unit.paint_specs) {
    const zone = p.zone?.trim() || t(lang, 'Autre', 'Other');
    groups.set(zone, [...(groups.get(zone) ?? []), p]);
  }
  const isUnits = (zone: string) => /logement|unit/i.test(zone);
  const zones = [...groups.keys()].sort((a, b) => Number(isUnits(b)) - Number(isUnits(a)));

  return (
    <div className={styles.unitPaint} data-testid="unit-paint">
      <h3 className={styles.panelTitle}>{t(lang, 'Peinture du bâtiment', 'Building paint')}</h3>
      {none ? (
        <p className={styles.cardSub}>{t(lang, 'Aucun code de peinture noté.', 'No paint code on file.')}</p>
      ) : (
        <div className={styles.paintGroups}>
          {unit.paint_notes.length > 0 && (
            <section className={styles.paintGroup}>
              <h4 className={styles.paintZone}>{t(lang, 'Notes', 'Notes')}</h4>
              <ul className={styles.paintList}>
                {unit.paint_notes.map((n) => (
                  <li key={n.label} className={styles.paintItem}>
                    <span className={styles.paintSurface}>{n.label}</span>
                    <span className={styles.paintProduct}><span className={styles.paintCode}>{n.value}</span></span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {zones.map((zone) => (
            <section key={zone} className={styles.paintGroup} data-testid="paint-zone">
              <h4 className={styles.paintZone}>
                {sentenceCase(zone)}
                {isUnits(zone) && <span className={styles.paintHere}>{t(lang, 'Ce logement', 'This unit')}</span>}
              </h4>
              <ul className={styles.paintList}>
                {groups.get(zone)!.map((p) => {
                  const product = [p.product_interior, p.product_exterior].filter(Boolean).join(' / ');
                  return (
                    <li key={p.paint_spec_id} className={styles.paintItem}>
                      <span className={styles.paintSurface}>{p.surface_label || t(lang, 'Peinture', 'Paint')}</span>
                      <span className={styles.paintProduct}>
                        <span className={styles.paintCode}>{product || '—'}</span>
                        {p.manufacturer && <span className={styles.paintMaker}>{p.manufacturer}</span>}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
      <Link className={styles.panelLink} to={`${portfolioPath.buildingInfo(unit.building_id)}#fiche-technique`}>
        {t(lang, 'Modifier sur la fiche du bâtiment', 'Edit on the building sheet')}
      </Link>
    </div>
  );
}

/** « Iryna Demchenko » → « ID ». */
const initials = (name: string | null | undefined) =>
  (name ?? '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join('') || '?';

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
  const [editing, setEditing] = useState(false);

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
        lang={lang}
        eyebrow={t(lang, 'Logement', 'Unit')}
        title={name}
        subtitle={data?.rue}
        facts={data && [
          data.grandeur && { key: 'size', icon: <HomeIcon />, label: data.grandeur },
          { key: 'occupants', icon: <UsersIcon />, label: plural(data.tenants.length, lang, ['occupant', 'occupants'], ['occupant', 'occupants']) },
          { key: 'building', icon: <BuildingIcon />, label: buildingName(lang, data), to: portfolioPath.building(data.building_id) },
          data.unique_unit_number && { key: 'ref', icon: <HashIcon />, label: t(lang, `Réf. ${data.unique_unit_number}`, `Ref. ${data.unique_unit_number}`) },
        ]}
        actionsBelow
        actions={data && (
          <div className={styles.headerActions}>
            <EditButton lang={lang} label={t(lang, 'Modifier le logement', 'Edit unit')} testId="edit-unit"
                        onClick={() => setEditing(true)} />
          </div>
        )}
      />
      {editing && data && (
        <UnitDialog mode="edit" unitId={unitId} initial={unitFields(data)} lang={lang}
                    onClose={() => setEditing(false)} />
      )}
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={2} />
      {data && (
        <div className={styles.unitLayout}>
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
                    <span className={styles.avatar} aria-hidden="true">{initials(tn.nom_complet)}</span>
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
                    <div className={styles.tenantContacts}>
                      {tn.telephone ? (
                        <a className={styles.contact} href={`tel:${tn.telephone_international ?? tn.telephone}`}
                           aria-label={`${t(lang, 'Appeler', 'Call')} ${tn.telephone}`}>
                          <span className={styles.contactIcon}><PhoneIcon /></span>{tn.telephone}
                        </a>
                      ) : (
                        <span className={styles.contactNone}>
                          <span className={styles.contactIcon}><PhoneIcon /></span>{t(lang, 'Aucun téléphone', 'No phone')}
                        </span>
                      )}
                      {tn.courriel ? (
                        <a className={styles.contact} href={`mailto:${tn.courriel}`}
                           aria-label={`${t(lang, 'Écrire à', 'Email')} ${tn.courriel}`}>
                          <span className={styles.contactIcon}><MailIcon /></span>{tn.courriel}
                        </a>
                      ) : (
                        <span className={styles.contactNone}>
                          <span className={styles.contactIcon}><MailIcon /></span>{t(lang, 'Aucun courriel', 'No email')}
                        </span>
                      )}
                    </div>
                    <svg className={styles.rowArrow} viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"
                         fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M8 5l5 5-5 5" />
                    </svg>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Lease and the building's paint codes: side by side when there is room. */}
          <div className={styles.leaseGrid}>
            <LeaseCard lease={lease} lang={lang} />
            <section className={styles.panel} aria-label={t(lang, 'Peinture du bâtiment', 'Building paint')}>
              <UnitPaint unit={data} lang={lang} />
            </section>
          </div>
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
        <Route path="logements" element={<UnitsListView lang={lang} />} />
        <Route path="secteurs/:sectorId" element={<SectorView lang={lang} />} />
        <Route path="secteurs/:sectorId/projets/:projectId" element={<ProjectView lang={lang} />} />
        <Route path="batiments/:buildingId" element={<BuildingView lang={lang} />} />
        <Route path="batiments/:buildingId/informations" element={<BuildingInfoView lang={lang} />} />
        <Route path="unites/:unitId" element={<UnitView lang={lang} />} />
        <Route path="*" element={<Navigate to="/portfolio" replace />} />
      </Routes>
    </div>
  );
}
