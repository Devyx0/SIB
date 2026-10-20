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

export default function SurveyPage({ lang }: { lang: Lang }) {
  const { token = '' } = useParams();
  const [survey, setSurvey] = useState<SurveyPublic | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [polite, setPolite] = useState<Ans>(null);
  const [satisfied, setSatisfied] = useState<Ans>(null);
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

  const ready = polite != null && satisfied != null && solved != null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitSurvey(token, {
        polite: polite!,
        satisfied: satisfied!,
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

            <div className={styles.question}>
              <span className={styles.questionLabel}>
                {t(lang, 'La personne était-elle polie?', 'Was the person polite?')}
              </span>
              <YesNo lang={lang} value={polite} onChange={setPolite} />
            </div>

            <div className={styles.question} style={{ marginTop: 16 }}>
              <span className={styles.questionLabel}>
                {t(lang, "Êtes-vous satisfait dans l'ensemble?", 'Overall, are you satisfied?')}
              </span>
              <YesNo lang={lang} value={satisfied} onChange={setSatisfied} />
            </div>

            <div className={styles.question} style={{ marginTop: 16 }}>
              <span className={styles.questionLabel}>
                {t(lang, 'Le problème a-t-il été résolu?', 'Was the problem solved?')}
              </span>
              <YesNo lang={lang} value={solved} onChange={setSolved} />
            </div>

            <div className={styles.question} style={{ marginTop: 16 }}>
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
