import { Fragment, useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, Navigate, Route, Routes, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  fetchPortfolioBuilding,
  fetchPortfolioProject,
  fetchPortfolioSector,
  fetchPortfolioSectors,
  fetchPortfolioUnit,
} from '../../api/client';
import type { PortfolioLease, PortfolioUnitDetail } from '../../api/client';
import type { PortfolioUnitSummary } from '../../api/schema.d.ts';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import BuildingInfo from './BuildingInfo';
import { BuildingDialog, ProjectDialog, UnitDialog } from './forms';
import { EyeIcon, PencilIcon, PlusIcon } from './icons';
import PortfolioSearch from './PortfolioSearch';
import TurnoverDialog, { capaciteLabel } from './TurnoverDialog';
import UnitsListView, { unitsPath } from './UnitsList';
import { fmtDate, matches, parseDate, plural } from './format';
import {
  Arrow, BUILDING_EN, BUILDING_FR, Breadcrumbs, Empty, Header, LevelState, PROJECT_EN, PROJECT_FR,
  SearchBox, UNIT_EN, UNIT_FR, buildingName, buildingPlace, portfolioPath, projectName, rootCrumb,
  sectorName, unitName,
} from './shared';
import styles from './Portfolio.module.css';

export { portfolioPath } from './shared';

/** A project / building card: the title links to it; eye and pencil sit top right.
 *  `viewTo` sends the eye somewhere else (a building's information page). */
function ItemCard({ to, viewTo, viewLabel, title, testId, lang, onEdit, children }: {
  to: string; viewTo?: string; viewLabel?: string; title: string; testId: string; lang: Lang;
  onEdit: () => void; children: React.ReactNode;
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
      <h2 className={styles.cardTitle}><Link to={to} className={styles.cardLink}>{title}</Link></h2>
      {children}
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

function EditButton({ label, onClick, testId }: { label: string; onClick: () => void; testId?: string }) {
  return (
    <button type="button" className={`${styles.btn} ${styles.btnIcon}`} onClick={onClick} data-testid={testId}
            aria-label={label} title={label}>
      <PencilIcon /> <span className={styles.btnText}>{label}</span>
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
        search={
          <div className={styles.headerTools}>
            <PortfolioSearch lang={lang} />
            <Link className={styles.btn} to={unitsPath()} data-testid="all-units-link">
              {t(lang, 'Tous les logements', 'All units')}
            </Link>
          </div>
        }
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
            <Link className={`${styles.totalsNote} ${styles.vacantLink}`} to={unitsPath({ occupation: 'vacant' })}
                  data-testid="vacant-link">
              {t(lang, `${n(units - occupied)} vacants`, `${n(units - occupied)} vacant`)}
            </Link>
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
  const [dialog, setDialog] = useState<{ edit: number } | 'new' | null>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'sector', sectorId],
    queryFn: () => fetchPortfolioSector(sectorId),
  });
  const editing = dialog && dialog !== 'new' ? data?.projects.find((p) => p.project_id === dialog.edit) : null;
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
        search={
          <div className={styles.headerTools}>
            {data && data.projects.length > 6 && (
              <SearchBox value={q} onChange={setQ}
                         placeholder={t(lang, 'Rechercher un projet…', 'Search projects…')} />
            )}
            <div className={styles.headerActions}>
              <Link className={styles.btn} to={unitsPath({ secteur: sectorId })}>
                {t(lang, 'Voir les logements', 'View units')}
              </Link>
              <AddButton label={t(lang, 'Projet', 'Project')} onClick={() => setDialog('new')} testId="add-project" />
            </div>
          </div>
        }
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} />
      {data && projects.length === 0 && (
        <Empty>{q ? t(lang, 'Aucun projet ne correspond.', 'No matching project.')
                  : t(lang, 'Aucun projet dans ce secteur.', 'No project in this sector.')}</Empty>
      )}
      {projects.length > 0 && (
        <div className={styles.grid}>
          {projects.map((p) => (
            <ItemCard key={p.project_id} to={portfolioPath.project(sectorId, p.project_id)}
                      title={projectName(lang, p.nom_unique_projet, p.project_id)} testId="project-card"
                      lang={lang} onEdit={() => setDialog({ edit: p.project_id })}>
              {p.adresse_quickbooks && <p className={styles.cardSub}>{p.adresse_quickbooks}</p>}
              <div className={styles.cardMeta}>
                <span><strong>{p.building_count}</strong> {p.building_count === 1 ? t(lang, 'bâtiment', 'building') : t(lang, 'bâtiments', 'buildings')}</span>
                {p.accounting_project_number && <span>{t(lang, 'No', 'No.')} {p.accounting_project_number}</span>}
              </div>
            </ItemCard>
          ))}
        </div>
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
        search={
          <div className={styles.headerActions}>
            <Link className={styles.btn} to={unitsPath({ secteur: sectorId, projet: projectId })}>
              {t(lang, 'Voir les logements', 'View units')}
            </Link>
            {data && <EditButton label={t(lang, 'Modifier le projet', 'Edit project')} testId="edit-project"
                                 onClick={() => setDialog('project')} />}
            <AddButton label={t(lang, 'Bâtiment', 'Building')} onClick={() => setDialog('new')} testId="add-building" />
          </div>
        }
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && data.buildings.length === 0 && (
        <Empty>{t(lang, 'Aucun bâtiment dans ce projet.', 'No building in this project.')}</Empty>
      )}
      {data && data.buildings.length > 0 && (
        <div className={styles.grid}>
          {data.buildings.map((b) => (
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
        search={data && (
          <div className={`${styles.headerTools} ${styles.headerToolsWide}`}>
            {data.units.length > 8 && (
              <SearchBox value={q} onChange={setQ}
                         placeholder={t(lang, 'Logement, locataire, grandeur…', 'Unit, tenant, size…')} />
            )}
            <div className={styles.headerActions}>
              <Link className={`${styles.btn} ${styles.btnIcon}`} to={portfolioPath.buildingInfo(buildingId)}
                    data-testid="building-info-link" title={t(lang, 'Informations du bâtiment', 'Building information')}>
                <EyeIcon /> <span className={styles.btnText}>{t(lang, 'Informations du bâtiment', 'Building information')}</span>
              </Link>
              <EditButton label={t(lang, 'Modifier le bâtiment', 'Edit building')} testId="edit-building"
                          onClick={() => setDialog('building')} />
              <AddButton label={t(lang, 'Logement', 'Unit')} onClick={() => setDialog('new')} testId="add-unit" />
            </div>
          </div>
        )}
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && data.units.length > 0 && (
        <div className={styles.unitTools}>
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
                <th className={styles.hideNarrow}>{t(lang, 'Adresse', 'Address')}</th>
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
                  <td className={`${styles.nowrap} ${styles.hideNarrow}`}>{u.rue ?? '—'}</td>
                  <td className={styles.nowrap}>{u.grandeur ?? '—'}</td>
                  <td>{u.tenant_names.length > 0
                    ? u.tenant_names.join(', ')
                    : <span className={styles.vacant}>{t(lang, 'Aucun locataire', 'No tenant')}</span>}</td>
                  <td className={`${styles.num} ${styles.fit} ${styles.hideNarrow}`}>{u.occupant_count}</td>
                  <td className={styles.nowrap}>{u.lease_statut ?? (u.occupant_count > 0 ? t(lang, 'En cours', 'Current') : '—')}</td>
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
        eyebrow={t(lang, 'Bâtiment', 'Building')}
        title={name}
        subtitle={data && buildingPlace(data)}
        chips={data ? [
          plural(data.unit_count, lang, UNIT_FR, UNIT_EN),
          data.nb_etages ? t(lang, `${data.nb_etages} étages`, `${data.nb_etages} floors`) : null,
          data.annee_construction ? t(lang, `Construit en ${data.annee_construction}`, `Built ${data.annee_construction}`) : null,
        ] : []}
        search={data && (
          <div className={styles.headerActions}>
            <Link className={styles.btn} to={portfolioPath.building(buildingId)} data-testid="building-units-link">
              {t(lang, 'Voir les logements', 'View units')}
            </Link>
            <EditButton label={t(lang, 'Modifier le bâtiment', 'Edit building')} testId="edit-building"
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

/** The building's paint codes — what staff most often need for a unit. */
function UnitPaint({ unit, lang }: { unit: PortfolioUnitDetail; lang: Lang }) {
  const none = unit.paint_specs.length === 0 && unit.paint_notes.length === 0;
  return (
    <div className={styles.unitPaint} data-testid="unit-paint">
      <h3 className={styles.panelTitle}>{t(lang, 'Peinture du bâtiment', 'Building paint')}</h3>
      {none ? (
        <p className={styles.cardSub}>{t(lang, 'Aucun code de peinture noté.', 'No paint code on file.')}</p>
      ) : (
        <dl className={styles.facts}>
          {unit.paint_notes.map((n) => (
            <Fragment key={n.label}><dt>{n.label}</dt><dd>{n.value}</dd></Fragment>
          ))}
          {unit.paint_specs.map((p) => (
            <Fragment key={p.paint_spec_id}>
              <dt>{[p.zone, p.surface_label].filter(Boolean).join(' · ') || t(lang, 'Peinture', 'Paint')}</dt>
              <dd>{[p.product_interior, p.product_exterior, p.manufacturer].filter(Boolean).join(' — ') || '—'}</dd>
            </Fragment>
          ))}
        </dl>
      )}
      <Link className={styles.panelLink} to={`${portfolioPath.buildingInfo(unit.building_id)}#fiche-technique`}>
        {t(lang, 'Modifier sur la fiche du bâtiment', 'Edit on the building sheet')}
      </Link>
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
        eyebrow={t(lang, 'Logement', 'Unit')}
        title={name}
        subtitle={data?.rue}
        chips={data ? [
          data.grandeur,
          plural(data.tenants.length, lang, ['occupant', 'occupants'], ['occupant', 'occupants']),
          data.unique_unit_number,
        ] : []}
        search={data && (
          <EditButton label={t(lang, 'Modifier le logement', 'Edit unit')} testId="edit-unit"
                      onClick={() => setEditing(true)} />
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
            <UnitPaint unit={data} lang={lang} />
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
