import { lazy, Suspense, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { fetchPortfolioMap } from '../../api/client';
import type { PortfolioMapBuilding } from '../../api/client';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import { BuildingIcon, FolderIcon, MapPinIcon, PieIcon } from './icons';
import { Breadcrumbs, Header, LevelState, buildingName, buildingPlace, portfolioPath, projectName, rootCrumb, sectorName } from './shared';
import type { MapBubble, MapPin } from './PortfolioMap';
import styles from './MapView.module.css';
import portfolio from './Portfolio.module.css';

// MapLibre is large: it only loads when someone opens the map.
const PortfolioMap = lazy(() => import('./PortfolioMap'));

/** Used when the API gives a sector no colour. */
const PALETTE = ['#123d72', '#2f8f83', '#c9792b', '#7a5cc4', '#b0476a', '#4a8c3a', '#5b7a99', '#a8872e'];
const HEX = /^#[0-9a-f]{6}$/i;

const pct = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0);

type SectorGroup = {
  id: number; name: string; color: string; buildings: PortfolioMapBuilding[]; lat: number; lng: number;
};

export function mapPath(scope: { secteur?: number; projet?: number } = {}): string {
  const q = new URLSearchParams();
  if (scope.secteur != null) q.set('secteur', String(scope.secteur));
  if (scope.projet != null) q.set('projet', String(scope.projet));
  const s = q.toString();
  return `${portfolioPath.root()}/carte${s ? `?${s}` : ''}`;
}

export default function MapView({ lang }: { lang: Lang }) {
  const [params, setParams] = useSearchParams();
  const sectorId = Number(params.get('secteur')) || null;
  const projectId = Number(params.get('projet')) || null;
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [q, setQ] = useState('');
  const n = (v: number) => v.toLocaleString(lang === 'fr' ? 'fr-CA' : 'en-CA');

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', 'map'],
    queryFn: fetchPortfolioMap,
    staleTime: 5 * 60_000,
  });

  const sectors = useMemo<SectorGroup[]>(() => {
    const by = new Map<number, PortfolioMapBuilding[]>();
    for (const b of data?.buildings ?? []) by.set(b.sector_id, [...(by.get(b.sector_id) ?? []), b]);
    return [...by.entries()]
      .map(([id, buildings], i) => ({
        id,
        name: sectorName(lang, buildings[0].territoire, id),
        color: HEX.test(buildings[0].color_code ?? '') ? buildings[0].color_code! : PALETTE[i % PALETTE.length],
        buildings,
        lat: buildings.reduce((s, b) => s + b.latitude, 0) / buildings.length,
        lng: buildings.reduce((s, b) => s + b.longitude, 0) / buildings.length,
      }))
      .sort((a, b) => a.name.localeCompare(b.name, lang === 'fr' ? 'fr-CA' : 'en-CA'));
  }, [data, lang]);

  const sector = sectors.find((s) => s.id === sectorId) ?? null;
  const scoped = useMemo(() => {
    const pool = sector ? sector.buildings : (data?.buildings ?? []);
    return projectId != null ? pool.filter((b) => b.project_id === projectId) : pool;
  }, [data, sector, projectId]);
  const colorOf = (id: number) => sectors.find((s) => s.id === id)?.color ?? PALETTE[0];

  const pins = useMemo<MapPin[]>(() => scoped.map((b) => ({
    id: b.building_id, lat: b.latitude, lng: b.longitude, sectorId: b.sector_id,
    color: sectors.find((s) => s.id === b.sector_id)?.color ?? PALETTE[0],
    label: buildingName(lang, b),
  })), [scoped, sectors, lang]);
  const bubbles = useMemo<MapBubble[]>(() => (sector ? [] : sectors.map((s) => ({
    id: s.id, lat: s.lat, lng: s.lng, color: s.color, label: s.name, count: s.buildings.length,
  }))), [sector, sectors]);

  const setScope = (next: { secteur?: number | null; projet?: number | null }) => {
    const p = new URLSearchParams();
    if (next.secteur != null) p.set('secteur', String(next.secteur));
    if (next.projet != null) p.set('projet', String(next.projet));
    setSelectedId(null);
    setQ('');
    setParams(p);
  };

  const projects = useMemo(() => {
    const by = new Map<number, { id: number; name: string; buildings: PortfolioMapBuilding[] }>();
    for (const b of sector?.buildings ?? []) {
      const g = by.get(b.project_id) ?? { id: b.project_id, name: projectName(lang, b.nom_unique_projet, b.project_id), buildings: [] };
      g.buildings.push(b);
      by.set(b.project_id, g);
    }
    return [...by.values()].sort((a, b) => a.name.localeCompare(b.name, lang === 'fr' ? 'fr-CA' : 'en-CA', { numeric: true }));
  }, [sector, lang]);
  const project = projects.find((p) => p.id === projectId) ?? null;

  const term = q.trim().toLowerCase();
  const found = term
    ? scoped.filter((b) => [b.adresse, b.web_building_name, b.ville, b.nom_unique_projet, b.code_postal]
        .some((v) => v?.toLowerCase().includes(term))).slice(0, 60)
    : [];

  const selected = scoped.find((b) => b.building_id === selectedId) ?? null;
  const listBack = project ? portfolioPath.project(project.buildings[0].sector_id, project.id)
    : sector ? portfolioPath.sector(sector.id) : portfolioPath.root();
  const total = data?.buildings.length ?? 0;

  const buildingRow = (b: PortfolioMapBuilding) => (
    <li key={b.building_id}>
      <button type="button" className={`${styles.row} ${b.building_id === selectedId ? styles.rowActive : ''}`}
              onClick={() => setSelectedId(b.building_id)} data-testid="map-building-row">
        <span className={styles.rowDot} style={{ background: colorOf(b.sector_id) }} />
        <span className={styles.rowMain}>
          <span className={styles.rowName}>{buildingName(lang, b)}</span>
          <span className={styles.rowSub}>{projectName(lang, b.nom_unique_projet, b.project_id)}{b.ville ? ` · ${b.ville}` : ''}</span>
        </span>
        <span className={styles.rowCount}>{pct(b.occupied_unit_count, b.unit_count)} %</span>
      </button>
    </li>
  );

  return (
    <>
      <Breadcrumbs items={[rootCrumb(lang), { label: t(lang, 'Carte', 'Map') }]} lang={lang} />
      <Header
        lang={lang}
        eyebrow={t(lang, 'Parc immobilier', 'Property portfolio')}
        title={t(lang, 'Carte', 'Map')}
        facts={data && total > 0 && [
          { key: 'buildings', icon: <BuildingIcon />, label: t(lang, `${n(scoped.length)} bâtiment${scoped.length === 1 ? '' : 's'}`, `${n(scoped.length)} building${scoped.length === 1 ? '' : 's'}`) },
          sector && { key: 'sector', icon: <MapPinIcon />, label: sector.name },
          project && { key: 'project', icon: <FolderIcon />, label: project.name },
        ]}
        actions={
          <div className={portfolio.headerActions}>
            <Link className={portfolio.btn} to={listBack} data-testid="map-list-link">{t(lang, 'Vue liste', 'List view')}</Link>
          </div>
        }
      />
      <LevelState isLoading={isLoading} error={error} lang={lang} onRetry={refetch} rows={3} />
      {data && total === 0 && (
        <div className={styles.empty} data-testid="map-empty">
          <MapPinIcon size={28} />
          <h2>{t(lang, 'Aucune position à afficher', 'No locations to show yet')}</h2>
          <p>{t(lang, 'La carte apparaîtra dès que les coordonnées des bâtiments seront enregistrées.',
                      'The map will appear once building coordinates have been recorded.')}</p>
          <Link className={portfolio.btn} to={portfolioPath.root()}>{t(lang, 'Retour au portfolio', 'Back to portfolio')}</Link>
        </div>
      )}
      {data && total > 0 && (
        <div className={styles.layout}>
          <aside className={styles.panel} aria-label={t(lang, 'Parcourir la carte', 'Browse the map')}>
            <div className={styles.panelHead}>
              {sector ? (
                <button type="button" className={styles.back} data-testid="map-back"
                        onClick={() => (project ? setScope({ secteur: sector.id }) : setScope({}))}>
                  <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor"
                       strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5L7 10l5.5 5.5" /></svg>
                  {project ? sector.name : t(lang, 'Tous les secteurs', 'All sectors')}
                </button>
              ) : <span className={styles.panelTitle}>{t(lang, 'Secteurs', 'Sectors')}</span>}
              {sector && <h2 className={styles.panelTitle}>{project ? project.name : sector.name}</h2>}
              <input className={styles.search} type="search" value={q} onChange={(e) => setQ(e.target.value)}
                     placeholder={t(lang, 'Rechercher une adresse, un projet…', 'Search address, project…')}
                     aria-label={t(lang, 'Rechercher sur la carte', 'Search the map')} />
            </div>

            <ul className={styles.list} data-testid="map-list">
              {term ? (
                found.length > 0 ? found.map(buildingRow)
                  : <li className={styles.none}>{t(lang, 'Aucun bâtiment ne correspond.', 'No matching building.')}</li>
              ) : project ? project.buildings.map(buildingRow)
              : sector ? projects.map((p) => (
                <li key={p.id}>
                  <button type="button" className={styles.row} onClick={() => setScope({ secteur: sector.id, projet: p.id })}
                          data-testid="map-project-row">
                    <span className={styles.rowIcon}><FolderIcon size={16} /></span>
                    <span className={styles.rowMain}><span className={styles.rowName}>{p.name}</span></span>
                    <span className={styles.rowCount}>{p.buildings.length}</span>
                  </button>
                </li>
              )) : sectors.map((s) => (
                <li key={s.id}>
                  <button type="button" className={styles.row} onClick={() => setScope({ secteur: s.id })} data-testid="map-sector-row">
                    <span className={styles.rowDot} style={{ background: s.color }} />
                    <span className={styles.rowMain}>
                      <span className={styles.rowName}>{s.name}</span>
                      <span className={styles.rowSub}>
                        {t(lang, `${n(new Set(s.buildings.map((b) => b.project_id)).size)} projets`, `${n(new Set(s.buildings.map((b) => b.project_id)).size)} projects`)}
                      </span>
                    </span>
                    <span className={styles.rowCount}>{s.buildings.length}</span>
                  </button>
                </li>
              ))}
            </ul>
            {data.missing_coordinates > 0 && (
              <p className={styles.note} data-testid="map-missing">
                {t(lang, `${n(data.missing_coordinates)} bâtiment${data.missing_coordinates === 1 ? '' : 's'} sans position`,
                         `${n(data.missing_coordinates)} building${data.missing_coordinates === 1 ? '' : 's'} without a location`)}
              </p>
            )}
          </aside>

          <div className={styles.mapWrap}>
            <Suspense fallback={<div className={styles.mapLoading}>{t(lang, 'Chargement de la carte…', 'Loading the map…')}</div>}>
              <PortfolioMap pins={pins} bubbles={bubbles} selectedId={selected?.building_id ?? null}
                            onSelectBuilding={setSelectedId}
                            onSelectSector={(id) => setScope({ secteur: id })}
                            fitKey={`${sectorId ?? ''}-${projectId ?? ''}`} />
            </Suspense>

            {selected && (
              <div className={styles.card} data-testid="map-card">
                <button type="button" className={styles.cardClose} onClick={() => setSelectedId(null)}
                        aria-label={t(lang, 'Fermer', 'Close')}>×</button>
                <span className={styles.cardSector}>
                  <span className={styles.rowDot} style={{ background: colorOf(selected.sector_id) }} />
                  {sectorName(lang, selected.territoire, selected.sector_id)}
                </span>
                <h3 className={styles.cardTitle}>{buildingName(lang, selected)}</h3>
                <p className={styles.cardSub}>{buildingPlace(selected) || '—'}</p>
                <p className={styles.cardProject}><FolderIcon size={14} /> {projectName(lang, selected.nom_unique_projet, selected.project_id)}</p>
                <div className={styles.cardOcc}>
                  <span className={styles.cardOccLabel}><PieIcon size={14} />
                    {t(lang, `${pct(selected.occupied_unit_count, selected.unit_count)} % occupé`, `${pct(selected.occupied_unit_count, selected.unit_count)} % occupied`)}
                  </span>
                  <span className={styles.cardOccUnits}>
                    {t(lang, `${n(selected.occupied_unit_count)} / ${n(selected.unit_count)} logements`, `${n(selected.occupied_unit_count)} / ${n(selected.unit_count)} units`)}
                  </span>
                </div>
                <span className={styles.bar} aria-hidden="true">
                  <span style={{ width: `${pct(selected.occupied_unit_count, selected.unit_count)}%` }} />
                </span>
                <Link className={`${portfolio.btn} ${portfolio.btnPrimary} ${styles.cardOpen}`}
                      to={portfolioPath.building(selected.building_id)} data-testid="map-open-building">
                  {t(lang, 'Ouvrir le bâtiment', 'Open building')}
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
