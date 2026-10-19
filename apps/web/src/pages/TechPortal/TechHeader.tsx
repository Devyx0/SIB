import { Link } from 'react-router-dom';
import type { MeResponse } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t } from '../../i18n';
import BrandMark from '../../components/BrandMark';
import styles from './TechPortal.module.css';

interface Props {
  lang: Lang;
  me: MeResponse | null;
  onSignOut: () => void;
  backTo?: string;
}

export default function TechHeader({ lang, me, onSignOut, backTo }: Props) {
  return (
    <header className={styles.header}>
      {backTo ? (
        <Link to={backTo} className={styles.backLink} aria-label={t(lang, 'Retour', 'Back')}>
          <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12.5 4.5L7 10l5.5 5.5" />
          </svg>
          {t(lang, 'Mes appels', 'My calls')}
        </Link>
      ) : (
        <span className={styles.brand}>
          <BrandMark size="sm" />
          <span className={styles.brandTitle}>{t(lang, 'Mes appels', 'My calls')}</span>
        </span>
      )}
      <div className={styles.headerRight}>
        {me && <span className={styles.userName}>{me.nom_employe}</span>}
        <button className={styles.signOutBtn} onClick={onSignOut}>
          {t(lang, 'Déconnexion', 'Sign out')}
        </button>
      </div>
    </header>
  );
}
