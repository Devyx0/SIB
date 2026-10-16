import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRequest } from '../../hooks/useRequest';
import {
  ApiError, fetchEmployees,
  dispatchAssign, dispatchReschedule, dispatchSetUrgency,
  dispatchSetFollowUpDate, dispatchSetNextSteps, dispatchSetCost, dispatchAddLog,
} from '../../api/client';
import type { MeResponse } from '../../api/schema.d.ts';
import { statusLabel, t } from '../../i18n';
import type { Lang } from '../../i18n';
import JustificationModal from '../../components/JustificationModal';
import styles from './DetailPanel.module.css';

const ROLE_LABELS: Record<string, { fr: string; en: string }> = {
  technician:  { fr: 'Technicien',    en: 'Technician' },
  contractor:  { fr: 'Sous-traitant', en: 'Subcontractor' },
  coordinator: { fr: 'Coordonnateur', en: 'Coordinator' },
  director:    { fr: 'Directeur',     en: 'Director' },
};

const DECISION_LABELS: Record<string, { fr: string; en: string }> = {
  assign:     { fr: 'Assignation',     en: 'Assignment' },
  reschedule: { fr: 'Reprogrammation', en: 'Reschedule' },
  urgency:    { fr: 'Urgence',         en: 'Urgency' },
};

const INPUT_LABELS: Record<string, { fr: string; en: string }> = {
  typed: { fr: 'Écrit',  en: 'Written' },
  voice: { fr: 'Dicté', en: 'Dictated' },
};

function roleLabel(lang: Lang, role: string): string {
  return ROLE_LABELS[role]?.[lang] ?? role;
}

function decisionLabel(lang: Lang, type: string): string {
  return DECISION_LABELS[type]?.[lang] ?? type;
}

function inputLabel(lang: Lang, method: string | null | undefined): string {
  if (!method) return '';
  return INPUT_LABELS[method]?.[lang] ?? method;
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

type PendingAction =
  | { type: 'assign'; employeeId: number | null }
  | { type: 'reschedule'; date: string }
  | { type: 'urgency'; tier: string | null };

const URGENCY_OPTIONS: Array<{ value: string | null }> = [
  { value: 'AJD' },
  { value: 'ajd' },
  { value: null },
];

export default function DetailPanel({ requestId, onClose, lang = 'fr', me }: Props) {
  const { data, isPending, isError, error } = useRequest(requestId);
  const qc = useQueryClient();
  const isEditor = !!(me?.roles.includes('coordinator') || me?.roles.includes('director'));
  const isClosed = data?.status === 'closed';

  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: fetchEmployees,
    staleTime: 5 * 60 * 1000,
    enabled: isEditor,
  });

  const assignableEmployees = (employees ?? []).filter(
    (e) => e.role === 'technician' || e.role === 'contractor'
  );

  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [staleMsg, setStaleMsg] = useState<string | null>(null);
  const [followUpDate, setFollowUpDate] = useState<string | null>(null);
  const [nextSteps, setNextSteps] = useState<string | null>(null);
  const [cost, setCost] = useState<string | null>(null);
  const [logText, setLogText] = useState('');
  const [rescheduleDate, setRescheduleDate] = useState<string | null>(null);
  const [assignEmpId, setAssignEmpId] = useState<number | null>(null);

  // Sync controlled select with server data when data first loads or request changes
  useEffect(() => {
    if (data) setAssignEmpId(data.assigned_employee_id ?? null);
  }, [data?.request_id, data?.assigned_employee_id]);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        if (pendingAction) { setPendingAction(null); return; }
        onClose();
      }
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose, pendingAction]);

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
        qc.invalidateQueries({ queryKey: ['request', requestId] });
      }
    }
  }

  function handleJustificationSave(text: string, inputMethod: 'voice' | 'typed') {
    if (!pendingAction || !data) return;
    const justification = { text, input_method: inputMethod };
    setPendingAction(null);
    if (pendingAction.type === 'assign') {
      applyAndRefresh(() => dispatchAssign(requestId, {
        employee_id: pendingAction.employeeId,
        current_assigned_employee_id: data.assigned_employee_id,
        current_start_date: data.start_date,
        current_urgency_tier: data.urgency_tier,
        justification,
      }));
    } else if (pendingAction.type === 'reschedule') {
      applyAndRefresh(() => dispatchReschedule(requestId, {
        start_date: pendingAction.date,
        current_start_date: data.start_date,
        current_assigned_employee_id: data.assigned_employee_id,
        current_urgency_tier: data.urgency_tier,
        justification,
      }));
    } else if (pendingAction.type === 'urgency') {
      applyAndRefresh(() => dispatchSetUrgency(requestId, {
        urgency_tier: pendingAction.tier as 'AJD' | 'ajd' | null,
        current_urgency_tier: data.urgency_tier,
        current_assigned_employee_id: data.assigned_employee_id,
        current_start_date: data.start_date,
        justification,
      }));
    }
  }

  function handleCancelJustification() {
    setPendingAction(null);
    setRescheduleDate(null);
    if (data) setAssignEmpId(data.assigned_employee_id ?? null);
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
                <dd>{data.time_estimate_bucket ?? '—'}</dd>

                <dt>{t(lang, 'Coût estimé', 'Est. cost')}</dt>
                <dd>{data.estimated_cost != null ? formatCost(data.estimated_cost, lang) : '—'}</dd>

                <dt>Source</dt>
                <dd>{data.source_calendar ?? '—'}</dd>
              </dl>

              {data.followup_log.length > 0 && (
                <section className={styles.followupSection}>
                  <h3 className={styles.followupHeading}>
                    {t(lang, 'Journal de suivi', 'Follow-up log')}
                  </h3>
                  {data.followup_log.map((entry) => (
                    <div key={entry.followup_id} className={styles.followupEntry}>
                      <span className={styles.followupMeta}>
                        {formatDate(entry.entry_date, lang)}
                        {entry.entered_by_initials ? ` · ${entry.entered_by_initials}` : ''}
                      </span>
                      <p className={styles.followupText}>{entry.entry_text ?? '—'}</p>
                    </div>
                  ))}
                </section>
              )}

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

                  {/* Assign */}
                  <div className={styles.editField}>
                    <label className={styles.editLabel}>{t(lang, 'Assigné à', 'Assigned to')}</label>
                    <select
                      className={styles.editInput}
                      value={String(assignEmpId ?? '')}
                      disabled={isClosed}
                      onChange={(e) => {
                        const empId = e.target.value === '' ? null : Number(e.target.value);
                        setAssignEmpId(empId);
                        setPendingAction({ type: 'assign', employeeId: empId });
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
                        if (d) setPendingAction({ type: 'reschedule', date: d });
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
                          onClick={() => setPendingAction({ type: 'urgency', tier: value })}
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

              {data.justification_log.length > 0 && (
                <section className={styles.justifSection}>
                  <h3 className={styles.followupHeading}>
                    {t(lang, 'Historique des décisions', 'Decision history')}
                  </h3>
                  {data.justification_log.map((entry) => (
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
              )}
            </>
          )}
        </div>
      </aside>

      <JustificationModal
        open={pendingAction !== null}
        onSave={handleJustificationSave}
        onCancel={handleCancelJustification}
        lang={lang}
      />
    </>
  );
}
