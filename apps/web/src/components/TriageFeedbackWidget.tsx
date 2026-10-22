import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, fetchFeedback, upsertFeedback } from '../api/client';
import type { TriageFeedback } from '../api/client';
import type { Lang } from '../i18n';
import { t } from '../i18n';
import MicButton from './MicButton';
import styles from './TriageFeedbackWidget.module.css';

type FeedbackLevel = 'utile' | 'partiellement utile' | 'pas utile';

const LEVELS: Array<{ value: FeedbackLevel; fr: string; en: string }> = [
  { value: 'utile',              fr: 'Utile',               en: 'Useful' },
  { value: 'partiellement utile', fr: 'Partiellement utile', en: 'Partially useful' },
  { value: 'pas utile',          fr: 'Pas utile',           en: 'Not useful' },
];

interface Props {
  requestId: number;
  lang?: Lang;
  /** When true, the primary action is « Dispatcher » (feedback then accept proposals). */
  hasProposals?: boolean;
  /** Accept remaining AI proposals (with local edits). Called after feedback is saved. */
  onDispatchProposals?: () => Promise<void>;
}

export default function TriageFeedbackWidget({
  requestId, lang = 'fr', hasProposals = false, onDispatchProposals,
}: Props) {
  const qc = useQueryClient();

  const { data: existing } = useQuery<TriageFeedback | null>({
    queryKey: ['feedback', requestId],
    queryFn: async () => {
      try {
        return await fetchFeedback(requestId);
      } catch (err) {
        if (err instanceof ApiError && err.code === 'NOT_FOUND') return null;
        throw err;
      }
    },
    staleTime: 30_000,
  });

  const [level, setLevel] = useState<FeedbackLevel | null>(null);
  const [reason, setReason] = useState('');
  const [, setInputMethod] = useState<'typed' | 'voice'>('typed');

  useEffect(() => {
    if (existing) {
      setLevel(existing.level);
      setReason(existing.reason ?? '');
    }
  }, [existing?.feedback_id]);

  const mutation = useMutation({
    mutationFn: async () => {
      const result = await upsertFeedback(requestId, {
        level: level!,
        reason: reason.trim() || null,
      });
      if (hasProposals && onDispatchProposals) {
        await onDispatchProposals();
      }
      return result;
    },
    onSuccess: (result) => {
      qc.setQueryData(['feedback', requestId], result);
      void qc.invalidateQueries({ queryKey: ['request', requestId] });
      void qc.invalidateQueries({ queryKey: ['tasks'] });
      void qc.invalidateQueries({ queryKey: ['requests'] });
    },
  });

  const needsReason = level === 'partiellement utile' || level === 'pas utile';
  const canSave = level !== null && (!needsReason || reason.trim().length >= 10);
  const isDispatch = hasProposals;

  return (
    <div className={styles.widget} data-testid="feedback-widget">
      <h4 className={styles.heading}>{t(lang, 'Retour sur le résumé IA', 'AI summary feedback')}</h4>
      <p className={styles.hint}>
        {isDispatch
          ? t(lang,
            'Utile → Dispatcher. Partiellement / Pas utile → commentez (min. 10 car.), corrigez les tâches, puis Dispatcher.',
            'Useful → Dispatch. Partially / Not useful → comment (min. 10 chars), edit tasks, then Dispatch.')
          : t(lang,
            'Mettez à jour votre retour sur le résumé IA.',
            'Update your feedback on the AI summary.')}
      </p>

      <div className={styles.levelBtns} role="group" aria-label={t(lang, 'Niveau de retour', 'Feedback level')}>
        {LEVELS.map(({ value, fr, en }) => (
          <button
            key={value}
            type="button"
            className={`${styles.levelBtn} ${level === value ? styles.levelActive : ''}`}
            onClick={() => setLevel(value)}
            data-testid={`feedback-level-${value.replace(/ /g, '-')}`}
          >
            {lang === 'fr' ? fr : en}
          </button>
        ))}
      </div>

      {needsReason && (
        <div className={styles.reasonRow}>
          <textarea
            className={styles.textarea}
            value={reason}
            onChange={(e) => { setReason(e.target.value); setInputMethod('typed'); }}
            rows={3}
            placeholder={t(lang, 'Expliquez (min. 10 car.)…', 'Explain (min. 10 chars.)…')}
            data-testid="feedback-reason"
          />
          <MicButton
            onTranscript={(text) => {
              setReason((prev) => (prev ? `${prev} ${text}` : text));
              setInputMethod('voice');
            }}
            lang={lang}
          />
        </div>
      )}

      {mutation.isError && (
        <p className={styles.error} data-testid="feedback-error">
          {mutation.error instanceof ApiError ? mutation.error.message : t(lang, 'Erreur — réessayez.', 'Error — retry.')}
        </p>
      )}

      <button
        type="button"
        className={styles.saveBtn}
        onClick={() => mutation.mutate()}
        disabled={!canSave || mutation.isPending}
        data-testid={isDispatch ? 'feedback-dispatch' : 'feedback-save'}
      >
        {mutation.isPending
          ? (isDispatch
            ? t(lang, 'Dispatch…', 'Dispatching…')
            : t(lang, 'Enregistrement…', 'Saving…'))
          : isDispatch
            ? t(lang, 'Dispatcher', 'Dispatch')
            : existing
              ? t(lang, 'Mettre à jour', 'Update')
              : t(lang, 'Enregistrer', 'Save')}
      </button>

      {existing && !mutation.isPending && !mutation.isError && (
        <p className={styles.savedNote} data-testid="feedback-saved-note">
          {t(lang, `Retour enregistré : ${existing.level}`, `Saved: ${existing.level}`)}
        </p>
      )}
    </div>
  );
}
