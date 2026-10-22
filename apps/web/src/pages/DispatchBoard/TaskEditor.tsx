/** Call detail: the call's tasks (assign / schedule) and « Nouvelle tâche ». */
import { forwardRef, useEffect, useImperativeHandle, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ApiError, apiErrorMessage, acceptTask, assignTask, cancelTask, createTask, followUpTask, rejectAllTasks, rejectTask,
  scheduleTask, updateTask,
  type Justification, type TechnicianSuggestion,
} from '../../api/client';
import type { EmployeeLookup, TaskOut } from '../../api/schema.d.ts';
import { useJustify, type JustifyRequest } from '../../components/Justification';
import { roleLabel, statusLabel, t, type Lang } from '../../i18n';
import { dueAtFromSlot, dueSlot, fmtSlot } from '../../lib/taskDates';
import { urgencyOptions } from '../../lib/urgencyLevels';
import Select from '../../components/Select';
import styles from './DetailPanel.module.css';
import { Avatar, initialsOf } from '../../components/Avatar';
import { joinTask, splitTask } from '../../lib/taskText';
import DueDateTime from '../../components/DueDateTime';

interface Props {
  lang: Lang;
  requestId: number;
  callStatus: string;
  tasks: TaskOut[];
  employees: EmployeeLookup[];
  /** Same ranked list for the call; applied per task (or new-task) assignee. */
  suggestions?: TechnicianSuggestion[];
  onError: (message: string) => void;
  onSuccess?: (message: string) => void;
  /** Staged accepted-task edits — parent Save bar uses this count. */
  onDirtyChange?: (count: number) => void;
}

export type TaskPendingRow = { label: string; before: string; after: string };

export type TaskEditorHandle = {
  discardDrafts: () => void;
  pendingRows: () => TaskPendingRow[];
  /** Apply staged accepted-task field edits with the shared justification. */
  commitDrafts: (justification: Justification) => Promise<void>;
  /** Accept every AI proposal, applying local draft overrides. Requires feedback first. */
  acceptProposals: () => Promise<void>;
};

// Assignee and date are dispatcher-editable until the tech leaves (backend _EDITABLE).
const EDITABLE = new Set(['queued', 'scheduled']);
const IN_PROGRESS = new Set(['en_route', 'arrived', 'working']);
// A follow-up child resolves these for auto-close (backend _FOLLOWED_UP).
const NEEDS_FOLLOW_UP = new Set(['needs_expertise', 'return_visit']);
// Machine edges into cancelled (backend task_status_machine).
const CAN_CANCEL = new Set(['queued', 'scheduled', 'needs_expertise', 'return_visit']);
// « Créer suivi » (POST /tasks/{id}/follow-up) is also open on done tasks (backend _FOLLOW_UP_PARENTS).
const CAN_FOLLOW_UP = new Set(['needs_expertise', 'return_visit', 'done']);
// Task creation opens the call (also from triage_proposal); refused before triage is done.
const NO_NEW_TASK = new Set([
  'intake_received', 'triage_pending', 'triage_clarify', 'triage_failed', 'closed',
]);

type Draft = {
  assignee?: number | null;
  day?: string;
  urgency?: string | null;
  sub?: string | null;
};
type ProposalDraft = {
  description?: string;
  subcontractor_name?: string | null;
  urgency_tier?: string | null;
  assignee?: number | null;
  day?: string;
};

function TechSuggestList({
  lang, suggestions, disabled, onPick, testId, compact = false, selectedId = null,
}: {
  lang: Lang;
  suggestions: TechnicianSuggestion[];
  disabled: boolean;
  onPick: (employeeId: number) => void;
  testId: string;
  /** One line of chips (existing tasks); the full cards stay in « Nouvelle tâche ». */
  compact?: boolean;
  /** The task's current assignee: its chip shows as picked. */
  selectedId?: number | null;
}) {
  if (suggestions.length === 0) return null;
  if (compact) {
    return (
      <div className={styles.suggestCompact} data-testid={testId}>
        <span className={styles.suggestCompactLabel}>{t(lang, 'Technicien recommandé :', 'Recommended technician:')}</span>
        {suggestions.map((s) => {
          const full = `${s.name}${s.is_en_route ? ` (${t(lang, 'en route', 'en route')})` : ''} — ${s.why}`;
          return (
            <button
              key={s.employee_id}
              type="button"
              className={`${styles.suggestChip} ${selectedId === s.employee_id ? styles.suggestChipOn : ''}`}
              disabled={disabled}
              aria-pressed={selectedId === s.employee_id}
              aria-label={t(lang, `Assigner à ${full}`, `Assign to ${full}`)}
              title={full}
              data-testid={`${testId}-${s.employee_id}`}
              onClick={() => onPick(s.employee_id)}
            >
              <span className={styles.suggestChipInit}>{initialsOf(s.name)}</span>
              {s.name}
              {s.is_en_route && <span className={styles.suggestChipDot} aria-hidden="true" />}
            </button>
          );
        })}
      </div>
    );
  }
  return (
    <div className={styles.suggestBlock} data-testid={testId}>
      <label className={styles.editLabel}>
        {t(lang, 'Suggestion technicien', 'Technician suggestion')}
      </label>
      <ul className={styles.suggestList}>
        {suggestions.map((s) => (
          <li key={s.employee_id}>
            <button
              type="button"
              className={styles.suggestBtn}
              disabled={disabled}
              data-testid={`${testId}-${s.employee_id}`}
              onClick={() => onPick(s.employee_id)}
            >
              <span className={styles.suggestName}>
                <Avatar name={s.name} size="sm" />{s.name}
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
  );
}

const TaskEditor = forwardRef<TaskEditorHandle, Props>(function TaskEditor({
  lang, requestId, callStatus, tasks, employees, suggestions = [], onError, onSuccess, onDirtyChange,
}, ref) {
  const qc = useQueryClient();
  const justify = useJustify();
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  // New task: a short name plus an optional description (saved as one text, name first).
  const [newName, setNewName] = useState('');
  const [newDetails, setNewDetails] = useState('');
  const newDesc = joinTask(newName, newDetails);
  const setNewDesc = (text: string) => { const x = splitTask(text); setNewName(x.name); setNewDetails(x.details); };
  const [newAssignee, setNewAssignee] = useState<number | null>(null);
  const [newDay, setNewDay] = useState('');
  const [parent, setParent] = useState<TaskOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [proposalDrafts, setProposalDrafts] = useState<Record<number, ProposalDraft>>({});

  const accepted = tasks.filter((x) => x.accepted_at != null);
  const proposals = tasks.filter((x) => x.accepted_at == null);
  const assignable = employees.filter((e) => e.role === 'technician' || e.role === 'contractor');
  const isClosed = callStatus === 'closed';
  const canCreate = !NO_NEW_TASK.has(callStatus);
  const hasFollowUp = (id: number) => accepted.some((x) => x.parent_task_id === id);

  function startFollowUp(task: TaskOut) {
    setParent(task);
    setNewDesc(task.description);
  }
  const UNASSIGNED = t(lang, 'Non assigné', 'Unassigned');
  const NONE = t(lang, 'Aucune', 'None');
  const nameOf = (id: number | null) =>
    id == null ? UNASSIGNED : employees.find((e) => e.employee_id === id)?.nom_employe ?? `#${id}`;

  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['request', requestId] }),
      qc.invalidateQueries({ queryKey: ['tasks'] }),
      qc.invalidateQueries({ queryKey: ['requests'] }),
    ]);
  }

  function report(err: unknown) {
    onError(apiErrorMessage(lang, err));
    if (err instanceof ApiError && err.code === 'ASSIGNEE_EN_ROUTE') {
      qc.invalidateQueries({ queryKey: ['employees'] });
    }
    qc.invalidateQueries({ queryKey: ['request', requestId] });
  }

  async function run(req: JustifyRequest, fn: (j: { text: string; input_method: 'voice' | 'typed' }) => Promise<void>) {
    const j = await justify(req);
    if (!j) return false;
    setBusy(true);
    try {
      await fn(j);
      await refresh();
      return true;
    } catch (err) {
      report(err);
      return false;
    } finally {
      setBusy(false);
    }
  }

  // Accepting / rejecting AI proposals needs no justification: the dispatcher
  // is confirming or discarding a draft, not overriding a decision.
  async function decideProposals(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await refresh();
    } catch (err) {
      report(err);
    } finally {
      setBusy(false);
    }
  }

  function proposalView(p: TaskOut) {
    const d = proposalDrafts[p.task_id] ?? {};
    return {
      description: d.description ?? p.description,
      subcontractor_name: d.subcontractor_name !== undefined ? d.subcontractor_name : p.subcontractor_name,
      urgency_tier: d.urgency_tier !== undefined ? d.urgency_tier : p.urgency_tier,
      assignee: d.assignee !== undefined ? d.assignee : p.assigned_employee_id,
      day: d.day !== undefined ? d.day : (dueSlot(p.due_at) ?? ''),
    };
  }
  function setProposal(taskId: number, patch: ProposalDraft) {
    setProposalDrafts((prev) => ({ ...prev, [taskId]: { ...prev[taskId], ...patch } }));
  }

  function acceptBody(p: TaskOut): Parameters<typeof acceptTask>[1] {
    const v = proposalView(p);
    const body: Parameters<typeof acceptTask>[1] = {};
    const text = v.description.trim();
    if (text && text !== p.description) body.description = text;
    if ((v.subcontractor_name ?? null) !== (p.subcontractor_name ?? null)) {
      body.subcontractor_name = v.subcontractor_name;
    }
    if ((v.urgency_tier ?? null) !== (p.urgency_tier ?? null)) {
      body.urgency_tier = v.urgency_tier;
    }
    if ((v.assignee ?? null) !== (p.assigned_employee_id ?? null)) {
      body.assigned_employee_id = v.assignee;
    }
    if ((v.day || null) !== (dueSlot(p.due_at) ?? null)) {
      body.due_at = v.day ? dueAtFromSlot(v.day) : null;
    }
    return body;
  }

  async function acceptProposals() {
    for (const p of proposals) {
      const text = proposalView(p).description.trim();
      if (!text) throw new Error(t(lang, 'Description requise', 'Description required'));
      await acceptTask(p.task_id, acceptBody(p));
    }
    setProposalDrafts({});
  }

  function rejectAllProposals() {
    const backToClarify = accepted.length === 0;
    const msg = backToClarify
      ? t(lang, "Rejeter toutes les propositions renvoie l'appel en clarification. Continuer ?",
        'Rejecting every proposal sends the call back to clarification. Continue?')
      : t(lang, 'Rejeter toutes les propositions ?', 'Reject all proposals?');
    if (!window.confirm(msg)) return;
    return decideProposals(() => rejectAllTasks(requestId));
  }

  function taskFieldChanges(task: TaskOut, d: Draft): TaskPendingRow[] {
    const assigneeChanged = d.assignee !== undefined && d.assignee !== task.assigned_employee_id;
    const dayChanged = d.day !== undefined && (d.day || null) !== dueSlot(task.due_at);
    const urgencyChanged = d.urgency !== undefined && (d.urgency ?? null) !== (task.urgency_tier ?? null);
    const subChanged = d.sub !== undefined && (d.sub ?? null) !== (task.subcontractor_name ?? null);
    const prefix = `${t(lang, 'Tâche', 'Task')} — ${splitTask(task.description).name}`;
    return [
      ...(assigneeChanged ? [{ label: `${prefix} · ${t(lang, 'Assignation', 'Assignment')}`,
        before: nameOf(task.assigned_employee_id), after: nameOf(d.assignee!)}] : []),
      ...(dayChanged ? [{ label: `${prefix} · ${t(lang, 'Date prévue', 'Due date')}`,
        before: fmtSlot(dueSlot(task.due_at)) || NONE, after: fmtSlot(d.day) || NONE }] : []),
      ...(urgencyChanged ? [{ label: `${prefix} · ${t(lang, 'Urgence', 'Urgency')}`,
        before: task.urgency_tier ?? NONE, after: d.urgency ?? NONE }] : []),
      ...(subChanged ? [{ label: `${prefix} · ${t(lang, 'Sous-traitant', 'Subcontractor')}`,
        before: task.subcontractor_name ?? NONE, after: d.sub || NONE }] : []),
    ];
  }

  function pendingRows(): TaskPendingRow[] {
    return accepted.flatMap((task) => taskFieldChanges(task, drafts[task.task_id] ?? {}));
  }

  const dirtyCount = pendingRows().length;
  useEffect(() => {
    onDirtyChange?.(dirtyCount);
  }, [dirtyCount, onDirtyChange]);

  useImperativeHandle(ref, () => ({
    discardDrafts: () => setDrafts({}),
    pendingRows,
    acceptProposals,
    commitDrafts: async (justification: Justification) => {
      for (const task of accepted) {
        const d = drafts[task.task_id] ?? {};
        const assigneeChanged = d.assignee !== undefined && d.assignee !== task.assigned_employee_id;
        const dayChanged = d.day !== undefined && (d.day || null) !== dueSlot(task.due_at);
        const urgencyChanged = d.urgency !== undefined && (d.urgency ?? null) !== (task.urgency_tier ?? null);
        const subChanged = d.sub !== undefined && (d.sub ?? null) !== (task.subcontractor_name ?? null);
        if (!assigneeChanged && !dayChanged && !urgencyChanged && !subChanged) continue;
        if (assigneeChanged) {
          await assignTask(task.task_id, { assigned_employee_id: d.assignee!, justification });
        }
        if (dayChanged) {
          await scheduleTask(task.task_id, { due_at: d.day ? dueAtFromSlot(d.day) : null, justification });
        }
        if (urgencyChanged || subChanged) {
          await updateTask(task.task_id, {
            ...(urgencyChanged ? { urgency_tier: d.urgency ?? null } : {}),
            ...(subChanged ? { subcontractor_name: d.sub || null } : {}),
            justification,
          });
        }
      }
      setDrafts({});
    },
  }), [accepted, drafts, lang, employees]);

  async function cancelTaskRow(task: TaskOut) {
    await run(
      {
        decision: `${t(lang, 'Annuler la tâche', 'Cancel task')} — ${splitTask(task.description).name}`,
        before: statusLabel(lang, task.status),
        after: statusLabel(lang, 'cancelled'),
      },
      async (justification) => {
        await cancelTask(task.task_id, { justification });
      },
    );
  }

  async function addTask() {
    const description = newDesc.trim();
    if (!newName.trim()) return;
    const ok = await run(
      {
        decision: parent
          ? `${t(lang, 'Redispatcher', 'Redispatch')} — ${splitTask(parent.description).name}`
          : t(lang, 'Nouvelle tâche', 'New task'),
        changes: [
          { label: t(lang, 'Tâche', 'Task'), before: NONE, after: description },
          { label: t(lang, 'Assignation', 'Assignment'), before: NONE, after: nameOf(newAssignee) },
          { label: t(lang, 'Date prévue', 'Due date'), before: NONE, after: fmtSlot(newDay) || NONE },
        ],
      },
      async (justification) => {
        await createTask({
          request_id: requestId,
          description,
          assigned_employee_id: newAssignee,
          due_at: newDay ? dueAtFromSlot(newDay) : null,
          parent_task_id: parent?.task_id ?? null,
          justification,
        });
      },
    );
    if (ok) {
      setNewDesc(''); setNewAssignee(null); setNewDay(''); setParent(null);
      onSuccess?.(t(lang, 'Tâche créée.', 'Task created.'));
    }
  }

  function assigneeOptions(current: number | null) {
    const currentEmp = current != null ? employees.find((e) => e.employee_id === current) : undefined;
    const ineligible = currentEmp && currentEmp.role !== 'technician' && currentEmp.role !== 'contractor';
    return (
      <>
        <option value="">— {UNASSIGNED} —</option>
        {ineligible && (
          <option value={String(current)} disabled>
            {currentEmp.nom_employe} ({roleLabel(lang, currentEmp.role)})
          </option>
        )}
        {assignable.map((e) => (
          <option key={e.employee_id} value={e.employee_id} disabled={e.is_en_route && e.employee_id !== current}>
            {e.nom_employe} ({roleLabel(lang, e.role)})
            {e.is_en_route ? ` — ${t(lang, 'en route', 'en route')}` : ''}
          </option>
        ))}
      </>
    );
  }

  return (
    <div className={`${styles.actionsGrid} ${styles.tasksGrid}`} data-testid="tasks-section">
      {accepted.length === 0 && (
        <p className={styles.closedNotice} data-testid="no-tasks">
          {t(lang, 'Aucune tâche sur cet appel.', 'No tasks on this call.')}
        </p>
      )}

      {accepted.map((task) => {
        const d = drafts[task.task_id] ?? {};
        const editable = !isClosed && EDITABLE.has(task.status);
        const assignee = d.assignee !== undefined ? d.assignee : task.assigned_employee_id;
        const day = d.day !== undefined ? d.day : (dueSlot(task.due_at) ?? '');
        const urgency = d.urgency !== undefined ? d.urgency : task.urgency_tier;
        const dirty = taskFieldChanges(task, d).length > 0;
        const setDraft = (patch: Draft) =>
          setDrafts((prev) => ({ ...prev, [task.task_id]: { ...prev[task.task_id], ...patch } }));
        return (
          <div
            key={task.task_id}
            className={`${styles.editField} ${dirty ? styles.editFieldChanged : ''}`}
            data-testid={`task-${task.task_id}`}
          >
            <span className={styles.editLabel}>
              <span className={styles.taskRowName} title={splitTask(task.description).name}>{splitTask(task.description).name}</span>
              {' · '}{statusLabel(lang, task.status)}
              {splitTask(task.description).details && (
                <span className={styles.taskRowDetails} title={splitTask(task.description).details}>
                  {splitTask(task.description).details}
                </span>
              )}
            </span>
            <Select
              className={styles.editInput}
              value={String(assignee ?? '')}
              disabled={!editable || busy}
              aria-label={t(lang, 'Assigné à', 'Assigned to')}
              data-testid={`task-assign-${task.task_id}`}
              searchable avatars
              searchPlaceholder={t(lang, 'Rechercher un employé…', 'Search employees…')}
              noResultsText={t(lang, 'Aucun employé trouvé', 'No employee found')}
              onChange={(e) => setDraft({ assignee: e.target.value === '' ? null : Number(e.target.value) })}
            >
              {assigneeOptions(task.assigned_employee_id)}
            </Select>
            {editable && (
              <TechSuggestList
                compact
                lang={lang}
                suggestions={suggestions}
                disabled={busy}
                selectedId={assignee ?? null}
                testId={`task-suggest-${task.task_id}`}
                onPick={(employeeId) => setDraft({ assignee: employeeId })}
              />
            )}
            <DueDateTime
              lang={lang}
              inputClassName={styles.editInput}
              value={day}
              disabled={!editable || busy}
              testId={`task-due-${task.task_id}`}
              onChange={(slot) => setDraft({ day: slot })}
            />
            <label className={styles.editLabel}>{t(lang, 'Urgence', 'Urgency')}</label>
            <Select
              className={styles.editInput}
              value={urgency ?? ''}
              disabled={!editable || busy}
              data-testid={`task-urgency-${task.task_id}`}
              onChange={(e) => setDraft({ urgency: e.target.value || null })}
            >
              {urgencyOptions(lang).map(({ value, label }) => (
                <option key={String(value)} value={value ?? ''}>{label}</option>
              ))}
            </Select>
            {IN_PROGRESS.has(task.status) && (
              <p className={styles.closedNotice} data-testid={`task-locked-${task.task_id}`}>
                {t(lang,
                  "Appel en cours — le technicien doit d'abord clôturer",
                  'Call in progress — the technician must close it out first')}
              </p>
            )}
            {!isClosed && CAN_CANCEL.has(task.status) && (
              <button
                type="button"
                className={styles.discardBtn}
                disabled={busy}
                onClick={() => cancelTaskRow(task)}
                data-testid={`task-cancel-${task.task_id}`}
              >
                {t(lang, 'Annuler', 'Cancel')}
              </button>
            )}
            {NEEDS_FOLLOW_UP.has(task.status) && !hasFollowUp(task.task_id) && canCreate && (
              <button
                type="button"
                className={styles.applyBtn}
                disabled={busy || parent?.task_id === task.task_id}
                onClick={() => startFollowUp(task)}
                data-testid={`task-redispatch-${task.task_id}`}
              >
                {t(lang, 'Redispatcher', 'Redispatch')}
              </button>
            )}
            {CAN_FOLLOW_UP.has(task.status) && !hasFollowUp(task.task_id) && canCreate && (
              <button
                type="button"
                className={styles.applyBtn}
                disabled={busy}
                title={t(lang, 'Crée une tâche de suivi non assignée, dans 14 jours', 'Creates an unassigned follow-up task, due in 14 days')}
                onClick={() => decideProposals(() => followUpTask(task.task_id))}
                data-testid={`task-follow-up-${task.task_id}`}
              >
                {t(lang, 'Créer suivi', 'Create follow-up')}
              </button>
            )}
          </div>
        );
      })}

      {proposals.length > 0 && !isClosed && (
        <div className={styles.editField} data-testid="task-proposals">
          <span className={styles.editLabel}>{t(lang, 'Propositions IA (à accepter)', 'AI proposals (to accept)')}</span>
          {proposals.map((p) => {
            const v = proposalView(p);
            return (
            <div key={p.task_id} className={styles.editField} data-testid={`proposal-${p.task_id}`}>
              <textarea
                className={styles.editTextarea}
                value={v.description}
                rows={2}
                disabled={busy}
                aria-label={t(lang, 'Proposition IA', 'AI proposal')}
                data-testid={`proposal-desc-${p.task_id}`}
                onChange={(e) => setProposal(p.task_id, { description: e.target.value })}
              />
              <label className={styles.editLabel}>{t(lang, 'Urgence', 'Urgency')}</label>
              <Select
                className={styles.editInput}
                value={v.urgency_tier ?? ''}
                disabled={busy}
                data-testid={`proposal-urgency-${p.task_id}`}
                onChange={(e) => setProposal(p.task_id, { urgency_tier: e.target.value || null })}
              >
                {urgencyOptions(lang).map(({ value, label }) => (
                  <option key={String(value)} value={value ?? ''}>{label}</option>
                ))}
              </Select>
              <label className={styles.editLabel}>{t(lang, 'Assigné à', 'Assigned to')}</label>
              <Select
                className={styles.editInput}
                value={String(v.assignee ?? '')}
                disabled={busy}
                data-testid={`proposal-assign-${p.task_id}`}
                searchable avatars
                searchPlaceholder={t(lang, 'Rechercher un employé…', 'Search employees…')}
                noResultsText={t(lang, 'Aucun employé trouvé', 'No employee found')}
                onChange={(e) => setProposal(p.task_id, {
                  assignee: e.target.value === '' ? null : Number(e.target.value),
                })}
              >
                {assigneeOptions(null)}
              </Select>
              <TechSuggestList
                compact
                lang={lang}
                suggestions={suggestions}
                disabled={busy}
                selectedId={v.assignee ?? null}
                testId={`proposal-suggest-${p.task_id}`}
                onPick={(employeeId) => setProposal(p.task_id, { assignee: employeeId })}
              />
              <label className={styles.editLabel}>{t(lang, 'Date prévue', 'Due date')}</label>
              <DueDateTime
                lang={lang}
                inputClassName={styles.editInput}
                value={v.day}
                disabled={busy}
                testId={`proposal-due-${p.task_id}`}
                onChange={(slot) => setProposal(p.task_id, { day: slot })}
              />
              <button
                type="button"
                className={styles.discardBtn}
                disabled={busy}
                onClick={() => decideProposals(() => rejectTask(p.task_id))}
                data-testid={`proposal-reject-${p.task_id}`}
              >
                {t(lang, 'Rejeter', 'Reject')}
              </button>
            </div>
            );
          })}
          <p className={styles.editLabel}>
            {t(lang,
              'Dispatcher via le retour IA ci-dessus (Utile / Partiellement / Pas utile).',
              'Dispatch via the AI feedback above (Useful / Partially / Not useful).')}
          </p>
          <button
            type="button"
            className={styles.discardBtn}
            disabled={busy}
            onClick={rejectAllProposals}
            data-testid="proposals-reject-all"
          >
            {t(lang, 'Tout rejeter', 'Reject all')}
          </button>
        </div>
      )}

      <div className={styles.editField} data-testid="new-task">
        <span className={styles.editLabel} data-testid={parent ? 'new-task-parent' : undefined}>
          {parent
            ? t(lang, `Redispatch — ${splitTask(parent.description).name}`, `Redispatch — ${splitTask(parent.description).name}`)
            : t(lang, 'Nouvelle tâche', 'New task')}
        </span>
        {parent && (
          <button type="button" className={styles.discardBtn} disabled={busy} onClick={() => { setParent(null); setNewDesc(''); }}>
            {t(lang, 'Annuler le redispatch', 'Cancel redispatch')}
          </button>
        )}
        <input
          className={styles.editInput}
          value={newName}
          maxLength={120}
          disabled={!canCreate || busy}
          aria-label={t(lang, 'Nom de la tâche', 'Task name')}
          placeholder={t(lang, 'Nom de la tâche (p. ex. Réparer la fuite)', 'Task name (e.g. Fix the leak)')}
          data-testid="new-task-name"
          onChange={(e) => setNewName(e.target.value)}
        />
        <textarea
          className={styles.editTextarea}
          value={newDetails}
          rows={2}
          disabled={!canCreate || busy}
          aria-label={t(lang, 'Description de la tâche', 'Task description')}
          placeholder={t(lang, 'Description (détails pour le technicien)…', 'Description (details for the technician)…')}
          data-testid="new-task-desc"
          onChange={(e) => setNewDetails(e.target.value)}
        />
        <Select
          className={styles.editInput}
          value={String(newAssignee ?? '')}
          disabled={!canCreate || busy}
          data-testid="new-task-assign"
          searchable avatars
          searchPlaceholder={t(lang, 'Rechercher un employé…', 'Search employees…')}
          noResultsText={t(lang, 'Aucun employé trouvé', 'No employee found')}
          onChange={(e) => setNewAssignee(e.target.value === '' ? null : Number(e.target.value))}
        >
          {assigneeOptions(null)}
        </Select>
        {canCreate && (
          <TechSuggestList
            lang={lang}
            suggestions={suggestions}
            disabled={busy}
            testId="new-task-suggest"
            onPick={(employeeId) => setNewAssignee(employeeId)}
          />
        )}
        <DueDateTime
          lang={lang}
          inputClassName={styles.editInput}
          value={newDay}
          disabled={!canCreate || busy}
          testId="new-task-due"
          onChange={setNewDay}
        />
        <button
          type="button"
          className={styles.applyBtn}
          disabled={!canCreate || busy || !newName.trim()}
          onClick={addTask}
          data-testid="new-task-btn"
        >
          {parent ? t(lang, 'Créer le redispatch', 'Create redispatch') : t(lang, 'Ajouter la tâche', 'Add task')}
        </button>
      </div>
    </div>
  );
});

export default TaskEditor;
