import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import BrandMark from '../../components/BrandMark';
import { ApiError, fetchSurvey, submitSurvey } from '../../api/client';
import type { SurveyPublic } from '../../api/schema.d.ts';
import { DEMO_SURVEY, isDemoSurvey } from '../../dev/demoSurvey';
import type { Lang } from '../../i18n';
import { t } from '../../i18n';
import styles from './Survey.module.css';
import { Avatar } from '../../components/Avatar';

type Ans = boolean | null;
type Question = 'rating' | 'polite' | 'solved';

/** On-screen order; the first unanswered one gets focus on submit. */
const FOCUS_ID: Record<Question, string> = {
  rating: 'survey-star-1',
  polite: 'survey-polite-yes',
  solved: 'survey-solved-yes',
};

const COMMENTS_MAX = 2000;

/** Oui / Non as two separate buttons, each with its own icon; once picked,
 *  Oui turns green and Non red so the answer reads at a glance. */
function YesNo({
  lang, name, value, onChange, labelledBy, describedBy,
}: {
  lang: Lang; name: string; value: Ans; onChange: (v: boolean) => void;
  labelledBy: string; describedBy?: string;
}) {
  return (
    <div className={styles.yesNo} role="radiogroup" aria-labelledby={labelledBy} aria-describedby={describedBy}>
      {([true, false] as const).map((v) => (
        <label
          key={String(v)}
          className={[
            styles.yn,
            v ? styles.ynYes : styles.ynNo,
            value === v ? styles.ynOn : '',
            value !== null && value !== v ? styles.ynOff : '',
          ].join(' ')}
        >
          <input
            id={v ? `survey-${name}-yes` : undefined}
            type="radio"
            name={name}
            checked={value === v}
            onChange={() => onChange(v)}
          />
          <span className={styles.ynIcon} aria-hidden="true">
            <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.6"
                 strokeLinecap="round" strokeLinejoin="round">
              {v ? <path d="M4.5 10.5l3.5 3.5 7.5-8" /> : <path d="M5.5 5.5l9 9M14.5 5.5l-9 9" />}
            </svg>
          </span>
          {v ? t(lang, 'Oui', 'Yes') : t(lang, 'Non', 'No')}
        </label>
      ))}
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
  lang, value, onChange, labelledBy, describedBy,
}: {
  lang: Lang; value: number | null; onChange: (v: number) => void;
  labelledBy: string; describedBy?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const shown = hover ?? value ?? 0;
  return (
    <div className={styles.ratingRow}>
      <div className={styles.stars} role="radiogroup" aria-labelledby={labelledBy} aria-describedby={describedBy}
        onMouseLeave={() => setHover(null)}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            id={`survey-star-${n}`}
            type="button"
            role="radio"
            aria-checked={value === n}
            aria-label={t(lang, `${n} étoile${n > 1 ? 's' : ''} — ${RATING_LABELS[n - 1][0]}`,
              `${n} star${n > 1 ? 's' : ''} — ${RATING_LABELS[n - 1][1]}`)}
            className={`${styles.star} ${n <= shown ? styles.starOn : ''}`}
            onMouseEnter={() => setHover(n)}
            onClick={() => onChange(n)}
            data-testid={`survey-star-${n}`}
          >
            <svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true">
              <path d="M12 2.8l2.8 5.9 6.4.8-4.7 4.4 1.2 6.3L12 17.1l-5.7 3.1 1.2-6.3L2.8 9.5l6.4-.8z"
                fill={n <= shown ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            </svg>
          </button>
        ))}
      </div>
      <span className={styles.ratingHint} aria-live="polite">
        {shown > 0 ? t(lang, RATING_LABELS[shown - 1][0], RATING_LABELS[shown - 1][1]) : ''}
      </span>
    </div>
  );
}

export default function SurveyPage({ lang, onToggleLang }: { lang: Lang; onToggleLang: () => void }) {
  const { token = '' } = useParams();
  const demo = isDemoSurvey(token);
  const [survey, setSurvey] = useState<SurveyPublic | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [polite, setPolite] = useState<Ans>(null);
  const [rating, setRating] = useState<number | null>(null);
  const [solved, setSolved] = useState<Ans>(null);
  const [comments, setComments] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [alreadyDone, setAlreadyDone] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [missing, setMissing] = useState<Partial<Record<Question, boolean>>>({});

  useEffect(() => {
    if (!token) return;
    if (demo) { setSurvey(DEMO_SURVEY); return; }
    fetchSurvey(token)
      .then((s) => {
        setSurvey(s);
        if (s.already_submitted) { setDone(true); setAlreadyDone(true); }
      })
      .catch((err) => {
        setLoadError(err instanceof ApiError ? err.message : t(lang, 'Sondage introuvable', 'Survey not found'));
      });
  }, [token, lang, demo]);

  const answered = [rating != null, polite != null, solved != null].filter(Boolean).length;

  function answer<T>(q: Question, set: (v: T) => void) {
    return (v: T) => { set(v); setMissing((m) => ({ ...m, [q]: false })); };
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    // Say which questions are still open instead of a silently greyed button.
    const open: Partial<Record<Question, boolean>> = {
      rating: rating == null, polite: polite == null, solved: solved == null,
    };
    setMissing(open);
    const first = (Object.keys(FOCUS_ID) as Question[]).find((q) => open[q]);
    if (first) {
      document.getElementById(FOCUS_ID[first])?.focus();
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      if (demo) {
        // Demo: nothing is sent; a short pause so the busy state shows.
        await new Promise((r) => setTimeout(r, 400));
        setDone(true);
        return;
      }
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

  const missingNote = (q: Question) => missing[q] && (
    <p className={styles.fieldError} id={`survey-${q}-err`}>
      {q === 'rating'
        ? t(lang, 'Choisissez une note de 1 à 5 étoiles.', 'Pick a rating from 1 to 5 stars.')
        : t(lang, 'Répondez par oui ou non.', 'Answer yes or no.')}
    </p>
  );
  const errId = (q: Question) => (missing[q] ? `survey-${q}-err` : undefined);
  // A word joiner keeps the * on the same line as the label's last word.
  const req = <span className={styles.req} aria-hidden="true">{'\u2060'}*</span>;

  return (
    // Thank-you / invalid link: a short card, centred on the screen like the login.
    <div className={`${styles.page} ${(survey && done) || loadError ? styles.pageCenter : ''}`}>
      <div className={styles.card} data-testid="survey-card">
        {/* Brand left, language right — same row as the public request form. */}
        <div className={styles.brand}>
          <BrandMark product="Maintenance" />
          <button type="button" className={styles.langBtn} onClick={onToggleLang}
                  aria-label={lang === 'fr' ? 'Switch to English' : 'Passer en français'}
                  data-testid="survey-lang">
            {lang === 'fr' ? 'EN' : 'FR'}
          </button>
        </div>

        {demo && (
          <p className={styles.demoNote} data-testid="survey-demo-note">
            {t(lang, 'Démo — rien n’est enregistré.', 'Demo — nothing is saved.')}
          </p>
        )}

        {loadError && (
          <div className={styles.state} role="alert">
            <span className={`${styles.stateIcon} ${styles.stateIconWarn}`} aria-hidden="true">
              <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2.2"
                   strokeLinecap="round" strokeLinejoin="round"><path d="M12 8v5M12 16.5v.5" /><circle cx="12" cy="12" r="9" /></svg>
            </span>
            <h1 className={styles.title}>{t(lang, 'Lien de sondage invalide', 'Invalid survey link')}</h1>
            <p className={styles.sub}>
              {t(lang,
                'Ce lien n’existe pas ou a expiré. Vérifiez qu’il a été copié en entier.',
                'This link does not exist or has expired. Check that it was copied in full.')}
            </p>
            <p className={styles.hint}>{loadError}</p>
          </div>
        )}

        {!loadError && !survey && (
          <div className={styles.loading} aria-busy="true" aria-label={t(lang, 'Chargement…', 'Loading…')}>
            <span className={styles.skelTitle} />
            <span className={styles.skelLine} />
            <span className={styles.skelBlock} />
          </div>
        )}

        {survey && done && (
          <div className={styles.state} role="status" data-testid="survey-done">
            <span className={styles.stateIcon} aria-hidden="true">
              <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="2.4"
                   strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
            </span>
            <h1 className={styles.title}>
              {alreadyDone
                ? t(lang, 'Vous avez déjà répondu', 'You have already answered')
                : t(lang, 'Merci pour votre avis !', 'Thank you for your feedback!')}
            </h1>
            <p className={styles.sub}>
              {alreadyDone
                ? t(lang, 'Votre avis sur cette intervention est déjà enregistré. Merci !',
                  'Your feedback on this visit is already saved. Thank you!')
                : t(lang, 'Votre avis a bien été enregistré. Il nous aide à améliorer nos services.',
                  'Your feedback was saved. It helps us improve our service.')}
            </p>
            <p className={styles.hint}>{t(lang, 'Vous pouvez fermer cette page.', 'You can close this page.')}</p>
          </div>
        )}

        {survey && !done && (
          <form onSubmit={onSubmit} noValidate className={styles.form}>
            <div className={styles.intro}>
              <p className={styles.step}>
                {t(lang, `${answered} sur 3 réponses`, `${answered} of 3 answered`)}
                <span className={styles.stepBar} aria-hidden="true">
                  <span style={{ width: `${(answered / 3) * 100}%` }} />
                </span>
              </p>
              <h1 className={styles.title}>
                {t(lang, "Votre avis sur l'intervention", 'How was the visit?')}
              </h1>
              <p className={styles.sub}>
                {t(lang, 'Trois questions rapides, moins d’une minute.', 'Three quick questions, under a minute.')}
              </p>
            </div>

            {(survey.technician_name || survey.building_address) && (
              <div className={styles.visit}>
                <svg className={styles.visitIcon} viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none"
                     stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z" />
                </svg>
                <div className={styles.visitText}>
                  {survey.technician_name && (
                    <span className={styles.visitTech}>
                      {t(lang, 'Technicien', 'Technician')} :
                      <Avatar name={survey.technician_name} size="xs" />
                      <strong>{survey.technician_name}</strong>
                    </span>
                  )}
                  {survey.building_address && <span className={styles.visitMeta}>{survey.building_address}</span>}
                </div>
              </div>
            )}

            <section className={styles.question}>
              <span className={styles.questionLabel} id="survey-rating-label">
                <span className={styles.qNum}>1</span>
                <span>{t(lang, "Dans l'ensemble, quelle note donnez-vous ?", 'Overall, how would you rate the visit?')}{req}</span>
              </span>
              <StarRating lang={lang} value={rating} onChange={answer('rating', setRating)}
                          labelledBy="survey-rating-label" describedBy={errId('rating')} />
              {missingNote('rating')}
            </section>

            <section className={styles.question}>
              <span className={styles.questionLabel} id="survey-polite-label">
                <span className={styles.qNum}>2</span>
                <span>{t(lang, 'La personne était-elle polie ?', 'Was the person polite?')}{req}</span>
              </span>
              <YesNo lang={lang} name="polite" value={polite} onChange={answer('polite', setPolite)}
                     labelledBy="survey-polite-label" describedBy={errId('polite')} />
              {missingNote('polite')}
            </section>

            <section className={styles.question}>
              <span className={styles.questionLabel} id="survey-solved-label">
                <span className={styles.qNum}>3</span>
                <span>{t(lang, 'Le problème a-t-il été résolu ?', 'Was the problem solved?')}{req}</span>
              </span>
              <YesNo lang={lang} name="solved" value={solved} onChange={answer('solved', setSolved)}
                     labelledBy="survey-solved-label" describedBy={errId('solved')} />
              {missingNote('solved')}
            </section>

            <section className={styles.question}>
              <label className={styles.questionLabel} htmlFor="survey-comments">
                {t(lang, 'Commentaires', 'Comments')} <span className={styles.optional}>{t(lang, '(optionnel)', '(optional)')}</span>
              </label>
              <textarea
                id="survey-comments"
                className={styles.comments}
                value={comments}
                placeholder={t(lang, 'Ce qui s’est bien passé, ce qu’on peut améliorer…', 'What went well, what we could improve…')}
                onChange={(e) => setComments(e.target.value)}
                maxLength={COMMENTS_MAX}
                aria-describedby="survey-comments-count"
              />
              <span className={styles.counter} id="survey-comments-count">
                {comments.length} / {COMMENTS_MAX}
              </span>
            </section>

            {Object.values(missing).some(Boolean) && (
              <p className={styles.error} role="alert">
                {t(lang, 'Il reste des questions sans réponse.', 'Some questions are still unanswered.')}
              </p>
            )}
            {submitError && <p className={styles.error} role="alert">{submitError}</p>}

            <button
              type="submit"
              className={styles.submit}
              disabled={submitting}
              aria-busy={submitting}
              data-testid="survey-submit"
            >
              {submitting && <span className={styles.spinner} aria-hidden="true" />}
              {submitting ? t(lang, 'Envoi…', 'Sending…') : t(lang, 'Envoyer mon avis', 'Send my feedback')}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
