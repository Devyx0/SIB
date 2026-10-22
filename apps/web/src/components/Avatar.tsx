import styles from './Avatar.module.css';

// Initials disc shown next to every employee name (tables, panels, history,
// dropdowns, the signed-in user). First + last name initial, brand navy.

/** « Marc-André Tremblay » → « MT »; « Réception » → « R »; already initials stay as they are. */
export function initialsOf(name: string | null | undefined): string {
  const clean = (name ?? '').replace(/\(.*?\)|—.*$/g, '').trim();
  if (!clean) return '?';
  if (/^[A-ZÀ-Ý]{1,3}$/.test(clean)) return clean;
  const parts = clean.split(/\s+/).filter(Boolean);
  const first = parts[0][0] ?? '';
  const last = parts.length > 1 ? parts[parts.length - 1][0] ?? '' : '';
  return (first + last).toUpperCase() || '?';
}

type Size = 'xs' | 'sm' | 'md' | 'lg';

export function Avatar({ name, size = 'sm', className = '' }: { name: string | null | undefined; size?: Size; className?: string }) {
  return (
    <span className={`${styles.avatar} ${styles[size]} ${className}`} aria-hidden="true" data-testid="avatar">
      {initialsOf(name)}
    </span>
  );
}

/** Avatar + name on one line; the name stays the accessible text. */
export function PersonName({ name, size = 'sm', className = '' }: { name: string; size?: Size; className?: string }) {
  return (
    <span className={`${styles.person} ${className}`}>
      <Avatar name={name} size={size} />
      <span className={styles.personName}>{name}</span>
    </span>
  );
}
