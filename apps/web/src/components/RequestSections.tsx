// Read-only request-history sections shared by the dispatch DetailPanel and
// the Dossiers detail page: visits (with signed-URL photos), follow-up log,
// decision history. Moved verbatim from DetailPanel — behavior unchanged.
import { useQuery } from '@tanstack/react-query';
import { fetchPhotoUrl } from '../api/client';
import type { FollowupEntry, JustificationEntry, VisitEntry } from '../api/schema.d.ts';
import { closeoutOutcomeLabel, t } from '../i18n';
import type { Lang } from '../i18n';
import styles from './RequestSections.module.css';

const DECISION_LABELS: Record<string, { fr: string; en: string }> = {
  assign:     { fr: 'Assignation',     en: 'Assignment' },
  reschedule: { fr: 'Reprogrammation', en: 'Reschedule' },
  urgency:    { fr: 'Urgence',         en: 'Urgency' },
};

const INPUT_LABELS: Record<string, { fr: string; en: string }> = {
  typed: { fr: 'Écrit',  en: 'Written' },
  voice: { fr: 'Dicté', en: 'Dictated' },
};

function decisionLabel(lang: Lang, type: string): string {
  return DECISION_LABELS[type]?.[lang] ?? type;
}

function inputLabel(lang: Lang, method: string | null | undefined): string {
  if (!method) return '';
  return INPUT_LABELS[method]?.[lang] ?? method;
}

export function durationLabel(startIso: string, endIso: string | null): string | null {
  if (!endIso) return null;
  const mins = Math.max(0, Math.round(
    (new Date(endIso).getTime() - new Date(startIso).getTime()) / 60000));
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)} h ${String(mins % 60).padStart(2, '0')}`;
}

function formatTime(iso: string | null, lang: Lang): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(lang === 'fr' ? 'fr-CA' : 'en-CA', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Toronto',
  });
}

function formatTimestamp(iso: string): string {
  return new Intl.DateTimeFormat('fr-CA', {
    timeZone: 'America/Toronto',
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(iso));
}

function formatDate(dateStr: string | null | undefined, lang: Lang): string {
  if (!dateStr) return '—';
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Intl.DateTimeFormat(lang === 'fr' ? 'fr-CA' : 'en-CA', { month: 'short', day: 'numeric' })
    .format(new Date(y, m - 1, d));
}

function VisitPhoto({ requestId, attachmentId }: { requestId: number; attachmentId: number }) {
  const { data } = useQuery({
    queryKey: ['photo-url', requestId, attachmentId],
    queryFn: () => fetchPhotoUrl(requestId, attachmentId),
    staleTime: 4 * 60 * 1000, // signed URLs live 5 min
  });
  if (!data) return null;
  return <img src={data.url} alt="" className={styles.visitPhoto} data-testid="visit-photo" />;
}

export function VisitsSection({ requestId, visits, lang }:
  { requestId: number; visits: VisitEntry[]; lang: Lang }) {
  if (visits.length === 0) return null;
  return (
    <section className={styles.followupSection} data-testid="visits-section">
      <h3 className={styles.followupHeading}>
        {t(lang, 'Visites', 'Visits')}
      </h3>
      {visits.map((v) => (
        <div key={v.visit_id} className={styles.followupEntry}>
          <span className={styles.followupMeta}>
            {v.employee_name ?? `#${v.employee_id}`}
            {' · '}{t(lang, 'En route', 'En route')} {formatTime(v.en_route_at, lang)}
            {v.closeout_at && <>{' · '}{t(lang, 'Clôturé', 'Closed')} {formatTime(v.closeout_at, lang)}</>}
            {durationLabel(v.en_route_at, v.closeout_at) && <>{' · '}{durationLabel(v.en_route_at, v.closeout_at)}</>}
          </span>
          <p className={styles.followupText}>
            {closeoutOutcomeLabel(lang, v.outcome)}
            {v.closeout_comment ? ` — ${v.closeout_comment}` : ''}
          </p>
          {v.photo_ids.length > 0 && (
            <div className={styles.visitPhotos}>
              {v.photo_ids.map((pid) => (
                <VisitPhoto key={pid} requestId={requestId} attachmentId={pid} />
              ))}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

export function FollowupLogSection({ entries, lang }:
  { entries: FollowupEntry[]; lang: Lang }) {
  if (entries.length === 0) return null;
  return (
    <section className={styles.followupSection}>
      <h3 className={styles.followupHeading}>
        {t(lang, 'Journal de suivi', 'Follow-up log')}
      </h3>
      {entries.map((entry) => (
        <div key={entry.followup_id} className={styles.followupEntry}>
          <span className={styles.followupMeta}>
            {formatDate(entry.entry_date, lang)}
            {entry.entered_by_initials ? ` · ${entry.entered_by_initials}` : ''}
          </span>
          <p className={styles.followupText}>{entry.entry_text ?? '—'}</p>
        </div>
      ))}
    </section>
  );
}

export function DecisionHistorySection({ entries, lang }:
  { entries: JustificationEntry[]; lang: Lang }) {
  if (entries.length === 0) return null;
  return (
    <section className={styles.justifSection}>
      <h3 className={styles.followupHeading}>
        {t(lang, 'Historique des décisions', 'Decision history')}
      </h3>
      {entries.map((entry) => (
        <div key={entry.id} className={styles.justifEntry}>
          <span className={styles.justifMeta}>
            {decisionLabel(lang, entry.decision_type)}
            {' · '}{formatTimestamp(entry.created_at)}
            {entry.input_method ? ` · ${inputLabel(lang, entry.input_method)}` : ''}
          </span>
          <p className={styles.justifText}>{entry.justification_text}</p>
        </div>
      ))}
    </section>
  );
}
