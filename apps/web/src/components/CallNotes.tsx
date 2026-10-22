import { useState } from 'react';
import type { FollowupEntry } from '../api/schema.d.ts';
import { t } from '../i18n';
import type { Lang } from '../i18n';
import { Avatar } from './Avatar';
import styles from './CallNotes.module.css';

// The call's notes (follow-up log) as their own tab: write one at the top,
// read them newest first as cards — author, date, text.

function noteDate(ymd: string | null, lang: Lang): string {
  if (!ymd) return '';
  const [y, m, d] = ymd.split('-').map(Number);
  if (!y || !m || !d) return ymd;
  return new Intl.DateTimeFormat(lang === 'fr' ? 'fr-CA' : 'en-CA', { day: 'numeric', month: 'short', year: 'numeric' })
    .format(new Date(y, m - 1, d));
}

export default function CallNotes({ notes, lang, canAdd, onAdd }: {
  notes: FollowupEntry[];
  lang: Lang;
  canAdd: boolean;
  /** Resolves once saved; rejects to keep the draft. */
  onAdd: (text: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');

  const sorted = [...notes].sort((a, b) =>
    (b.entry_date ?? '').localeCompare(a.entry_date ?? '') || b.followup_id - a.followup_id);
  const needle = q.trim().toLowerCase();
  const shown = needle
    ? sorted.filter((n) => `${n.entry_text ?? ''} ${n.entered_by_initials ?? ''}`.toLowerCase().includes(needle))
    : sorted;

  async function add() {
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      await onAdd(text);
      setDraft('');
    } catch {
      // The panel shows the error; the draft stays for another try.
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.wrap} data-testid="call-notes">
      {canAdd && (
        <div className={styles.composer}>
          <label className={styles.srOnly} htmlFor="call-note-draft">{t(lang, 'Nouvelle note', 'New note')}</label>
          <textarea
            id="call-note-draft"
            className={styles.input}
            rows={3}
            value={draft}
            placeholder={t(lang, 'Écrire une note…', 'Write a note…')}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void add(); } }}
            data-testid="note-draft"
          />
          <div className={styles.composerBar}>
            <span className={styles.hint}>{t(lang, 'Ctrl + Entrée pour ajouter', 'Ctrl + Enter to add')}</span>
            <button type="button" className={styles.addBtn} onClick={() => void add()}
                    disabled={!draft.trim() || busy} data-testid="note-add">
              {busy ? t(lang, 'Ajout…', 'Adding…') : t(lang, 'Ajouter la note', 'Add note')}
            </button>
          </div>
        </div>
      )}

      <div className={styles.listHead}>
        <h3 className={styles.listTitle}>
          {t(lang, 'Notes', 'Notes')} <span className={styles.count}>{notes.length}</span>
        </h3>
        {notes.length > 4 && (
          <input type="search" className={styles.search} value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder={t(lang, 'Rechercher dans les notes…', 'Search notes…')}
                 aria-label={t(lang, 'Rechercher dans les notes', 'Search notes')} data-testid="note-search" />
        )}
      </div>

      {notes.length === 0 ? (
        <p className={styles.empty}>{t(lang, 'Aucune note pour cet appel.', 'No notes on this call yet.')}</p>
      ) : shown.length === 0 ? (
        <p className={styles.empty}>{t(lang, 'Aucune note ne correspond.', 'No matching note.')}</p>
      ) : (
        <ol className={styles.list}>
          {shown.map((n) => (
            <li key={n.followup_id} className={styles.note} data-testid="note">
              <div className={styles.noteHead}>
                <Avatar name={n.entered_by_initials ?? '?'} size="sm" />
                <span className={styles.author}>{n.entered_by_initials ?? '—'}</span>
                <span className={styles.date}>{noteDate(n.entry_date, lang)}</span>
              </div>
              <p className={styles.text}>{n.entry_text?.trim() || '—'}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
