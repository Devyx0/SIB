import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRequest } from '../../hooks/useRequest';
import {
  ApiError, fetchEmployees,
  dispatchAssign, dispatchReschedule, dispatchSetUrgency,
  dispatchSetFollowUpDate, dispatchSetNextSteps, dispatchSetCost, dispatchAddLog,
  triggerTriage, routeRequest,
} from '../../api/client';
import TriageFeedbackWidget from '../../components/TriageFeedbackWidget';
import {
  DecisionHistorySection, FollowupLogSection, VisitsSection,
} from '../../components/RequestSections';
import type { MeResponse } from '../../api/schema.d.ts';
import { roleLabel, statusLabel, timeEstimateLabel, sourceCalendarLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import styles from './DetailPanel.module.css';


function formatCost(amount: number | string, lang: Lang): string {
  return new Intl.NumberFormat(lang === 'fr' ? 'fr-CA' : 'en-CA', {
    style: 'currency',
    currency: 'CAD',
  }).format(Number(amount));
}

interface Props {
  requestId: number;
  onClose: () => void;
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

export default function DetailPanel({ requestId, onClose, lang = 'fr', me }: Props) {
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

  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: fetchEmployees,
    staleTime: 5 * 60 * 1000,
    enabled: isEditor,
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
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  useEffect(() => {
    document.body.classList.add('modal-open');
    return () => { document.body.classList.remove('modal-open'); };
  }, []);

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
      }
    }
  }

  function doAssign(employeeId: number | null) {
    if (!data) return;
    applyAndRefresh(() => dispatchAssign(requestId, {
      employee_id: employeeId,
      current_assigned_employee_id: data.assigned_employee_id,
      current_start_date: data.start_date,
      current_urgency_tier: data.urgency_tier,
    }));
  }

  function doReschedule(date: string) {
    if (!data) return;
    applyAndRefresh(() => dispatchReschedule(requestId, {
      start_date: date,
      current_start_date: data.start_date,
      current_assigned_employee_id: data.assigned_employee_id,
      current_urgency_tier: data.urgency_tier,
    }));
  }

  function doSetUrgency(tier: string | null) {
    if (!data) return;
    applyAndRefresh(() => dispatchSetUrgency(requestId, {
      urgency_tier: tier as 'AJD' | 'ajd' | null,
      current_urgency_tier: data.urgency_tier,
      current_assigned_employee_id: data.assigned_employee_id,
      current_start_date: data.start_date,
      weather_evaluation_id: null,
    }));
  }

  // Detect ineligible (coordinator/director) current assignee for item 8
  const currentAssigneeInAll = data?.assigned_employee_id != null
    ? (employees ?? []).find((e) => e.employee_id === data.assigned_employee_id)
    : null;
  const isIneligibleAssignee = currentAssigneeInAll != null
    && currentAssigneeInAll.role !== 'technician'
    && currentAssigneeInAll.role !== 'contractor';

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden />
      <aside className={styles.panel} data-testid="detail-panel" aria-label={t(lang, 'Détails de la demande', 'Request details')}>
        <header className={styles.header}>
          <span className={styles.requestId}>#{requestId}</span>
          <button className={styles.closeBtn} onClick={onClose} aria-label={t(lang, 'Fermer', 'Close')}>✕</button>
        </header>

        <div className={styles.body}>
          {isPending && <p className={styles.loading}>{t(lang, 'Chargement…', 'Loading…')}</p>}
          {isError && <p className={styles.error}>{errorText()}</p>}
          {staleMsg && <p className={styles.staleMsg}>{staleMsg}</p>}

          {data && (
            <>
              <h2 className={styles.title}>{data.raw_title ?? '—'}</h2>

              <dl className={styles.dl}>
                <dt>{t(lang, 'Date', 'Date')}</dt>
                <dd>{data.start_date ?? '—'}</dd>

                <dt>ASNU</dt>
                <dd className={styles.mono}>{data.asnu ?? '—'}</dd>

                <dt>{t(lang, 'Urgence', 'Urgency')}</dt>
                <dd>{data.urgency_tier ?? '—'}</dd>

                <dt>{t(lang, 'Statut', 'Status')}</dt>
                <dd>{statusLabel(lang, data.status)}</dd>

                <dt>{t(lang, 'Immeuble', 'Building')}</dt>
                <dd>{data.building_address ?? '—'}</dd>

                <dt>{t(lang, 'Territoire', 'Territory')}</dt>
                <dd>{data.territoire ?? '—'}</dd>

                <dt>{t(lang, 'Employé', 'Employee')}</dt>
                <dd>{data.assigned_employee_name ?? '—'}</dd>

                <dt>{t(lang, 'Sous-traitant', 'Subcontractor')}</dt>
                <dd>{data.subcontractor_name ?? '—'}</dd>

                <dt>{t(lang, 'Estimation', 'Est. time')}</dt>
                <dd>{timeEstimateLabel(lang, data.time_estimate_bucket)}</dd>

                <dt>{t(lang, 'Coût estimé', 'Est. cost')}</dt>
                <dd>{data.estimated_cost != null ? formatCost(data.estimated_cost, lang) : '—'}</dd>

                <dt>Source</dt>
                <dd>{sourceCalendarLabel(lang, data.source_calendar)}</dd>

                <dt>{t(lang, 'Appelant', 'Caller')}</dt>
                <dd>{data.caller_name ?? '—'}</dd>

                <dt>{t(lang, 'Téléphone', 'Phone')}</dt>
                <dd data-testid="phone-display">
                  {data.caller_phone_placeholder
                    ? t(lang, 'non fourni', 'not provided')
                    : (data.caller_phone ?? '—')}
                </dd>

                <dt>{t(lang, 'Courriel', 'Email')}</dt>
                <dd data-testid="email-display">
                  {data.caller_email_placeholder
                    ? t(lang, 'non fourni', 'not provided')
                    : (data.caller_email ?? '—')}
                </dd>

                <dt>{t(lang, 'Unité', 'Unit')}</dt>
                <dd>{data.unit_label ?? '—'}</dd>

                <dt>{t(lang, 'Accès', 'Access')}</dt>
                <dd>{(data.raw_caller_body?.entry_permission ?? data.entry_permission) || '—'}</dd>

                <dt>{t(lang, 'Animaux', 'Animals')}</dt>
                <dd>{(data.raw_caller_body?.animals ?? data.animals) || '—'}</dd>
              </dl>

              {(data.raw_caller_body?.problems || data.problems) && (
                <section className={styles.followupSection} data-testid="problems-section">
                  <h3 className={styles.followupHeading}>{t(lang, 'Problème décrit', 'Reported problem')}</h3>
                  <p style={{ whiteSpace: 'pre-wrap', fontSize: 13, margin: 0 }}>{data.raw_caller_body?.problems ?? data.problems}</p>
                </section>
              )}

              {/* AI interpretation comparison — only when AI ran AND values differ from tenant's */}
              {data.triage_model_version && data.raw_caller_body && (() => {
                const accessDiffers = data.raw_caller_body.entry_permission !== data.entry_permission;
                const animalsDiffers = data.raw_caller_body.animals !== data.animals;
                const problemsDiffer = !!data.problems && data.raw_caller_body?.problems !== data.problems;
                if (!accessDiffers && !animalsDiffers && !problemsDiffer) return null;
                return (
                  <section className={styles.followupSection} data-testid="dual-display">
                    <h3 className={styles.followupHeading}>
                      {t(lang, 'Interprétation IA', 'AI interpretation')}
                    </h3>
                    <dl className={styles.dl}>
                      {problemsDiffer && (
                        <>
                          <dt style={{ fontSize: 11 }}>{t(lang, 'Problème — déclaré par le locataire', 'Problem — tenant declared')}</dt>
                          <dd style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{data.raw_caller_body?.problems ?? '—'}</dd>
                          <dt style={{ fontSize: 11, color: 'var(--color-accent)' }}>{t(lang, 'Problème — interprétation IA', 'Problem — AI interpretation')}</dt>
                          <dd style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{data.problems ?? '—'}</dd>
                        </>
                      )}
                      {accessDiffers && (
                        <>
                          <dt style={{ fontSize: 11 }}>{t(lang, 'Accès — déclaré par le locataire', 'Access — tenant declared')}</dt>
                          <dd style={{ fontSize: 12 }}>{data.raw_caller_body.entry_permission ?? '—'}</dd>
                          <dt style={{ fontSize: 11, color: 'var(--color-accent)' }}>{t(lang, 'Accès — interprétation IA', 'Access — AI interpretation')}</dt>
                          <dd style={{ fontSize: 12 }}>{data.entry_permission ?? '—'}</dd>
                        </>
                      )}
                      {animalsDiffers && (
                        <>
                          <dt style={{ fontSize: 11 }}>{t(lang, 'Animaux — déclaré par le locataire', 'Animals — tenant declared')}</dt>
                          <dd style={{ fontSize: 12 }}>{data.raw_caller_body.animals ?? '—'}</dd>
                          <dt style={{ fontSize: 11, color: 'var(--color-accent)' }}>{t(lang, 'Animaux — interprétation IA', 'Animals — AI interpretation')}</dt>
                          <dd style={{ fontSize: 12 }}>{data.animals ?? '—'}</dd>
                        </>
                      )}
                    </dl>
                  </section>
                );
              })()}

              {/* AI section — triage summary and notes, coord/dir only */}
              {isEditor && data.triage_model_version && (
                <section className={styles.followupSection} data-testid="ai-section">
                  <h3 className={styles.followupHeading}>{t(lang, 'Résumé IA', 'AI summary')}</h3>
                  {data.problem_summary && (
                    <p style={{ whiteSpace: 'pre-wrap', fontSize: 13, margin: '0 0 8px' }}>{data.problem_summary}</p>
                  )}
                  {data.other_notes && (
                    <>
                      <h4 style={{ fontSize: 12, fontWeight: 600, margin: '8px 0 2px' }}>{t(lang, 'Notes IA', 'AI notes')}</h4>
                      <p style={{ whiteSpace: 'pre-wrap', fontSize: 12, margin: 0 }}>{data.other_notes}</p>
                    </>
                  )}
                  <TriageFeedbackWidget requestId={requestId} lang={lang} />
                </section>
              )}

              {/* Weather summary — read-only; the evaluation runs at triage (or via the
                  weather-check endpoint) and the escalation is applied automatically. */}
              {isEditor && weatherEnabled && data.weather_evaluation?.status === 'ok' && (() => {
                const ev = data.weather_evaluation;
                const bandFr = ev.band_name ? (BAND_FR[ev.band_name] ?? ev.band_name) : '';
                const locFr = ev.location ? (LOC_FR[ev.location] ?? ev.location) : '';
                return (
                  <section className={styles.editSection} data-testid="weather-section">
                    <h3 className={styles.editSectionHeading}>{t(lang, 'Météo', 'Weather')}</h3>
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
                <section className={styles.editSection} data-testid="triage-section">
                  <h3 className={styles.editSectionHeading}>{t(lang, 'Triage automatique', 'Auto triage')}</h3>
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
                            await triggerTriage(requestId);
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

              {/* Routing buttons — available for all triaged calls (including re-route) */}
              {isEditor && data.status === 'triaged' && (
                <section className={styles.editSection} data-testid="routing-section">
                  <h3 className={styles.editSectionHeading}>{t(lang, 'Acheminer vers', 'Route to')}</h3>
                  <div className={styles.urgencyPills}>
                    <button
                      className={styles.applyBtn}
                      data-testid="route-majordome"
                      onClick={() => applyAndRefresh(() =>
                        routeRequest(requestId, { source_calendar: 'st_maj', expected_source_calendar: data.source_calendar })
                      )}
                    >
                      {t(lang, 'Envoyer à Majordome', 'Send to Butler')}
                    </button>
                    <button
                      className={styles.applyBtn}
                      data-testid="route-principal"
                      onClick={() => applyAndRefresh(() =>
                        routeRequest(requestId, { source_calendar: 'main', expected_source_calendar: data.source_calendar })
                      )}
                    >
                      {t(lang, 'Garder sur Principal', 'Keep on Main')}
                    </button>
                  </div>
                </section>
              )}

              <VisitsSection requestId={data.request_id} visits={data.visits ?? []} lang={lang} />

              <FollowupLogSection entries={data.followup_log} lang={lang} />

              {isEditor && (
                <section className={styles.editSection} data-testid="edit-controls">
                  <h3 className={styles.editSectionHeading}>
                    {t(lang, 'Actions répartiteur', 'Dispatch actions')}
                  </h3>

                  {isClosed && (
                    <p className={styles.closedNotice}>
                      {t(lang, 'Demande fermée — seul le journal est modifiable.', 'Closed — only log entries are allowed.')}
                    </p>
                  )}

                  {/* Assign — locked while the technician is en route */}
                  <div className={styles.editField}>
                    <label className={styles.editLabel}>{t(lang, 'Assigné à', 'Assigned to')}</label>
                    <select
                      className={styles.editInput}
                      value={String(assignEmpId ?? '')}
                      disabled={isClosed || isEnRoute}
                      data-testid="assign-select"
                      onChange={(e) => {
                        const empId = e.target.value === '' ? null : Number(e.target.value);
                        setAssignEmpId(empId);
                        doAssign(empId);
                      }}
                    >
                      <option value="">— {t(lang, 'Non assigné', 'Unassigned')} —</option>
                      {isIneligibleAssignee && currentAssigneeInAll && (
                        <option value={String(data.assigned_employee_id)} disabled>
                          {currentAssigneeInAll.nom_employe} ({roleLabel(lang, currentAssigneeInAll.role)})
                        </option>
                      )}
                      {assignableEmployees.map((e) => (
                        <option key={e.employee_id} value={e.employee_id}>
                          {e.nom_employe} ({roleLabel(lang, e.role)})
                        </option>
                      ))}
                    </select>
                    {isEnRoute && (
                      <p className={styles.closedNotice} data-testid="en-route-notice">
                        {EN_ROUTE_MSG}
                      </p>
                    )}
                  </div>

                  {/* Reschedule */}
                  <div className={styles.editField}>
                    <label className={styles.editLabel}>{t(lang, 'Date de répartition', 'Schedule date')}</label>
                    <input
                      type="date"
                      className={styles.editInput}
                      value={rescheduleDate ?? data.start_date ?? ''}
                      disabled={isClosed}
                      onChange={(e) => setRescheduleDate(e.target.value)}
                    />
                    <button
                      className={styles.applyBtn}
                      disabled={isClosed}
                      onClick={() => {
                        const d = rescheduleDate ?? data.start_date;
                        if (d) doReschedule(d);
                      }}
                    >
                      {t(lang, 'Appliquer', 'Apply')}
                    </button>
                  </div>

                  {/* Urgency */}
                  <div className={styles.editField}>
                    <span className={styles.editLabel}>{t(lang, 'Urgence', 'Urgency')}</span>
                    <div className={styles.urgencyPills}>
                      {URGENCY_OPTIONS.map(({ value }) => (
                        <button
                          key={String(value)}
                          className={`${styles.pill} ${data.urgency_tier === value ? styles.pillActive : ''}`}
                          disabled={isClosed}
                          onClick={() => doSetUrgency(value)}
                        >
                          {value ?? t(lang, 'Aucune', 'None')}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Next follow-up date */}
                  <div className={styles.editField}>
                    <label className={styles.editLabel}>{t(lang, 'Prochain suivi', 'Next follow-up')}</label>
                    <input
                      type="date"
                      className={styles.editInput}
                      value={followUpDate ?? data.next_follow_up_date ?? ''}
                      disabled={isClosed}
                      onChange={(e) => setFollowUpDate(e.target.value)}
                    />
                    <button
                      className={styles.applyBtn}
                      disabled={isClosed}
                      onClick={() => applyAndRefresh(() => dispatchSetFollowUpDate(requestId, {
                        next_follow_up_date: followUpDate ?? data.next_follow_up_date,
                        current_next_follow_up_date: data.next_follow_up_date,
                      }))}
                    >
                      {t(lang, 'Appliquer', 'Apply')}
                    </button>
                  </div>

                  {/* Next steps */}
                  <div className={styles.editField}>
                    <label className={styles.editLabel}>{t(lang, 'Prochaines étapes', 'Next steps')}</label>
                    <textarea
                      className={styles.editTextarea}
                      value={nextSteps ?? data.next_steps ?? ''}
                      disabled={isClosed}
                      onChange={(e) => setNextSteps(e.target.value)}
                      rows={2}
                    />
                    <button
                      className={styles.applyBtn}
                      disabled={isClosed}
                      onClick={() => applyAndRefresh(() => dispatchSetNextSteps(requestId, {
                        next_steps: nextSteps ?? data.next_steps,
                        current_next_steps: data.next_steps,
                      }))}
                    >
                      {t(lang, 'Appliquer', 'Apply')}
                    </button>
                  </div>

                  {/* Cost */}
                  <div className={styles.editField}>
                    <label className={styles.editLabel}>{t(lang, 'Coût estimé ($)', 'Est. cost ($)')}</label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      className={styles.editInput}
                      value={cost ?? (data.estimated_cost != null ? String(data.estimated_cost) : '')}
                      disabled={isClosed}
                      onChange={(e) => setCost(e.target.value)}
                    />
                    <button
                      className={styles.applyBtn}
                      disabled={isClosed}
                      onClick={() => applyAndRefresh(() => dispatchSetCost(requestId, {
                        estimated_cost: cost !== null && cost !== '' ? Number(cost) : null,
                        current_estimated_cost: data.estimated_cost,
                      }))}
                    >
                      {t(lang, 'Appliquer', 'Apply')}
                    </button>
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
                </section>
              )}

              <DecisionHistorySection entries={data.justification_log} lang={lang} />
            </>
          )}
        </div>
      </aside>
    </>
  );
}
