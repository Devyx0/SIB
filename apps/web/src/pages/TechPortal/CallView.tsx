import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useRequest } from '../../hooks/useRequest';
import { goEnRoute, ApiError } from '../../api/client';
import type { MeResponse, RequestDetail } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t, statusLabel } from '../../i18n';
import TechHeader from './TechHeader';
import { elapsedLabel } from './elapsed';
import styles from './TechPortal.module.css';

interface Props {
  lang: Lang;
  me: MeResponse | null;
  onSignOut: () => void;
}

// Fiche technique data arrives in three shapes: link in ft_link; name only in
// ft_name; or "name (url)" mashed into ft_name with ft_link null.
function ftInfo(req: RequestDetail): { href: string | null; label: string | null } {
  const raw = [req.ft_name, req.ft_link].filter(Boolean).join(' ');
  const m = raw.match(/https?:\/\/\S+/);
  const href = m ? m[0].replace(/\)+$/, '') : null;
  const label = raw.replace(/\(?https?:\/\/\S+\)?/g, '').replace(/[()]/g, ' ').trim() || null;
  return { href, label };
}

// Location point only if the browser grants it — null on deny/timeout/absent.
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

export default function TechCallView({ lang, me, onSignOut }: Props) {
  const { id } = useParams();
  const requestId = Number(id);
  const { data: req, isPending, isError } = useRequest(Number.isFinite(requestId) ? requestId : null);
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [enRouteError, setEnRouteError] = useState<string | null>(null);

  const isAssignedToMe = me != null && req != null && req.assigned_employee_id === me.employee_id;
  const canGoEnRoute = isAssignedToMe && req != null && req.status !== 'closed' && req.status !== 'en_route';
  const noContact = req != null && !req.caller_phone && !req.caller_email;

  async function handleEnRoute() {
    if (!req) return;
    setBusy(true);
    setEnRouteError(null);
    const pos = await getPosition();
    try {
      const updated = await goEnRoute(req.request_id, {
        current_status: req.status,
        current_start_date: req.start_date,
        lat: pos?.lat ?? null,
        lng: pos?.lng ?? null,
      });
      qc.setQueryData(['request', req.request_id], updated);
      qc.invalidateQueries({ queryKey: ['requests'] });
    } catch (e) {
      if (e instanceof ApiError) {
        const d = e.details as { open_request_title?: string | null } | null;
        setEnRouteError(d?.open_request_title ? `${e.message} (${d.open_request_title})` : e.message);
      } else {
        setEnRouteError(String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  const ft = req ? ftInfo(req) : { href: null, label: null };

  return (
    <div className={styles.page}>
      <TechHeader lang={lang} me={me} onSignOut={onSignOut} backTo="/tech" />
      <main className={styles.main}>
        {isPending && <p className={styles.muted}>{t(lang, 'Chargement…', 'Loading…')}</p>}
        {isError && (
          <p className={styles.error}>{t(lang, 'Appel introuvable', 'Call not found')}</p>
        )}

        {req && (
          <>
            <div className={styles.callRowTop}>
              <span className={styles.callDate}>{req.start_date ?? t(lang, 'Sans date', 'No date')}</span>
              <span className={styles.statusBadge} data-status={req.status}>
                {statusLabel(lang, req.status)}
              </span>
              {req.urgency_tier && req.urgency_tier !== 'none' && (
                <span className={styles.urgencyBadge}>{req.urgency_tier}</span>
              )}
            </div>
            <h1 className={styles.callViewTitle}>{req.raw_title ?? `#${req.request_id}`}</h1>

            {req.status === 'en_route' && (
              <div className={styles.openCallBannerCard}>
                {t(lang, 'En route', 'En route')}
                {elapsedLabel(req.en_route_at) && (
                  <> {t(lang, 'depuis', 'for')} {elapsedLabel(req.en_route_at)}</>
                )}
              </div>
            )}
            {req.status === 'en_route' && isAssignedToMe && noContact && (
              <p className={styles.warning} data-testid="no-contact-warning">
                {t(lang, 'Aucun contact pour aviser le locataire', 'No contact to notify the tenant')}
              </p>
            )}

            {canGoEnRoute && (
              <button
                type="button"
                className={styles.enRouteBtn}
                onClick={handleEnRoute}
                disabled={busy}
                data-testid="en-route-btn"
              >
                {busy ? t(lang, 'Envoi…', 'Sending…') : t(lang, 'En route', 'En route')}
              </button>
            )}
            {enRouteError && <p className={styles.error}>{enRouteError}</p>}

            <section className={styles.card}>
              <h2 className={styles.cardTitle}>{t(lang, 'Adresse', 'Address')}</h2>
              <p>
                {req.building_address ?? '—'}
                {req.unit_label ? `, app. ${req.unit_label}` : ''}
              </p>
              {req.building_name && <p className={styles.muted}>{req.building_name}</p>}
            </section>

            {req.raw_caller_body ? (
              <section className={styles.card}>
                <h2 className={styles.cardTitle}>
                  {t(lang, 'Problème (version du locataire)', 'Problem (tenant version)')}
                </h2>
                <p className={styles.preWrap}>{req.raw_caller_body.problems ?? '—'}</p>
                <h2 className={styles.cardTitle}>{t(lang, "Permission d'entrer", 'Entry permission')}</h2>
                <p>{req.raw_caller_body.entry_permission ?? '—'}</p>
                <h2 className={styles.cardTitle}>{t(lang, 'Animaux', 'Animals')}</h2>
                <p>{req.raw_caller_body.animals ?? '—'}</p>
              </section>
            ) : (
              <section className={styles.card}>
                <h2 className={styles.cardTitle}>{t(lang, 'Problème', 'Problem')}</h2>
                <p className={styles.preWrap}>{req.problems ?? '—'}</p>
              </section>
            )}

            <section className={styles.card}>
              <h2 className={styles.cardTitle}>{t(lang, 'Fiche technique', 'Technical sheet')}</h2>
              {ft.href ? (
                <a href={ft.href} target="_blank" rel="noreferrer" className={styles.ftLink}>
                  {ft.label ?? t(lang, 'Ouvrir la fiche', 'Open the sheet')}
                </a>
              ) : (
                <p className={styles.muted}>
                  {t(lang, 'Fiche technique non disponible', 'Technical sheet not available')}
                </p>
              )}
            </section>

            <section className={styles.card}>
              <h2 className={styles.cardTitle}>{t(lang, 'Contact locataire', 'Tenant contact')}</h2>
              {req.caller_name || req.caller_phone || req.caller_email ? (
                <>
                  {req.caller_name && <p>{req.caller_name}</p>}
                  {req.caller_phone && (
                    <p><a href={`tel:${req.caller_phone}`} className={styles.contactLink}>{req.caller_phone}</a></p>
                  )}
                  {req.caller_email && (
                    <p><a href={`mailto:${req.caller_email}`} className={styles.contactLink}>{req.caller_email}</a></p>
                  )}
                </>
              ) : (
                <p className={styles.muted}>—</p>
              )}
            </section>

            <section className={styles.card}>
              <h2 className={styles.cardTitle}>{t(lang, 'Suivis', 'Follow-ups')}</h2>
              {req.followup_log.length === 0 && <p className={styles.muted}>—</p>}
              {req.followup_log.map((f) => (
                <div key={f.followup_id} className={styles.followupEntry}>
                  <span className={styles.muted}>
                    {f.entry_date ?? '—'} {f.entered_by_initials ? `· ${f.entered_by_initials}` : ''}
                  </span>
                  <p className={styles.preWrap}>{f.entry_text}</p>
                </div>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
