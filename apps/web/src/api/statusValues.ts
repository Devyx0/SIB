// Generated from openapi.json — do not edit manually (run npm run gen-schema).
export const STATUS_VALUES = [
  'intake_received',
  'triage_pending',
  'triaged',
  'scheduled',
  'awaiting_redispatch',
  'triage_clarify',
  'triage_proposal',
  'triage_failed',
  'en_route',
  'arrived',
  'closed',
] as const;

export type StatusValue = (typeof STATUS_VALUES)[number];

/** Coordinator-facing statuses — triage_pending is an in-flight lock, aliased to Received. */
export const FILTER_STATUS_VALUES = STATUS_VALUES.filter((s) => s !== 'triage_pending');

/** When filtering by Received, include the transient triage_pending lock. */
export function expandStatusFilter(statuses: string[]): string[] {
  if (!statuses.includes('intake_received') || statuses.includes('triage_pending')) {
    return statuses;
  }
  return [...statuses, 'triage_pending'];
}

export const STATUS_LABELS: Record<StatusValue, string> = {
  intake_received: 'Reçu',
  triage_pending: 'Reçu',
  triaged: 'Trié',
  scheduled: 'Planifié',
  awaiting_redispatch: 'À redispatcher',
  triage_clarify: 'Clarification',
  triage_proposal: 'Proposition',
  triage_failed: 'Triage échoué',
  en_route: 'En route',
  arrived: 'Arrivé',
  closed: 'Fermé',
};
