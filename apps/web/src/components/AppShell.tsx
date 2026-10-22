import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation, useNavigationType } from 'react-router-dom';
import type { MeResponse } from '../api/schema.d.ts';
import type { Lang } from '../i18n';
import { roleLabel, t } from '../i18n';
import DemoUserSwitcher from '../dev/DemoUserSwitcher';
import { demoUserSwitchEnabled } from '../dev/demoUserSwitch';
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

export default function AppShell({ lang, onToggleLang, me, onSignOut, children }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const burgerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  const mainRef = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const navType = useNavigationType();

  // A new page starts at the top (the page scrolls on phones, the main panel
  // on desktop). Filter / query changes keep their place, and Back (POP)
  // leaves the position to the browser.
  useEffect(() => {
    if (navType === 'POP') return;
    // Instant, not the page-wide smooth scroll: the new page simply opens at the top.
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' as ScrollBehavior });
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [pathname, navType]);
  const intakeOnly = !!me?.roles.includes('receptionist')
    && !me.roles.some((r) => r === 'coordinator' || r === 'director');
  const navItemClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? `${styles.navItem} ${styles.navActive}` : styles.navItem;

  // Phone drawer: Escape closes it, focus moves into it on open and back to
  // the menu button on close, and the page behind stays put.
  useEffect(() => {
    if (!menuOpen) {
      if (wasOpen.current) burgerRef.current?.focus();
      wasOpen.current = false;
      return;
    }
    wasOpen.current = true;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [menuOpen]);

  return (
    <div className={styles.shell}>
      {/* Phone only: a slim bar with the menu button and the logo, sticky at the top. */}
      <header className={styles.topbar}>
        <button
          ref={burgerRef}
          className={styles.burger}
          data-testid="burger"
          aria-label={t(lang, 'Ouvrir le menu', 'Open menu')}
          aria-expanded={menuOpen}
          aria-controls="app-nav-drawer"
          onClick={() => setMenuOpen((o) => !o)}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
        <BrandMark size="sm" />
      </header>
      {menuOpen && <div className={styles.overlay} onClick={() => setMenuOpen(false)} />}

      <aside id="app-nav-drawer" className={`${styles.sidebar} ${menuOpen ? styles.sidebarOpen : ''}`}>
        <div className={styles.brand}>
          <BrandMark product="Maintenance" />
          <button
            ref={closeRef}
            type="button"
            className={styles.drawerClose}
            onClick={() => setMenuOpen(false)}
            aria-label={t(lang, 'Fermer le menu', 'Close menu')}
            data-testid="drawer-close"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <nav className={styles.nav} onClick={() => setMenuOpen(false)}>
          {!intakeOnly && (
            <>
              <NavLink to="/triage" data-testid="nav-triage" className={navItemClass}>
                {t(lang, 'Triage', 'Triage')}
              </NavLink>
              <NavLink to="/tasks" data-testid="nav-tasks" className={navItemClass}>
                {t(lang, 'Tâches', 'Tasks')}
              </NavLink>
              <NavLink to="/portfolio" data-testid="nav-portfolio" className={navItemClass}>
                {t(lang, 'Portfolio', 'Portfolio')}
              </NavLink>

              <div className={styles.navGroup}>{t(lang, "Vue d'ensemble", 'Overview')}</div>
              <NavLink to="/tableau-de-bord" data-testid="nav-tableau-bord" className={navItemClass}>
                {t(lang, 'Tableau de bord', 'Dashboard')}
              </NavLink>
              <NavLink to="/utilisation" data-testid="nav-utilisation" className={navItemClass}>
                {t(lang, 'Utilisation', 'Utilization')}
              </NavLink>
            </>
          )}
        </nav>

        <div className={styles.bottom}>
          <div className={styles.newCall} onClick={() => setMenuOpen(false)}>
            {intakeOnly ? (
              <NavLink to="/intake" data-testid="nav-nouvel-appel" className={navItemClass}>
                <span className={styles.plus} aria-hidden="true">+</span>
                {t(lang, 'Nouvel appel', 'New call')}
              </NavLink>
            ) : (
              <Link to="/triage?nouvel-appel=1" data-testid="nav-nouvel-appel" className={styles.navItem}>
                <span className={styles.plus} aria-hidden="true">+</span>
                {t(lang, 'Nouvel appel', 'New call')}
              </Link>
            )}
          </div>

          {me && (
            <div className={styles.userInfo}>
              {demoUserSwitchEnabled() ? (
                <DemoUserSwitcher
                  lang={lang}
                  displayName={me.nom_employe}
                  displayRole={roleLabel(lang, me.roles[0] ?? '')}
                />
              ) : (
                <>
                  <span className={styles.userName}>{me.nom_employe}</span>
                  <span className={styles.userRole}>{roleLabel(lang, me.roles[0] ?? '')}</span>
                </>
              )}
            </div>
          )}

          <div className={styles.bottomRow}>
            {!intakeOnly && <AlertBell lang={lang} />}
            <button className={styles.langBtn} onClick={onToggleLang} aria-label={lang === 'fr' ? 'Switch to English' : 'Passer en français'}>
              {t(lang, 'EN', 'FR')}
            </button>
            <button className={styles.signOutBtn} onClick={onSignOut}>
              {t(lang, 'Déconnexion', 'Sign out')}
            </button>
          </div>
        </div>
      </aside>

      <main ref={mainRef} className={styles.main}>{children}</main>
    </div>
  );
}
