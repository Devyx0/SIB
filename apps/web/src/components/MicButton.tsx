import { useRef, useState } from 'react';
import type { Lang } from '../i18n';
import { t } from '../i18n';
import styles from './MicButton.module.css';

// ponytail: any cast — SpeechRecognition browser types are not in standard TS lib
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SpeechRecognitionAPI: any =
  typeof window !== 'undefined'
    ? ((window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition)
    : undefined;

interface Props {
  onTranscript: (text: string) => void;
  lang?: Lang;
}

export default function MicButton({ onTranscript, lang = 'fr' }: Props) {
  const [listening, setListening] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);

  if (!SpeechRecognitionAPI) return null;

  function startListening() {
    const rec = new SpeechRecognitionAPI();
    rec.lang = 'fr-CA';
    rec.continuous = false;
    rec.interimResults = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onresult = (e: any) => {
      onTranscript(e.results[0][0].transcript);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;
    rec.start();
    setListening(true);
  }

  function stopListening() {
    recognitionRef.current?.stop();
  }

  return (
    <button
      type="button"
      className={`${styles.micBtn} ${listening ? styles.micActive : ''}`}
      onClick={listening ? stopListening : startListening}
      aria-label={listening ? t(lang, 'Arrêter', 'Stop') : t(lang, 'Dicter', 'Dictate')}
      data-testid="mic-btn"
    >
      {listening ? '⏹' : '🎤'}
    </button>
  );
}
