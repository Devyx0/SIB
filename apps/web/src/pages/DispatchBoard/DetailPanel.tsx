import { useEffect, useId, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRequest } from '../../hooks/useRequest';
import {
  ApiError, fetchEmployees, fetchTechnicianSuggestions,
  dispatchAddLog, dispatchSave,
  triggerTriage,
} from '../../api/client';
import TriageFeedbackWidget from '../../components/TriageFeedbackWidget';
import { useJustify, type JustifyRequest } from '../../components/Justification';
import type { DispatchFields, Justification } from '../../api/client';
import {
  IntakePhotos,
} from '../../components/RequestSections';
import HistoryTimeline from '../../components/HistoryTimeline';
import type { MeResponse } from '../../api/schema.d.ts';
import { roleLabel, statusLabel, timeEstimateLabel, sourceCalendarLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import { googleMapsUrl } from '../../lib/maps';
import styles from './DetailPanel.module.css';
import Select from '../../components/Select';


function formatCost(amount: number | string, lang: Lang): string {
  return new Intl.NumberFormat(lang === 'fr' ? 'fr-CA' : 'en-CA', {
    style: 'currency',
    currency: 'CAD',
  }).format(Number(amount));
}

interface Props {
  requestId: number;
  onClose: () => void;
  onSelectPeer?: (id: number) => void;
  lang?: Lang;
  me?: MeResponse | null;
}

const URGENCY_OPTIONS: Array<{ value: string | null }> = [
  { value: 'AJD' },
  { value: 'ajd' },
  { value: null },
];

const BAND_FR: Record<string, string> = {
  critical: 'critique', emergency: 'urgence', priority: 'priorité', normal: 'normal',
};
const LOC_FR: Record<string, string> = { quebec: 'Québec', levis: 'Lévis' };

export default function DetailPanel({ requestId, onClose, onSelectPeer, lang = 'fr', me }: Props) {
  const [polling, setPolling] = useState(false);
  const [triageTimeout, setTriageTimeout] = useState(false);
  const pollingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { data, isPending, isError, error } = useRequest(requestId, { refetchInterval: polling ? 2000 : false });
  const qc = useQueryClient();
  const isEditor = !!(me?.roles.includes('coordinator') || me?.roles.includes('director'));
  const isClosed = data?.status === 'closed';
  const isEnRoute = data?.status === 'en_route';
  const EN_ROUTE_MSG = t(lang,
    "Appel en cours — le technicien doit d'abord clôturer",
    'Call in progress — the technician must close it out first');
  const ASSIGNEE_EN_ROUTE_MSG = t(lang,
    'Technicien déjà en route — clôturer d\'abord',
    'Technician already en route — close out first');

  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: fetchEmployees,
    staleTime: 5 * 60 * 1000,
    enabled: isEditor,
  });

  const { data: techSuggestions } = useQuery({
    queryKey: ['technician-suggestions', requestId, lang],
    queryFn: () => fetchTechnicianSuggestions(requestId, lang === 'en' ? 'en' : 'fr'),
    enabled: isEditor && (data?.status === 'triaged' || data?.status === 'awaiting_redispatch'),
    staleTime: 60 * 1000,
  });

  const assignableEmployees = (employees ?? []).filter(
    (e) => e.role === 'technician' || e.role === 'contractor'
  );

  const [staleMsg, setStaleMsg] = useState<string | null>(null);
  const [followUpDate, setFollowUpDate] = useState<string | null>(null);
  const [nextSteps, setNextSteps] = useState<string | null>(null);
  const [cost, setCost] = useState<string | null>(null);
  const [logText, setLogText] = useState('');
  const [rescheduleDate, setRescheduleDate] = useState<string | null>(null);
  const [assignEmpId, setAssignEmpId] = useState<number | null>(null);
  // undefined = untouched; null = « Aucune »
  const [urgencyDraft, setUrgencyDraft] = useState<string | null | undefined>(undefined);
  const weatherEnabled = !!me?.weather_escalation_enabled;

  // Sync controlled select with server data when data first loads or request changes
  useEffect(() => {
    if (data) setAssignEmpId(data.assigned_employee_id ?? null);
  }, [data?.request_id, data?.assigned_employee_id]);

  // Poll while triage is in progress; stop after 3 minutes with retry option
  useEffect(() => {
    if (data?.status === 'triage_pending') {
      setPolling(true);
      setTriageTimeout(false);
      pollingTimerRef.current = setTimeout(() => {
        setPolling(false);
        setTriageTimeout(true);
      }, 3 * 60 * 1000);
    } else {
      setPolling(false);
      setTriageTimeout(false);
      if (pollingTimerRef.current) { clearTimeout(pollingTimerRef.current); pollingTimerRef.current = null; }
    }
    return () => {
      if (pollingTimerRef.current) { clearTimeout(pollingTimerRef.current); pollingTimerRef.current = null; }
    };
  }, [data?.status]);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') requestCloseRef.current();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, []);

  useEffect(() => {
    document.body.classList.add('modal-open');
    return () => { document.body.classList.remove('modal-open'); };
  }, []);

  // Move focus into the dialog on open and give it back on close.
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => { prev?.focus?.(); };
  }, []);
  const titleId = useId();

  function errorText() {
    const traceId = error instanceof ApiError ? error.traceId : undefined;
    const base = t(lang, 'Erreur lors du chargement', 'Error loading request');
    return traceId ? `${base} [${traceId}]` : base;
  }

  async function applyAndRefresh(fn: () => Promise<unknown>) {
    setStaleMsg(null);
    try {
      const updated = await fn();
      qc.setQueryData(['request', requestId], updated);
      qc.invalidateQueries({ queryKey: ['requests'] });
      setFollowUpDate(null);
      setNextSteps(null);
      setCost(null);
      setRescheduleDate(null);
      setUrgencyDraft(undefined);
      setLogText('');
    } catch (err) {
      if (err instanceof ApiError && err.code === 'STALE_DATA') {
        setStaleMsg(t(lang, 'La demande a été modifiée — rechargement…', 'Modified by another user — reloading…'));
        qc.invalidateQueries({ queryKey: ['requests'] });
        qc.invalidateQueries({ queryKey: ['request', requestId] });
        setTimeout(() => setStaleMsg(null), 3000);
      } else if (err instanceof ApiError && err.code === 'REQUEST_EN_ROUTE') {
        // The refetched status becomes en_route, which also disables the control.
        setStaleMsg(EN_ROUTE_MSG);
        qc.invalidateQueries({ queryKey: ['requests'] });
        qc.invalidateQueries({ queryKey: ['request', requestId] });
      } else if (err instanceof ApiError && err.code === 'ASSIGNEE_EN_ROUTE') {
        setStaleMsg(ASSIGNEE_EN_ROUTE_MSG);
        qc.invalidateQueries({ queryKey: ['employees'] });
        if (data) setAssignEmpId(data.assigned_employee_id ?? null);
      }
    }
  }

  // Every dispatcher decision is justified (voice or typed) before it is
  // saved; cancelling the prompt leaves the call untouched.
  const justify = useJustify();
  async function decide(
    req: JustifyRequest,
    run: (j: Justification) => Promise<unknown>,
    onCancel?: () => void,
  ) {
    const j = await justify(req);
    if (!j) { onCancel?.(); return; }
    await applyAndRefresh(() => run(j));
  }

  const NONE = t(lang, 'Aucun', 'None');
  const employeeName = (id: number | null) =>
    id == null
      ? t(lang, 'Non assigné', 'Unassigned')
      : (employees ?? []).find((e) => e.employee_id === id)?.nom_employe ?? `#${id}`;
  const clip = (v: string | null | undefined) => (v && v.length > 60 ? `${v.slice(0, 57)}…` : v || NONE);

  // ── Staged edits: everything is saved together with « Enregistrer » ──
  const fmtCost = (v: number | null) => (v != null ? formatCost(v, lang) : NONE);
  const costDraft: number | null | undefined =
    cost === null ? undefined : cost.trim() === '' ? null : Number(cost);
  type Pending = { key: keyof DispatchFields; label: string; before: string; after: string; value: unknown };
  const pending: Pending[] = [];
  if (data) {
    if (assignEmpId !== (data.assigned_employee_id ?? null)) {
      pending.push({ key: 'assigned_employee_id', label: t(lang, 'Assignation', 'Assignment'),
        before: data.assigned_employee_name ?? employeeName(data.assigned_employee_id), after: employeeName(assignEmpId), value: assignEmpId });
    }
    if (rescheduleDate && rescheduleDate !== data.start_date) {
      pending.push({ key: 'start_date', label: t(lang, 'Date de répartition', 'Schedule date'),
        before: data.start_date ?? NONE, after: rescheduleDate, value: rescheduleDate });
    }
    if (urgencyDraft !== undefined && urgencyDraft !== (data.urgency_tier ?? null)) {
      pending.push({ key: 'urgency_tier', label: t(lang, 'Urgence', 'Urgency'),
        before: data.urgency_tier ?? t(lang, 'Aucune', 'None'), after: urgencyDraft ?? t(lang, 'Aucune', 'None'), value: urgencyDraft });
    }
    if (followUpDate !== null && (followUpDate || null) !== (data.next_follow_up_date ?? null)) {
      pending.push({ key: 'next_follow_up_date', label: t(lang, 'Prochain suivi', 'Next follow-up'),
        before: data.next_follow_up_date ?? NONE, after: followUpDate || NONE, value: followUpDate || null });
    }
    if (nextSteps !== null && (nextSteps.trim() || null) !== (data.next_steps ?? null)) {
      pending.push({ key: 'next_steps', label: t(lang, 'Prochaines étapes', 'Next steps'),
        before: clip(data.next_steps), after: clip(nextSteps.trim()), value: nextSteps.trim() || null });
    }
    const savedCost = data.estimated_cost != null ? Number(data.estimated_cost) : null;
    if (costDraft !== undefined && !Number.isNaN(costDraft) && costDraft !== savedCost) {
      pending.push({ key: 'estimated_cost', label: t(lang, 'Coût estimé', 'Estimated cost'),
        before: fmtCost(savedCost), after: fmtCost(costDraft), value: costDraft });
    }
  }
  const changedKeys = new Set(pending.map((p) => p.key));
  const effectiveUrgency = urgencyDraft !== undefined ? urgencyDraft : (data?.urgency_tier ?? null);

  function discardEdits() {
    setAssignEmpId(data?.assigned_employee_id ?? null);
    setRescheduleDate(null);
    setUrgencyDraft(undefined);
    setFollowUpDate(null);
    setNextSteps(null);
    setCost(null);
  }

  function doSave() {
    if (!data || pending.length === 0) return;
    const changes = Object.fromEntries(pending.map((p) => [p.key, p.value])) as Partial<DispatchFields>;
    const n = pending.length;
    decide(
      {
        decision: n === 1 ? pending[0].label : t(lang, `${n} modifications`, `${n} changes`),
        ...(n === 1 ? { before: pending[0].before, after: pending[0].after } : {}),
        changes: pending.map(({ label, before, after }) => ({ label, before, after })),
      },
      (justification) => dispatchSave(requestId, {
        current: {
          assigned_employee_id: data.assigned_employee_id ?? null,
          start_date: data.start_date ?? null,
          urgency_tier: data.urgency_tier ?? null,
          next_follow_up_date: data.next_follow_up_date ?? null,
          next_steps: data.next_steps ?? null,
          estimated_cost: data.estimated_cost != null ? Number(data.estimated_cost) : null,
        },
        changes,
        justification,
      }),
    );
  }

  // Closing with unsaved edits asks first.
  function requestClose() {
    if (pending.length > 0 && !window.confirm(t(lang,
      'Des modifications ne sont pas enregistrées. Fermer quand même ?',
      'You have unsaved changes. Close anyway?'))) return;
    onClose();
  }
  const requestCloseRef = useRef(requestClose);
  requestCloseRef.current = requestClose;


  // Detect ineligible (coordinator/director) current assignee for item 8
  const currentAssigneeInAll = data?.assigned_employee_id != null
    ? (employees ?? []).find((e) => e.employee_id === data.assigned_employee_id)
    : null;
  const isIneligibleAssignee = currentAssigneeInAll != null
    && currentAssigneeInAll.role !== 'technician'
    && currentAssigneeInAll.role !== 'contractor';

  const accessText = data ? ((data.raw_caller_body?.entry_permission ?? data.entry_permission) || '—') : '—';
  const animalsText = data ? ((data.raw_caller_body?.animals ?? data.animals) || '—') : '—';
  const buildingAddress = data ? (data.building_full_address ?? data.building_address) : null;

  return (
    <>
      <div className={styles.backdrop} onClick={requestClose} aria-hidden />
      <div className={styles.frame}>
        <section
          className={styles.panel}
          data-testid="detail-panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby={data ? titleId : undefined}
          aria-label={data ? undefined : t(lang, 'Détails de la demande', 'Request details')}
        >
          <header className={styles.header}>
            <div className={styles.headMain}>
              <div className={styles.headMeta}>
                <span className={styles.requestId}>#{requestId}</span>
                {data && (
                  <>
                    <span className={styles.statusBadge} data-status={data.status}>{statusLabel(lang, data.status)}</span>
                    {data.urgency_tier ? (
                      <span className={data.urgency_tier === 'AJD' ? styles.urgentBadge : styles.softBadge}>
                        {data.urgency_tier}
                      </span>
                    ) : (
                      <span className={styles.softBadge}>{t(lang, 'non urgente', 'not urgent')}</span>
                    )}
                    {data.closeout_urgent && <span className={styles.urgentBadge}>URGENT</span>}
                  </>
                )}
              </div>
              {data && <h2 className={styles.title} id={titleId}>{data.raw_title ?? '—'}</h2>}
              {data && (
                <dl className={styles.headFacts}>
                  <div><dt>{t(lang, 'Date', 'Date')}</dt><dd>{data.start_date ?? '—'}</dd></div>
                  <div><dt>ASNU</dt><dd className={styles.mono}>{data.asnu ?? '—'}</dd></div>
                  <div><dt>{t(lang, 'Source', 'Source')}</dt><dd>{sourceCalendarLabel(lang, data.source_calendar)}</dd></div>
                </dl>
              )}
            </div>
            <button ref={closeRef} className={styles.closeBtn} onClick={requestClose} aria-label={t(lang, 'Fermer', 'Close')}>
              <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
          </header>

          <div className={styles.body}>
            {isPending && <p className={styles.loading}>{t(lang, 'Chargement…', 'Loading…')}</p>}
            {isError && <p className={styles.error}>{errorText()}</p>}
            {staleMsg && <p className={styles.staleMsg}>{staleMsg}</p>}

            {data && (
              <>
              <div className={styles.grid}>
                {/* ── Left: what happened ───────────────────────────── */}
                <div className={styles.colMain}>
                  {(data.raw_caller_body?.problems || data.problems) && (
                    <section className={styles.card} data-testid="problems-section">
                      <h3 className={styles.cardTitle}>{t(lang, 'Problème décrit', 'Reported problem')}</h3>
                      <p className={styles.prose}>{data.raw_caller_body?.problems ?? data.problems}</p>
                      <IntakePhotos requestId={data.request_id} ids={data.intake_photo_ids ?? []} lang={lang} />
                    </section>
                  )}

                  {/* AI interpretation comparison — only when AI ran AND values differ from tenant's */}
                  {data.triage_model_version && data.raw_caller_body && (() => {
                    const accessDiffers = data.raw_caller_body.entry_permission !== data.entry_permission;
                    const animalsDiffers = data.raw_caller_body.animals !== data.animals;
                    const problemsDiffer = !!data.problems && data.raw_caller_body?.problems !== data.problems;
                    if (!accessDiffers && !animalsDiffers && !problemsDiffer) return null;
                    const pair = (label: string, tenant: string | null, ai: string | null) => (
                      <div className={styles.compare}>
                        <span className={styles.compareLabel}>{label}</span>
                        <div className={styles.compareCols}>
                          <div>
                            <span className={styles.compareWho}>{t(lang, 'Déclaré par le locataire', 'Tenant declared')}</span>
                            <p className={styles.prose}>{tenant ?? '—'}</p>
                          </div>
                          <div className={styles.compareAi}>
                            <span className={styles.compareWho}>{t(lang, 'Interprétation IA', 'AI interpretation')}</span>
                            <p className={styles.prose}>{ai ?? '—'}</p>
                          </div>
                        </div>
                      </div>
                    );
                    return (
                      <section className={styles.card} data-testid="dual-display">
                        <h3 className={styles.cardTitle}>{t(lang, 'Interprétation IA', 'AI interpretation')}</h3>
                        {problemsDiffer && pair(t(lang, 'Problème', 'Problem'), data.raw_caller_body?.problems ?? null, data.problems)}
                        {accessDiffers && pair(t(lang, 'Accès', 'Access'), data.raw_caller_body.entry_permission, data.entry_permission)}
                        {animalsDiffers && pair(t(lang, 'Animaux', 'Animals'), data.raw_caller_body.animals, data.animals)}
                      </section>
                    );
                  })()}

                  {/* AI section — triage summary and notes, coord/dir only */}
                  {isEditor && data.triage_model_version && (
                    <section className={styles.card} data-testid="ai-section">
                      <h3 className={styles.cardTitle}>{t(lang, 'Résumé IA', 'AI summary')}</h3>
                      {data.problem_summary && <p className={styles.prose}>{data.problem_summary}</p>}
                      {data.other_notes && (
                        <>
                          <h4 className={styles.subTitle}>{t(lang, 'Notes IA', 'AI notes')}</h4>
                          <p className={styles.prose}>{data.other_notes}</p>
                        </>
                      )}
                      <TriageFeedbackWidget requestId={requestId} lang={lang} />
                    </section>
                  )}

                  {(data.duplicate_of_request_id || data.addition_to_request_id) && (
                    <section
                      className={`${styles.card} ${data.duplicate_of_request_id ? styles.dupBanner : styles.addBanner}`}
                      data-testid="dup-add-section"
                    >
                      <h3 className={styles.cardTitle}>
                        {data.duplicate_of_request_id
                          ? t(lang, 'Doublon potentiel', 'Possible duplicate')
                          : t(lang, 'Ajout / fusion', 'Addition / merge')}
                      </h3>
                      {data.duplicate_of_request_id != null && (
                        <p className={styles.prose} data-testid="duplicate-of">
                          {t(
                            lang,
                            'Même unité + même problème — ne pas fusionner automatiquement. Voir',
                            'Same unit + same problem — do not auto-merge. See',
                          )}{' '}
                          <button
                            type="button"
                            className={styles.peerLink}
                            onClick={() => onSelectPeer?.(data.duplicate_of_request_id!)}
                          >
                            #{data.duplicate_of_request_id}
                          </button>
                        </p>
                      )}
                      {data.addition_to_request_id != null && (
                        <p className={styles.prose} data-testid="addition-to">
                          {t(
                            lang,
                            'Problème différent — fusionné dans / lié à',
                            'Different problem — merged into / linked to',
                          )}{' '}
                          <button
                            type="button"
                            className={styles.peerLink}
                            onClick={() => onSelectPeer?.(data.addition_to_request_id!)}
                          >
                            #{data.addition_to_request_id}
                          </button>
                        </p>
                      )}
                    </section>
                  )}

                  <section className={`${styles.card} ${styles.historyCard}`}>
                    <HistoryTimeline
                      requestId={data.request_id}
                      visits={data.visits ?? []}
                      followups={data.followup_log}
                      decisions={data.justification_log}
                      statusChanges={data.status_history ?? []}
                      lang={lang}
                    />
                  </section>
                </div>

                {/* ── Right: reference facts + actions ──────────────── */}
                <div className={styles.colSide}>
                  <section className={styles.card}>
                    <h3 className={styles.cardTitle}>{t(lang, 'Lieu', 'Location')}</h3>
                    <dl className={styles.facts}>
                      <dt>{t(lang, 'Immeuble', 'Building')}</dt>
                      <dd>
                        {buildingAddress ? (
                          <a
                            className={styles.mapLink}
                            href={googleMapsUrl(buildingAddress)}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={t(lang, 'Ouvrir dans Google Maps', 'Open in Google Maps')}
                            data-testid="building-map-link"
                          >
                            {buildingAddress}
                            <span aria-hidden="true"> ↗</span>
                          </a>
                        ) : '—'}
                      </dd>
                      <dt>{t(lang, 'Unité', 'Unit')}</dt>
                      <dd>{data.unit_label ?? '—'}</dd>
                      <dt>{t(lang, "N° d'unité", 'Unit #')}</dt>
                      <dd>{data.unique_unit_number ?? '—'}</dd>
                      <dt>{t(lang, 'Territoire', 'Territory')}</dt>
                      <dd>{data.territoire ?? '—'}</dd>
                      <dt>{t(lang, 'Accès', 'Access')}</dt>
                      <dd>{accessText}</dd>
                      <dt>{t(lang, 'Animaux', 'Animals')}</dt>
                      <dd>{animalsText}</dd>
                    </dl>
                  </section>

                  <section className={styles.card}>
                    <h3 className={styles.cardTitle}>{t(lang, 'Appelant', 'Caller')}</h3>
                    <dl className={styles.facts}>
                      <dt>{t(lang, 'Nom', 'Name')}</dt>
                      <dd>{data.caller_name ?? '—'}</dd>
                      <dt>{t(lang, 'Téléphone', 'Phone')}</dt>
                      <dd data-testid="phone-display">
                        {data.caller_phone_placeholder
                          ? t(lang, 'non fourni', 'not provided')
                          : data.caller_phone
                            ? <a href={`tel:${data.caller_phone}`}>{data.caller_phone}</a>
                            : '—'}
                      </dd>
                      <dt>{t(lang, 'Courriel', 'Email')}</dt>
                      <dd data-testid="email-display">
                        {data.caller_email_placeholder
                          ? t(lang, 'non fourni', 'not provided')
                          : data.caller_email
                            ? <a href={`mailto:${data.caller_email}`}>{data.caller_email}</a>
                            : '—'}
                      </dd>
                    </dl>
                  </section>

                  <section className={styles.card}>
                    <h3 className={styles.cardTitle}>{t(lang, 'Planification', 'Planning')}</h3>
                    <dl className={styles.facts}>
                      <dt>{t(lang, 'Employé', 'Employee')}</dt>
                      <dd>{data.assigned_employee_name ?? '—'}</dd>
                      <dt>{t(lang, 'Sous-traitant', 'Subcontractor')}</dt>
                      <dd>{data.subcontractor_name ?? '—'}</dd>
                      <dt>{t(lang, 'Estimation', 'Est. time')}</dt>
                      <dd>{timeEstimateLabel(lang, data.time_estimate_bucket)}</dd>
                      <dt>{t(lang, 'Coût estimé', 'Est. cost')}</dt>
                      <dd>{data.estimated_cost != null ? formatCost(data.estimated_cost, lang) : '—'}</dd>
                    </dl>
                  </section>
                  {/* Weather summary — read-only; the evaluation runs at triage (or via the
                      weather-check endpoint) and the escalation is applied automatically. */}
                  {isEditor && weatherEnabled && data.weather_evaluation?.status === 'ok' && (() => {
                    const ev = data.weather_evaluation;
                    const bandFr = ev.band_name ? (BAND_FR[ev.band_name] ?? ev.band_name) : '';
                    const locFr = ev.location ? (LOC_FR[ev.location] ?? ev.location) : '';
                    return (
                      <section className={styles.card} data-testid="weather-section">
                        <h3 className={styles.cardTitle}>{t(lang, 'Météo', 'Weather')}</h3>
                        <div className={styles.weatherResult} data-testid="weather-result">
                          <p className={styles.weatherContext}>
                            {t(lang, 'Météo', 'Weather')} — {locFr} : {ev.min_forecast_temp_24h_c}&nbsp;°C {t(lang, 'prévu (24 h)', 'forecast (24 h)')}, {t(lang, 'palier', 'band')} {bandFr}
                          </p>
                          {ev.evaluated_at && (
                            <p className={styles.weatherTime}>
                              {t(lang, 'évalué le', 'evaluated')} {new Date(ev.evaluated_at).toLocaleString(lang === 'fr' ? 'fr-CA' : 'en-CA')}
                            </p>
                          )}
                          {ev.is_critical && (
                            <span className={styles.astreinteBadge} data-testid="weather-astreinte">
                              {t(lang, 'Astreinte / garde', 'On-call')}
                            </span>
                          )}
                          <p className={styles.weatherDraft}>
                            {t(lang, 'Seuils provisoires — à valider', 'Provisional thresholds — to validate')}
                          </p>
                          <p className={styles.weatherLicence} data-testid="weather-licence">
                            {t(lang, 'Source : Environnement et Changement climatique Canada', 'Source: Environment and Climate Change Canada')}
                          </p>
                        </div>
                      </section>
                    );
                  })()}

                  {/* Triage button — intake_received or triage_failed */}
                  {isEditor && (data.status === 'intake_received' || data.status === 'triage_failed' || data.status === 'triage_pending') && (
                    <section className={styles.card} data-testid="triage-section">
                      <h3 className={styles.cardTitle}>{t(lang, 'Triage automatique', 'Auto triage')}</h3>
                      {data.status === 'triage_pending' && !triageTimeout ? (
                        <p className={styles.loading} data-testid="triage-pending-msg">
                          {t(lang, 'Triage en cours…', 'Triage in progress…')}
                        </p>
                      ) : (
                        <>
                          {data.status === 'triage_failed' && (
                            <p className={styles.error}>{t(lang, 'Triage échoué — réessayez.', 'Triage failed — retry.')}</p>
                          )}
                          {triageTimeout && (
                            <p className={styles.error} data-testid="triage-timeout-msg">
                              {t(lang, 'Triage toujours en cours après 3 min — réessayez si nécessaire.', 'Triage still running after 3 min — retry if needed.')}
                            </p>
                          )}
                          <button
                            className={styles.applyBtn}
                            data-testid="triage-btn"
                            onClick={async () => {
                              setTriageTimeout(false);
                              try {
                                await triggerTriage(requestId, { lang });
                                qc.invalidateQueries({ queryKey: ['request', requestId] });
                                setPolling(true);
                              } catch (err) {
                                const msg = err instanceof ApiError ? err.message : String(err);
                                setStaleMsg(msg);
                              }
                            }}
                          >
                            {t(lang, 'Lancer le triage', 'Run triage')}
                          </button>
                        </>
                      )}
                    </section>
                  )}

                </div>
              </div>

                {isEditor && (
                  <section className={`${styles.card} ${styles.actionsCard}`} data-testid="edit-controls">
                    <h3 className={styles.cardTitle}>
                      {t(lang, 'Actions répartiteur', 'Dispatch actions')}
                    </h3>

                    {isClosed && (
                      <p className={styles.closedNotice}>
                        {t(lang, 'Demande fermée — seul le journal est modifiable.', 'Closed — only log entries are allowed.')}
                      </p>
                    )}

                    <div className={styles.actionsGrid}>
                      {/* Post-triage suggestions — pre-fill assign only */}
                      {(data.status === 'triaged' || data.status === 'awaiting_redispatch')
                        && (techSuggestions?.suggestions?.length ?? 0) > 0 && (
                        <div className={styles.suggestBlock} data-testid="tech-suggestions">
                          <label className={styles.editLabel}>
                            {t(lang, 'Suggestion technicien', 'Technician suggestion')}
                          </label>
                          <ul className={styles.suggestList}>
                            {techSuggestions!.suggestions.map((s) => (
                              <li key={s.employee_id}>
                                <button
                                  type="button"
                                  className={styles.suggestBtn}
                                  disabled={isClosed || isEnRoute}
                                  data-testid={`tech-suggest-${s.employee_id}`}
                                  onClick={() => setAssignEmpId(s.employee_id)}
                                >
                                  <span className={styles.suggestName}>
                                    {s.initials ? `${s.initials} — ` : ''}{s.name}
                                    {s.is_en_route && (
                                      <span className={styles.suggestEnRoute} data-testid="suggest-en-route">
                                        {t(lang, 'En route', 'En route')}
                                      </span>
                                    )}
                                  </span>
                                  <span className={styles.suggestWhy}>{s.why}</span>
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Assign — locked while the technician is en route */}
                      <div className={`${styles.editField} ${changedKeys.has('assigned_employee_id') ? styles.editFieldChanged : ''}`}>
                        <label className={styles.editLabel}>{t(lang, 'Assigné à', 'Assigned to')}</label>
                        <Select
                          className={styles.editInput}
                          value={String(assignEmpId ?? '')}
                          disabled={isClosed || isEnRoute}
                          data-testid="assign-select"
                          onChange={(e) => {
                            const empId = e.target.value === '' ? null : Number(e.target.value);
                            setAssignEmpId(empId);
                          }}
                        >
                          <option value="">— {t(lang, 'Non assigné', 'Unassigned')} —</option>
                          {isIneligibleAssignee && currentAssigneeInAll && (
                            <option value={String(data.assigned_employee_id)} disabled>
                              {currentAssigneeInAll.nom_employe} ({roleLabel(lang, currentAssigneeInAll.role)})
                            </option>
                          )}
                          {assignableEmployees.map((e) => (
                            <option
                              key={e.employee_id}
                              value={e.employee_id}
                              disabled={e.is_en_route}
                            >
                              {e.nom_employe} ({roleLabel(lang, e.role)})
                              {e.is_en_route
                                ? ` — ${t(lang, 'en route', 'en route')}`
                                : ''}
                            </option>
                          ))}
                        </Select>
                        {isEnRoute && (
                          <p className={styles.closedNotice} data-testid="en-route-notice">
                            {EN_ROUTE_MSG}
                          </p>
                        )}
                      </div>

                      {/* Reschedule */}
                      <div className={`${styles.editField} ${changedKeys.has('start_date') ? styles.editFieldChanged : ''}`}>
                        <label className={styles.editLabel}>{t(lang, 'Date de répartition', 'Schedule date')}</label>
                        <input
                          type="date"
                          className={styles.editInput}
                          value={rescheduleDate ?? data.start_date ?? ''}
                          disabled={isClosed}
                          onChange={(e) => setRescheduleDate(e.target.value)}
                          data-testid="reschedule-input"
                        />
                      </div>

                      {/* Urgency */}
                      <div className={`${styles.editField} ${changedKeys.has('urgency_tier') ? styles.editFieldChanged : ''}`}>
                        <span className={styles.editLabel}>{t(lang, 'Urgence', 'Urgency')}</span>
                        <div className={styles.urgencyPills}>
                          {URGENCY_OPTIONS.map(({ value }) => (
                            <button
                              key={String(value)}
                              type="button"
                              className={`${styles.pill} ${effectiveUrgency === value ? styles.pillActive : ''}`}
                              aria-pressed={effectiveUrgency === value}
                              disabled={isClosed}
                              onClick={() => setUrgencyDraft(value)}
                            >
                              {value ?? t(lang, 'Aucune', 'None')}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Next follow-up date */}
                      <div className={`${styles.editField} ${changedKeys.has('next_follow_up_date') ? styles.editFieldChanged : ''}`}>
                        <label className={styles.editLabel}>{t(lang, 'Prochain suivi', 'Next follow-up')}</label>
                        <input
                          type="date"
                          className={styles.editInput}
                          value={followUpDate ?? data.next_follow_up_date ?? ''}
                          disabled={isClosed}
                          onChange={(e) => setFollowUpDate(e.target.value)}
                          data-testid="follow-up-input"
                        />
                      </div>

                      {/* Next steps */}
                      <div className={`${styles.editField} ${changedKeys.has('next_steps') ? styles.editFieldChanged : ''}`}>
                        <label className={styles.editLabel}>{t(lang, 'Prochaines étapes', 'Next steps')}</label>
                        <textarea
                          className={styles.editTextarea}
                          value={nextSteps ?? data.next_steps ?? ''}
                          disabled={isClosed}
                          onChange={(e) => setNextSteps(e.target.value)}
                          rows={2}
                          data-testid="next-steps-input"
                        />
                      </div>

                      {/* Cost */}
                      <div className={`${styles.editField} ${changedKeys.has('estimated_cost') ? styles.editFieldChanged : ''}`}>
                        <label className={styles.editLabel}>{t(lang, 'Coût estimé ($)', 'Est. cost ($)')}</label>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          className={styles.editInput}
                          value={cost ?? (data.estimated_cost != null ? String(data.estimated_cost) : '')}
                          disabled={isClosed}
                          onChange={(e) => setCost(e.target.value)}
                          data-testid="cost-input"
                        />
                      </div>

                      {/* Log entry — always enabled even on closed */}
                      <div className={styles.editField}>
                        <span className={styles.editLabel}>{t(lang, 'Ajouter une note', 'Add log entry')}</span>
                        <div className={styles.logForm}>
                          <textarea
                            className={styles.editTextarea}
                            value={logText}
                            onChange={(e) => setLogText(e.target.value)}
                            rows={2}
                            placeholder={t(lang, 'Note de suivi…', 'Follow-up note…')}
                            data-testid="log-text"
                          />
                          <button
                            className={styles.applyBtn}
                            disabled={!logText.trim()}
                            onClick={() => applyAndRefresh(() =>
                              dispatchAddLog(requestId, { entry_text: logText.trim() })
                            )}
                          >
                            {t(lang, 'Ajouter', 'Add')}
                          </button>
                        </div>
                      </div>
                    </div>

                    {!isClosed && (
                      <div className={`${styles.saveBar} ${pending.length ? styles.saveBarDirty : ''}`} data-testid="save-bar">
                        <span className={styles.saveStatus} aria-live="polite">
                          {pending.length === 0
                            ? t(lang, 'Aucune modification', 'No changes')
                            : t(lang,
                              `${pending.length} modification${pending.length > 1 ? 's' : ''} non enregistrée${pending.length > 1 ? 's' : ''}`,
                              `${pending.length} unsaved change${pending.length > 1 ? 's' : ''}`)}
                        </span>
                        {pending.length > 0 && (
                          <button type="button" className={styles.discardBtn} onClick={discardEdits}>
                            {t(lang, 'Annuler les modifications', 'Discard changes')}
                          </button>
                        )}
                        <button
                          type="button"
                          className={styles.saveBtn}
                          disabled={pending.length === 0}
                          onClick={doSave}
                          data-testid="save-btn"
                        >
                          {t(lang, 'Enregistrer', 'Save')}
                        </button>
                      </div>
                    )}
                  </section>
                )}
              </>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
