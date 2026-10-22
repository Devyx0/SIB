import { useRef, useState } from 'react';
import BrandMark from '../../components/BrandMark';
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
  const [photos, setPhotos] = useState<Array<{ file: File; url: string }>>([]);
  const photoInputRef = useRef<HTMLInputElement>(null);

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
    if (access === 'yes_instructions' && !accessDetails.trim()) {
      setErrorMsg(t(lang, "Précisions d'accès requises.", 'Access instructions required.'));
      return;
    }
    if (profile.pets_allowed && animals == null) {
      setErrorMsg(t(lang, 'Indiquez si un animal est présent.', 'Say whether a pet is present.'));
      return;
    }
    if (!problem.trim() || !element.trim() || !symptome.trim() || !composante.trim() || !emplacement.trim()) {
      setErrorMsg(t(lang, 'Remplissez le problème et la taxonomie.', 'Fill in the problem and taxonomy.'));
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

  if (doneId != null) {
    return (
      <div className={styles.page}>
        <div className={styles.card} data-testid="public-demande-done">
          <BrandMark />
          <p className={styles.success}>
            {t(lang, 'Demande envoyée', 'Request submitted')} #{doneId}
          </p>
          <p className={styles.sub}>
            {t(lang, 'La maintenance a bien reçu votre appel.', 'Maintenance has received your call.')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.card} data-testid="public-demande">
        <button type="button" className={styles.langToggle} onClick={onToggleLang}>
          {lang === 'fr' ? 'English' : 'Français'}
        </button>
        <BrandMark />
        <h1 className={styles.title}>{t(lang, 'Demande de maintenance', 'Maintenance request')}</h1>
        <p className={styles.sub}>
          {t(
            lang,
            'Identifiez-vous avec votre téléphone ou courriel. Le logement se remplit automatiquement.',
            'Identify yourself with your phone or email. Your unit fills in automatically.',
          )}
        </p>

        {!profile ? (
          <form onSubmit={onLookup}>
            <div className={styles.row}>
              <label className={styles.radioRow}>
                <input type="radio" checked={mode === 'phone'} onChange={() => { setMode('phone'); setShowDeskPhone(false); setErrorMsg(null); }} />
                {t(lang, 'Téléphone', 'Phone')}
              </label>
              <label className={styles.radioRow}>
                <input type="radio" checked={mode === 'email'} onChange={() => { setMode('email'); setShowDeskPhone(false); setErrorMsg(null); }} />
                {t(lang, 'Courriel', 'Email')}
              </label>
            </div>
            {mode === 'phone' ? (
              <div className={styles.field}>
                <label className={styles.label} htmlFor="pub-phone">{t(lang, 'Téléphone', 'Phone')}</label>
                <input
                  id="pub-phone"
                  className={styles.input}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  data-testid="public-phone"
                  required
                />
              </div>
            ) : (
              <div className={styles.field}>
                <label className={styles.label} htmlFor="pub-email">{t(lang, 'Courriel', 'Email')}</label>
                <input
                  id="pub-email"
                  type="email"
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
              <p className={styles.deskHelp} data-testid="public-desk-help">
                {t(
                  lang,
                  'Veuillez nous contacter au ',
                  'Please contact us at ',
                )}
                <a href={`tel:${FRONT_DESK_PHONE.replace(/\D/g, '')}`}>{FRONT_DESK_PHONE}</a>
                .
              </p>
            )}
            {errorMsg && <p className={styles.error}>{errorMsg}</p>}
            <button
              type="submit"
              className={styles.btn}
              disabled={!lookupToken || lookingUp}
              data-testid="public-lookup-btn"
            >
              {lookingUp
                ? t(lang, 'Recherche…', 'Looking up…')
                : t(lang, 'Continuer', 'Continue')}
            </button>
          </form>
        ) : (
          <form onSubmit={onSubmit}>
            <div className={styles.autofill} data-testid="public-autofill">
              <strong>{profile.caller_name}</strong>
              <span>{profile.address_label}</span>
              {profile.phone && <span>{profile.phone}</span>}
              {profile.email && <span>{profile.email}</span>}
            </div>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnSecondary}`}
              onClick={() => {
                setProfile(null);
                setErrorMsg(null);
                setLookupReset((k) => k + 1);
              }}
            >
              {t(lang, 'Ce n’est pas moi', 'Not me')}
            </button>

            <fieldset className={styles.fieldset}>
              <legend className={styles.label}>{t(lang, 'Accès', 'Access')}</legend>
              {accessOptions(lang).map((o) => (
                <label key={o.value} className={styles.radioRow}>
                  <input
                    type="radio"
                    name="access"
                    checked={access === o.value}
                    onChange={() => setAccess(o.value)}
                  />
                  {o.label}
                </label>
              ))}
            </fieldset>
            {access === 'yes_instructions' && (
              <div className={styles.field}>
                <label className={styles.label}>{t(lang, "Instructions d'accès", 'Access instructions')}</label>
                <input
                  className={styles.input}
                  value={accessDetails}
                  onChange={(e) => setAccessDetails(e.target.value)}
                  data-testid="public-access-details"
                />
              </div>
            )}

            {profile.pets_allowed && (
              <>
                <fieldset className={styles.fieldset}>
                  <legend className={styles.label}>{t(lang, 'Animal présent', 'Pet present')}</legend>
                  <div className={styles.row}>
                    {(['oui', 'non'] as const).map((v) => (
                      <label key={v} className={styles.radioRow}>
                        <input
                          type="radio"
                          name="animals"
                          checked={animals === v}
                          onChange={() => setAnimals(v)}
                        />
                        {v === 'oui' ? t(lang, 'Oui', 'Yes') : t(lang, 'Non', 'No')}
                      </label>
                    ))}
                  </div>
                </fieldset>
                {animals === 'oui' && (
                  <div className={styles.field}>
                    <label className={styles.label}>{t(lang, "Type d'animaux", 'Animal type')}</label>
                    <input
                      className={styles.input}
                      value={animalDetails}
                      onChange={(e) => setAnimalDetails(e.target.value)}
                    />
                  </div>
                )}
              </>
            )}

            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Problème', 'Problem')}</label>
              <textarea
                className={styles.textarea}
                value={problem}
                onChange={(e) => setProblem(e.target.value)}
                data-testid="public-problem"
                required
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Élément', 'Element')}</label>
              <select
                className={styles.select}
                value={element}
                onChange={(e) => setElement(e.target.value)}
                data-testid="public-element"
                required
              >
                <option value="">{t(lang, 'Choisir…', 'Choose…')}</option>
                {taxonomyElementOptions(lang).map(({ value, label }) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Symptôme', 'Symptom')}</label>
              <input className={styles.input} value={symptome} onChange={(e) => setSymptome(e.target.value)} required />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Composante', 'Component')}</label>
              <input className={styles.input} value={composante} onChange={(e) => setComposante(e.target.value)} required />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Emplacement', 'Location')}</label>
              <input className={styles.input} value={emplacement} onChange={(e) => setEmplacement(e.target.value)} required />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'À noter', 'Notes')}</label>
              <input className={styles.input} value={attention} onChange={(e) => setAttention(e.target.value)} />
            </div>

            <div className={styles.field}>
              <label className={styles.label}>{t(lang, 'Photos (optionnel)', 'Photos (optional)')}</label>
              <input
                ref={photoInputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={(e) => {
                  const files = Array.from(e.target.files || []).slice(0, 5);
                  setPhotos(files.map((file) => ({ file, url: URL.createObjectURL(file) })));
                }}
              />
              <div className={styles.photos}>
                {photos.map((p) => (
                  <img key={p.url} src={p.url} alt="" className={styles.thumb} />
                ))}
              </div>
            </div>

            <div className={styles.turnstile}>
              <Turnstile action="tenant_submit" onToken={setSubmitToken} resetKey={submitReset} />
            </div>
            {errorMsg && <p className={styles.error}>{errorMsg}</p>}
            <button
              type="submit"
              className={styles.btn}
              disabled={!submitToken || submitting}
              data-testid="public-submit-btn"
            >
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
