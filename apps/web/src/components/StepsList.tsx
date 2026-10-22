import { useId, useRef, useState } from 'react';
import type { Lang } from '../i18n';
import { t } from '../i18n';
import styles from './StepsList.module.css';

// Enter-to-add, reorderable list of steps. The value stays a plain string,
// one step per line, so it saves into the existing text field unchanged.
// Reorder: drag the ⠿ grip (mouse), the ↑ ↓ buttons (touch), or Alt+↑/↓.

interface Props {
  lang: Lang;
  /** Steps, one per line. */
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  label: string;
  inputTestId?: string;
}

/** Fit a step's box to its wrapped text (fallback where CSS field-sizing isn't supported). */
function autoGrow(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${el.scrollHeight}px`;
}

const toSteps = (v: string) => v.split('\n').map((s) => s.trim()).filter(Boolean);
const toValue = (steps: string[]) => steps.join('\n');

export default function StepsList({ lang, value, onChange, disabled, label, inputTestId }: Props) {
  const steps = toSteps(value);
  const [draft, setDraft] = useState('');
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const [announce, setAnnounce] = useState('');
  const listRef = useRef<HTMLOListElement>(null);
  const labelId = useId();

  function commit(next: string[]) {
    onChange(toValue(next));
  }

  function add(text: string) {
    const added = text.split('\n').map((s) => s.trim()).filter(Boolean);
    if (!added.length) return;
    commit([...steps, ...added]);
    setDraft('');
    // The list scrolls inside a capped height: bring the new step into view.
    requestAnimationFrame(() => {
      const el = listRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  function remove(i: number) {
    commit(steps.filter((_, j) => j !== i));
    setAnnounce(t(lang, `Étape ${i + 1} retirée`, `Step ${i + 1} removed`));
  }

  function edit(i: number, text: string) {
    const next = [...steps];
    if (text.trim()) next[i] = text.trim();
    else next.splice(i, 1);
    commit(next);
  }

  function move(from: number, to: number) {
    if (to < 0 || to >= steps.length || from === to) return;
    const next = [...steps];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    commit(next);
    setAnnounce(t(lang, `Étape déplacée en position ${to + 1}`, `Step moved to position ${to + 1}`));
    // Keep keyboard focus on the moved step.
    requestAnimationFrame(() => {
      listRef.current?.querySelector<HTMLTextAreaElement>(`[data-step-index="${to}"]`)?.focus();
    });
  }

  return (
    <div className={styles.wrap}>
      <span className={styles.head}>
        <span className={styles.label} id={labelId}>{label}</span>
        {steps.length > 0 && (
          <span className={styles.count} data-testid="steps-count">
            {t(lang, `${steps.length} étape${steps.length > 1 ? 's' : ''}`, `${steps.length} step${steps.length > 1 ? 's' : ''}`)}
          </span>
        )}
      </span>

      {steps.length > 0 && (
        <ol className={styles.list} ref={listRef} aria-labelledby={labelId} data-testid="steps-list">
          {steps.map((s, i) => (
            <li
              key={`${i}-${s}`}
              className={[
                styles.item,
                dragFrom === i ? styles.dragging : '',
                dragOver === i && dragFrom !== null && dragFrom !== i ? styles.dropTarget : '',
              ].join(' ')}
              draggable={!disabled}
              onDragStart={(e) => {
                setDragFrom(i);
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', String(i));
              }}
              onDragOver={(e) => {
                if (dragFrom === null) return;
                e.preventDefault();
                setDragOver(i);
              }}
              onDrop={(e) => {
                e.preventDefault();
                if (dragFrom !== null) move(dragFrom, i);
                setDragFrom(null);
                setDragOver(null);
              }}
              onDragEnd={() => { setDragFrom(null); setDragOver(null); }}
              data-testid="step-item"
            >
              {!disabled && <span className={styles.grip} aria-hidden="true">⠿</span>}
              <span className={styles.num} aria-hidden="true">{i + 1}.</span>
              <textarea
                className={styles.text}
                rows={1}
                defaultValue={s}
                disabled={disabled}
                data-step-index={i}
                aria-label={t(lang, `Étape ${i + 1}`, `Step ${i + 1}`)}
                ref={autoGrow}
                onInput={(e) => autoGrow(e.currentTarget)}
                onBlur={(e) => { if (e.target.value !== s) edit(i, e.target.value); }}
                onKeyDown={(e) => {
                  // One step = one line: Enter finishes editing instead of adding a newline.
                  if (e.key === 'Enter') { e.preventDefault(); (e.target as HTMLTextAreaElement).blur(); }
                  if (e.altKey && e.key === 'ArrowUp') { e.preventDefault(); move(i, i - 1); }
                  if (e.altKey && e.key === 'ArrowDown') { e.preventDefault(); move(i, i + 1); }
                }}
              />
              {!disabled && (
                <span className={styles.actions}>
                  <button type="button" className={styles.iconBtn} onClick={() => move(i, i - 1)}
                    disabled={i === 0} aria-label={t(lang, `Monter l’étape ${i + 1}`, `Move step ${i + 1} up`)}>↑</button>
                  <button type="button" className={styles.iconBtn} onClick={() => move(i, i + 1)}
                    disabled={i === steps.length - 1} aria-label={t(lang, `Descendre l’étape ${i + 1}`, `Move step ${i + 1} down`)}>↓</button>
                  <button type="button" className={`${styles.iconBtn} ${styles.remove}`} onClick={() => remove(i)}
                    aria-label={t(lang, `Retirer l’étape ${i + 1}`, `Remove step ${i + 1}`)}>✕</button>
                </span>
              )}
            </li>
          ))}
        </ol>
      )}

      {!disabled && (
        <div className={styles.addRow}>
          <input
            className={styles.addInput}
            value={draft}
            placeholder={t(lang, 'Ajouter une étape puis Entrée…', 'Add a step, then Enter…')}
            aria-label={t(lang, 'Nouvelle étape', 'New step')}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(draft); } }}
            onPaste={(e) => {
              const text = e.clipboardData.getData('text');
              if (text.includes('\n')) { e.preventDefault(); add(`${draft}${text}`); }
            }}
            data-testid={inputTestId}
          />
          <button type="button" className={styles.addBtn} onClick={() => add(draft)} disabled={!draft.trim()}>
            {t(lang, 'Ajouter', 'Add')}
          </button>
        </div>
      )}
      {disabled && steps.length === 0 && <p className={styles.empty}>—</p>}

      <span className={styles.srOnly} aria-live="polite">{announce}</span>
    </div>
  );
}
