import { useEffect, useRef, useState } from 'react';
import type { Lang } from '../i18n';
import { t } from '../i18n';
import MicButton from './MicButton';
import styles from './JustificationModal.module.css';

interface Props {
  open: boolean;
  onSave: (text: string, inputMethod: 'voice' | 'typed') => void;
  onCancel: () => void;
  lang?: Lang;
  context?: string;
}

export default function JustificationModal({ open, onSave, onCancel, lang = 'fr', context }: Props) {
  const [text, setText] = useState('');
  const inputMethodRef = useRef<'voice' | 'typed'>('typed');

  useEffect(() => {
    if (!open) return;
    document.body.classList.add('modal-open');
    return () => { document.body.classList.remove('modal-open'); };
  }, [open]);

  if (!open) return null;

  function handleSave() {
    onSave(text.trim(), inputMethodRef.current);
    setText('');
    inputMethodRef.current = 'typed';
  }

  const canSave = text.trim().length >= 10;

  return (
    <div className={styles.overlay} role="dialog" aria-modal aria-label={t(lang, 'Justification', 'Justification')}>
      <div className={styles.modal}>
        <h2 className={styles.heading}>{t(lang, 'Justification requise', 'Justification required')}</h2>
        {context && (
          <p className={styles.context} data-testid="justification-context">{context}</p>
        )}
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
          <MicButton
            onTranscript={(transcript) => {
              setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
              inputMethodRef.current = 'voice';
            }}
            lang={lang}
          />
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
