import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useRequest } from '../../hooks/useRequest';
import { goEnRoute, markArrived, ApiError, GENERIC_ERROR_FR } from '../../api/client';
import type { MeResponse, RequestDetail } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t, statusLabel, timeEstimateLabel } from '../../i18n';
import { formatEntryDate } from '../../components/HistoryTimeline';
import { IntakePhotos } from '../../components/RequestSections';
import { urgencyLabel } from '../../lib/urgencyLevels';
import TechHeader from './TechHeader';
import { elapsedLabel } from './elapsed';
import styles from './TechPortal.module.css';

interface Props {
  lang: Lang;
  me: MeResponse | null;
  onSignOut: () => void;
  onToggleLang: () => void;
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

export default function TechCallView({ lang, me, onSignOut, onToggleLang }: Props) {
  const { id } = useParams();
  const requestId = Number(id);
  const { data: req, isPending, isError } = useRequest(Number.isFinite(requestId) ? requestId : null);
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const isAssignedToMe = me != null && req != null && req.assigned_employee_id === me.employee_id;
  const inProgress = req?.status === 'en_route' || req?.status === 'arrived';
  const canGoEnRoute = isAssignedToMe && req != null && req.status !== 'closed' && !inProgress;
  const canMarkArrived = isAssignedToMe && req?.status === 'en_route';
  const canCloseout = isAssignedToMe && req?.status === 'arrived';
  const noContact = req != null && !req.caller_phone && !req.caller_email;

  async function handleEnRoute() {
    if (!req) return;
    setBusy(true);
    setActionError(null);
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
        setActionError(d?.open_request_title ? `${e.message} (${d.open_request_title})` : e.message);
      } else {
        setActionError(GENERIC_ERROR_FR);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleArrived() {
    if (!req) return;
    setBusy(true);
    setActionError(null);
    const pos = await getPosition();
    try {
      const updated = await markArrived(req.request_id, {
        current_status: req.status,
        lat: pos?.lat ?? null,
        lng: pos?.lng ?? null,
      });
      qc.setQueryData(['request', req.request_id], updated);
      qc.invalidateQueries({ queryKey: ['requests'] });
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : GENERIC_ERROR_FR);
    } finally {
      setBusy(false);
    }
  }

  const ft = req ? ftInfo(req) : { href: null, label: null };
  const problemText = req
    ? (req.raw_caller_body?.problems ?? req.problems)
    : null;
  const entryPermission = req
    ? (req.raw_caller_body?.entry_permission ?? req.entry_permission)
    : null;
  const animals = req
    ? (req.raw_caller_body?.animals ?? req.animals)
    : null;
  const hasTaxonomy = !!(
    req?.element || req?.symptome || req?.composante || req?.emplacement || req?.category_raw
  );

  return (
    <div className={styles.page}>
      <TechHeader lang={lang} me={me} onSignOut={onSignOut} onToggleLang={onToggleLang} backTo="/tech" />
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
                <span className={styles.urgencyBadge}>{urgencyLabel(lang, req.urgency_tier)}</span>
              )}
            </div>
            <h1 className={styles.callViewTitle}>{req.raw_title ?? `#${req.request_id}`}</h1>
            {(req.asnu || req.time_estimate_bucket || req.next_follow_up_date) && (
              <dl className={styles.callFacts} data-testid="call-facts">
                {req.asnu && (
                  <div>
                    <dt>ASNU</dt>
                    <dd className={styles.mono}>{req.asnu}</dd>
                  </div>
                )}
                {req.time_estimate_bucket && (
                  <div>
                    <dt>{t(lang, 'Estimation', 'Estimate')}</dt>
                    <dd>{timeEstimateLabel(lang, req.time_estimate_bucket)}</dd>
                  </div>
                )}
                {req.next_follow_up_date && (
                  <div>
                    <dt>{t(lang, 'Suivi', 'Follow-up')}</dt>
                    <dd>{req.next_follow_up_date}</dd>
                  </div>
                )}
              </dl>
            )}

            {req.status === 'en_route' && (
              <div className={styles.openCallBannerCard}>
                {t(lang, 'En route', 'En route')}
                {elapsedLabel(req.en_route_at) && (
                  <> {t(lang, 'depuis', 'for')} {elapsedLabel(req.en_route_at)}</>
                )}
              </div>
            )}
            {req.status === 'arrived' && (
              <div className={styles.openCallBannerCard} data-status="arrived">
                {t(lang, 'Arrivé', 'Arrived')}
                {elapsedLabel(req.arrived_at) && (
                  <> {t(lang, 'depuis', 'for')} {elapsedLabel(req.arrived_at)}</>
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
            {canMarkArrived && (
              <button
                type="button"
                className={styles.enRouteBtn}
                onClick={handleArrived}
                disabled={busy}
                data-testid="arrived-btn"
              >
                {busy ? t(lang, 'Envoi…', 'Sending…') : t(lang, 'Arrivé', 'Arrived')}
              </button>
            )}
            {canCloseout && (
              <Link
                to={`/tech/appels/${req.request_id}/cloture`}
                className={`${styles.enRouteBtn} ${styles.btnLink}`}
                data-testid="closeout-btn"
              >
                {t(lang, 'Clôturer', 'Close out')}
              </Link>
            )}
            {actionError && <p className={styles.error}>{actionError}</p>}

            <section className={styles.card}>
              <h2 className={styles.cardTitle}>{t(lang, 'Adresse', 'Address')}</h2>
              <p>
                {req.building_address ?? '—'}
                {req.unit_label ? `, app. ${req.unit_label}` : ''}
              </p>
              {req.building_name && <p className={styles.muted}>{req.building_name}</p>}
            </section>

            <section className={styles.card} data-testid="call-problem">
              <h2 className={styles.cardTitle}>
                {req.raw_caller_body
                  ? t(lang, 'Problème (version du locataire)', 'Problem (tenant version)')
                  : t(lang, 'Problème', 'Problem')}
              </h2>
              <p className={styles.preWrap}>{problemText ?? '—'}</p>
              <IntakePhotos requestId={req.request_id} ids={req.intake_photo_ids ?? []} lang={lang} />
              <h2 className={styles.cardTitle}>{t(lang, "Permission d'entrer", 'Entry permission')}</h2>
              <p>{entryPermission ?? '—'}</p>
              <h2 className={styles.cardTitle}>{t(lang, 'Animaux', 'Animals')}</h2>
              <p>{animals ?? '—'}</p>
            </section>

            {hasTaxonomy && (
              <section className={styles.card} data-testid="call-taxonomy">
                <h2 className={styles.cardTitle}>{t(lang, 'Taxonomie', 'Taxonomy')}</h2>
                <dl className={styles.taxonomyList}>
                  {req.element && (
                    <div>
                      <dt>{t(lang, 'Élément', 'Element')}</dt>
                      <dd>{req.element}</dd>
                    </div>
                  )}
                  {req.symptome && (
                    <div>
                      <dt>{t(lang, 'Symptôme', 'Symptom')}</dt>
                      <dd>{req.symptome}</dd>
                    </div>
                  )}
                  {req.composante && (
                    <div>
                      <dt>{t(lang, 'Composante', 'Component')}</dt>
                      <dd>{req.composante}</dd>
                    </div>
                  )}
                  {req.emplacement && (
                    <div>
                      <dt>{t(lang, 'Emplacement', 'Location')}</dt>
                      <dd>{req.emplacement}</dd>
                    </div>
                  )}
                  {req.category_raw && !req.element && (
                    <div>
                      <dt>{t(lang, 'Catégorie', 'Category')}</dt>
                      <dd>{req.category_raw}</dd>
                    </div>
                  )}
                </dl>
              </section>
            )}

            {req.next_steps && (
              <section className={styles.card} data-testid="call-next-steps">
                <h2 className={styles.cardTitle}>{t(lang, 'Prochaines étapes', 'Next steps')}</h2>
                <p className={styles.preWrap}>{req.next_steps}</p>
              </section>
            )}

            {req.work_performed && (
              <section className={styles.card} data-testid="call-work-performed">
                <h2 className={styles.cardTitle}>{t(lang, 'Travail effectué', 'Work performed')}</h2>
                <p className={styles.preWrap}>{req.work_performed}</p>
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
                    {formatEntryDate(f.entry_date, lang)} {f.entered_by_initials ? `· ${f.entered_by_initials}` : ''}
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
