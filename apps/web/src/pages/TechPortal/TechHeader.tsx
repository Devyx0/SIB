import { Link } from 'react-router-dom';
import type { MeResponse } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t } from '../../i18n';
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
          ‹ {t(lang, 'Mes appels', 'My calls')}
        </Link>
      ) : (
        <span className={styles.brand}>SIB — {t(lang, 'Mes appels', 'My calls')}</span>
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
