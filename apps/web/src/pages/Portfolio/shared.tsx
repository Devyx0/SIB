import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { portfolioPath } from './paths';
import PortfolioSearch from './PortfolioSearch';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './Portfolio.module.css';

export { portfolioPath } from './paths';

export const PROJECT_FR: [string, string] = ['projet', 'projets'];
export const PROJECT_EN: [string, string] = ['project', 'projects'];
export const BUILDING_FR: [string, string] = ['bâtiment', 'bâtiments'];
export const BUILDING_EN: [string, string] = ['building', 'buildings'];
export const UNIT_FR: [string, string] = ['logement', 'logements'];
export const UNIT_EN: [string, string] = ['unit', 'units'];

const PHONE = '(max-width: 639px)';

/** True on phone widths (same breakpoint as the CSS). Some buttons sit in a
 *  different place there, so the page renders them in one spot or the other. */
export function useIsPhone() {
  const query = typeof window !== 'undefined' ? window.matchMedia?.(PHONE) : undefined;
  const [phone, setPhone] = useState(() => query?.matches ?? false);
  useEffect(() => {
    if (!query) return;
    const on = () => setPhone(query.matches);
    on();
    query.addEventListener?.('change', on);
    return () => query.removeEventListener?.('change', on);
  }, [query]);
  return phone;
}

export type Crumb = { label: string; to?: string };

/** Full trail on wider screens. On a phone it folds into « ‹ parent » (one
 *  level up) and a home button (the sectors page) — the trail is too long
 *  to read on a narrow screen. */
export function Breadcrumbs({ items, lang, action }: {
  items: Crumb[]; lang: Lang;
  /** Phone: a button at the right end of the back / home row (the page's « + »). */
  action?: React.ReactNode;
}) {
  const parent = [...items.slice(0, -1)].reverse().find((c) => c.to);
  const home = items[0]?.to;
  return (
    <nav aria-label={t(lang, "Fil d'Ariane", 'Breadcrumb')}>
      {parent?.to && (
        <div className={styles.crumbsCompact} data-testid="crumbs-compact">
          <Link to={parent.to} className={styles.backLink} data-testid="crumbs-back"
                aria-label={t(lang, `Retour : ${parent.label}`, `Back: ${parent.label}`)}>
            <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none"
                 stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12.5 4.5L7 10l5.5 5.5" />
            </svg>
            <span className={styles.backLabel}>{parent.label}</span>
          </Link>
          {home && home !== parent.to && (
            <Link to={home} className={styles.homeLink} data-testid="crumbs-home"
                  aria-label={t(lang, 'Accueil du portfolio (secteurs)', 'Portfolio home (sectors)')}
                  title={t(lang, 'Accueil du portfolio', 'Portfolio home')}>
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none"
                   stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10" /><path d="M10 20v-6h4v6" />
              </svg>
            </Link>
          )}
          {action && <div className={styles.crumbsAction}>{action}</div>}
        </div>
      )}
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

/** One fact under a heading: an icon, a short text, optionally a link (the parent level). */
export type Fact = { icon: React.ReactNode; label: React.ReactNode; to?: string; key: string };

/** The facts row under a heading: « ⌂ 4 1/2 | 👥 2 occupants | 🏢 117 Sainte-Anne ». */
function Facts({ facts }: { facts: Fact[] }) {
  return (
    <ul className={styles.levelFacts} data-testid="level-summary">
      {facts.map((f) => (
        <li key={f.key} className={styles.factItem} data-testid={`fact-${f.key}`}>
          <span className={styles.factIcon}>{f.icon}</span>
          {f.to ? <Link to={f.to} className={styles.factLink}>{f.label}</Link> : <span>{f.label}</span>}
        </li>
      ))}
    </ul>
  );
}

/** Eyebrow above; title and the page's buttons share the next row (title left,
 *  actions far right). Subtitle / facts stay under the title so they never
 *  push the buttons down. `globalSearch` (Portfolio home) puts the
 *  portfolio-wide search on that same row, left of the buttons. */
export function Header({ lang, eyebrow, title, subtitle, chips, facts, actions, globalSearch = false, actionsBelow = false }: {
  lang: Lang;
  eyebrow: string;
  title: string;
  subtitle?: string | null;
  chips?: (string | null)[];
  /** What the level holds, as icon facts under the title. */
  facts?: (Fact | null | false | '' | undefined)[] | null | false;
  actions?: React.ReactNode;
  globalSearch?: boolean;
  /** Desktop: the buttons sit under the heading instead of on the right. */
  actionsBelow?: boolean;
}) {
  return (
    <header className={`${styles.header} ${actionsBelow ? styles.headerBelow : ''} ${globalSearch ? styles.headerHome : ''}`}>
      <p className={styles.eyebrow}>{eyebrow}</p>
      <div className={styles.headerTitleRow}>
        <h1 className={styles.title}>{title}</h1>
        {(globalSearch || actions) && (
          <div className={`${styles.headerSide} ${globalSearch ? styles.headerSideSearch : ''}`}>
            {globalSearch && <div role="search" className={styles.headerSearch}><PortfolioSearch lang={lang} /></div>}
            {actions}
          </div>
        )}
      </div>
      {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
      {facts && facts.some(Boolean) && <Facts facts={facts.filter(Boolean) as Fact[]} />}
      {chips && chips.some(Boolean) && (
        <div className={styles.chips}>
          {chips.filter(Boolean).map((c) => <span key={c} className={styles.chip}>{c}</span>)}
        </div>
      )}
    </header>
  );
}

export function SearchBox({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder: string;
}) {
  // Searches the list right below it (projects, buildings or units).
  return (
    <span className={styles.filterBox} role="search">
      <svg className={styles.filterIcon} viewBox="0 0 20 20" width="15" height="15" aria-hidden="true"
           fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="9" cy="9" r="6" /><path d="M13.5 13.5L17 17" />
      </svg>
      <input type="search" className={styles.search} value={value} placeholder={placeholder}
             aria-label={placeholder} data-testid="portfolio-search"
             onChange={(e) => onChange(e.target.value)} />
    </span>
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

/** A unit's tenants, one per line, lettered A, B, C… when there are several
 *  (one tenant needs no letter). */
export function TenantNames({ names }: { names: string[] }) {
  if (names.length === 1) return <>{names[0]}</>;
  return (
    <ul className={styles.tenantNames} data-testid="tenant-names">
      {names.map((name, i) => (
        <li key={`${i}-${name}`}>
          <span className={styles.tenantLetter} aria-hidden="true">{String.fromCharCode(65 + (i % 26))}</span>
          {name}
        </li>
      ))}
    </ul>
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

