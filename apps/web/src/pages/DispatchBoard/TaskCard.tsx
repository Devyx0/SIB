import { useEffect, useId, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ApiError, apiErrorMessage, assignTask, fetchEmployees, scheduleTask, updateTask,
} from '../../api/client';
import type { MeResponse, TaskListItem } from '../../api/schema.d.ts';
import { Avatar } from '../../components/Avatar';
import { useJustify } from '../../components/Justification';
import Select from '../../components/Select';
import { statusLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import { cleanCallTitle } from '../../lib/callTitle';
import { dueAtFromSlot, dueSlot, fmtSlot } from '../../lib/taskDates';
import DueDateTime from '../../components/DueDateTime';
import { joinTask, splitTask } from '../../lib/taskText';
import { unitNumberOf } from '../../lib/unitNumber';
import { urgencyLabel, urgencyOptions } from '../../lib/urgencyLevels';
import { BuildingIcon, CalendarIcon, DocumentIcon, MapPinIcon, UsersIcon } from '../Portfolio/icons';
import styles from './TaskCard.module.css';

// The task card: what the task is, who does it, when and where — with one
// clear way to the service call it came from (« Voir l'appel de service »).

// Assignee / date / name stay editable until the tech leaves (backend _EDITABLE).
const EDITABLE = new Set(['queued', 'scheduled']);

function AlertIcon() {
  return (
    <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor"
         strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 3l7.5 13h-15z" /><path d="M10 8v3.5M10 14h.01" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  );
}

export default function TaskCard({ task, lang, me, onClose, onOpenCall }: {
  task: TaskListItem;
  lang: Lang;
  me?: MeResponse | null;
  onClose: () => void;
  /** Opens the service call (the triage this task came from). */
  onOpenCall: (requestId: number) => void;
}) {
  const qc = useQueryClient();
  const justify = useJustify();
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const isEditor = !!(me?.roles.includes('coordinator') || me?.roles.includes('director'));
  const canEdit = isEditor && task.accepted_at != null && EDITABLE.has(task.status);

  const { data: employees } = useQuery({
    queryKey: ['employees'], queryFn: fetchEmployees, staleTime: 5 * 60 * 1000, enabled: canEdit,
  });

  const saved = splitTask(task.description);
  const savedDay = dueSlot(task.due_at) ?? '';
  const urgency = task.urgency_tier ?? task.request_urgency_tier;
  const [name, setName] = useState(saved.name);
  const [details, setDetails] = useState(saved.details);
  const [assignee, setAssignee] = useState(task.assigned_employee_id != null ? String(task.assigned_employee_id) : '');
  const [day, setDay] = useState(savedDay);
  const [urg, setUrg] = useState(task.urgency_tier ?? '');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // Fresh values after a save (or another task) replace the drafts.
  useEffect(() => {
    const s = splitTask(task.description);
    setName(s.name); setDetails(s.details);
    setAssignee(task.assigned_employee_id != null ? String(task.assigned_employee_id) : '');
    setDay(dueSlot(task.due_at) ?? '');
    setUrg(task.urgency_tier ?? '');
  }, [task.task_id, task.description, task.assigned_employee_id, task.due_at, task.urgency_tier]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const empName = (id: string) =>
    id === '' ? t(lang, 'Non assigné', 'Unassigned')
      : employees?.find((e) => String(e.employee_id) === id)?.nom_employe
        ?? (String(task.assigned_employee_id) === id ? task.assigned_employee_name : null) ?? `#${id}`;
  const NONE = t(lang, 'Aucun', 'None');
  const newText = joinTask(name, details);
  const changes = [
    newText !== joinTask(saved.name, saved.details) && {
      key: 'text', label: t(lang, 'Tâche', 'Task'), before: saved.name || NONE, after: name.trim() || NONE,
    },
    assignee !== (task.assigned_employee_id != null ? String(task.assigned_employee_id) : '') && {
      key: 'assignee', label: t(lang, 'Assigné à', 'Assigned to'),
      before: empName(task.assigned_employee_id != null ? String(task.assigned_employee_id) : ''), after: empName(assignee),
    },
    day !== savedDay && { key: 'day', label: t(lang, 'Date prévue', 'Due date'), before: fmtSlot(savedDay) || NONE, after: fmtSlot(day) || NONE },
    urg !== (task.urgency_tier ?? '') && {
      key: 'urg', label: t(lang, 'Urgence', 'Urgency'),
      before: urgencyLabel(lang, task.urgency_tier), after: urgencyLabel(lang, urg || null),
    },
  ].filter((c): c is { key: string; label: string; before: string; after: string } => !!c);

  async function save() {
    if (!changes.length || busy) return;
    if (!name.trim()) { setMsg({ ok: false, text: t(lang, 'La tâche doit avoir un nom.', 'The task needs a name.') }); return; }
    const j = await justify({
      decision: changes.length === 1 ? changes[0].label : t(lang, `${changes.length} modifications`, `${changes.length} changes`),
      ...(changes.length === 1 ? { before: changes[0].before, after: changes[0].after } : {}),
      changes,
    });
    if (!j) return;
    setBusy(true);
    setMsg(null);
    try {
      const keys = new Set(changes.map((c) => c.key));
      if (keys.has('text') || keys.has('urg')) {
        await updateTask(task.task_id, {
          ...(keys.has('text') ? { description: newText } : {}),
          ...(keys.has('urg') ? { urgency_tier: urg || null } : {}),
          justification: j,
        });
      }
      if (keys.has('assignee')) await assignTask(task.task_id, { assigned_employee_id: assignee ? Number(assignee) : null, justification: j });
      if (keys.has('day')) await scheduleTask(task.task_id, { due_at: day ? dueAtFromSlot(day) : null, justification: j });
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['tasks'] }),
        qc.invalidateQueries({ queryKey: ['request', task.request_id] }),
      ]);
      setMsg({ ok: true, text: t(lang, 'Tâche enregistrée.', 'Task saved.') });
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError ? apiErrorMessage(lang, err) : t(lang, 'Échec de l’enregistrement.', 'Save failed.') });
    } finally {
      setBusy(false);
    }
  }

  const place = [task.building_address, task.unit_label && `${t(lang, 'app.', 'unit')} ${unitNumberOf(task.unit_label)}`]
    .filter(Boolean).join(', ');
  const urgClass = urgency === 'URGENT' ? styles.badgeUrgent : urgency === 'Intermédiaire' ? styles.badgeMedium : styles.badgeLow;

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden />
      <section className={styles.card} role="dialog" aria-modal="true" aria-labelledby={titleId} data-testid="task-card">
        <header className={styles.head}>
          <div className={styles.headMain}>
            <div className={styles.badges}>
              <span className={styles.statusBadge} data-status={task.status}>{statusLabel(lang, task.status)}</span>
              {urgency && <span className={`${styles.badge} ${urgClass}`}><AlertIcon />{urgencyLabel(lang, urgency)}</span>}
              {task.request_asnu && <span className={styles.asnu}>{task.request_asnu}</span>}
            </div>
            <h2 className={styles.title} id={titleId} title={saved.name}>{saved.name || t(lang, 'Tâche sans nom', 'Untitled task')}</h2>
            {saved.details && <p className={styles.desc} title={saved.details} data-testid="task-card-desc">{saved.details}</p>}
          </div>
          <button ref={closeRef} type="button" className={styles.close} onClick={onClose} aria-label={t(lang, 'Fermer', 'Close')}>
            <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        </header>

        <div className={styles.body}>
          <button type="button" className={styles.callBtn} onClick={() => onOpenCall(task.request_id)} data-testid="open-call">
            <span>{t(lang, "Voir l'appel de service", 'View service call')}</span>
            <ArrowIcon />
          </button>

          <dl className={styles.facts}>
            <div className={styles.fact}>
              <span className={styles.factIcon}><UsersIcon /></span>
              <dt>{t(lang, 'Assigné à', 'Assigned to')}</dt>
              <dd>
                {task.assigned_employee_name
                  ? <span className={styles.person}><Avatar name={task.assigned_employee_name} size="xs" />{task.assigned_employee_name}</span>
                  : task.subcontractor_name ?? <span className={styles.muted}>{t(lang, 'Non assigné', 'Unassigned')}</span>}
              </dd>
            </div>
            <div className={styles.fact}>
              <span className={styles.factIcon}><CalendarIcon /></span>
              <dt>{t(lang, 'Date prévue', 'Due date')}</dt>
              <dd>{fmtSlot(savedDay) || <span className={styles.muted}>{t(lang, 'Sans date', 'No date')}</span>}</dd>
            </div>
            <div className={styles.fact}>
              <span className={styles.factIcon}><MapPinIcon /></span>
              <dt>{t(lang, 'Lieu', 'Location')}</dt>
              <dd>{place || '—'}{task.territoire ? <span className={styles.muted}> · {task.territoire}</span> : null}</dd>
            </div>
            <div className={styles.fact}>
              <span className={styles.factIcon}><DocumentIcon size={20} /></span>
              <dt>{t(lang, 'Appel', 'Call')}</dt>
              <dd className={styles.oneLine} title={task.request_title ?? undefined}>{cleanCallTitle(task.request_title) || '—'}</dd>
            </div>
            {task.subcontractor_name && task.assigned_employee_name && (
              <div className={styles.fact}>
                <span className={styles.factIcon}><BuildingIcon /></span>
                <dt>{t(lang, 'Sous-traitant', 'Subcontractor')}</dt>
                <dd>{task.subcontractor_name}</dd>
              </div>
            )}
          </dl>

          {canEdit ? (
            <section className={styles.edit} aria-labelledby={`${titleId}-edit`}>
              <h3 className={styles.editTitle} id={`${titleId}-edit`}>{t(lang, 'Modifier la tâche', 'Edit task')}</h3>
              <label className={styles.field}>
                <span className={styles.label}>{t(lang, 'Nom de la tâche', 'Task name')}</span>
                <input className={styles.input} value={name} maxLength={120} onChange={(e) => setName(e.target.value)}
                       placeholder={t(lang, 'p. ex. Réparer la fuite sous l’évier', 'e.g. Fix the leak under the sink')}
                       data-testid="task-name" />
              </label>
              <label className={styles.field}>
                <span className={styles.label}>{t(lang, 'Description', 'Description')}</span>
                <textarea className={styles.input} rows={3} value={details} onChange={(e) => setDetails(e.target.value)}
                          placeholder={t(lang, 'Détails pour le technicien…', 'Details for the technician…')}
                          data-testid="task-description" />
              </label>
              <div className={styles.row}>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor={`${titleId}-assignee`}>{t(lang, 'Assigné à', 'Assigned to')}</label>
                  <Select id={`${titleId}-assignee`} className={styles.input} value={assignee}
                          onChange={(e) => setAssignee(e.target.value)} searchable avatars
                          searchPlaceholder={t(lang, 'Rechercher un employé…', 'Search employees…')}
                          noResultsText={t(lang, 'Aucun employé trouvé', 'No employee found')} data-testid="task-assignee">
                    <option value="">— {t(lang, 'Non assigné', 'Unassigned')} —</option>
                    {(employees ?? []).filter((e) => e.role === 'technician' || e.role === 'contractor').map((e) => (
                      <option key={e.employee_id} value={e.employee_id}>{e.nom_employe}</option>
                    ))}
                  </Select>
                </div>
                <div className={styles.field}>
                  <span className={styles.label}>{t(lang, 'Date et heure prévues', 'Due date & time')}</span>
                  <DueDateTime lang={lang} inputClassName={styles.input} value={day} onChange={setDay} testId="task-day" />
                </div>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor={`${titleId}-urg`}>{t(lang, 'Urgence', 'Urgency')}</label>
                  <Select id={`${titleId}-urg`} className={styles.input} value={urg} onChange={(e) => setUrg(e.target.value)} data-testid="task-urgency">
                    {urgencyOptions(lang).map((o) => <option key={o.value ?? 'none'} value={o.value ?? ''}>{o.label}</option>)}
                  </Select>
                </div>
              </div>
            </section>
          ) : isEditor && (
            <p className={styles.locked}>
              {t(lang, 'Cette tâche ne se modifie plus (technicien en route ou tâche terminée).',
                'This task can no longer be edited (technician on the way or task done).')}
            </p>
          )}
          {msg && <p className={msg.ok ? styles.ok : styles.error} role={msg.ok ? 'status' : 'alert'}>{msg.text}</p>}
        </div>

        {canEdit && (
          <footer className={styles.foot}>
            <span className={styles.footStatus}>
              {changes.length
                ? t(lang, `${changes.length} modification${changes.length > 1 ? 's' : ''} non enregistrée${changes.length > 1 ? 's' : ''}`,
                  `${changes.length} unsaved change${changes.length > 1 ? 's' : ''}`)
                : t(lang, 'Aucune modification', 'No changes')}
            </span>
            <button type="button" className={styles.saveBtn} disabled={!changes.length || busy} onClick={() => void save()}
                    data-testid="task-save">
              {busy ? t(lang, 'Enregistrement…', 'Saving…') : t(lang, 'Enregistrer', 'Save')}
            </button>
          </footer>
        )}
      </section>
    </>
  );
}
