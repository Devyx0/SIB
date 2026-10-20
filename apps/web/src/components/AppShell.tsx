import { useEffect, useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import type { MeResponse } from '../api/schema.d.ts';
import type { Lang } from '../i18n';
import { roleLabel, t } from '../i18n';
import AlertBell from './AlertBell';
import BrandMark from './BrandMark';
import styles from './AppShell.module.css';

interface Props {
  lang: Lang;
  onToggleLang: () => void;
  me: MeResponse | null;
  onSignOut: () => void;
  children: React.ReactNode;
}

function SoonChip({ lang }: { lang: Lang }) {
  return <span className={styles.soonChip}>{t(lang, 'Bientôt', 'Soon')}</span>;
}

export default function AppShell({ lang, onToggleLang, me, onSignOut, children }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const navItemClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? `${styles.navItem} ${styles.navActive}` : styles.navItem;

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  return (
    <div className={styles.shell}>
      <button
        className={styles.burger}
        data-testid="burger"
        aria-label={t(lang, 'Ouvrir le menu', 'Open menu')}
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((o) => !o)}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M4 7h16M4 12h16M4 17h16" />
        </svg>
      </button>
      {menuOpen && <div className={styles.overlay} onClick={() => setMenuOpen(false)} />}

      <aside className={`${styles.sidebar} ${menuOpen ? styles.sidebarOpen : ''}`}>
        <div className={styles.brand}>
          <BrandMark product="Maintenance" />
        </div>

        <nav className={styles.nav} onClick={() => setMenuOpen(false)}>
          <NavLink to="/board" data-testid="nav-board" className={navItemClass}>
            {t(lang, 'Répartition', 'Dispatch')}
          </NavLink>
          <Link to="/board?nouvel-appel=1" data-testid="nav-nouvel-appel" className={styles.navItem}>
            <span className={styles.plus} aria-hidden="true">+</span>
            {t(lang, 'Nouvel appel', 'New call')}
          </Link>
          <NavLink to="/dossiers" data-testid="nav-dossiers" className={navItemClass}>
            {t(lang, 'Dossiers', 'Cases')}
          </NavLink>
          <NavLink to="/portfolio" data-testid="nav-portfolio" className={navItemClass}>
            {t(lang, 'Portfolio', 'Portfolio')}
          </NavLink>
          <span
            className={`${styles.navItem} ${styles.navDisabled}`}
            data-testid="nav-apres-heures"
            aria-disabled="true"
          >
            {t(lang, 'Après les heures', 'After hours')} <SoonChip lang={lang} />
          </span>

          <div className={styles.navGroup}>{t(lang, "Vue d'ensemble", 'Overview')}</div>
          <NavLink to="/tableau-de-bord" data-testid="nav-tableau-bord" className={navItemClass}>
            {t(lang, 'Tableau de bord', 'Dashboard')}
          </NavLink>
          <NavLink to="/utilisation" data-testid="nav-utilisation" className={navItemClass}>
            {t(lang, 'Utilisation', 'Utilization')}
          </NavLink>
        </nav>

        <div className={styles.bottom}>
          {me && (
            <div className={styles.userInfo}>
              <span className={styles.userName}>{me.nom_employe}</span>
              <span className={styles.userRole}>{roleLabel(lang, me.roles[0] ?? '')}</span>
            </div>
          )}

          <div className={styles.bottomRow}>
            <AlertBell lang={lang} />
            <button className={styles.langBtn} onClick={onToggleLang} aria-label={lang === 'fr' ? 'Switch to English' : 'Passer en français'}>
              {t(lang, 'EN', 'FR')}
            </button>
            <button className={styles.signOutBtn} onClick={onSignOut}>
              {t(lang, 'Déconnexion', 'Sign out')}
            </button>
          </div>
        </div>
      </aside>

      <main className={styles.main}>{children}</main>
    </div>
  );
}
