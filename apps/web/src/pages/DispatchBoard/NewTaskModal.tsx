/**
 * Top-level « Nouvelle tâche »: pick an existing call, then create a task on it
 * (POST /tasks with request_id). Replaces the board New Call CTA for coord/dir.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  apiErrorMessage, createTask, fetchEmployees, fetchRequests,
} from '../../api/client';
import type { ListRow } from '../../api/schema.d.ts';
import { STATUS_VALUES } from '../../api/statusValues';
import Select from '../../components/Select';
import { useJustify } from '../../components/Justification';
import { roleLabel, statusLabel, t, type Lang } from '../../i18n';
import { dueAtFromDay } from '../../lib/taskDates';
import { NO_NEW_TASK } from './TaskEditor';
import styles from './NouvelAppelModal.module.css';

const ELIGIBLE_STATUSES = STATUS_VALUES.filter((s) => !NO_NEW_TASK.has(s));
const CALL_PAGE_SIZE = 100;

interface Props {
  open: boolean;
  onClose: () => void;
  lang?: Lang;
  /** After create: parent opens that call's detail. */
  onCreated?: (requestId: number) => void;
}

function callLabel(row: ListRow, lang: Lang): string {
  const asnu = row.asnu ?? `#${row.request_id}`;
  const title = row.raw_title?.trim() || t(lang, 'Sans titre', 'Untitled');
  const where = [row.building_address, row.unit_label].filter(Boolean).join(' · ');
  const status = statusLabel(lang, row.status);
  return where ? `${asnu} — ${title} (${where}) · ${status}` : `${asnu} — ${title} · ${status}`;
}

function callHaystack(row: ListRow): string {
  return [
    row.asnu, row.raw_title, row.building_address, row.building_full_address,
    row.unit_label, row.unique_unit_number, row.territoire, String(row.request_id),
  ].filter(Boolean).join(' ').toLowerCase();
}

export default function NewTaskModal({ open, onClose, lang = 'fr', onCreated }: Props) {
  const qc = useQueryClient();
  const justify = useJustify();
  const wrapRef = useRef<HTMLDivElement>(null);

  const [callQuery, setCallQuery] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [callOpen, setCallOpen] = useState(false);
  const [selected, setSelected] = useState<ListRow | null>(null);
  const [description, setDescription] = useState('');
  const [assignee, setAssignee] = useState<number | null>(null);
  const [day, setDay] = useState('');
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setCallQuery('');
    setDebouncedQ('');
    setCallOpen(false);
    setSelected(null);
    setDescription('');
    setAssignee(null);
    setDay('');
    setBusy(false);
    setErrorMsg(null);
  }, [open]);

  useEffect(() => {
    if (callQuery === debouncedQ) return;
    const id = setTimeout(() => setDebouncedQ(callQuery.trim()), 250);
    return () => clearTimeout(id);
  }, [callQuery, debouncedQ]);

  useEffect(() => {
    if (!callOpen) return;
    function onDoc(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setCallOpen(false);
      }
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [callOpen]);

  const { data: employees = [] } = useQuery({
    queryKey: ['employees'],
    queryFn: fetchEmployees,
    enabled: open,
  });

  // Load eligible calls; optional server filter when typing.
  const { data: callsPage, isFetching: callsLoading } = useQuery({
    queryKey: ['requests', 'new-task-picker', { q: debouncedQ, status: ELIGIBLE_STATUSES }],
    queryFn: () => fetchRequests({
      status: [...ELIGIBLE_STATUSES],
      q: debouncedQ || undefined,
      limit: CALL_PAGE_SIZE,
      offset: 0,
      sort_by: 'start_date',
      sort_dir: 'desc',
    }),
    enabled: open,
  });

  const calls = useMemo(() => {
    const items = (callsPage?.items ?? []).filter((r) => !NO_NEW_TASK.has(r.status));
    const needle = callQuery.trim().toLowerCase();
    if (!needle) return items;
    // Extra client filter so the open list responds while debounce catches up.
    return items.filter((r) => callHaystack(r).includes(needle));
  }, [callsPage, callQuery]);

  const assignable = employees.filter((e) => e.role === 'technician' || e.role === 'contractor');
  const UNASSIGNED = t(lang, 'Non assigné', 'Unassigned');
  const NONE = t(lang, 'Aucune', 'None');
  const nameOf = (id: number | null) =>
    id == null ? UNASSIGNED : employees.find((e) => e.employee_id === id)?.nom_employe ?? `#${id}`;

  const inputValue = callOpen
    ? callQuery
    : (selected ? callLabel(selected, lang) : callQuery);

  function pickCall(row: ListRow) {
    setSelected(row);
    setCallQuery('');
    setDebouncedQ('');
    setCallOpen(false);
  }

  function clearCall() {
    setSelected(null);
    setCallQuery('');
    setDebouncedQ('');
    setCallOpen(true);
  }

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const desc = description.trim();
    const requestId = selected?.request_id;
    if (!requestId || !desc || busy) return;
    setErrorMsg(null);
    const j = await justify({
      decision: t(lang, 'Nouvelle tâche', 'New task'),
      changes: [
        {
          label: t(lang, 'Appel', 'Call'),
          before: NONE,
          after: callLabel(selected, lang),
        },
        { label: t(lang, 'Tâche', 'Task'), before: NONE, after: desc },
        { label: t(lang, 'Assignation', 'Assignment'), before: NONE, after: nameOf(assignee) },
        { label: t(lang, 'Date prévue', 'Due date'), before: NONE, after: day || NONE },
      ],
    });
    if (!j) return;
    setBusy(true);
    try {
      await createTask({
        request_id: requestId,
        description: desc,
        assigned_employee_id: assignee,
        due_at: day ? dueAtFromDay(day) : null,
        justification: j,
      });
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['tasks'] }),
        qc.invalidateQueries({ queryKey: ['requests'] }),
        qc.invalidateQueries({ queryKey: ['request', requestId] }),
      ]);
      onCreated?.(requestId);
      onClose();
    } catch (err) {
      setErrorMsg(apiErrorMessage(lang, err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label={t(lang, 'Nouvelle tâche', 'New task')}
      data-testid="nouvelle-tache-modal"
    >
      <div className={styles.modal} style={{ maxWidth: 560 }}>
        <div className={styles.headRow}>
          <div>
            <h2 className={styles.heading}>{t(lang, 'Nouvelle tâche', 'New task')}</h2>
            <p className={styles.subheading}>
              {t(lang, 'Choisissez un appel existant, puis décrivez le travail.',
                      'Pick an existing call, then describe the work.')}
            </p>
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label={t(lang, 'Fermer', 'Close')}
            data-testid="nouvelle-tache-close"
          >
            <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        </div>

        <form className={styles.modalForm} onSubmit={handleSubmit} noValidate>
          <div className={styles.formBody} style={{ padding: '16px 24px' }}>
            <div className={styles.field} style={{ marginBottom: 14 }}>
              <span className={styles.optionTitle} id="nouvelle-tache-call-label">
                {t(lang, 'Appel de service *', 'Service call *')}
              </span>
              <div className={styles.suggestWrap} ref={wrapRef}>
                <input
                  type="text"
                  className={styles.input}
                  role="combobox"
                  aria-expanded={callOpen}
                  aria-controls="nouvelle-tache-suggestions"
                  aria-autocomplete="list"
                  aria-labelledby="nouvelle-tache-call-label"
                  value={inputValue}
                  disabled={busy}
                  placeholder={t(lang, 'Rechercher ou choisir un appel…', 'Search or pick a call…')}
                  onChange={(e) => {
                    setCallQuery(e.target.value);
                    setSelected(null);
                    setCallOpen(true);
                  }}
                  onFocus={() => {
                    setCallOpen(true);
                    if (selected) setCallQuery('');
                  }}
                  data-testid="nouvelle-tache-call"
                  autoComplete="off"
                />
                {selected && !callOpen && (
                  <button
                    type="button"
                    className={styles.cancelBtn}
                    style={{
                      position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)',
                      minHeight: 28, padding: '2px 8px', fontSize: 12,
                    }}
                    onClick={clearCall}
                    data-testid="nouvelle-tache-call-clear"
                    aria-label={t(lang, 'Effacer', 'Clear')}
                  >
                    ×
                  </button>
                )}
                {callOpen && (
                  <ul
                    id="nouvelle-tache-suggestions"
                    className={styles.suggestList}
                    role="listbox"
                    data-testid="nouvelle-tache-suggestions"
                  >
                    {callsLoading && calls.length === 0 && (
                      <li className={styles.suggestMeta} style={{ padding: '8px 10px' }}>
                        {t(lang, 'Chargement…', 'Loading…')}
                      </li>
                    )}
                    {!callsLoading && calls.length === 0 && (
                      <li className={styles.suggestMeta} style={{ padding: '8px 10px' }}>
                        {t(lang, 'Aucun appel éligible.', 'No eligible calls.')}
                      </li>
                    )}
                    {calls.map((r) => (
                      <li key={r.request_id} role="option" aria-selected={selected?.request_id === r.request_id}>
                        <button
                          type="button"
                          className={`${styles.suggestItem}${selected?.request_id === r.request_id ? ` ${styles.suggestItemActive}` : ''}`}
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => pickCall(r)}
                          data-testid={`nouvelle-tache-call-option-${r.request_id}`}
                        >
                          <strong>{r.asnu ?? `#${r.request_id}`}</strong>
                          {' — '}
                          {r.raw_title?.trim() || t(lang, 'Sans titre', 'Untitled')}
                          <span className={styles.suggestMeta}>
                            {[r.building_address, r.unit_label, statusLabel(lang, r.status)]
                              .filter(Boolean).join(' · ')}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <label className={styles.field} style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
              <span className={styles.optionTitle}>{t(lang, 'Travail à faire *', 'Work to do *')}</span>
              <textarea
                className={styles.textarea}
                rows={3}
                value={description}
                disabled={busy}
                placeholder={t(lang, 'Décrire la tâche…', 'Describe the task…')}
                onChange={(e) => setDescription(e.target.value)}
                data-testid="nouvelle-tache-desc"
                required
              />
            </label>

            <label className={styles.field} style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
              <span className={styles.optionTitle}>{t(lang, 'Assignation', 'Assignment')}</span>
              <Select
                className={styles.input}
                value={String(assignee ?? '')}
                disabled={busy}
                onChange={(e) => setAssignee(e.target.value === '' ? null : Number(e.target.value))}
                data-testid="nouvelle-tache-assign"
              >
                <option value="">— {UNASSIGNED} —</option>
                {assignable.map((e) => (
                  <option
                    key={e.employee_id}
                    value={e.employee_id}
                    disabled={e.is_en_route && e.employee_id !== assignee}
                  >
                    {e.nom_employe} ({roleLabel(lang, e.role)})
                    {e.is_en_route ? ` — ${t(lang, 'en route', 'en route')}` : ''}
                  </option>
                ))}
              </Select>
            </label>

            <label className={styles.field} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span className={styles.optionTitle}>{t(lang, 'Date prévue', 'Due date')}</span>
              <input
                type="date"
                className={styles.input}
                value={day}
                disabled={busy}
                onChange={(e) => setDay(e.target.value)}
                data-testid="nouvelle-tache-due"
              />
            </label>
          </div>

          <div className={styles.footer}>
            {errorMsg && <p className={styles.errorMsg} data-testid="nouvelle-tache-error">{errorMsg}</p>}
            <div className={styles.footerRow}>
              <div />
              <div className={styles.actions}>
                <button type="button" className={styles.cancelBtn} onClick={onClose} disabled={busy}>
                  {t(lang, 'Annuler', 'Cancel')}
                </button>
                <button
                  type="submit"
                  className={styles.submitBtn}
                  disabled={busy || !selected || !description.trim()}
                  data-testid="nouvelle-tache-submit"
                >
                  {busy
                    ? t(lang, 'Création…', 'Creating…')
                    : t(lang, 'Créer la tâche', 'Create task')}
                </button>
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
