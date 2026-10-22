import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import BrandMark from '../../components/BrandMark';
import { ApiError, fetchSurvey, submitSurvey } from '../../api/client';
import type { SurveyPublic } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t } from '../../i18n';
import styles from './Survey.module.css';

type Ans = boolean | null;

function YesNo({
  lang, value, onChange,
}: { lang: Lang; value: Ans; onChange: (v: boolean) => void }) {
  return (
    <div className={styles.choices}>
      <button
        type="button"
        className={`${styles.choice} ${value === true ? styles.choiceSelected : ''}`}
        onClick={() => onChange(true)}
      >
        {t(lang, 'Oui', 'Yes')}
      </button>
      <button
        type="button"
        className={`${styles.choice} ${value === false ? styles.choiceSelected : ''}`}
        onClick={() => onChange(false)}
      >
        {t(lang, 'Non', 'No')}
      </button>
    </div>
  );
}

const RATING_LABELS: Array<readonly [string, string]> = [
  ['Très insatisfait', 'Very dissatisfied'],
  ['Insatisfait', 'Dissatisfied'],
  ['Correct', 'Okay'],
  ['Satisfait', 'Satisfied'],
  ['Très satisfait', 'Very satisfied'],
];

function StarRating({
  lang, value, onChange, labelledBy,
}: { lang: Lang; value: number | null; onChange: (v: number) => void; labelledBy: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const shown = hover ?? value ?? 0;
  return (
    <div className={styles.ratingRow}>
      <div className={styles.stars} role="radiogroup" aria-labelledby={labelledBy}
        onMouseLeave={() => setHover(null)}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            aria-label={t(lang, `${n} étoile${n > 1 ? 's' : ''}`, `${n} star${n > 1 ? 's' : ''}`)}
            className={`${styles.star} ${n <= shown ? styles.starOn : ''}`}
            onMouseEnter={() => setHover(n)}
            onClick={() => onChange(n)}
            data-testid={`survey-star-${n}`}
          >
            {n <= shown ? '★' : '☆'}
          </button>
        ))}
      </div>
      <span className={styles.ratingHint} aria-live="polite">
        {shown > 0 ? t(lang, RATING_LABELS[shown - 1][0], RATING_LABELS[shown - 1][1]) : ''}
      </span>
    </div>
  );
}

export default function SurveyPage({ lang }: { lang: Lang }) {
  const { token = '' } = useParams();
  const [survey, setSurvey] = useState<SurveyPublic | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [polite, setPolite] = useState<Ans>(null);
  const [rating, setRating] = useState<number | null>(null);
  const [solved, setSolved] = useState<Ans>(null);
  const [comments, setComments] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetchSurvey(token)
      .then((s) => {
        setSurvey(s);
        if (s.already_submitted) setDone(true);
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : t(lang, 'Sondage introuvable', 'Survey not found'));
      });
  }, [token, lang]);

  const ready = polite != null && rating != null && solved != null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitSurvey(token, {
        polite: polite!,
        satisfaction_rating: rating!,
        problem_solved: solved!,
        comments: comments.trim() || null,
      });
      setDone(true);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : t(lang, 'Échec — réessayez', 'Failed — retry'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.brand}>
          <BrandMark product="Maintenance" />
        </div>

        {loadError && <p className={styles.error} role="alert">{loadError}</p>}

        {!loadError && !survey && (
          <p className={styles.meta}>{t(lang, 'Chargement…', 'Loading…')}</p>
        )}

        {survey && done && (
          <p className={styles.done} data-testid="survey-done">
            {t(
              lang,
              'Merci — votre avis a bien été enregistré.',
              'Thank you — your feedback was saved.',
            )}
          </p>
        )}

        {survey && !done && (
          <form onSubmit={onSubmit}>
            <h1 className={styles.title}>
              {t(lang, "Votre avis sur l'intervention", 'How was the visit?')}
            </h1>
            <p className={styles.meta}>
              {[survey.technician_name, survey.building_address].filter(Boolean).join(' · ') || '—'}
            </p>

            {/* 1) overall rating · 2) the two yes/no questions · 3) comments */}
            <div className={styles.question} style={{ marginTop: 24 }}>
              <span className={styles.questionLabel} id="survey-rating-label">
                {t(lang, "Dans l'ensemble, quelle note donnez-vous?", 'Overall, how would you rate the visit?')}
              </span>
              <StarRating lang={lang} value={rating} onChange={setRating} labelledBy="survey-rating-label" />
            </div>

            <div className={styles.question} style={{ marginTop: 24}}>
              <span className={styles.questionLabel}>
                {t(lang, 'La personne était-elle polie?', 'Was the person polite?')}
              </span>
              <YesNo lang={lang} value={polite} onChange={setPolite} />
            </div>

            <div className={styles.question} style={{ marginTop: 24 }}>
              <span className={styles.questionLabel}>
                {t(lang, 'Le problème a-t-il été résolu?', 'Was the problem solved?')}
              </span>
              <YesNo lang={lang} value={solved} onChange={setSolved} />
            </div>

            <div className={styles.question} style={{ marginTop: 24 }}>
              <label className={styles.questionLabel} htmlFor="survey-comments">
                {t(lang, 'Commentaires (optionnel)', 'Comments (optional)')}
              </label>
              <textarea
                id="survey-comments"
                className={styles.comments}
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                maxLength={2000}
              />
            </div>

            {submitError && <p className={styles.error} role="alert">{submitError}</p>}

            <button
              type="submit"
              className={styles.submit}
              disabled={!ready || submitting}
              style={{ marginTop: 20, width: '100%' }}
              data-testid="survey-submit"
            >
              {t(lang, 'Envoyer', 'Submit')}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
