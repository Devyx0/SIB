// Request photo and duration helpers shared by the dispatch DetailPanel, the
// Dossiers pages and the history timeline (HistoryTimeline.tsx).
import { useQuery } from '@tanstack/react-query';
import { fetchPhotoUrl } from '../api/client';
import { t } from '../i18n';
import type { Lang } from '../i18n';
import styles from './RequestSections.module.css';

export function formatDurationMinutes(mins: number): string {
  const m = Math.max(0, Math.round(mins));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}`;
}

export function durationLabel(
  startIso: string,
  endIso: string | null,
  storedMinutes?: number | null,
): string | null {
  if (storedMinutes != null) return formatDurationMinutes(storedMinutes);
  if (!endIso) return null;
  const mins = Math.max(0, Math.round(
    (new Date(endIso).getTime() - new Date(startIso).getTime()) / 60000));
  return formatDurationMinutes(mins);
}

/** Photos attached to the call at intake; each opens full size in a new tab. */
export function IntakePhotos({ requestId, ids, lang }: { requestId: number; ids: number[]; lang: Lang }) {
  if (ids.length === 0) return null;
  return (
    <div className={styles.intakePhotos} data-testid="intake-photos">
      <span className={styles.followupMeta}>
        {t(lang, `Photos jointes à l’appel (${ids.length})`, `Photos attached to the call (${ids.length})`)}
      </span>
      <div className={styles.visitPhotos}>
        {ids.map((id) => <IntakePhoto key={id} requestId={requestId} attachmentId={id} lang={lang} />)}
      </div>
    </div>
  );
}

function IntakePhoto({ requestId, attachmentId, lang }: { requestId: number; attachmentId: number; lang: Lang }) {
  const { data } = useQuery({
    queryKey: ['photo-url', requestId, attachmentId],
    queryFn: () => fetchPhotoUrl(requestId, attachmentId),
    staleTime: 4 * 60 * 1000, // signed URLs live 5 min
  });
  if (!data) return <span className={styles.photoPlaceholder} aria-hidden="true" />;
  return (
    <a href={data.url} target="_blank" rel="noreferrer" title={t(lang, 'Ouvrir en grand', 'Open full size')}>
      <img src={data.url} alt={t(lang, 'Photo de l’appel', 'Call photo')} className={styles.intakePhoto} data-testid="intake-photo" />
    </a>
  );
}

export function VisitPhoto({ requestId, attachmentId }: { requestId: number; attachmentId: number }) {
  const { data } = useQuery({
    queryKey: ['photo-url', requestId, attachmentId],
    queryFn: () => fetchPhotoUrl(requestId, attachmentId),
    staleTime: 4 * 60 * 1000, // signed URLs live 5 min
  });
  if (!data) return null;
  return <img src={data.url} alt="" className={styles.visitPhoto} data-testid="visit-photo" />;
}
