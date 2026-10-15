import type { Lang } from '../i18n';
import { t } from '../i18n';
import styles from './AppShell.module.css';

interface Props {
  lang: Lang;
  onToggleLang: () => void;
  employeeId: string | null;
  onSetEmployee: (id: string) => void;
  children: React.ReactNode;
}

const DEV_USERS = [
  { id: '4',  label: 'Coordinateur (4)' },
  { id: '5',  label: 'Directeur (5)' },
  { id: '24', label: 'Technicien (24)' },
  { id: '20', label: 'Contractuel Butler (20)' },
];

export default function AppShell({ lang, onToggleLang, employeeId, onSetEmployee, children }: Props) {
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
          {import.meta.env.DEV && (
            <label className={styles.devLabel}>
              {t(lang, 'Utilisateur (dev)', 'User (dev)')}
              <select
                className={styles.devSelect}
                value={employeeId ?? '4'}
                onChange={(e) => onSetEmployee(e.target.value)}
                data-testid="dev-employee-input"
              >
                {DEV_USERS.map((u) => (
                  <option key={u.id} value={u.id}>{u.label}</option>
                ))}
              </select>
            </label>
          )}

          <button className={styles.langBtn} onClick={onToggleLang} aria-label="Toggle language">
            {t(lang, 'EN', 'FR')}
          </button>
        </div>
      </aside>

      <main className={styles.main}>{children}</main>
    </div>
  );
}
