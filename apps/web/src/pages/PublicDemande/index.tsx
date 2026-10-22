import { useState } from 'react';
import type { ReactNode } from 'react';
import BrandMark from '../../components/BrandMark';
import PhotoPicker, { type PickedPhoto } from '../../components/PhotoPicker';
import Select from '../../components/Select';
import Turnstile from '../../components/Turnstile';
import {
  ApiError,
  publicIntakeLookup,
  publicIntakeSubmit,
  type AccessChoice,
  type AnimalsChoice,
  type PublicIntakeLookupResponse,
} from '../../api/client';
import { shrinkImage } from '../../lib/shrinkImage';
import { taxonomyElementOptions } from '../../lib/taxonomyElements';
import type { Lang } from '../../i18n';
import { t } from '../../i18n';
import styles from './PublicDemande.module.css';

/** Central maintenance / front desk — DISP in client guide. Override via env. */
const FRONT_DESK_PHONE =
  (import.meta.env.VITE_FRONT_DESK_PHONE as string | undefined)?.trim() || '581-531-1011';

function accessOptions(lang: Lang): { value: AccessChoice; label: string }[] {
  return [
    { value: 'yes', label: t(lang, 'Accès autorisé', 'Access granted') },
    { value: 'yes_instructions', label: t(lang, 'Accès avec instructions', 'Access with instructions') },
    { value: 'tenant_required', label: t(lang, 'Présence du locataire exigée', 'Tenant presence required') },
    { value: 'common_area', label: t(lang, 'Espace commun', 'Common area') },
  ];
}

type FieldKey = 'accessDetails' | 'animals' | 'problem' | 'element' | 'symptome' | 'composante' | 'emplacement';

/** id of the control each field error points at, in on-screen order: the
 *  first missing one gets focus. */
const FIELD_ID: Record<FieldKey, string> = {
  problem: 'pub-problem',
  element: 'pub-element',
  symptome: 'pub-symptome',
  composante: 'pub-composante',
  emplacement: 'pub-emplacement',
  accessDetails: 'pub-access-details',
  animals: 'pub-animals-oui',
};

function isLookupNoMatch(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  if (err.code === 'NOT_FOUND') return true;
  // Ambiguous multi-unit match — same UX: call the desk, no free-text apartment.
  return err.code === 'VALIDATION_FAILED' && /plusieurs logements|multiple|contactez/i.test(err.message);
}

export default function PublicDemande({
  lang,
  onToggleLang,
}: {
  lang: Lang;
  onToggleLang: () => void;
}) {
  const [mode, setMode] = useState<'phone' | 'email'>('phone');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [lookupToken, setLookupToken] = useState<string | null>(null);
  const [submitToken, setSubmitToken] = useState<string | null>(null);
  const [lookupReset, setLookupReset] = useState(0);
  const [submitReset, setSubmitReset] = useState(0);

  const [profile, setProfile] = useState<PublicIntakeLookupResponse | null>(null);
  const [lookingUp, setLookingUp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [doneId, setDoneId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showDeskPhone, setShowDeskPhone] = useState(false);

  const [access, setAccess] = useState<AccessChoice>('yes');
  const [accessDetails, setAccessDetails] = useState('');
  const [animals, setAnimals] = useState<AnimalsChoice | null>(null);
  const [animalDetails, setAnimalDetails] = useState('');
  const [element, setElement] = useState('');
  const [symptome, setSymptome] = useState('');
  const [composante, setComposante] = useState('');
  const [emplacement, setEmplacement] = useState('');
  const [problem, setProblem] = useState('');
  const [attention, setAttention] = useState('');
  const [photos, setPhotos] = useState<PickedPhoto[]>([]);
  // Per-field messages, shown under the field they belong to.
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({});

  function clearError(k: FieldKey) {
    setFieldErrors((prev) => (prev[k] ? { ...prev, [k]: undefined } : prev));
  }

  async function onLookup(e: React.FormEvent) {
    e.preventDefault();
    if (!lookupToken || lookingUp) return;
    setLookingUp(true);
    setErrorMsg(null);
    setShowDeskPhone(false);
    try {
      const res = await publicIntakeLookup({
        phone: mode === 'phone' ? phone.trim() : undefined,
        email: mode === 'email' ? email.trim() : undefined,
        turnstile_token: lookupToken,
      });
      setProfile(res);
      setAnimals(null);
      setLookupToken(null);
      setLookupReset((k) => k + 1);
    } catch (err) {
      if (isLookupNoMatch(err)) {
        setShowDeskPhone(true);
      } else {
        setErrorMsg(err instanceof ApiError ? err.message : t(lang, 'Échec — réessayez', 'Failed — retry'));
      }
      setLookupReset((k) => k + 1);
      setLookupToken(null);
    } finally {
      setLookingUp(false);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!profile || !submitToken || submitting) return;
    // Each missing answer gets its own message under its field; focus goes
    // to the first one so the person lands right where to fix it.
    const missing: Partial<Record<FieldKey, string>> = {};
    if (access === 'yes_instructions' && !accessDetails.trim()) {
      missing.accessDetails = t(lang, 'Précisez comment entrer (code, clé, etc.).', 'Say how to get in (code, key, etc.).');
    }
    if (profile.pets_allowed && animals == null) {
      missing.animals = t(lang, 'Indiquez si un animal est présent.', 'Say whether a pet is present.');
    }
    if (!problem.trim()) missing.problem = t(lang, 'Décrivez le problème en quelques mots.', 'Describe the problem in a few words.');
    if (!element.trim()) missing.element = t(lang, 'Choisissez ce qui est touché.', 'Choose what is affected.');
    if (!symptome.trim()) missing.symptome = t(lang, 'Indiquez le symptôme (ex. fuite, bruit).', 'Give the symptom (e.g. leak, noise).');
    if (!composante.trim()) missing.composante = t(lang, 'Indiquez la pièce en cause (ex. robinet).', 'Give the part involved (e.g. faucet).');
    if (!emplacement.trim()) missing.emplacement = t(lang, 'Indiquez où (ex. cuisine).', 'Say where (e.g. kitchen).');
    setFieldErrors(missing);
    const first = (Object.keys(FIELD_ID) as FieldKey[]).find((k) => missing[k]);
    if (first) {
      setErrorMsg(null);
      const el = document.getElementById(FIELD_ID[first]);
      el?.focus();
      el?.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
      return;
    }
    setSubmitting(true);
    setErrorMsg(null);
    try {
      let encoded: Awaited<ReturnType<typeof shrinkImage>>[] = [];
      try {
        encoded = await Promise.all(photos.map((p) => shrinkImage(p.file)));
      } catch {
        setErrorMsg(t(lang, 'Une photo est illisible.', 'A photo could not be read.'));
        return;
      }
      const res = await publicIntakeSubmit({
        session_token: profile.session_token,
        turnstile_token: submitToken,
        access,
        access_details: accessDetails.trim() || undefined,
        animals: profile.pets_allowed && animals ? animals : undefined,
        animal_details: profile.pets_allowed && animals === 'oui' ? (animalDetails.trim() || undefined) : undefined,
        problem: problem.trim(),
        element: element.trim(),
        symptome: symptome.trim(),
        composante: composante.trim(),
        emplacement: emplacement.trim(),
        attention: attention.trim() || undefined,
        ui_lang: lang,
        photos: encoded.map((p) => ({ mime: p.mime, data_base64: p.data_base64 })),
      });
      setDoneId(res.request_id);
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : t(lang, 'Échec — réessayez', 'Failed — retry'));
      setSubmitReset((k) => k + 1);
      setSubmitToken(null);
    } finally {
      setSubmitting(false);
    }
  }

  // Brand on the left, language on the right — the same boxed FR / EN button
  // as the staff app, over a divider like the login card.
  const brandRow = (
    <div className={styles.brand}>
      <BrandMark />
      <button type="button" className={styles.langBtn} onClick={onToggleLang}
              aria-label={lang === 'fr' ? 'Switch to English' : 'Passer en français'}>
        {lang === 'fr' ? 'EN' : 'FR'}
      </button>
    </div>
  );

  if (doneId != null) {
    return (
      <div className={`${styles.page} ${styles.pageCenter}`}>
        <div className={styles.card} data-testid="public-demande-done">
          {brandRow}
          <div className={styles.done} role="status">
            <span className={styles.doneIcon} aria-hidden="true">
              <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="2.4"
                   strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
            </span>
            <h1 className={styles.title}>{t(lang, 'Demande envoyée', 'Request submitted')}</h1>
            <p className={styles.sub}>
              {t(lang,
                'La maintenance a bien reçu votre demande. Nous vous contacterons pour planifier la visite.',
                'Maintenance has received your request. We will contact you to schedule the visit.')}
            </p>
            {/* The number a tenant may be asked for: set apart, easy to note. */}
            <div className={styles.doneRef}>
              <span className={styles.doneRefLabel}>{t(lang, 'Numéro de demande', 'Request number')}</span>
              <strong className={styles.doneRefNum}>#{doneId}</strong>
            </div>
          </div>
          <button type="button" className={`${styles.btn} ${styles.btnSecondary}`}
                  onClick={() => window.location.assign(window.location.pathname)}>
            {t(lang, 'Faire une autre demande', 'Submit another request')}
          </button>
          <p className={styles.doneHelp}>
            {t(lang, 'Une question ? Appelez-nous au ', 'A question? Call us at ')}
            <a href={`tel:${FRONT_DESK_PHONE.replace(/\D/g, '')}`}>{FRONT_DESK_PHONE}</a>
          </p>
        </div>
      </div>
    );
  }

  /** Error line under a field, linked to it with aria-describedby. */
  const fieldError = (k: FieldKey): ReactNode => fieldErrors[k] && (
    <p className={styles.fieldError} id={`${FIELD_ID[k]}-err`}>{fieldErrors[k]}</p>
  );
  const describedBy = (k: FieldKey) => (fieldErrors[k] ? `${FIELD_ID[k]}-err` : undefined);
  // A word joiner keeps the * on the same line as the label's last word.
  const req = <span className={styles.req} aria-hidden="true">{'\u2060'}*</span>;
  const step = profile ? 2 : 1;

  return (
    <div className={styles.page}>
      <div className={styles.card} data-testid="public-demande">
        {brandRow}
        <div className={styles.intro}>
          <p className={styles.step}>
            {t(lang, `Étape ${step} sur 2`, `Step ${step} of 2`)}
            <span className={styles.stepBar} aria-hidden="true"><span style={{ width: step === 1 ? '50%' : '100%' }} /></span>
          </p>
          <h1 className={styles.title}>
            {step === 1
              ? t(lang, 'Demande de maintenance', 'Maintenance request')
              : t(lang, 'Décrivez le problème', 'Describe the problem')}
          </h1>
          <p className={styles.sub}>
            {step === 1
              ? t(lang,
                'Entrez le téléphone ou le courriel de votre dossier : nous retrouvons votre logement.',
                'Enter the phone or email on file: we find your unit for you.')
              : t(lang,
                'Quelques détails aident le technicien à venir avec le bon matériel.',
                'A few details help the technician come with the right tools.')}
          </p>
        </div>

        {!profile ? (
          <form onSubmit={onLookup}>
            <div className={styles.segment} role="radiogroup" aria-label={t(lang, 'Me retrouver par', 'Find me by')}>
              {(['phone', 'email'] as const).map((m) => (
                <label key={m} className={`${styles.segmentOpt} ${mode === m ? styles.segmentOn : ''}`}>
                  <input type="radio" name="lookup-mode" checked={mode === m}
                         onChange={() => { setMode(m); setShowDeskPhone(false); setErrorMsg(null); }} />
                  {m === 'phone' ? t(lang, 'Téléphone', 'Phone') : t(lang, 'Courriel', 'Email')}
                </label>
              ))}
            </div>
            {mode === 'phone' ? (
              <div className={styles.field}>
                <label className={styles.label} htmlFor="pub-phone">{t(lang, 'Numéro de téléphone', 'Phone number')}{req}</label>
                <input
                  id="pub-phone"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  placeholder="418 555-0142"
                  className={styles.input}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  data-testid="public-phone"
                  required
                />
              </div>
            ) : (
              <div className={styles.field}>
                <label className={styles.label} htmlFor="pub-email">{t(lang, 'Adresse courriel', 'Email address')}{req}</label>
                <input
                  id="pub-email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder={t(lang, 'nom@exemple.com', 'name@example.com')}
                  className={styles.input}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  data-testid="public-email"
                  required
                />
              </div>
            )}
            <div className={styles.turnstile}>
              <Turnstile action="tenant_lookup" onToken={setLookupToken} resetKey={lookupReset} />
            </div>
            {showDeskPhone && (
              <p className={styles.deskHelp} data-testid="public-desk-help" role="status">
                {t(
                  lang,
                  'Nous n’avons pas trouvé votre logement. Veuillez nous contacter au ',
                  'We could not find your unit. Please contact us at ',
                )}
                <a href={`tel:${FRONT_DESK_PHONE.replace(/\D/g, '')}`}>{FRONT_DESK_PHONE}</a>
                .
              </p>
            )}
            {errorMsg && <p className={styles.error} role="alert">{errorMsg}</p>}
            <button
              type="submit"
              className={styles.btn}
              disabled={!lookupToken || lookingUp}
              aria-busy={lookingUp}
              data-testid="public-lookup-btn"
            >
              {lookingUp && <span className={styles.spinner} aria-hidden="true" />}
              {lookingUp
                ? t(lang, 'Recherche…', 'Looking up…')
                : t(lang, 'Continuer', 'Continue')}
            </button>
          </form>
        ) : (
          <form onSubmit={onSubmit} noValidate>
            {/* Who and where — found from the lookup. */}
            <div className={styles.autofill} data-testid="public-autofill">
              <svg className={styles.autofillIcon} viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none"
                   stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10" /><path d="M10 20v-6h4v6" />
              </svg>
              <div className={styles.autofillText}>
                <strong>{profile.caller_name}</strong>
                <span>{profile.address_label}</span>
                {(profile.phone || profile.email) && (
                  <span className={styles.autofillMeta}>{[profile.phone, profile.email].filter(Boolean).join(' · ')}</span>
                )}
              </div>
              <button
                type="button"
                className={styles.linkBtn}
                onClick={() => {
                  setProfile(null);
                  setErrorMsg(null);
                  setFieldErrors({});
                  setLookupReset((k) => k + 1);
                }}
              >
                {t(lang, 'Ce n’est pas moi', 'Not me')}
              </button>
            </div>

            <section className={styles.section} aria-labelledby="pub-sec-problem">
              <div className={styles.sectionHead}>
                <span className={styles.sectionNum} aria-hidden="true">1</span>
                <div>
                  <h2 className={styles.sectionTitle} id="pub-sec-problem">{t(lang, 'Le problème', 'The problem')}</h2>
                  <p className={styles.sectionSub}>{t(lang, 'Dites-nous ce qui ne va pas.', 'Tell us what is wrong.')}</p>
                </div>
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="pub-problem">{t(lang, 'Que se passe-t-il ?', 'What is happening?')}{req}</label>
                <textarea
                  id="pub-problem"
                  className={`${styles.textarea} ${fieldErrors.problem ? styles.invalid : ''}`}
                  value={problem}
                  placeholder={t(lang, 'Ex. : de l’eau coule sous l’évier de la cuisine depuis ce matin.', 'E.g. water has been leaking under the kitchen sink since this morning.')}
                  onChange={(e) => { setProblem(e.target.value); clearError('problem'); }}
                  aria-invalid={!!fieldErrors.problem}
                  aria-describedby={describedBy('problem')}
                  data-testid="public-problem"
                  required
                />
                {fieldError('problem')}
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="pub-element">{t(lang, 'Ce qui est touché', 'What is affected')}{req}</label>
                <Select
                  id="pub-element"
                  className={`${styles.select} ${fieldErrors.element ? styles.invalid : ''}`}
                  value={element}
                  onChange={(e) => { setElement(e.target.value); clearError('element'); }}
                  aria-invalid={!!fieldErrors.element}
                  aria-describedby={describedBy('element')}
                  data-testid="public-element"
                >
                  <option value="">{t(lang, 'Choisir…', 'Choose…')}</option>
                  {taxonomyElementOptions(lang).map(({ value, label }) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </Select>
                {fieldError('element')}
              </div>
              <div className={styles.grid3}>
                {([
                  ['symptome', symptome, setSymptome, t(lang, 'Symptôme', 'Symptom'), t(lang, 'Ex. fuite', 'E.g. leak')],
                  ['composante', composante, setComposante, t(lang, 'Composante', 'Component'), t(lang, 'Ex. robinet', 'E.g. faucet')],
                  ['emplacement', emplacement, setEmplacement, t(lang, 'Emplacement', 'Location'), t(lang, 'Ex. cuisine', 'E.g. kitchen')],
                ] as const).map(([k, v, set, label, ph]) => (
                  <div key={k} className={styles.field}>
                    <label className={styles.label} htmlFor={FIELD_ID[k]}>{label}{req}</label>
                    <input
                      id={FIELD_ID[k]}
                      className={`${styles.input} ${fieldErrors[k] ? styles.invalid : ''}`}
                      value={v}
                      placeholder={ph}
                      onChange={(e) => { set(e.target.value); clearError(k); }}
                      aria-invalid={!!fieldErrors[k]}
                      aria-describedby={describedBy(k)}
                      required
                    />
                    {fieldError(k)}
                  </div>
                ))}
              </div>
              <div className={styles.field}>
                <span className={styles.label} id="pub-photos-label">
                  {t(lang, 'Photos', 'Photos')}
                  <span className={styles.recommended}>{t(lang, 'Recommandé', 'Recommended')}</span>
                </span>
                <p className={styles.hint}>
                  {t(lang, 'Aide le technicien à préparer sa visite. Jusqu’à 5 photos.', 'Helps the technician prepare. Up to 5 photos.')}
                </p>
                <PhotoPicker lang={lang} photos={photos} onChange={setPhotos} labelledBy="pub-photos-label" />
              </div>
            </section>

            <section className={styles.section} aria-labelledby="pub-sec-access">
              <div className={styles.sectionHead}>
                <span className={styles.sectionNum} aria-hidden="true">2</span>
                <div>
                  <h2 className={styles.sectionTitle} id="pub-sec-access">{t(lang, 'Accès au logement', 'Access to the unit')}</h2>
                  <p className={styles.sectionSub}>{t(lang, 'Comment le technicien peut-il entrer chez vous ?', 'How can the technician get in?')}</p>
                </div>
              </div>
              <fieldset className={styles.fieldset}>
                <legend className={styles.srOnly}>{t(lang, 'Accès', 'Access')}</legend>
                <div className={styles.choiceGrid}>
                  {accessOptions(lang).map((o) => (
                    <label key={o.value} className={`${styles.choice} ${access === o.value ? styles.choiceOn : ''}`}>
                      <input
                        type="radio"
                        name="access"
                        checked={access === o.value}
                        onChange={() => { setAccess(o.value); clearError('accessDetails'); }}
                      />
                      {o.label}
                    </label>
                  ))}
                </div>
              </fieldset>
              {access === 'yes_instructions' && (
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="pub-access-details">{t(lang, "Instructions d'accès", 'Access instructions')}{req}</label>
                  <input
                    id="pub-access-details"
                    className={`${styles.input} ${fieldErrors.accessDetails ? styles.invalid : ''}`}
                    value={accessDetails}
                    placeholder={t(lang, 'Ex. : clé chez le concierge, code 1234', 'E.g. key with the janitor, code 1234')}
                    onChange={(e) => { setAccessDetails(e.target.value); clearError('accessDetails'); }}
                    aria-invalid={!!fieldErrors.accessDetails}
                    aria-describedby={describedBy('accessDetails')}
                    data-testid="public-access-details"
                  />
                  {fieldError('accessDetails')}
                </div>
              )}

              {profile.pets_allowed && (
                <>
                  <fieldset className={styles.fieldset} aria-describedby={describedBy('animals')}>
                    <legend className={styles.label}>{t(lang, 'Un animal sera-t-il présent ?', 'Will a pet be present?')}{req}</legend>
                    <div className={styles.segment}>
                      {(['oui', 'non'] as const).map((v) => (
                        <label key={v} className={`${styles.segmentOpt} ${animals === v ? styles.segmentOn : ''}`}>
                          <input
                            id={v === 'oui' ? FIELD_ID.animals : undefined}
                            type="radio"
                            name="animals"
                            checked={animals === v}
                            onChange={() => { setAnimals(v); clearError('animals'); }}
                          />
                          {v === 'oui' ? t(lang, 'Oui', 'Yes') : t(lang, 'Non', 'No')}
                        </label>
                      ))}
                    </div>
                    {fieldError('animals')}
                  </fieldset>
                  {animals === 'oui' && (
                    <div className={styles.field}>
                      <label className={styles.label} htmlFor="pub-animal-details">
                        {t(lang, "Type d'animal", 'Type of pet')} <span className={styles.optional}>{t(lang, '(optionnel)', '(optional)')}</span>
                      </label>
                      <input
                        id="pub-animal-details"
                        className={styles.input}
                        value={animalDetails}
                        placeholder={t(lang, 'Ex. chat, chien', 'E.g. cat, dog')}
                        onChange={(e) => setAnimalDetails(e.target.value)}
                      />
                    </div>
                  )}
                </>
              )}

              <div className={styles.field}>
                <label className={styles.label} htmlFor="pub-attention">
                  {t(lang, 'À savoir avant la visite', 'Good to know before the visit')} <span className={styles.optional}>{t(lang, '(optionnel)', '(optional)')}</span>
                </label>
                <input
                  id="pub-attention"
                  className={styles.input}
                  value={attention}
                  placeholder={t(lang, 'Ex. : bébé qui dort l’après-midi', 'E.g. baby naps in the afternoon')}
                  onChange={(e) => setAttention(e.target.value)}
                />
              </div>
            </section>

            <div className={styles.turnstile}>
              <Turnstile action="tenant_submit" onToken={setSubmitToken} resetKey={submitReset} />
            </div>
            {Object.values(fieldErrors).some(Boolean) && (
              <p className={styles.error} role="alert">
                {t(lang, 'Il manque des informations : voyez les champs en rouge.', 'Some information is missing: see the fields in red.')}
              </p>
            )}
            {errorMsg && <p className={styles.error} role="alert">{errorMsg}</p>}
            <button
              type="submit"
              className={styles.btn}
              disabled={!submitToken || submitting}
              aria-busy={submitting}
              data-testid="public-submit-btn"
            >
              {submitting && <span className={styles.spinner} aria-hidden="true" />}
              {submitting
                ? t(lang, 'Envoi…', 'Sending…')
                : t(lang, 'Envoyer la demande', 'Submit request')}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
