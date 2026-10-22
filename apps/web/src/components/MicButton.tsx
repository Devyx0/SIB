import type { Lang } from '../i18n';
import { t } from '../i18n';
import { useDictation } from '../hooks/useDictation';
import styles from './MicButton.module.css';

// Dictation toggle for a text field (AssemblyAI Universal-3.6 Pro, see
// hooks/useDictation). Each finished turn is handed to `onTranscript`; the
// words still being recognised show next to the button. Renders nothing
// where the browser can't stream audio — the field stays typeable.

interface Props {
  onTranscript: (text: string) => void;
  lang?: Lang;
}

export default function MicButton({ onTranscript, lang = 'fr' }: Props) {
  const dictation = useDictation({ lang, onFinal: onTranscript });
  if (!dictation.supported) return null;

  const errorText = dictation.error === 'not-allowed'
    ? t(lang, 'Micro bloqué', 'Microphone blocked')
    : dictation.error === 'no-microphone'
      ? t(lang, 'Aucun micro', 'No microphone')
      : dictation.error
        ? t(lang, 'Dictée indisponible', 'Dictation unavailable')
        : null;

  return (
    <span className={styles.wrap}>
      <button
        type="button"
        className={`${styles.micBtn} ${dictation.listening ? styles.micActive : ''}`}
        onClick={() => void dictation.toggle()}
        aria-pressed={dictation.listening}
        aria-label={dictation.listening ? t(lang, 'Arrêter la dictée', 'Stop dictation') : t(lang, 'Dicter', 'Dictate')}
        title={dictation.listening ? t(lang, 'Arrêter la dictée', 'Stop dictation') : t(lang, 'Dicter', 'Dictate')}
        data-testid="mic-btn"
      >
        {dictation.listening ? (
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
          </svg>
        )}
      </button>
      {dictation.connecting && <span className={styles.note}>{t(lang, 'Connexion…', 'Connecting…')}</span>}
      {!dictation.connecting && dictation.interim && (
        <span className={styles.interim} aria-live="polite">{dictation.interim}</span>
      )}
      {errorText && <span className={styles.error} role="alert">{errorText}</span>}
    </span>
  );
}
