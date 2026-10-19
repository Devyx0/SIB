import { useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useRequest } from '../../hooks/useRequest';
import { uploadPhoto, closeoutRequest, ApiError } from '../../api/client';
import type { MeResponse } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t, closeoutOutcomeLabel } from '../../i18n';
import MicButton from '../../components/MicButton';
import TechHeader from './TechHeader';
import styles from './TechPortal.module.css';

interface Props {
  lang: Lang;
  me: MeResponse | null;
  onSignOut: () => void;
}

const OUTCOMES = ['complete', 'partial_reschedule', 'partial_expertise', 'failed'] as const;
type Outcome = (typeof OUTCOMES)[number];

interface PhotoItem {
  attachment_id: number;
  objectUrl: string;
}

function todayToronto(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
}

function getPosition(): Promise<{ lat: number; lng: number } | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => resolve(null),
      { timeout: 5000, maximumAge: 60000 },
    );
  });
}

export default function CloseoutForm({ lang, me, onSignOut }: Props) {
  const { id } = useParams();
  const requestId = Number(id);
  const { data: req } = useRequest(Number.isFinite(requestId) ? requestId : null);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [photos, setPhotos] = useState<PhotoItem[]>([]);
  const [comment, setComment] = useState('');
  const [nextDate, setNextDate] = useState('');
  const [urgent, setUrgent] = useState(false);
  const [micUsed, setMicUsed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const today = todayToronto();
  const needsDate = outcome === 'partial_reschedule';
  const allowsUrgent = outcome === 'partial_expertise' || outcome === 'failed';

  const valid =
    outcome !== null &&
    photos.length >= 1 &&
    comment.trim().length >= 10 &&
    (!needsDate || (nextDate !== '' && nextDate >= today));

  async function handleAddPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ''; // same file can be re-picked
    if (!file || !req) return;
    setError(null);
    setBusy(true);
    try {
      const { attachment_id } = await uploadPhoto(req.request_id, file);
      setPhotos((p) => [...p, { attachment_id, objectUrl: URL.createObjectURL(file) }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit() {
    if (!req || !outcome || !valid) return;
    setBusy(true);
    setError(null);
    const pos = await getPosition();
    try {
      await closeoutRequest(req.request_id, {
        outcome,
        comment: comment.trim(),
        input_method: micUsed ? 'voice' : 'typed',
        attachment_ids: photos.map((p) => p.attachment_id),
        next_date: needsDate ? nextDate : null,
        urgent: allowsUrgent ? urgent : false,
        current_status: req.status,
        lat: pos?.lat ?? null,
        lng: pos?.lng ?? null,
      });
      qc.invalidateQueries({ queryKey: ['requests'] });
      qc.invalidateQueries({ queryKey: ['request', req.request_id] });
      navigate('/tech');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.page}>
      <TechHeader lang={lang} me={me} onSignOut={onSignOut} backTo={`/tech/appels/${requestId}`} />
      <main className={styles.main}>
        <h1 className={styles.callViewTitle}>
          {t(lang, 'Clôturer', 'Close out')} — {req?.raw_title ?? `#${requestId}`}
        </h1>

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>{t(lang, 'Résultat', 'Outcome')}</h2>
          {OUTCOMES.map((o) => (
            <label key={o} className={styles.outcomeOption}>
              <input
                type="radio"
                name="outcome"
                value={o}
                checked={outcome === o}
                onChange={() => setOutcome(o)}
              />
              <span>{closeoutOutcomeLabel(lang, o)}</span>
            </label>
          ))}
        </section>

        {needsDate && (
          <section className={styles.card}>
            <h2 className={styles.cardTitle}>{t(lang, 'Nouvelle date', 'New date')}</h2>
            <input
              type="date"
              value={nextDate}
              min={today}
              onChange={(e) => setNextDate(e.target.value)}
              data-testid="next-date"
            />
          </section>
        )}

        {allowsUrgent && (
          <section className={styles.card}>
            <label className={styles.outcomeOption}>
              <input
                type="checkbox"
                checked={urgent}
                onChange={(e) => setUrgent(e.target.checked)}
                data-testid="urgent-checkbox"
              />
              <span>Urgent</span>
            </label>
          </section>
        )}

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>
            {t(lang, 'Photos (minimum 1)', 'Photos (minimum 1)')}
          </h2>
          <div className={styles.photoThumbs}>
            {photos.map((p) => (
              <img key={p.attachment_id} src={p.objectUrl} alt="" className={styles.photoThumb} />
            ))}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            onChange={handleAddPhoto}
            hidden
            data-testid="photo-input"
          />
          <button
            type="button"
            className={styles.addPhotoBtn}
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
          >
            {t(lang, 'Ajouter une photo', 'Add a photo')}
          </button>
        </section>

        <section className={styles.card}>
          <h2 className={styles.cardTitle}>{t(lang, 'Explication', 'Explanation')}</h2>
          <div className={styles.commentRow}>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={4}
              placeholder={t(lang, 'Décrivez le travail et les prochaines étapes…', 'Describe the work and next steps…')}
              data-testid="closeout-comment"
            />
            <MicButton
              lang={lang}
              onTranscript={(text) => {
                setMicUsed(true);
                setComment((c) => (c ? `${c} ${text}` : text));
              }}
            />
          </div>
        </section>

        {error && <p className={styles.error}>{error}</p>}

        <button
          type="button"
          className={styles.enRouteBtn}
          onClick={handleSubmit}
          disabled={!valid || busy}
          data-testid="closeout-submit"
        >
          {busy ? t(lang, 'Envoi…', 'Sending…') : t(lang, 'Clôturer le call', 'Close the call')}
        </button>
      </main>
    </div>
  );
}
