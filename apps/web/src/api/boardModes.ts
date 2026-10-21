/** Coordinator board split: Triage (decide) vs Tasks (do). */

export type BoardMode = 'triage' | 'tasks';

/** New / undecided — not yet on a tech’s plan. */
export const TRIAGE_STATUSES = [
  'intake_received',
  'triage_failed',
  'triage_clarify',
  'triaged',
] as const;

/** Already dispatched (or escalated for re-dispatch). */
export const TASKS_STATUSES = [
  'scheduled',
  'en_route',
  'arrived',
  'awaiting_redispatch',
] as const;

export function statusesForMode(mode: BoardMode): string[] {
  return mode === 'triage' ? [...TRIAGE_STATUSES] : [...TASKS_STATUSES];
}

export function clampStatusesToMode(mode: BoardMode, selected: string[]): string[] {
  const allowed = new Set(statusesForMode(mode));
  const next = selected.filter((s) => allowed.has(s));
  return next;
}
