/** Coordinator board split: Triage (decide, Service Calls) vs Tasks (do, dispatch_task). */
import { ACTIVE_TASK_STATUSES, TASK_STATUS_VALUES } from './statusValues';

export type BoardMode = 'triage' | 'tasks';

/** Service Calls not yet turned into work. `open` calls live on /tasks via their tasks. */
export const TRIAGE_STATUSES = [
  'intake_received',
  'triage_failed',
  'triage_clarify',
  'triage_proposal',
  'triaged',
] as const;

/** Task statuses offered on /tasks. */
export const TASKS_STATUSES = TASK_STATUS_VALUES;

export function statusesForMode(mode: BoardMode): string[] {
  return mode === 'triage' ? [...TRIAGE_STATUSES] : [...TASKS_STATUSES];
}

/** What the board lists when no status is picked. */
export function defaultStatusesForMode(mode: BoardMode): string[] {
  return mode === 'triage' ? [...TRIAGE_STATUSES] : [...ACTIVE_TASK_STATUSES];
}

export function clampStatusesToMode(mode: BoardMode, selected: string[]): string[] {
  const allowed = new Set(statusesForMode(mode));
  const next = selected.filter((s) => allowed.has(s));
  return next;
}
