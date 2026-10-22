/**
 * DEMO ONLY — remove after demo (see demoUserSwitch.ts).
 * Name/role look like AppShell; menu matches FilterBar / StatusSelect popover.
 */
import { useEffect, useId, useRef, useState } from 'react';
import { supabase } from '../lib/supabase';
import type { Lang } from '../i18n';
import { roleLabel, t } from '../i18n';
import {
  DEMO_ROLE_GROUPS,
  DEMO_USERS,
  demoSeedPassword,
  demoUserSwitchEnabled,
} from './demoUserSwitch';
import styles from './DemoUserSwitcher.module.css';

interface Props {
  lang: Lang;
  displayName: string;
  displayRole: string;
  compact?: boolean;
}

export default function DemoUserSwitcher({
  lang,
  displayName,
  displayRole,
  compact = false,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [currentEmail, setCurrentEmail] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listId = useId();

  useEffect(() => {
    void supabase.auth.getSession().then(({ data }) => {
      setCurrentEmail(data.session?.user.email ?? null);
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const match = DEMO_USERS.find((u) => u.email === currentEmail);
  const name = match?.name ?? displayName;
  const role = match ? roleLabel(lang, match.role) : displayRole;

  async function onPick(email: string) {
    setOpen(false);
    if (!email || email === currentEmail) return;
    const password = demoSeedPassword();
    if (!password) {
      setErr('Set VITE_DEMO_SEED_PASSWORD');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) {
        setErr(error.message);
        return;
      }
      window.location.assign('/');
    } catch {
      setErr('Switch failed');
    } finally {
      setBusy(false);
    }
  }

  if (!demoUserSwitchEnabled()) {
    return (
      <div className={compact ? styles.compactStatic : styles.static}>
        <span className={styles.name}>{displayName}</span>
        {!compact && <span className={styles.role}>{displayRole}</span>}
      </div>
    );
  }

  return (
    <div
      className={`${styles.root} ${compact ? styles.compact : ''}`}
      ref={rootRef}
      data-testid="demo-user-switcher"
    >
      <button
        ref={triggerRef}
        type="button"
        className={styles.trigger}
        disabled={busy}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        title={t(lang, 'Démo — changer d’utilisateur', 'Demo — switch user')}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={styles.triggerText}>
          <span className={styles.name}>{name}</span>
          {!compact && <span className={styles.role}>{role}</span>}
        </span>
        <svg className={styles.chevron} viewBox="0 0 12 8" width="10" height="7" aria-hidden="true">
          <path fill="currentColor" d="M1 1l5 5 5-5" />
        </svg>
      </button>

      {open && (
        <div
          id={listId}
          className={styles.popover}
          role="listbox"
          aria-label={t(lang, 'Changer d’utilisateur (démo)', 'Switch user (demo)')}
        >
          {DEMO_ROLE_GROUPS.map((g) => {
            const users = DEMO_USERS.filter((u) => u.role === g.role);
            if (users.length === 0) return null;
            return (
              <div key={g.role} className={styles.group}>
                <div className={styles.groupLabel}>{lang === 'fr' ? g.fr : g.en}</div>
                {users.map((u) => {
                  const selected = u.email === currentEmail;
                  return (
                    <button
                      key={u.email}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={`${styles.option} ${selected ? styles.optionSelected : ''}`}
                      onClick={() => void onPick(u.email)}
                    >
                      <span className={styles.optionName}>{u.name}</span>
                      <span className={styles.optionRole}>{roleLabel(lang, u.role)}</span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      )}

      {err && <p className={styles.err} role="alert">{err}</p>}
    </div>
  );
}
