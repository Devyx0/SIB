import { Link } from 'react-router-dom';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
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

export const PROJECT_FR: [string, string] = ['projet', 'projets'];
export const PROJECT_EN: [string, string] = ['project', 'projects'];
export const BUILDING_FR: [string, string] = ['bâtiment', 'bâtiments'];
export const BUILDING_EN: [string, string] = ['building', 'buildings'];
export const UNIT_FR: [string, string] = ['logement', 'logements'];
export const UNIT_EN: [string, string] = ['unit', 'units'];

export type Crumb = { label: string; to?: string };

export function Breadcrumbs({ items, lang }: { items: Crumb[]; lang: Lang }) {
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

export function Header({ eyebrow, title, subtitle, chips, search }: {
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

export function SearchBox({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder: string;
}) {
  return (
    <input type="search" className={styles.search} value={value} placeholder={placeholder}
           aria-label={placeholder} data-testid="portfolio-search"
           onChange={(e) => onChange(e.target.value)} />
  );
}

/** Loading / error / not-found for a level; renders children once data is there. */
export function LevelState({ isLoading, error, lang, onRetry, rows = 6 }: {
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

export function Arrow() {
  return (
    <svg className={styles.arrow} viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"
         fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 5l5 5-5 5" />
    </svg>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className={styles.empty}>{children}</p>;
}

export const rootCrumb = (lang: Lang): Crumb => ({ label: t(lang, 'Portfolio', 'Portfolio'), to: portfolioPath.root() });
export const sectorName = (lang: Lang, name: string | null | undefined, id: number) =>
  name ?? t(lang, `Secteur ${id}`, `Sector ${id}`);
export const projectName = (lang: Lang, name: string | null | undefined, id: number) =>
  name ?? t(lang, `Projet ${id}`, `Project ${id}`);
// Address first: the web name often repeats the project name for every building.
export const buildingName = (lang: Lang, b: { web_building_name?: string | null; adresse?: string | null; building_adresse?: string | null; building_id: number }) =>
  b.adresse ?? b.building_adresse ?? b.web_building_name ?? t(lang, `Bâtiment ${b.building_id}`, `Building ${b.building_id}`);
export const buildingPlace = (b: { web_building_name: string | null; ville: string | null; code_postal: string | null }) =>
  [b.web_building_name, b.ville, b.code_postal].filter(Boolean).join(' · ');
export const unitName = (lang: Lang, u: { numero_appartement: string | null; unit_id: number }) =>
  u.numero_appartement ? t(lang, `Logement ${u.numero_appartement}`, `Unit ${u.numero_appartement}`)
    : t(lang, `Logement #${u.unit_id}`, `Unit #${u.unit_id}`);

