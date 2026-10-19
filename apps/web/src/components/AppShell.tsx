import { useEffect, useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import type { MeResponse } from '../api/schema.d.ts';
import type { Lang } from '../i18n';
import { roleLabel, t } from '../i18n';
import styles from './AppShell.module.css';

// The mockup is state-routed (no deep links — it only reads a ?theme= param),
// so both overview items open its root; it lands on its default screen.
const MOCKUP_URL = 'https://sib-maintenance-mockups.vercel.app';

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
      >☰</button>
      {menuOpen && <div className={styles.overlay} onClick={() => setMenuOpen(false)} />}

      <aside className={`${styles.sidebar} ${menuOpen ? styles.sidebarOpen : ''}`}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>SIB</span>
          <span className={styles.brandName}>Maintenance</span>
        </div>

        <nav className={styles.nav} onClick={() => setMenuOpen(false)}>
          <NavLink to="/board" data-testid="nav-board" className={navItemClass}>
            {t(lang, 'Répartition', 'Dispatch')}
          </NavLink>
          <Link to="/board?nouvel-appel=1" data-testid="nav-nouvel-appel" className={styles.navItem}>
            {t(lang, 'Nouvel appel', 'New call')}
          </Link>
          <NavLink to="/dossiers" data-testid="nav-dossiers" className={navItemClass}>
            {t(lang, 'Dossiers', 'Cases')}
          </NavLink>
          <span
            className={`${styles.navItem} ${styles.navDisabled}`}
            data-testid="nav-apres-heures"
            aria-disabled="true"
          >
            {t(lang, 'Après les heures', 'After hours')} <SoonChip lang={lang} />
          </span>

          <div className={styles.navGroup}>{t(lang, "Vue d'ensemble", 'Overview')}</div>
          <a
            href={MOCKUP_URL} target="_blank" rel="noreferrer"
            data-testid="nav-tableau-bord"
            title={t(lang, 'Aperçu — maquette, données fictives', 'Preview — mockup, fictional data')}
            className={`${styles.navItem} ${styles.navDisabled}`}
          >
            {t(lang, 'Tableau de bord', 'Dashboard')} <SoonChip lang={lang} />
          </a>
          <a
            href={MOCKUP_URL} target="_blank" rel="noreferrer"
            data-testid="nav-utilisation"
            title={t(lang, 'Aperçu — maquette, données fictives', 'Preview — mockup, fictional data')}
            className={`${styles.navItem} ${styles.navDisabled}`}
          >
            {t(lang, 'Utilisation', 'Utilization')} <SoonChip lang={lang} />
          </a>
        </nav>

        <div className={styles.bottom}>
          {me && (
            <div className={styles.userInfo}>
              <span className={styles.userName}>{me.nom_employe}</span>
              <span className={styles.userRole}>{roleLabel(lang, me.roles[0] ?? '')}</span>
            </div>
          )}

          <div className={styles.bottomRow}>
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
