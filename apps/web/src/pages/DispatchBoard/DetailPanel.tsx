import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRequest } from '../../hooks/useRequest';
import {
  ApiError, apiErrorMessage, fetchEmployees, fetchTechnicianSuggestions,
  dispatchSave,
  triggerTriage,
} from '../../api/client';
import TriageFeedbackWidget, { type FeedbackHandle, type FeedbackState } from '../../components/TriageFeedbackWidget';
import { parseAiNotes } from '../../lib/aiNotes';
import AiNotesSections from '../../components/AiNotesSections';
import StepsList from '../../components/StepsList';
import { useJustify, type JustifyRequest } from '../../components/Justification';
import type { DispatchFields, Justification } from '../../api/client';
import {
  IntakePhotos,
} from '../../components/RequestSections';
import HistoryTimeline from '../../components/HistoryTimeline';
import type { MeResponse } from '../../api/schema.d.ts';
import { statusLabel, timeEstimateLabel, sourceCalendarLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import { googleMapsUrl } from '../../lib/maps';
import { urgencyLabel } from '../../lib/urgencyLevels';
import styles from './DetailPanel.module.css';
import TaskEditor, { type TaskEditorHandle } from './TaskEditor';


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


const BAND_FR: Record<string, string> = {
  critical: 'critique', emergency: 'urgence', priority: 'priorité', normal: 'normal',
};
const LOC_FR: Record<string, string> = { quebec: 'Québec', levis: 'Lévis' };
// Calls where per-task technician suggestions help pick assignees.
const SUGGEST_STATUSES = new Set(['triaged', 'triage_proposal', 'open', 'awaiting_redispatch']);

type DetailTab = 'call' | 'tenant' | 'tasks' | 'history';

export default function DetailPanel({ requestId, onClose, onSelectPeer, lang = 'fr', me }: Props) {
  const [tab, setTab] = useState<DetailTab>('call');
  const [polling, setPolling] = useState(false);
  const [triageTimeout, setTriageTimeout] = useState(false);
  const pollingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { data, isPending, isError, error } = useRequest(requestId, { refetchInterval: polling ? 2000 : false });
  const qc = useQueryClient();
  const isEditor = !!(me?.roles.includes('coordinator') || me?.roles.includes('director'));
  const isClosed = data?.status === 'closed';

  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: fetchEmployees,
    staleTime: 5 * 60 * 1000,
    enabled: isEditor,
  });

  const { data: techSuggestions } = useQuery({
    queryKey: ['technician-suggestions', requestId, lang],
    queryFn: () => fetchTechnicianSuggestions(requestId, lang === 'en' ? 'en' : 'fr'),
    enabled: isEditor && SUGGEST_STATUSES.has(data?.status ?? ''),
    staleTime: 60 * 1000,
  });

  const [staleMsg, setStaleMsg] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [taskDirty, setTaskDirty] = useState(0);
  const taskEditorRef = useRef<TaskEditorHandle>(null);
  // AI-summary feedback is saved by the footer's single « Enregistrer ».
  const feedbackRef = useRef<FeedbackHandle>(null);
  const [fb, setFb] = useState<FeedbackState>({ dirty: false, valid: true, dispatch: false });
  /** Set when « Utile » is picked: save (and dispatch) as soon as the rating registers. */
  const autoSaveRef = useRef(false);
  const okTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onTaskDirty = useCallback((n: number) => {
    setTaskDirty((prev) => (prev === n ? prev : n));
  }, []);

  function flashOk(message: string) {
    setStaleMsg(null);
    setOkMsg(message);
    if (okTimerRef.current) clearTimeout(okTimerRef.current);
    okTimerRef.current = setTimeout(() => setOkMsg(null), 3000);
  }

  function flashErr(message: string) {
    setOkMsg(null);
    setStaleMsg(message);
  }

  useEffect(() => () => {
    if (okTimerRef.current) clearTimeout(okTimerRef.current);
  }, []);

  // Fresh card → start on Call Info.
  useEffect(() => { setTab('call'); }, [requestId]);
  // Tasks tab is editor-only — fall back if role changes while open.
  useEffect(() => {
    if (tab === 'tasks' && !isEditor) setTab('call');
  }, [tab, isEditor]);

  const [nextSteps, setNextSteps] = useState<string | null>(null);
  const [cost, setCost] = useState<string | null>(null);
  const weatherEnabled = !!me?.weather_escalation_enabled;

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
    setOkMsg(null);
    try {
      const updated = await fn();
      if (updated && typeof updated === 'object' && updated !== null && 'request_id' in updated) {
        qc.setQueryData(['request', requestId], updated);
      } else {
        await qc.invalidateQueries({ queryKey: ['request', requestId] });
      }
      qc.invalidateQueries({ queryKey: ['requests'] });
      qc.invalidateQueries({ queryKey: ['tasks'] });
      setNextSteps(null);
      setCost(null);
      flashOk(t(lang, 'Enregistré.', 'Saved.'));
    } catch (err) {
      if (err instanceof ApiError && err.code === 'STALE_DATA') {
        flashErr(t(lang, 'La demande a été modifiée — rechargement…', 'Modified by another user — reloading…'));
        qc.invalidateQueries({ queryKey: ['requests'] });
        qc.invalidateQueries({ queryKey: ['request', requestId] });
        setTimeout(() => setStaleMsg(null), 3000);
      } else if (err instanceof ApiError) {
        flashErr(apiErrorMessage(lang, err));
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
  const employeeName = (id: number) =>
    (employees ?? []).find((e) => e.employee_id === id)?.nom_employe ?? `#${id}`;
  const clip = (v: string | null | undefined) => (v && v.length > 60 ? `${v.slice(0, 57)}…` : v || NONE);

  // ── Staged edits: tasks + call notes share one « Enregistrer » ──
  const fmtCost = (v: number | null) => (v != null ? formatCost(v, lang) : NONE);
  const costDraft: number | null | undefined =
    cost === null ? undefined : cost.trim() === '' ? null : Number(cost);
  type NotePending = { key: keyof DispatchFields; label: string; before: string; after: string; value: unknown };
  const notePending: NotePending[] = [];
  if (data) {
    if (nextSteps !== null && (nextSteps.trim() || null) !== (data.next_steps ?? null)) {
      notePending.push({ key: 'next_steps', label: t(lang, 'Prochaines étapes', 'Next steps'),
        before: clip(data.next_steps), after: clip(nextSteps.trim()), value: nextSteps.trim() || null });
    }
    const savedCost = data.estimated_cost != null ? Number(data.estimated_cost) : null;
    if (costDraft !== undefined && !Number.isNaN(costDraft) && costDraft !== savedCost) {
      notePending.push({ key: 'estimated_cost', label: t(lang, 'Coût estimé', 'Estimated cost'),
        before: fmtCost(savedCost), after: fmtCost(costDraft), value: costDraft });
    }
  }
  const changedKeys = new Set(notePending.map((p) => p.key));
  const pendingCount = notePending.length + taskDirty + (fb.dirty ? 1 : 0);
  // A changed rating needs its 10-char reason before anything can be saved.
  const fbBlocked = fb.dirty && !fb.valid;

  // « Utile » = everything is fine: save all pending edits and dispatch now.
  useEffect(() => {
    if (!autoSaveRef.current || !fb.dirty) return;
    autoSaveRef.current = false;
    if (fb.valid) doSave();
    // doSave reads this render's state; only a new rating should trigger it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fb]);

  function discardEdits() {
    setNextSteps(null);
    setCost(null);
    taskEditorRef.current?.discardDrafts();
    setTaskDirty(0);
    feedbackRef.current?.reset();
  }

  function doSave() {
    if (!data || pendingCount === 0 || fbBlocked) return;
    const taskRows = taskEditorRef.current?.pendingRows() ?? [];
    const allChanges = [
      ...taskRows,
      ...notePending.map(({ label, before, after }) => ({ label, before, after })),
    ];
    const saveFeedback = async () => {
      if (fb.dirty) await feedbackRef.current?.save();
    };
    // Only the feedback changed: not a dispatcher decision, no justification.
    if (allChanges.length === 0) {
      void applyAndRefresh(async () => { await saveFeedback(); return null; });
      return;
    }
    const n = allChanges.length;
    decide(
      {
        decision: n === 1 ? allChanges[0].label : t(lang, `${n} modifications`, `${n} changes`),
        ...(n === 1 ? { before: allChanges[0].before, after: allChanges[0].after } : {}),
        changes: allChanges,
      },
      async (justification) => {
        if (taskRows.length) await taskEditorRef.current?.commitDrafts(justification);
        let updated = null;
        if (notePending.length) {
          const changes = Object.fromEntries(notePending.map((p) => [p.key, p.value])) as Partial<DispatchFields>;
          updated = await dispatchSave(requestId, {
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
          });
        }
        await saveFeedback();
        return updated;
      },
    );
  }

  // Closing with unsaved edits asks first.
  function requestClose() {
    if (pendingCount > 0 && !window.confirm(t(lang,
      'Des modifications ne sont pas enregistrées. Fermer quand même ?',
      'You have unsaved changes. Close anyway?'))) return;
    onClose();
  }
  const requestCloseRef = useRef(requestClose);
  requestCloseRef.current = requestClose;

  // Who works the call now: assignees of its accepted tasks (the call-level field is legacy).
  const taskAssignees = [...new Set((data?.tasks ?? [])
    .filter((x) => x.accepted_at != null && x.assigned_employee_id != null)
    .map((x) => x.assigned_employee_id!))];

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
                      <span className={data.urgency_tier === 'URGENT' ? styles.urgentBadge : styles.softBadge}>
                        {urgencyLabel(lang, data.urgency_tier)}
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

          {data && (
            <div className={styles.tabList} role="tablist" aria-label={t(lang, 'Sections de l\'appel', 'Call sections')} data-testid="detail-tabs">
              {([
                { id: 'call' as const, fr: 'Info appel', en: 'Call info' },
                { id: 'tenant' as const, fr: 'Locataire & unité', en: 'Tenant & unit' },
                ...(isEditor ? [{ id: 'tasks' as const, fr: 'Tâches', en: 'Tasks' }] : []),
                { id: 'history' as const, fr: 'Histororique', en: 'History' },
              ]).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  id={`detail-tab-${item.id}`}
                  aria-selected={tab === item.id}
                  aria-controls={`detail-panel-${item.id}`}
                  tabIndex={tab === item.id ? 0 : -1}
                  className={`${styles.tab} ${tab === item.id ? styles.tabActive : ''}`}
                  data-testid={`detail-tab-${item.id}`}
                  onClick={() => setTab(item.id)}
                >
                  {t(lang, item.fr, item.en)}
                </button>
              ))}
            </div>
          )}

          <div className={styles.body}>
            {isPending && <p className={styles.loading}>{t(lang, 'Chargement…', 'Loading…')}</p>}
            {isError && <p className={styles.error}>{errorText()}</p>}
            {staleMsg && <p className={styles.staleMsg} data-testid="panel-error">{staleMsg}</p>}
            {okMsg && <p className={styles.okMsg} role="status" data-testid="panel-success">{okMsg}</p>}

            {data && (
              <>
                {/* Panels stay mounted (hidden) so TaskEditor / save bar keep state. */}
                <div
                  className={styles.tabPanel}
                  role="tabpanel"
                  id="detail-panel-call"
                  aria-labelledby="detail-tab-call"
                  hidden={tab !== 'call'}
                  data-testid="tab-panel-call"
                >
                  {(data.raw_caller_body?.problems || data.problems) && (
                    <section className={styles.card} data-testid="problems-section">
                      <h3 className={styles.cardTitle}>{t(lang, 'Problème décrit', 'Reported problem')}</h3>
                      <p className={styles.prose}>{data.raw_caller_body?.problems ?? data.problems}</p>
                      <IntakePhotos requestId={data.request_id} ids={data.intake_photo_ids ?? []} lang={lang} />
                    </section>
                  )}

                  {data.triage_model_version && data.raw_caller_body && (() => {
                    const accessDiffers = data.raw_caller_body.entry_permission !== data.entry_permission;
                    const problemsDiffer = !!data.problems && data.raw_caller_body?.problems !== data.problems;
                    if (!accessDiffers && !problemsDiffer) return null;
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
                      </section>
                    );
                  })()}

                  {isEditor && data.triage_model_version && (() => {
                    const ai = parseAiNotes(data.other_notes, data.problem_summary, data.ai_important_notes, data.ai_next_steps);
                    return ai.important.length + ai.next.length > 0 || !!data.ai_reasoning?.trim();
                  })() && (
                    <section className={styles.card} data-testid="ai-section">
                      <h3 className={styles.cardTitle}>{t(lang, 'Résumé IA', 'AI summary')}</h3>
                      <AiNotesSections
                        embedded
                        hideSummary
                        lang={lang}
                        problemSummary={data.problem_summary}
                        otherNotes={data.other_notes}
                        aiImportantNotes={data.ai_important_notes}
                        aiNextSteps={data.ai_next_steps}
                      />
                      {data.ai_reasoning?.trim() && (
                        <div className={styles.reasoning} data-testid="ai-reasoning">
                          <h4 className={styles.subTitle}>{t(lang, 'Raisonnement IA', 'AI reasoning')}</h4>
                          <p className={styles.prose}>{data.ai_reasoning.trim()}</p>
                        </div>
                      )}
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

                  <section className={styles.card}>
                    <h3 className={styles.cardTitle}>{t(lang, 'Planification', 'Planning')}</h3>
                    <dl className={styles.facts}>
                      <dt>{t(lang, 'Employé', 'Employee')}</dt>
                      <dd>
                        {taskAssignees.length
                          ? taskAssignees.map(employeeName).join(', ')
                          : (data.assigned_employee_name ?? '—')}
                      </dd>
                      <dt>{t(lang, 'Sous-traitant', 'Subcontractor')}</dt>
                      <dd>{(() => {
                        const fromTasks = [...new Set(
                          (data.tasks ?? [])
                            .map((x) => x.subcontractor_name)
                            .filter((x): x is string => !!x),
                        )];
                        if (fromTasks.length) return fromTasks.join(', ');
                        return data.subcontractor_name ?? '—';
                      })()}
                      </dd>
                      <dt>{t(lang, 'Urgence', 'Urgency')}</dt>
                      <dd>{(() => {
                        const fromTasks = [...new Set(
                          (data.tasks ?? [])
                            .map((x) => x.urgency_tier)
                            .filter((x): x is string => !!x),
                        )];
                        if (fromTasks.length) {
                          return fromTasks.map((u) => urgencyLabel(lang, u)).join(', ');
                        }
                        return urgencyLabel(lang, data.urgency_tier);
                      })()}
                      </dd>
                      <dt>{t(lang, 'Estimation', 'Est. time')}</dt>
                      <dd>{timeEstimateLabel(lang, data.time_estimate_bucket)}</dd>
                      {!isEditor && (
                        <>
                          <dt>{t(lang, 'Coût estimé', 'Est. cost')}</dt>
                          <dd>{data.estimated_cost != null ? formatCost(data.estimated_cost, lang) : '—'}</dd>
                        </>
                      )}
                    </dl>
                  </section>

                  {isEditor && (
                    <section className={`${styles.card} ${styles.notesCard}`} data-testid="edit-controls">
                      <h3 className={styles.cardTitle}>
                        {t(lang, 'Notes d\'appel', 'Call notes')}
                      </h3>

                      {isClosed && (
                        <p className={styles.closedNotice}>
                          {t(lang, 'Demande fermée — notes non modifiables.', 'Closed — notes are read-only.')}
                        </p>
                      )}

                      <div className={styles.actionsGrid}>
                        <div className={`${styles.editField} ${changedKeys.has('next_steps') ? styles.editFieldChanged : ''}`}>
                          <StepsList
                            lang={lang}
                            label={t(lang, 'Prochaines étapes', 'Next steps')}
                            value={nextSteps ?? data.next_steps ?? ''}
                            onChange={setNextSteps}
                            disabled={isClosed}
                            inputTestId="next-steps-input"
                          />
                        </div>

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
                      </div>
                    </section>
                  )}

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
                                setStaleMsg(apiErrorMessage(lang, err));
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

                <div
                  className={styles.tabPanel}
                  role="tabpanel"
                  id="detail-panel-tenant"
                  aria-labelledby="detail-tab-tenant"
                  hidden={tab !== 'tenant'}
                  data-testid="tab-panel-tenant"
                >
                  <section className={styles.card}>
                    <h3 className={styles.cardTitle}>{t(lang, 'Lieu et appelant', 'Location & caller')}</h3>
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
                    <dl className={`${styles.facts} ${styles.factsSplit}`} aria-label={t(lang, 'Appelant', 'Caller')}>
                      <dt>{t(lang, 'Appelant', 'Caller')}</dt>
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
                </div>

                {isEditor && (
                  <div
                    className={styles.tabPanel}
                    role="tabpanel"
                    id="detail-panel-tasks"
                    aria-labelledby="detail-tab-tasks"
                    hidden={tab !== 'tasks'}
                    data-testid="tab-panel-tasks"
                  >
                    <section className={`${styles.card} ${styles.actionsCard}`}>
                      <h3 className={styles.cardTitle}>{t(lang, 'Tâches', 'Tasks')}</h3>
                      <TaskEditor
                        ref={taskEditorRef}
                        lang={lang}
                        requestId={requestId}
                        callStatus={data.status}
                        tasks={data.tasks ?? []}
                        employees={employees ?? []}
                        suggestions={techSuggestions?.suggestions ?? []}
                        onError={flashErr}
                        onSuccess={flashOk}
                        onDirtyChange={onTaskDirty}
                      />
                    </section>
                  </div>
                )}

                <div
                  className={styles.tabPanel}
                  role="tabpanel"
                  id="detail-panel-history"
                  aria-labelledby="detail-tab-history"
                  hidden={tab !== 'history'}
                  data-testid="tab-panel-history"
                >
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
              </>
            )}
          </div>

          {data && isEditor && !isClosed && (
            <footer className={`${styles.saveBar} ${pendingCount ? styles.saveBarDirty : ''}`} data-testid="save-bar">
              {/* AI feedback lives beside « Enregistrer »: « Utile » saves and
                  dispatches at once; the other two ask for a comment first. */}
              <div className={styles.saveBarFeedback}>
                <TriageFeedbackWidget
                  ref={feedbackRef}
                  variant="bar"
                  standalone={false}
                  onStateChange={setFb}
                  onPick={(level, willSave) => { autoSaveRef.current = level === 'utile' && willSave; }}
                  requestId={requestId}
                  lang={lang}
                  hasProposals={(data.tasks ?? []).some((x) => x.accepted_at == null)}
                  onDispatchProposals={async () => {
                    await taskEditorRef.current?.acceptProposals();
                  }}
                />
              </div>
              <span className={styles.saveStatus} aria-live="polite">
                {fbBlocked
                  ? t(lang, 'Retour IA : ajoutez un commentaire (10 car. min.)', 'AI feedback: add a comment (10 chars min.)')
                  : pendingCount === 0
                    ? t(lang, 'Aucune modification', 'No changes')
                    : t(lang,
                      `${pendingCount} modification${pendingCount > 1 ? 's' : ''} non enregistrée${pendingCount > 1 ? 's' : ''}`,
                      `${pendingCount} unsaved change${pendingCount > 1 ? 's' : ''}`)}
              </span>
              {pendingCount > 0 && (
                <button type="button" className={styles.discardBtn} onClick={discardEdits}>
                  {t(lang, 'Annuler les modifications', 'Discard changes')}
                </button>
              )}
              <button
                type="button"
                className={styles.saveBtn}
                disabled={pendingCount === 0 || fbBlocked}
                onClick={doSave}
                data-testid="save-btn"
              >
                {fb.dirty && fb.dispatch
                  ? t(lang, 'Enregistrer et dispatcher', 'Save and dispatch')
                  : t(lang, 'Enregistrer', 'Save')}
              </button>
            </footer>
          )}
        </section>
      </div>
    </>
  );
}
