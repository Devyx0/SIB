import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRequest } from '../../hooks/useRequest';
import {
  ApiError, apiErrorMessage, assignTask, fetchEmployees, fetchTechnicianSuggestions, updateTask,
  dispatchSave, dispatchAddLog,
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
import CallNotes from '../../components/CallNotes';
import type { MeResponse, RequestDetail } from '../../api/schema.d.ts';
import { statusLabel, timeEstimateLabel, sourceCalendarLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import { googleMapsUrl } from '../../lib/maps';
import { urgencyLabel, urgencyOptions } from '../../lib/urgencyLevels';
import Select from '../../components/Select';
import styles from './DetailPanel.module.css';
import TaskEditor, { type TaskEditorHandle } from './TaskEditor';
import { Avatar, PersonName } from '../../components/Avatar';
import { cleanCallTitle } from '../../lib/callTitle';
import { MailIcon, MapPinIcon, PencilIcon, PhoneIcon } from '../Portfolio/icons';
import { formatPhone, telHref } from '../../lib/phone';
import { unitNumberOf } from '../../lib/unitNumber';


// Call details the dispatcher can correct here (sent with the one « Enregistrer »).
const DETAIL_KEYS = ['raw_title', 'problem_summary', 'entry_permission', 'animals',
  'caller_name', 'caller_phone', 'caller_email', 'subcontractor_name', 'time_estimate_bucket'] as const;
type DetailKey = (typeof DETAIL_KEYS)[number];
const DETAIL_LABEL: Record<DetailKey, [string, string]> = {
  raw_title: ['Titre', 'Title'],
  problem_summary: ['Problème', 'Issue'],
  entry_permission: ['Accès', 'Access'],
  animals: ['Animaux', 'Animals'],
  caller_name: ['Appelant', 'Caller'],
  caller_phone: ['Téléphone', 'Phone'],
  caller_email: ['Courriel', 'Email'],
  subcontractor_name: ['Sous-traitant', 'Subcontractor'],
  time_estimate_bucket: ['Estimation', 'Est. time'],
};
const L2 = (lang: Lang, p: [string, string]) => (lang === 'fr' ? p[0] : p[1]);

const TIME_BUCKETS = ['UNDER_30_MIN', 'MIN30_TO_1H', 'H1_TO_2H', 'H2_TO_4H', 'HALF_DAY_PLUS', 'TBD_ON_SITE'] as const;
// Accepted tasks the dispatcher can still change (backend _EDITABLE).
const PLAN_EDITABLE = new Set(['queued', 'scheduled']);
/** One value when every task agrees; 'mixed' when they differ; undefined with no task. */
function shared<T>(vals: T[]): T | 'mixed' | undefined {
  if (vals.length === 0) return undefined;
  return vals.every((v) => v === vals[0]) ? vals[0] : 'mixed';
}

/** What the field holds now, as the dispatcher sees it (placeholders read as empty). */
function detailValue(d: RequestDetail, k: DetailKey): string | null {
  if (k === 'caller_phone' && d.caller_phone_placeholder) return null;
  if (k === 'caller_email' && d.caller_email_placeholder) return null;
  if (k === 'problem_summary') return (d.problem_summary ?? d.problems)?.trim() || null;
  if (k === 'entry_permission') return (d.entry_permission ?? d.raw_caller_body?.entry_permission)?.trim() || null;
  if (k === 'animals') return (d.raw_caller_body?.animals ?? d.animals)?.trim() || null;
  const v = d[k as keyof RequestDetail];
  return typeof v === 'string' ? v.trim() || null : null;
}

/** The stored column value — the server's stale check compares against this. */
function detailStored(d: RequestDetail, k: DetailKey): string | null {
  if (k === 'caller_phone' && d.caller_phone_placeholder) return null;
  if (k === 'caller_email' && d.caller_email_placeholder) return null;
  const v = d[k as keyof RequestDetail];
  return typeof v === 'string' ? v.trim() || null : null;
}

/** Pencil in a card's corner: switches the card to its edit form. */
function EditToggle({ on, label, onClick, testId }: { on: boolean; label: string; onClick: () => void; testId: string }) {
  return (
    <button type="button" className={`${styles.cardEditBtn} ${on ? styles.cardEditBtnOn : ''}`} onClick={onClick}
            aria-pressed={on} aria-label={label} title={label} data-testid={testId}>
      <PencilIcon size={15} />
    </button>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg className={`${styles.disclosureIcon} ${open ? styles.disclosureOpen : ''}`} viewBox="0 0 20 20" width="16" height="16"
         aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7.5 5l5 5-5 5" />
    </svg>
  );
}

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
  /** Opened from the task table: look, don't edit. */
  readOnly?: boolean;
}


// Calls where per-task technician suggestions help pick assignees.
const SUGGEST_STATUSES = new Set(['triaged', 'triage_proposal', 'open', 'awaiting_redispatch']);

export default function DetailPanel({ requestId, onClose, onSelectPeer, lang = 'fr', me, readOnly = false }: Props) {
  const [polling, setPolling] = useState(false);
  const [triageTimeout, setTriageTimeout] = useState(false);
  const pollingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { data, isPending, isError, error } = useRequest(requestId, { refetchInterval: polling ? 2000 : false });
  const qc = useQueryClient();
  const isEditor = !!(me?.roles.includes('coordinator') || me?.roles.includes('director'));
  // Editing happens from the triage page; the task table opens the call view-only.
  const editMode = isEditor && !readOnly;
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
  // Collapsed by default: the tenant's own words and the AI's reasoning.
  const [showOriginal, setShowOriginal] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);
  type DetailTab = 'call' | 'tenant' | 'tasks' | 'history' | 'notes';
  const [tab, setTab] = useState<DetailTab>('call');
  useEffect(() => { setShowOriginal(false); setShowReasoning(false); setTab('call'); }, [requestId]);
  useEffect(() => {
    if (tab === 'tasks' && !isEditor) setTab('call');
  }, [tab, isEditor]);
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
  const [nextSteps, setNextSteps] = useState<string | null>(null);
  const [cost, setCost] = useState<string | null>(null);
  const [followUp, setFollowUp] = useState<string | null>(null);
  // Call details being corrected (title, issue, access, caller), staged until « Enregistrer ».
  const [details, setDetails] = useState<Partial<Record<DetailKey, string>>>({});
  const [editCards, setEditCards] = useState<Set<string>>(new Set());
  // Planning card drafts: employee / urgency / subcontractor apply to the open tasks.
  const [plan, setPlan] = useState<{ emp?: string; urg?: string; sub?: string }>({});
  const toggleCard = (id: string) => setEditCards((prev) => {
    const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n;
  });
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
      setFollowUp(null);
      setDetails({});
      setEditCards(new Set());
      setPlan({});
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
    if (followUp !== null && (followUp || null) !== (data.next_follow_up_date ?? null)) {
      notePending.push({ key: 'next_follow_up_date', label: t(lang, 'Prochain suivi', 'Next follow-up'),
        before: data.next_follow_up_date ?? NONE, after: followUp || NONE, value: followUp || null });
    }
    for (const k of DETAIL_KEYS) {
      const draft = details[k];
      if (draft === undefined) continue;
      const before = detailValue(data, k);
      const after = draft.trim() || null;
      if (after !== before) {
        const show = (v: string | null) => (k === 'time_estimate_bucket' ? (v ? timeEstimateLabel(lang, v) : NONE) : clip(v));
        notePending.push({ key: k, label: L2(lang, DETAIL_LABEL[k]), before: show(before), after: show(after), value: after });
      }
    }
    const savedCost = data.estimated_cost != null ? Number(data.estimated_cost) : null;
    if (costDraft !== undefined && !Number.isNaN(costDraft) && costDraft !== savedCost) {
      notePending.push({ key: 'estimated_cost', label: t(lang, 'Coût estimé', 'Estimated cost'),
        before: fmtCost(savedCost), after: fmtCost(costDraft), value: costDraft });
    }
  }
  // Planning card: employee / urgency / subcontractor live on the call's open
  // tasks, so a change there applies to each of them (same justification).
  const openTasks = (data?.tasks ?? []).filter((x) => x.accepted_at != null && PLAN_EDITABLE.has(x.status));
  const curEmp = shared(openTasks.map((x) => x.assigned_employee_id ?? null));
  const curUrg = openTasks.length ? shared(openTasks.map((x) => x.urgency_tier ?? null)) : (data?.urgency_tier ?? null);
  const curSub = openTasks.length ? shared(openTasks.map((x) => x.subcontractor_name ?? null)) : (data?.subcontractor_name ?? null);
  type PlanOp = { label: string; before: string; after: string; apply: (j: Justification) => Promise<unknown> };
  const planOps: PlanOp[] = [];
  const MIXED = t(lang, 'Selon la tâche', 'Per task');
  if (data) {
    if (plan.emp !== undefined && openTasks.length) {
      const next = plan.emp === '' ? null : Number(plan.emp);
      if (curEmp === 'mixed' || next !== curEmp) {
        planOps.push({
          label: t(lang, 'Employé', 'Employee'),
          before: curEmp === 'mixed' ? MIXED : curEmp != null ? employeeName(curEmp) : NONE,
          after: next != null ? employeeName(next) : NONE,
          apply: async (j) => { for (const x of openTasks) if ((x.assigned_employee_id ?? null) !== next) await assignTask(x.task_id, { assigned_employee_id: next, justification: j }); },
        });
      }
    }
    if (plan.urg !== undefined) {
      const next = plan.urg || null;
      if (curUrg === 'mixed' || next !== curUrg) {
        const before = curUrg === 'mixed' ? MIXED : urgencyLabel(lang, curUrg ?? null);
        if (openTasks.length) {
          planOps.push({ label: t(lang, 'Urgence', 'Urgency'), before, after: urgencyLabel(lang, next),
            apply: async (j) => { for (const x of openTasks) if ((x.urgency_tier ?? null) !== next) await updateTask(x.task_id, { urgency_tier: next, justification: j }); } });
        } else {
          notePending.push({ key: 'urgency_tier', label: t(lang, 'Urgence', 'Urgency'), before, after: urgencyLabel(lang, next), value: next });
        }
      }
    }
    if (plan.sub !== undefined) {
      const next = plan.sub.trim() || null;
      if (curSub === 'mixed' || next !== curSub) {
        const before = curSub === 'mixed' ? MIXED : clip(curSub ?? null);
        if (openTasks.length) {
          planOps.push({ label: t(lang, 'Sous-traitant', 'Subcontractor'), before, after: clip(next),
            apply: async (j) => { for (const x of openTasks) if ((x.subcontractor_name ?? null) !== next) await updateTask(x.task_id, { subcontractor_name: next, justification: j }); } });
        } else {
          notePending.push({ key: 'subcontractor_name', label: t(lang, 'Sous-traitant', 'Subcontractor'), before, after: clip(next), value: next });
        }
      }
    }
  }
  const changedKeys = new Set(notePending.map((p) => p.key));
  const pendingCount = notePending.length + planOps.length + taskDirty + (fb.dirty ? 1 : 0);
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
    setFollowUp(null);
    setDetails({});
    setEditCards(new Set());
    setPlan({});
    taskEditorRef.current?.discardDrafts();
    setTaskDirty(0);
    feedbackRef.current?.reset();
  }

  function doSave() {
    if (!data || pendingCount === 0 || fbBlocked) return;
    const taskRows = taskEditorRef.current?.pendingRows() ?? [];
    const allChanges = [
      ...taskRows,
      ...planOps.map(({ label, before, after }) => ({ label, before, after })),
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
        for (const op of planOps) await op.apply(justification);
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
              ...Object.fromEntries(DETAIL_KEYS.map((k) => [k, detailStored(data, k)])),
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

  // Access: the AI-cleaned wording; the tenant's own words sit under « Demande originale ».
  const accessText = data ? ((data.entry_permission ?? data.raw_caller_body?.entry_permission) || '—') : '—';
  const animalsText = data ? ((data.raw_caller_body?.animals ?? data.animals) || '—') : '—';
  const buildingAddress = data ? (data.building_full_address ?? data.building_address) : null;

  const canEdit = editMode && !isClosed;
  const detailInput = (k: DetailKey, opts: { multiline?: boolean; type?: string; label?: string } = {}) => {
    if (!data) return null;
    const value = details[k] ?? detailValue(data, k) ?? '';
    const changed = details[k] !== undefined && (details[k]!.trim() || null) !== detailValue(data, k);
    const id = `${titleId}-${k}`;
    const onChange = (v: string) => setDetails((d) => ({ ...d, [k]: v }));
    return (
      <div className={`${styles.editField} ${changed ? styles.editFieldChanged : ''}`}>
        <label className={styles.editLabel} htmlFor={id}>{opts.label ?? L2(lang, DETAIL_LABEL[k])}</label>
        {opts.multiline ? (
          <textarea id={id} className={styles.editInput} rows={3} value={value} data-testid={`edit-${k}`}
                    onChange={(e) => onChange(e.target.value)} />
        ) : (
          <input id={id} className={styles.editInput} type={opts.type ?? 'text'} value={value} data-testid={`edit-${k}`}
                 onChange={(e) => onChange(e.target.value)} />
        )}
      </div>
    );
  };

  return (
    <>
      <div className={styles.backdrop} onClick={requestClose} aria-hidden />
      <div className={styles.frame}>
        <section
          className={`${styles.panel} ${data ? styles.panelTall : ''}`}
          data-testid="detail-panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby={data ? titleId : undefined}
          aria-label={data ? undefined : t(lang, 'Détails de la demande', 'Request details')}
        >
          <header className={styles.header}>
            <div className={styles.headMain}>
              <div className={styles.headMeta}>
                {data?.asnu && <span className={styles.requestId} data-testid="header-asnu">{data.asnu}</span>}
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
              {data && (
                <div className={styles.titleRow}>
                  {editCards.has('title') ? (
                    <div className={styles.titleEdit}>{detailInput('raw_title', { label: t(lang, "Titre de l'appel", 'Call title') })}</div>
                  ) : (
                    <h2 className={styles.title} id={titleId} title={data.raw_title ?? undefined}>
                      {cleanCallTitle(details.raw_title ?? data.raw_title, data.project_label) || '—'}
                    </h2>
                  )}
                  {canEdit && (
                    <EditToggle on={editCards.has('title')} onClick={() => toggleCard('title')} testId="edit-title-toggle"
                                label={t(lang, 'Modifier le titre', 'Edit title')} />
                  )}
                </div>
              )}
              {data && (
                <dl className={styles.headFacts}>
                  <div><dt>{t(lang, 'Date', 'Date')}</dt><dd>{data.start_date ?? '—'}</dd></div>
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
            <div className={styles.tabList} role="tablist" aria-label={t(lang, "Sections de l'appel", 'Call sections')} data-testid="detail-tabs">
              {([
                { id: 'call' as const, fr: 'Info appel', en: 'Call info' },
                { id: 'tenant' as const, fr: 'Locataire & unité', en: 'Tenant & unit' },
                ...(isEditor ? [{ id: 'tasks' as const, fr: 'Tâches', en: 'Tasks' }] : []),
                { id: 'history' as const, fr: 'Historique', en: 'History' },
                { id: 'notes' as const, fr: 'Notes', en: 'Notes' },
              ] as const).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  id={`detail-tab-${item.id}`}
                  aria-selected={tab === item.id}
                  aria-controls={item.id === 'notes' ? `${titleId}-panel-notes` : `detail-panel-${item.id}`}
                  tabIndex={tab === item.id ? 0 : -1}
                  className={`${styles.tab} ${tab === item.id ? styles.tabActive : ''}`}
                  data-testid={item.id === 'notes' ? 'tab-notes' : `detail-tab-${item.id}`}
                  onClick={() => setTab(item.id)}
                >
                  {t(lang, item.fr, item.en)}
                  {item.id === 'notes' ? (
                    <span className={styles.tabCount}>{data.followup_log.length}</span>
                  ) : null}
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
                  {/* The issue: the AI's summary up front; the tenant's own words
                      stay one click away under « Demande originale ». */}
                  {(() => {
                    const raw = data.raw_caller_body;
                    const rawProblem = raw?.problems?.trim() || null;
                    // Never repeat the title: skip a description that only says what the title says.
                    const norm = (v: string | null | undefined) => (v ?? '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
                    const titleNorm = norm(cleanCallTitle(data.raw_title, data.project_label));
                    const pick = (...c: (string | null | undefined)[]) => {
                      const list = c.map((v) => v?.trim() || null).filter((v): v is string => !!v);
                      return list.find((v) => norm(v) !== titleNorm) ?? null;
                    };
                    const aiSummary = data.triage_model_version ? pick(data.problem_summary, data.problems) : null;
                    const main = aiSummary ?? pick(rawProblem, data.problems, data.problem_summary);
                    const original = aiSummary ? [
                      rawProblem && { label: t(lang, 'Problème', 'Problem'), text: rawProblem },
                      raw?.entry_permission?.trim() && { label: t(lang, 'Accès', 'Access'), text: raw.entry_permission.trim() },
                      raw?.animals?.trim() && { label: t(lang, 'Animaux', 'Animals'), text: raw.animals.trim() },
                    ].filter((x): x is { label: string; text: string } => !!x) : [];
                    if (!main && !canEdit) return null;
                    return (
                      <section className={styles.card} data-testid="problems-section">
                        <div className={styles.cardHeadRow}>
                          <h3 className={styles.cardTitle}>{t(lang, 'Problème', 'Issue')}</h3>
                          <span className={styles.cardHeadTools}>
                            {aiSummary && <span className={styles.aiTag}>{t(lang, 'Résumé IA', 'AI summary')}</span>}
                            {canEdit && (
                              <EditToggle on={editCards.has('issue')} onClick={() => toggleCard('issue')} testId="edit-issue-toggle"
                                          label={t(lang, 'Modifier le problème', 'Edit issue')} />
                            )}
                          </span>
                        </div>
                        {editCards.has('issue')
                          ? detailInput('problem_summary', { multiline: true, label: t(lang, 'Description du problème', 'Issue description') })
                          : <p className={`${styles.prose} ${styles.issueText}`} data-testid="issue-summary">{details.problem_summary ?? main ?? '—'}</p>}
                        {original.length > 0 && (
                          <>
                            <button type="button" className={styles.disclosure} aria-expanded={showOriginal}
                                    aria-controls={`${titleId}-original`} data-testid="original-toggle"
                                    onClick={() => setShowOriginal((v) => !v)}>
                              <Chevron open={showOriginal} />
                              {showOriginal
                                ? t(lang, 'Masquer la demande originale', 'Hide original request')
                                : t(lang, 'Demande originale', 'Original request')}
                            </button>
                            {showOriginal && (
                              <div id={`${titleId}-original`} className={styles.original} data-testid="original-request">
                                <p className={styles.originalNote}>
                                  {t(lang, 'Texte saisi par le locataire, non modifié.', "The tenant's words, unedited.")}
                                </p>
                                <dl className={styles.facts}>
                                  {original.flatMap((o) => [
                                    <dt key={`${o.label}-t`}>{o.label}</dt>,
                                    <dd key={`${o.label}-d`}>{o.text}</dd>,
                                  ])}
                                </dl>
                              </div>
                            )}
                          </>
                        )}
                        <IntakePhotos requestId={data.request_id} ids={data.intake_photo_ids ?? []} lang={lang} />
                      </section>
                    );
                  })()}

                  {/* AI section — important notes, next steps, reasoning; coord/dir only.
                      The summary bullets are left out (the header already says it)
                      and the feedback moved to the footer beside « Enregistrer ». */}
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
                        <div className={styles.reasoning}>
                          <button type="button" className={styles.disclosure} aria-expanded={showReasoning}
                                  aria-controls={`${titleId}-reasoning`} data-testid="reasoning-toggle"
                                  onClick={() => setShowReasoning((v) => !v)}>
                            <Chevron open={showReasoning} />
                            {showReasoning
                              ? t(lang, 'Masquer le raisonnement IA', 'Hide AI reasoning')
                              : t(lang, 'Raisonnement IA', 'AI reasoning')}
                          </button>
                          {showReasoning && (
                            <p id={`${titleId}-reasoning`} className={`${styles.prose} ${styles.reasoningText}`}
                               data-testid="ai-reasoning">
                              {data.ai_reasoning.trim()}
                            </p>
                          )}
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
                            {data.duplicate_of_asnu ?? t(lang, "l'appel lié", 'the linked call')}
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
                            {data.addition_to_asnu ?? t(lang, "l'appel lié", 'the linked call')}
                          </button>
                        </p>
                      )}
                    </section>
                  )}

                  <section className={styles.card}>
                    <div className={styles.cardHeadRow}>
                      <h3 className={styles.cardTitle}>{t(lang, 'Planification', 'Planning')}</h3>
                      {canEdit && (
                        <EditToggle on={editCards.has('planning')} onClick={() => toggleCard('planning')} testId="edit-planning-toggle"
                                    label={t(lang, 'Modifier la planification', 'Edit planning')} />
                      )}
                    </div>
                    {canEdit && editCards.has('planning') ? (
                      <div className={styles.planForm} data-testid="planning-form">
                        <div className={`${styles.editField} ${planOps.some((o) => o.label === t(lang, 'Employé', 'Employee')) ? styles.editFieldChanged : ''}`}>
                          <label className={styles.editLabel} htmlFor={`${titleId}-plan-emp`}>{t(lang, 'Employé', 'Employee')}</label>
                          <Select
                            id={`${titleId}-plan-emp`}
                            className={styles.editInput}
                            value={plan.emp ?? (curEmp === 'mixed' ? 'mixed' : curEmp != null ? String(curEmp) : '')}
                            disabled={openTasks.length === 0}
                            onChange={(e) => setPlan((p) => ({ ...p, emp: e.target.value }))}
                            searchable avatars
                            searchPlaceholder={t(lang, 'Rechercher un employé…', 'Search employees…')}
                            noResultsText={t(lang, 'Aucun employé trouvé', 'No employee found')}
                            data-testid="plan-employee"
                          >
                            <option value="">— {t(lang, 'Non assigné', 'Unassigned')} —</option>
                            {curEmp === 'mixed' && <option value="mixed" disabled>{MIXED}</option>}
                            {(employees ?? []).filter((e) => e.role === 'technician' || e.role === 'contractor').map((e) => (
                              <option key={e.employee_id} value={e.employee_id}>{e.nom_employe}</option>
                            ))}
                          </Select>
                          {openTasks.length === 0 && (
                            <p className={styles.cardFormNote}>
                              {t(lang, 'Ajoutez une tâche ci-dessous pour assigner quelqu’un.', 'Add a task below to assign someone.')}
                            </p>
                          )}
                        </div>
                        <div className={`${styles.editField} ${planOps.some((o) => o.label === t(lang, 'Sous-traitant', 'Subcontractor')) || changedKeys.has('subcontractor_name') ? styles.editFieldChanged : ''}`}>
                          <label className={styles.editLabel} htmlFor={`${titleId}-plan-sub`}>{t(lang, 'Sous-traitant', 'Subcontractor')}</label>
                          <input id={`${titleId}-plan-sub`} className={styles.editInput} data-testid="plan-subcontractor"
                                 value={plan.sub ?? (curSub === 'mixed' ? '' : curSub ?? '')}
                                 placeholder={curSub === 'mixed' ? MIXED : t(lang, 'Aucun', 'None')}
                                 onChange={(e) => setPlan((p) => ({ ...p, sub: e.target.value }))} />
                        </div>
                        <div className={`${styles.editField} ${planOps.some((o) => o.label === t(lang, 'Urgence', 'Urgency')) || changedKeys.has('urgency_tier') ? styles.editFieldChanged : ''}`}>
                          <label className={styles.editLabel} htmlFor={`${titleId}-plan-urg`}>{t(lang, 'Urgence', 'Urgency')}</label>
                          <Select id={`${titleId}-plan-urg`} className={styles.editInput} data-testid="plan-urgency"
                                  value={plan.urg ?? (curUrg === 'mixed' ? 'mixed' : curUrg ?? '')}
                                  onChange={(e) => setPlan((p) => ({ ...p, urg: e.target.value }))}>
                            {curUrg === 'mixed' && <option value="mixed" disabled>{MIXED}</option>}
                            {urgencyOptions(lang).map((o) => <option key={o.value ?? 'none'} value={o.value ?? ''}>{o.label}</option>)}
                          </Select>
                        </div>
                        <div className={`${styles.editField} ${changedKeys.has('time_estimate_bucket') ? styles.editFieldChanged : ''}`}>
                          <label className={styles.editLabel} htmlFor={`${titleId}-plan-est`}>{t(lang, 'Estimation', 'Est. time')}</label>
                          <Select id={`${titleId}-plan-est`} className={styles.editInput} data-testid="plan-estimate"
                                  value={details.time_estimate_bucket ?? data.time_estimate_bucket ?? ''}
                                  onChange={(e) => setDetails((d) => ({ ...d, time_estimate_bucket: e.target.value }))}>
                            <option value="">—</option>
                            {TIME_BUCKETS.map((b) => <option key={b} value={b}>{timeEstimateLabel(lang, b)}</option>)}
                          </Select>
                        </div>
                        <div className={`${styles.editField} ${changedKeys.has('estimated_cost') ? styles.editFieldChanged : ''}`}>
                          <label className={styles.editLabel} htmlFor={`${titleId}-plan-cost`}>{t(lang, 'Coût estimé ($)', 'Est. cost ($)')}</label>
                          <input
                            id={`${titleId}-plan-cost`}
                            type="number"
                            min="0"
                            step="0.01"
                            className={styles.editInput}
                            value={cost ?? (data.estimated_cost != null ? String(data.estimated_cost) : '')}
                            onChange={(e) => setCost(e.target.value)}
                            data-testid="cost-input"
                          />
                        </div>
                      </div>
                    ) : (
                      <dl className={styles.facts}>
                      <dt>{t(lang, 'Employé', 'Employee')}</dt>
                      <dd>
                        {(() => {
                          const names = taskAssignees.length
                            ? taskAssignees.map(employeeName)
                            : data.assigned_employee_name ? [data.assigned_employee_name] : [];
                          if (names.length === 0) return '—';
                          return (
                            <span className={styles.people}>
                              {names.map((n) => <PersonName key={n} name={n} size="xs" />)}
                            </span>
                          );
                        })()}
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
                      <dt>{t(lang, 'Coût estimé', 'Est. cost')}</dt>
                          <dd>{data.estimated_cost != null ? formatCost(data.estimated_cost, lang) : '—'}</dd>
</dl>
                    )}
                  </section>

                  {/* Call notes sit with the planning facts they belong to. */}
                  {/* View-only: next steps as plain text. */}
                  {isEditor && !editMode && data.next_steps && (
                    <section className={styles.card} data-testid="notes-readonly">
                      <h3 className={styles.cardTitle}>{t(lang, 'Prochaines étapes', 'Next steps')}</h3>
                      <p className={styles.prose}>{data.next_steps}</p>
                    </section>
                  )}
                  {editMode && (
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

                        <div className={`${styles.editField} ${changedKeys.has('next_follow_up_date') ? styles.editFieldChanged : ''}`}>
                          <label className={styles.editLabel} htmlFor={`${titleId}-followup`}>{t(lang, 'Prochain suivi', 'Next follow-up')}</label>
                          <input
                            id={`${titleId}-followup`}
                            type="date"
                            className={styles.editInput}
                            value={followUp ?? data.next_follow_up_date ?? ''}
                            disabled={isClosed}
                            onChange={(e) => setFollowUp(e.target.value)}
                            data-testid="followup-input"
                          />
                        </div>
                      </div>

                    </section>
                  )}
                  {/* Triage button — intake_received or triage_failed */}
                  {editMode && (data.status === 'intake_received' || data.status === 'triage_failed' || data.status === 'triage_pending') && (
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
                  {/* The unit: where the work is and how to get in. */}
                  <section className={styles.card} data-testid="unit-card">
                    <div className={styles.cardHeadRow}>
                      <h3 className={styles.cardTitle}>{t(lang, 'Logement', 'Unit')}</h3>
                      {canEdit && (
                        <EditToggle on={editCards.has('unit')} onClick={() => toggleCard('unit')} testId="edit-unit-toggle"
                                    label={t(lang, "Modifier l'accès et les animaux", 'Edit access and animals')} />
                      )}
                    </div>
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
                      <dt>{t(lang, "N° d'unité", 'Unit #')}</dt>
                      <dd title={data.unique_unit_number ?? undefined} data-testid="unit-number">
                        {unitNumberOf(data.unit_label, data.unique_unit_number) ?? '—'}
                      </dd>
                      <dt>{t(lang, 'Territoire', 'Territory')}</dt>
                      <dd>{data.territoire ?? '—'}</dd>
                      {!editCards.has('unit') && (
                        <>
                          <dt>{t(lang, 'Accès', 'Access')}</dt>
                          <dd>{details.entry_permission ?? accessText}</dd>
                          <dt>{t(lang, 'Animaux', 'Animals')}</dt>
                          <dd>{details.animals ?? animalsText}</dd>
                        </>
                      )}
                    </dl>
                    {editCards.has('unit') && (
                      <div className={styles.cardForm}>
                        {detailInput('entry_permission', { multiline: true })}
                        {detailInput('animals')}
                        <p className={styles.cardFormNote}>
                          {t(lang, "L'immeuble et l'unité se changent dans le portfolio.", 'Building and unit are changed in the portfolio.')}
                        </p>
                      </div>
                    )}
                  </section>

                  {/* The tenant / caller as a contact card: who, where, and one tap to call or write. */}
                  {(() => {
                    const phone = data.caller_phone_placeholder ? null : data.caller_phone;
                    const email = data.caller_email_placeholder ? null : data.caller_email;
                    const name = data.caller_name?.trim() || null;
                    const role = data.caller_type === 'tenant' || data.caller_tenant_id != null
                      ? t(lang, 'Locataire', 'Tenant') : t(lang, 'Appelant', 'Caller');
                    const unitNo = unitNumberOf(data.unit_label, data.unique_unit_number);
                    const place = [unitNo && t(lang, `Unité ${unitNo}`, `Unit ${unitNo}`),
                      data.building_address].filter(Boolean).join(' · ');
                    return (
                      <section className={`${styles.card} ${styles.contactCard}`} data-testid="tenant-card"
                               aria-label={t(lang, 'Appelant', 'Caller')}>
                        <div className={styles.cardHeadRow}>
                          <h3 className={styles.cardTitle}>{role}</h3>
                          {canEdit && (
                            <EditToggle on={editCards.has('caller')} onClick={() => toggleCard('caller')} testId="edit-caller-toggle"
                                        label={t(lang, "Modifier l'appelant", 'Edit caller')} />
                          )}
                        </div>
                        {editCards.has('caller') && (
                          <div className={styles.cardForm}>
                            {detailInput('caller_name', { label: t(lang, 'Nom', 'Name') })}
                            {detailInput('caller_phone', { type: 'tel' })}
                            {detailInput('caller_email', { type: 'email' })}
                          </div>
                        )}
                        {!editCards.has('caller') && (<>
                        <div className={styles.contactHead}>
                          <Avatar name={name ?? '?'} size="lg" />
                          <div className={styles.contactWho}>
                            <p className={styles.contactName}>{name ?? t(lang, 'Nom non fourni', 'Name not provided')}</p>
                            {place && (
                              <p className={styles.contactPlace}><MapPinIcon size={16} />{place}</p>
                            )}
                          </div>
                        </div>
                        <ul className={styles.contactRows}>
                          <li>
                            <span className={styles.contactIcon}><MailIcon size={18} /></span>
                            <span data-testid="email-display">
                              {data.caller_email_placeholder
                                ? <span className={styles.contactMissing}>{t(lang, 'non fourni', 'not provided')}</span>
                                : email
                                  ? <a className={styles.contactLink} href={`mailto:${email}`}>{email}</a>
                                  : '—'}
                            </span>
                          </li>
                          <li>
                            <span className={styles.contactIcon}><PhoneIcon size={18} /></span>
                            <span data-testid="phone-display">
                              {data.caller_phone_placeholder
                                ? <span className={styles.contactMissing}>{t(lang, 'non fourni', 'not provided')}</span>
                                : phone
                                  ? <a className={styles.contactPhone} href={telHref(phone)}>{formatPhone(phone)}</a>
                                  : '—'}
                            </span>
                          </li>
                        </ul>
                        <div className={styles.contactActions}>
                          {phone ? (
                            <a className={styles.contactBtn} href={telHref(phone)} data-testid="contact-call">
                              <PhoneIcon size={18} />{t(lang, 'Appeler', 'Call')}
                            </a>
                          ) : (
                            <button type="button" className={styles.contactBtn} disabled>
                              <PhoneIcon size={18} />{t(lang, 'Appeler', 'Call')}
                            </button>
                          )}
                          {email ? (
                            <a className={styles.contactBtn} href={`mailto:${email}`} data-testid="contact-mail">
                              <MailIcon size={18} />{t(lang, 'Courriel', 'Email')}
                            </a>
                          ) : (
                            <button type="button" className={styles.contactBtn} disabled>
                              <MailIcon size={18} />{t(lang, 'Courriel', 'Email')}
                            </button>
                          )}
                        </div>
                        </>)}
                      </section>
                    );
                  })()}

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

                {tab === 'notes' && (
                  <div
                    className={styles.tabPanel}
                    role="tabpanel"
                    id={`${titleId}-panel-notes`}
                    aria-labelledby={`${titleId}-tab-notes`}
                    data-testid="tab-panel-notes"
                  >
                    <CallNotes
                      notes={data.followup_log}
                      lang={lang}
                      canAdd={isEditor}
                      onAdd={async (text) => {
                        try {
                          const updated = await dispatchAddLog(requestId, { entry_text: text });
                          qc.setQueryData(['request', requestId], updated);
                          qc.invalidateQueries({ queryKey: ['requests'] });
                          flashOk(t(lang, 'Note ajoutée.', 'Note added.'));
                        } catch (err) {
                          flashErr(err instanceof ApiError ? apiErrorMessage(lang, err) : t(lang, 'Note non enregistrée.', 'Note not saved.'));
                          throw err;
                        }
                      }}
                    />
                  </div>
                )}
              </>
            )}
          </div>

          {data && isEditor && !isClosed && (
            <footer className={`${styles.saveBar} ${pendingCount ? styles.saveBarDirty : ''}`} data-testid="save-bar">
              {/* AI feedback lives beside « Enregistrer »: « Utile » saves and
                  dispatches at once; the other two ask for a comment first. */}
              {editMode && <div className={styles.saveBarFeedback}>
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
              </div>}
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
