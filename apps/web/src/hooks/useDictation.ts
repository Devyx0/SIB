import { useCallback, useEffect, useRef, useState } from 'react';
import type { Lang } from '../i18n';

// Live speech-to-text on the browser's built-in engine (Chrome, Edge, Safari).
// Words stream in while the person talks (`interim`), settle into `final`
// text, and the session restarts itself after the browser's silence cut-off
// so long dictations are not chopped. Firefox has no engine: `supported` is
// false and callers fall back to typing.

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Recognition = any;

function getEngine(): (new () => Recognition) | undefined {
  if (typeof window === 'undefined') return undefined;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = window as any;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

export type DictationError = 'not-allowed' | 'no-microphone' | 'network' | 'other';

/** Sentence-case a fragment and join it to what is already there. */
export function appendSpoken(existing: string, spoken: string): string {
  const piece = spoken.trim();
  if (!piece) return existing;
  const base = existing.replace(/\s+$/, '');
  const startsSentence = base === '' || /[.!?]$/.test(base);
  const text = startsSentence ? piece.charAt(0).toUpperCase() + piece.slice(1) : piece;
  return base ? `${base} ${text}` : text;
}

/** Close the last sentence with a period when dictation stops. */
export function finishSentence(text: string): string {
  const t = text.replace(/\s+$/, '');
  return t && !/[.!?…]$/.test(t) ? `${t}.` : t;
}

interface Options {
  lang: Lang;
  /** Called with each settled chunk of speech. */
  onFinal: (chunk: string) => void;
}

export function useDictation({ lang, onFinal }: Options) {
  const Engine = getEngine();
  const supported = !!Engine;
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<DictationError | null>(null);
  const recRef = useRef<Recognition | null>(null);
  const wantRef = useRef(false);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  const startSession = useCallback(() => {
    if (!Engine) return;
    const rec: Recognition = new Engine();
    rec.lang = lang === 'fr' ? 'fr-CA' : 'en-CA';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onresult = (e: any) => {
      let live = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) onFinalRef.current(r[0].transcript);
        else live += r[0].transcript;
      }
      setInterim(live);
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onerror = (e: any) => {
      const code = e?.error;
      if (code === 'no-speech' || code === 'aborted') return; // harmless; onend restarts
      wantRef.current = false;
      setError(
        code === 'not-allowed' || code === 'service-not-allowed' ? 'not-allowed'
          : code === 'audio-capture' ? 'no-microphone'
            : code === 'network' ? 'network' : 'other',
      );
    };
    rec.onend = () => {
      setInterim('');
      if (wantRef.current) {
        // The browser ends sessions after a pause; keep going until told to stop.
        try { rec.start(); return; } catch { /* fall through */ }
      }
      recRef.current = null;
      setListening(false);
    };
    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
      setError(null);
    } catch {
      wantRef.current = false;
      setListening(false);
    }
  }, [Engine, lang]);

  const start = useCallback(() => {
    if (!supported || wantRef.current) return;
    wantRef.current = true;
    startSession();
  }, [supported, startSession]);

  const stop = useCallback(() => {
    wantRef.current = false;
    recRef.current?.stop();
  }, []);

  const toggle = useCallback(() => (wantRef.current ? stop() : start()), [start, stop]);

  // Never leave the microphone on after the component goes away.
  useEffect(() => () => {
    wantRef.current = false;
    recRef.current?.abort?.();
  }, []);

  return { supported, listening, interim, error, start, stop, toggle };
}
