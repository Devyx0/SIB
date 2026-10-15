import { useRef, useState } from 'react';
import type { Lang } from '../i18n';
import { t } from '../i18n';
import styles from './JustificationModal.module.css';

// ponytail: any cast — SpeechRecognition browser types are not in standard TS lib
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SpeechRecognitionAPI: any =
  typeof window !== 'undefined'
    ? ((window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition)
    : undefined;

interface Props {
  open: boolean;
  onSave: (text: string, inputMethod: 'voice' | 'typed') => void;
  onCancel: () => void;
  lang?: Lang;
}

export default function JustificationModal({ open, onSave, onCancel, lang = 'fr' }: Props) {
  const [text, setText] = useState('');
  const [listening, setListening] = useState(false);
  const inputMethodRef = useRef<'voice' | 'typed'>('typed');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);

  if (!open) return null;

  function handleSave() {
    onSave(text.trim(), inputMethodRef.current);
    setText('');
    inputMethodRef.current = 'typed';
  }

  function startListening() {
    if (!SpeechRecognitionAPI) return;
    const rec = new SpeechRecognitionAPI();
    rec.lang = 'fr-CA';
    rec.continuous = false;
    rec.interimResults = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onresult = (e: any) => {
      const transcript = e.results[0][0].transcript;
      setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
      inputMethodRef.current = 'voice';
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

  const canSave = text.trim().length >= 10;

  return (
    <div className={styles.overlay} role="dialog" aria-modal aria-label={t(lang, 'Justification', 'Justification')}>
      <div className={styles.modal}>
        <h2 className={styles.heading}>{t(lang, 'Justification requise', 'Justification required')}</h2>
        <p className={styles.hint}>{t(lang, 'Minimum 10 caractères.', 'Minimum 10 characters.')}</p>

        <textarea
          className={styles.textarea}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            inputMethodRef.current = 'typed';
          }}
          rows={4}
          placeholder={t(lang, 'Expliquez votre décision…', 'Explain your decision…')}
          data-testid="justification-text"
        />

        <div className={styles.actions}>
          {SpeechRecognitionAPI && (
            <button
              type="button"
              className={`${styles.micBtn} ${listening ? styles.micActive : ''}`}
              onClick={listening ? stopListening : startListening}
              aria-label={listening ? t(lang, 'Arrêter', 'Stop') : t(lang, 'Dicter', 'Dictate')}
              data-testid="mic-btn"
            >
              {listening ? '⏹' : '🎤'}
            </button>
          )}
          <button type="button" className={styles.cancelBtn} onClick={onCancel}>
            {t(lang, 'Annuler', 'Cancel')}
          </button>
          <button
            type="button"
            className={styles.saveBtn}
            onClick={handleSave}
            disabled={!canSave}
            data-testid="justification-save"
          >
            {t(lang, 'Confirmer', 'Confirm')}
          </button>
        </div>
      </div>
    </div>
  );
}
