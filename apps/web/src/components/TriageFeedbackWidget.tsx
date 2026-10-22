import { forwardRef, useEffect, useImperativeHandle, useState } from 'react';
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

/** Lets a parent save the feedback with its own button (the call popup's footer). */
export interface FeedbackHandle {
  save: () => Promise<void>;
  /** Back to the saved rating (or none). */
  reset: () => void;
}

export interface FeedbackState {
  /** Something to save: a new/changed rating, or proposals waiting to be dispatched. */
  dirty: boolean;
  /** The rating can be saved (a reason of 10+ chars when not « utile »). */
  valid: boolean;
  /** Saving will also dispatch the AI's proposed tasks. */
  dispatch: boolean;
}

interface Props {
  requestId: number;
  lang?: Lang;
  /** false = no own save button; the parent saves through the ref (default true). */
  standalone?: boolean;
  onStateChange?: (s: FeedbackState) => void;
  /** When true, the primary action is « Dispatcher » (feedback then accept proposals). */
  hasProposals?: boolean;
  /** Accept remaining AI proposals (with local edits). Called after feedback is saved. */
  onDispatchProposals?: () => Promise<void>;
  /** 'bar' = one compact row for the call popup's footer (no heading or hint). */
  variant?: 'card' | 'bar';
  /** A level was picked; `willSave` = picking it leaves something to save. */
  onPick?: (level: FeedbackLevel, willSave: boolean) => void;
}

const TriageFeedbackWidget = forwardRef<FeedbackHandle, Props>(function TriageFeedbackWidget({
  requestId, lang = 'fr', hasProposals = false, onDispatchProposals, standalone = true, onStateChange,
  variant = 'card', onPick,
}, ref) {
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

  const changed = level !== null && (
    level !== (existing?.level ?? null) || reason.trim() !== (existing?.reason ?? '').trim()
  );
  const dirty = changed || (isDispatch && level !== null);
  useEffect(() => {
    onStateChange?.({ dirty, valid: canSave, dispatch: isDispatch });
  }, [dirty, canSave, isDispatch, onStateChange]);

  useImperativeHandle(ref, () => ({
    save: async () => {
      if (!dirty || !canSave) return;
      await mutation.mutateAsync();
    },
    reset: () => {
      setLevel(existing?.level ?? null);
      setReason(existing?.reason ?? '');
    },
  }), [dirty, canSave, mutation, existing]);

  function pick(value: FeedbackLevel) {
    setLevel(value);
    const willSave = value !== (existing?.level ?? null)
      || reason.trim() !== (existing?.reason ?? '').trim()
      || isDispatch;
    onPick?.(value, willSave);
  }

  const levelButtons = (
    <div className={styles.levelBtns} role="group" aria-label={t(lang, 'Retour sur le résumé IA', 'AI summary feedback')}>
      {LEVELS.map(({ value, fr, en }) => (
        <button
          key={value}
          type="button"
          className={`${styles.levelBtn} ${level === value ? styles.levelActive : ''}`}
          aria-pressed={level === value}
          onClick={() => pick(value)}
          data-testid={`feedback-level-${value.replace(/ /g, '-')}`}
        >
          {lang === 'fr' ? fr : en}
        </button>
      ))}
    </div>
  );

  const reasonBox = needsReason && (
    <div className={styles.reasonRow}>
      <textarea
        className={styles.textarea}
        value={reason}
        onChange={(e) => { setReason(e.target.value); setInputMethod('typed'); }}
        rows={variant === 'bar' ? 2 : 3}
        aria-label={t(lang, 'Pourquoi ? (10 car. min.)', 'Why? (10 chars min.)')}
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
  );

  const errorLine = mutation.isError && (
    <p className={styles.error} role="alert" data-testid="feedback-error">
      {mutation.error instanceof ApiError ? mutation.error.message : t(lang, 'Erreur — réessayez.', 'Error — retry.')}
    </p>
  );

  // Footer row of the call popup: label + the three levels; the comment box
  // opens under them when the summary was only partly or not useful.
  if (variant === 'bar') {
    return (
      <div className={styles.bar} data-testid="feedback-widget">
        <div className={styles.barRow}>
          <span className={styles.barLabel}>{t(lang, 'Résumé IA', 'AI summary')}</span>
          {levelButtons}
        </div>
        {reasonBox}
        {errorLine}
      </div>
    );
  }

  return (
    <div className={styles.widget} data-testid="feedback-widget">
      <h4 className={styles.heading}>{t(lang, 'Retour sur le résumé IA', 'AI summary feedback')}</h4>
      <p className={styles.hint}>
        {isDispatch
          ? standalone
            ? t(lang,
              'Utile → Dispatcher. Partiellement / Pas utile → commentez (min. 10 car.), corrigez les tâches, puis Dispatcher.',
              'Useful → Dispatch. Partially / Not useful → comment (min. 10 chars), edit tasks, then Dispatch.')
            : t(lang,
              'Choisissez votre retour (commentaire de 10 car. min. si pas utile), puis « Enregistrer et dispatcher » en bas.',
              'Pick your feedback (10-char comment if not useful), then « Save and dispatch » at the bottom.')
          : standalone
            ? t(lang, 'Mettez à jour votre retour sur le résumé IA.', 'Update your feedback on the AI summary.')
            : t(lang, 'Votre retour est enregistré avec le bouton « Enregistrer » en bas.', 'Your feedback is saved with « Save » at the bottom.')}
      </p>

      {levelButtons}
      {reasonBox}
      {errorLine}

      {standalone && <button
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
      </button>}

      {existing && !mutation.isPending && !mutation.isError && (
        <p className={styles.savedNote} data-testid="feedback-saved-note">
          {t(lang, `Retour enregistré : ${existing.level}`, `Saved: ${existing.level}`)}
        </p>
      )}
    </div>
  );
});

export default TriageFeedbackWidget;
