import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react';
import type { Justification } from '../api/client';
import type { Lang } from '../i18n';
import { t } from '../i18n';
import { appendSpoken, finishSentence, useDictation } from '../hooks/useDictation';
import styles from './Justification.module.css';

// System-wide decision justification. Wrap the app in <JustificationProvider>
// and, from any screen, `const justify = useJustify()` then
// `const j = await justify({ decision, before, after })` — resolves with
// { text, input_method } or null if the person cancels. Voice-first: the
// microphone starts as soon as the prompt opens (where the browser supports
// it); typing always works too.

export const MIN_JUSTIFICATION = 10;

export interface JustifyRequest {
  /** What is being decided, e.g. « Assignation ». */
  decision: string;
  before?: string | null;
  after?: string | null;
  /** Several edits saved together — listed under the title, one justification for all. */
  changes?: Array<{ label: string; before: string; after: string }>;
}

type JustifyFn = (req: JustifyRequest) => Promise<Justification | null>;

const JustifyContext = createContext<JustifyFn | null>(null);

const missingProvider: JustifyFn = () =>
  Promise.reject(new Error('useJustify must be used inside <JustificationProvider>'));

export function useJustify(): JustifyFn {
  // Read-only screens may render without the provider; only an actual
  // decision needs it, so fail loudly at that point rather than on render.
  return useContext(JustifyContext) ?? missingProvider;
}

interface Pending extends JustifyRequest {
  resolve: (j: Justification | null) => void;
}

export function JustificationProvider({ lang, children }: { lang: Lang; children: React.ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);

  const justify = useCallback<JustifyFn>(
    (req) => new Promise((resolve) => setPending({ ...req, resolve })),
    [],
  );

  function settle(result: Justification | null) {
    pending?.resolve(result);
    setPending(null);
  }

  return (
    <JustifyContext.Provider value={justify}>
      {children}
      {pending && (
        <JustificationDialog
          key={`${pending.decision}-${pending.after ?? ''}`}
          lang={lang}
          request={pending}
          onCancel={() => settle(null)}
          onConfirm={settle}
        />
      )}
    </JustifyContext.Provider>
  );
}

const BARS = [0.45, 0.7, 1, 0.8, 0.55, 0.9, 0.65];

function JustificationDialog({
  lang, request, onCancel, onConfirm,
}: {
  lang: Lang;
  request: JustifyRequest;
  onCancel: () => void;
  onConfirm: (j: Justification) => void;
}) {
  const [text, setText] = useState('');
  const [usedVoice, setUsedVoice] = useState(false);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const micRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  const dictation = useDictation({
    lang,
    onFinal: (chunk) => {
      setUsedVoice(true);
      setText((prev) => appendSpoken(prev, chunk));
    },
  });
  const level = dictation.level;
  // Latest text, readable after awaiting the last dictated words.
  const latestText = useRef(text);
  latestText.current = text;
  const [finishing, setFinishing] = useState(false);

  // Voice-first: start listening as soon as the prompt opens.
  useEffect(() => {
    if (dictation.supported) {
      micRef.current?.focus();
      dictation.start();
    } else {
      textRef.current?.focus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.body.classList.add('modal-open');
    return () => { document.body.classList.remove('modal-open'); };
  }, []);

  const trimmed = text.trim();
  const ready = trimmed.length >= MIN_JUSTIFICATION;

  function stopAndTidy() {
    if (dictation.listening) dictation.stop();
    setText((prev) => finishSentence(prev));
  }

  async function confirm() {
    if (!ready || finishing) return;
    if (dictation.listening) {
      // Wait for the words still in flight before saving.
      setFinishing(true);
      await dictation.stop();
      setFinishing(false);
    }
    const finalText = latestText.current.trim();
    if (finalText.length < MIN_JUSTIFICATION) return;
    onConfirm({ text: finishSentence(finalText), input_method: usedVoice ? 'voice' : 'typed' });
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') { e.stopPropagation(); dictation.stop(); onCancel(); }
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void confirm(); }
  }

  const errorText = dictation.error === 'not-allowed'
    ? t(lang, 'Micro bloqué — autorisez-le dans le navigateur, ou écrivez.', 'Microphone blocked — allow it in the browser, or type.')
    : dictation.error === 'no-microphone'
      ? t(lang, 'Aucun micro détecté — écrivez votre justification.', 'No microphone found — type your justification.')
      : dictation.error === 'unavailable'
        ? t(lang, 'Dictée indisponible pour le moment — écrivez votre justification.', 'Dictation unavailable right now — type your justification.')
        : dictation.error
          ? t(lang, 'La dictée s’est interrompue — réessayez ou écrivez.', 'Dictation stopped — try again or type.')
          : null;

  const remaining = Math.max(0, MIN_JUSTIFICATION - trimmed.length);

  return (
    <div className={styles.overlay} onKeyDown={onKeyDown}>
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="justification-dialog"
      >
        <header className={styles.header}>
          <div>
            <h2 id={titleId} className={styles.title}>{t(lang, 'Justifier la décision', 'Justify the decision')}</h2>
            <p className={styles.decision}>
              <span className={styles.decisionName}>{request.decision}</span>
              {(request.before !== undefined || request.after !== undefined) && (
                <span className={styles.change}>
                  <span className={styles.before}>{request.before || '—'}</span>
                  <span aria-hidden="true" className={styles.arrow}>→</span>
                  <span className={styles.after}>{request.after || '—'}</span>
                </span>
              )}
            </p>
            {request.changes && request.changes.length > 1 && (
              <ul className={styles.changeList} data-testid="justification-changes">
                {request.changes.map((c) => (
                  <li key={c.label}>
                    <span className={styles.changeLabel}>{c.label}</span>
                    <span className={styles.before}>{c.before || '—'}</span>
                    <span aria-hidden="true" className={styles.arrow}>→</span>
                    <span className={styles.after}>{c.after || '—'}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={() => { dictation.stop(); onCancel(); }}
            aria-label={t(lang, 'Fermer', 'Close')}
          >
            <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        </header>

        {dictation.supported && (
          <div className={`${styles.voice} ${dictation.listening ? styles.voiceOn : ''}`}>
            <button
              ref={micRef}
              type="button"
              className={styles.mic}
              onClick={dictation.listening ? stopAndTidy : dictation.start}
              aria-pressed={dictation.listening}
              aria-label={dictation.listening ? t(lang, 'Arrêter la dictée', 'Stop dictation') : t(lang, 'Dicter', 'Dictate')}
              data-testid="justification-mic"
            >
              {dictation.listening ? (
                <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2" /></svg>
              ) : (
                <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                </svg>
              )}
            </button>
            <div className={styles.voiceText}>
              <span className={styles.voiceState} aria-live="polite">
                {dictation.connecting
                  ? t(lang, 'Connexion au micro…', 'Connecting…')
                  : dictation.listening
                    ? t(lang, 'À l’écoute — parlez naturellement', 'Listening — speak naturally')
                    : t(lang, 'Appuyez pour dicter', 'Tap to dictate')}
              </span>
              <span className={styles.voiceHint}>
                {dictation.listening
                  ? t(lang, 'Appuyez à nouveau pour arrêter', 'Tap again to stop')
                  : t(lang, 'Ou écrivez ci-dessous', 'Or type below')}
              </span>
            </div>
            <div className={styles.wave} aria-hidden="true">
              {BARS.map((b, i) => (
                <span key={i} style={{ transform: `scaleY(${dictation.listening ? 0.18 + Math.min(1, level * b * 1.6) * 0.82 : 0.18})` }} />
              ))}
            </div>
          </div>
        )}

        <label className={styles.label} htmlFor={`${titleId}-text`}>
          {t(lang, 'Pourquoi ce changement ?', 'Why this change?')}
        </label>
        <textarea
          id={`${titleId}-text`}
          ref={textRef}
          className={styles.textarea}
          value={text}
          rows={4}
          placeholder={dictation.supported
            ? t(lang, 'Votre justification apparaît ici pendant que vous parlez…', 'Your justification appears here as you speak…')
            : t(lang, 'Expliquez brièvement la raison de ce changement…', 'Briefly explain the reason for this change…')}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => { if (dictation.listening) stopAndTidy(); }}
          data-testid="justification-text"
        />
        {dictation.interim && (
          <p className={styles.interim} aria-live="polite" data-testid="justification-interim">{dictation.interim}</p>
        )}

        <div className={styles.meta}>
          {errorText
            ? <span className={styles.error} role="alert">{errorText}</span>
            : <span className={ready ? styles.ok : styles.count}>
                {ready
                  ? t(lang, 'Prêt à enregistrer', 'Ready to save')
                  : t(lang, `Encore ${remaining} caractère(s) minimum`, `${remaining} more character(s) needed`)}
              </span>}
          <span className={styles.shortcut}>⌘/Ctrl + Entrée</span>
        </div>

        <footer className={styles.actions}>
          <button type="button" className={styles.cancelBtn} onClick={() => { dictation.stop(); onCancel(); }}>
            {t(lang, 'Annuler', 'Cancel')}
          </button>
          <button
            type="button"
            className={styles.confirmBtn}
            disabled={!ready || finishing}
            onClick={() => void confirm()}
            data-testid="justification-confirm"
          >
            {t(lang, 'Confirmer la décision', 'Confirm decision')}
          </button>
        </footer>
      </div>
    </div>
  );
}
