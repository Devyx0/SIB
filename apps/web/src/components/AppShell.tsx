import type { MeResponse } from '../api/schema.d.ts';
import type { Lang } from '../i18n';
import { roleLabel, t } from '../i18n';
import styles from './AppShell.module.css';

interface Props {
  lang: Lang;
  onToggleLang: () => void;
  me: MeResponse | null;
  onSignOut: () => void;
  children: React.ReactNode;
}

export default function AppShell({ lang, onToggleLang, me, onSignOut, children }: Props) {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>SIB</span>
          <span className={styles.brandName}>Maintenance</span>
        </div>

        <nav className={styles.nav}>
          <span className={styles.navItem} aria-current="page">
            {t(lang, 'Répartition', 'Dispatch')}
          </span>
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
