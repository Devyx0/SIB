import { useCallback, useEffect, useRef, useState } from 'react';
import type { Lang } from '../i18n';
import { startAssemblyStream, streamingSupported } from '../lib/assemblyStream';
import type { StreamError, StreamSession } from '../lib/assemblyStream';

// Live speech-to-text on AssemblyAI Universal-3.6 Pro (see lib/assemblyStream).
// Words stream in while the person talks (`interim`) and settle into
// punctuated turns passed to `onFinal`. Without a microphone or browser
// support, `supported` is false and callers fall back to typing.

export type DictationError = StreamError;

/** Join a spoken fragment to what is already there, sentence-cased. */
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
  /** Called with each finished turn of speech. */
  onFinal: (chunk: string) => void;
}

export function useDictation({ lang, onFinal }: Options) {
  const supported = streamingSupported();
  const [listening, setListening] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [interim, setInterim] = useState('');
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<DictationError | null>(null);
  const sessionRef = useRef<StreamSession | null>(null);
  const startingRef = useRef(false);
  const cancelledRef = useRef(false);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  const start = useCallback(async () => {
    if (!supported || startingRef.current || sessionRef.current) return;
    startingRef.current = true;
    cancelledRef.current = false;
    setError(null);
    setConnecting(true);
    setListening(true);
    const session = await startAssemblyStream(lang, {
      onPartial: setInterim,
      onFinal: (text) => onFinalRef.current(text),
      onLevel: setLevel,
      onError: (code) => {
        setError(code);
        setListening(false);
        setConnecting(false);
        setInterim('');
        const s = sessionRef.current;
        sessionRef.current = null;
        void s?.stop();
      },
    });
    startingRef.current = false;
    setConnecting(false);
    if (!session) { setListening(false); return; }
    if (cancelledRef.current) { void session.stop(); setListening(false); return; }
    sessionRef.current = session;
  }, [supported, lang]);

  /** Stop and wait for the last words to arrive. */
  const stop = useCallback(async () => {
    cancelledRef.current = true;
    const s = sessionRef.current;
    sessionRef.current = null;
    setListening(false);
    setLevel(0);
    if (s) await s.stop();
    setInterim('');
  }, []);

  const toggle = useCallback(() => (sessionRef.current || startingRef.current ? stop() : start()), [start, stop]);

  // Never leave the microphone on after the component goes away.
  useEffect(() => () => {
    cancelledRef.current = true;
    void sessionRef.current?.stop();
    sessionRef.current = null;
  }, []);

  return { supported, listening, connecting, interim, level, error, start, stop, toggle };
}
