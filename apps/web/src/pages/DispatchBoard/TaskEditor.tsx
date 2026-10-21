/** Call detail: the call's tasks (assign / schedule) and « Nouvelle tâche ». */
import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ApiError, acceptAllTasks, acceptTask, assignTask, createTask, followUpTask, rejectAllTasks, rejectTask,
  scheduleTask,
} from '../../api/client';
import type { EmployeeLookup, TaskOut } from '../../api/schema.d.ts';
import { useJustify, type JustifyRequest } from '../../components/Justification';
import { roleLabel, statusLabel, t, type Lang } from '../../i18n';
import { dueAtFromDay, dueDay } from '../../lib/taskDates';
import Select from '../../components/Select';
import styles from './DetailPanel.module.css';

interface Props {
  lang: Lang;
  requestId: number;
  callStatus: string;
  tasks: TaskOut[];
  employees: EmployeeLookup[];
  /** A technician suggestion picked in the panel — pre-fills the new task's assignee. */
  suggestedEmployeeId: number | null;
  onError: (message: string) => void;
}

// Assignee and date are dispatcher-editable until the tech leaves (backend _EDITABLE).
const EDITABLE = new Set(['queued', 'scheduled']);
const IN_PROGRESS = new Set(['en_route', 'arrived', 'working']);
// A follow-up child resolves these for auto-close (backend _FOLLOWED_UP).
const NEEDS_FOLLOW_UP = new Set(['needs_expertise', 'return_visit']);
// « Créer suivi » (POST /tasks/{id}/follow-up) is also open on done tasks (backend _FOLLOW_UP_PARENTS).
const CAN_FOLLOW_UP = new Set(['needs_expertise', 'return_visit', 'done']);
// Task creation opens the call (also from triage_proposal); refused before triage is done.
const NO_NEW_TASK = new Set([
  'intake_received', 'triage_pending', 'triage_clarify', 'triage_failed', 'closed',
]);

type Draft = { assignee?: number | null; day?: string };

export default function TaskEditor({
  lang, requestId, callStatus, tasks, employees, suggestedEmployeeId, onError,
}: Props) {
  const qc = useQueryClient();
  const justify = useJustify();
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [newDesc, setNewDesc] = useState('');
  const [newAssignee, setNewAssignee] = useState<number | null>(null);
  const [newDay, setNewDay] = useState('');
  const [parent, setParent] = useState<TaskOut | null>(null);
  const [busy, setBusy] = useState(false);
  // Re-worded proposals, keyed by task id; untouched proposals are accepted as written.
  const [wording, setWording] = useState<Record<number, string>>({});

  useEffect(() => {
    if (suggestedEmployeeId != null) setNewAssignee(suggestedEmployeeId);
  }, [suggestedEmployeeId]);

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
    if (err instanceof ApiError && err.code === 'ASSIGNEE_EN_ROUTE') {
      onError(t(lang, "Technicien déjà en route — clôturer d'abord", 'Technician already en route — close out first'));
      qc.invalidateQueries({ queryKey: ['employees'] });
    } else {
      onError(err instanceof ApiError ? err.message : t(lang, 'Erreur', 'Error'));
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

  const proposalText = (p: TaskOut) => wording[p.task_id] ?? p.description;
  const anyReworded = proposals.some((p) => proposalText(p).trim() !== p.description);

  function acceptProposal(p: TaskOut) {
    const text = proposalText(p).trim();
    if (!text) return;
    return decideProposals(() => acceptTask(p.task_id, text !== p.description ? { description: text } : {}));
  }

  function rejectAllProposals() {
    // With nothing accepted yet, this sends the call back to clarify.
    const backToClarify = accepted.length === 0;
    const msg = backToClarify
      ? t(lang, "Rejeter toutes les propositions renvoie l'appel en clarification. Continuer ?",
        'Rejecting every proposal sends the call back to clarification. Continue?')
      : t(lang, 'Rejeter toutes les propositions ?', 'Reject all proposals?');
    if (!window.confirm(msg)) return;
    return decideProposals(() => rejectAllTasks(requestId));
  }

  async function saveTask(task: TaskOut) {
    const d = drafts[task.task_id] ?? {};
    const assigneeChanged = d.assignee !== undefined && d.assignee !== task.assigned_employee_id;
    const dayChanged = d.day !== undefined && (d.day || null) !== dueDay(task.due_at);
    if (!assigneeChanged && !dayChanged) return;
    const changes = [
      ...(assigneeChanged ? [{ label: t(lang, 'Assignation', 'Assignment'),
        before: nameOf(task.assigned_employee_id), after: nameOf(d.assignee!) }] : []),
      ...(dayChanged ? [{ label: t(lang, 'Date prévue', 'Due date'),
        before: dueDay(task.due_at) ?? NONE, after: d.day || NONE }] : []),
    ];
    const ok = await run(
      {
        decision: `${t(lang, 'Tâche', 'Task')} — ${task.description}`,
        ...(changes.length === 1 ? { before: changes[0].before, after: changes[0].after } : {}),
        changes,
      },
      async (justification) => {
        if (assigneeChanged) await assignTask(task.task_id, { assigned_employee_id: d.assignee!, justification });
        if (dayChanged) {
          await scheduleTask(task.task_id, { due_at: d.day ? dueAtFromDay(d.day) : null, justification });
        }
      },
    );
    if (ok) setDrafts((prev) => { const next = { ...prev }; delete next[task.task_id]; return next; });
  }

  async function addTask() {
    const description = newDesc.trim();
    if (!description) return;
    const ok = await run(
      {
        decision: parent
          ? `${t(lang, 'Redispatcher', 'Redispatch')} — ${parent.description}`
          : t(lang, 'Nouvelle tâche', 'New task'),
        changes: [
          { label: t(lang, 'Tâche', 'Task'), before: NONE, after: description },
          { label: t(lang, 'Assignation', 'Assignment'), before: NONE, after: nameOf(newAssignee) },
          { label: t(lang, 'Date prévue', 'Due date'), before: NONE, after: newDay || NONE },
        ],
      },
      async (justification) => {
        await createTask({
          request_id: requestId,
          description,
          assigned_employee_id: newAssignee,
          due_at: newDay ? dueAtFromDay(newDay) : null,
          parent_task_id: parent?.task_id ?? null,
          justification,
        });
      },
    );
    if (ok) { setNewDesc(''); setNewAssignee(null); setNewDay(''); setParent(null); }
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
    <div className={styles.actionsGrid} data-testid="tasks-section">
      {accepted.length === 0 && (
        <p className={styles.closedNotice} data-testid="no-tasks">
          {t(lang, 'Aucune tâche sur cet appel.', 'No tasks on this call.')}
        </p>
      )}

      {accepted.map((task) => {
        const d = drafts[task.task_id] ?? {};
        const editable = !isClosed && EDITABLE.has(task.status);
        const assignee = d.assignee !== undefined ? d.assignee : task.assigned_employee_id;
        const day = d.day !== undefined ? d.day : (dueDay(task.due_at) ?? '');
        const dirty = (d.assignee !== undefined && d.assignee !== task.assigned_employee_id)
          || (d.day !== undefined && (d.day || null) !== dueDay(task.due_at));
        const setDraft = (patch: Draft) =>
          setDrafts((prev) => ({ ...prev, [task.task_id]: { ...prev[task.task_id], ...patch } }));
        return (
          <div key={task.task_id} className={styles.editField} data-testid={`task-${task.task_id}`}>
            <span className={styles.editLabel}>
              {task.description} · {statusLabel(lang, task.status)}
            </span>
            <Select
              className={styles.editInput}
              value={String(assignee ?? '')}
              disabled={!editable || busy}
              aria-label={t(lang, 'Assigné à', 'Assigned to')}
              data-testid={`task-assign-${task.task_id}`}
              onChange={(e) => setDraft({ assignee: e.target.value === '' ? null : Number(e.target.value) })}
            >
              {assigneeOptions(task.assigned_employee_id)}
            </Select>
            <input
              type="date"
              className={styles.editInput}
              value={day}
              disabled={!editable || busy}
              aria-label={t(lang, 'Date prévue', 'Due date')}
              data-testid={`task-due-${task.task_id}`}
              onChange={(e) => setDraft({ day: e.target.value })}
            />
            {IN_PROGRESS.has(task.status) && (
              <p className={styles.closedNotice} data-testid={`task-locked-${task.task_id}`}>
                {t(lang,
                  "Appel en cours — le technicien doit d'abord clôturer",
                  'Call in progress — the technician must close it out first')}
              </p>
            )}
            {editable && (
              <button
                type="button"
                className={styles.applyBtn}
                disabled={!dirty || busy}
                onClick={() => saveTask(task)}
                data-testid={`task-save-${task.task_id}`}
              >
                {t(lang, 'Enregistrer', 'Save')}
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
          {proposals.map((p) => (
            <div key={p.task_id} className={styles.editField} data-testid={`proposal-${p.task_id}`}>
              <textarea
                className={styles.editTextarea}
                value={proposalText(p)}
                rows={2}
                disabled={busy}
                aria-label={t(lang, 'Proposition IA', 'AI proposal')}
                data-testid={`proposal-desc-${p.task_id}`}
                onChange={(e) => setWording((prev) => ({ ...prev, [p.task_id]: e.target.value }))}
              />
              <button
                type="button"
                className={styles.applyBtn}
                disabled={busy || !proposalText(p).trim()}
                onClick={() => acceptProposal(p)}
                data-testid={`proposal-accept-${p.task_id}`}
              >
                {t(lang, 'Accepter', 'Accept')}
              </button>
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
          ))}
          <button
            type="button"
            className={styles.applyBtn}
            disabled={busy || anyReworded}
            title={anyReworded ? t(lang, 'Acceptez les propositions modifiées une à une', 'Accept edited proposals one by one') : undefined}
            onClick={() => decideProposals(() => acceptAllTasks(requestId))}
            data-testid="proposals-accept-all"
          >
            {t(lang, 'Tout accepter', 'Accept all')}
          </button>
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
        <span className={styles.editLabel}>{t(lang, 'Nouvelle tâche', 'New task')}</span>
        {parent && (
          <p className={styles.closedNotice} data-testid="new-task-parent">
            {t(lang, 'Suite de', 'Follow-up to')} : {parent.description} · {statusLabel(lang, parent.status)}{' '}
            <button
              type="button"
              className={styles.applyBtn}
              disabled={busy}
              onClick={() => setParent(null)}
              data-testid="new-task-parent-clear"
            >
              {t(lang, 'Retirer', 'Remove')}
            </button>
          </p>
        )}
        <textarea
          className={styles.editTextarea}
          value={newDesc}
          rows={2}
          disabled={!canCreate || busy}
          placeholder={t(lang, 'Travail à faire…', 'Work to do…')}
          onChange={(e) => setNewDesc(e.target.value)}
          data-testid="new-task-desc"
        />
        <Select
          className={styles.editInput}
          value={String(newAssignee ?? '')}
          disabled={!canCreate || busy}
          aria-label={t(lang, 'Assigné à', 'Assigned to')}
          data-testid="new-task-assign"
          onChange={(e) => setNewAssignee(e.target.value === '' ? null : Number(e.target.value))}
        >
          {assigneeOptions(null)}
        </Select>
        <input
          type="date"
          className={styles.editInput}
          value={newDay}
          disabled={!canCreate || busy}
          aria-label={t(lang, 'Date prévue', 'Due date')}
          onChange={(e) => setNewDay(e.target.value)}
          data-testid="new-task-due"
        />
        <button
          type="button"
          className={styles.applyBtn}
          disabled={!canCreate || busy || !newDesc.trim()}
          onClick={addTask}
          data-testid="new-task-btn"
        >
          {t(lang, 'Ajouter la tâche', 'Add task')}
        </button>
      </div>
    </div>
  );
}
