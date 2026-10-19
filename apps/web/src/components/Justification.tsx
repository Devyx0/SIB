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

/** Live microphone level (0–1) for the waveform, while `active`. */
function useMicLevel(active: boolean): number {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    if (!active || !navigator.mediaDevices?.getUserMedia) return;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    let raf = 0;
    let cancelled = false;
    navigator.mediaDevices.getUserMedia({ audio: true }).then((s) => {
      if (cancelled) { s.getTracks().forEach((tr) => tr.stop()); return; }
      stream = s;
      ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      ctx.createMediaStreamSource(s).connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) { const d = (v - 128) / 128; sum += d * d; }
        setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4));
        raf = requestAnimationFrame(tick);
      };
      tick();
    }).catch(() => { /* the speech engine reports permission problems */ });
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((tr) => tr.stop());
      ctx?.close();
      setLevel(0);
    };
  }, [active]);
  return level;
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
  const level = useMicLevel(dictation.listening);

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

  function confirm() {
    if (!ready) return;
    dictation.stop();
    onConfirm({ text: finishSentence(trimmed), input_method: usedVoice ? 'voice' : 'typed' });
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') { e.stopPropagation(); dictation.stop(); onCancel(); }
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); confirm(); }
  }

  const errorText = dictation.error === 'not-allowed'
    ? t(lang, 'Micro bloqué — autorisez-le dans le navigateur, ou écrivez.', 'Microphone blocked — allow it in the browser, or type.')
    : dictation.error === 'no-microphone'
      ? t(lang, 'Aucun micro détecté — écrivez votre justification.', 'No microphone found — type your justification.')
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
                {dictation.listening
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
            disabled={!ready}
            onClick={confirm}
            data-testid="justification-confirm"
          >
            {t(lang, 'Confirmer la décision', 'Confirm decision')}
          </button>
        </footer>
      </div>
    </div>
  );
}
