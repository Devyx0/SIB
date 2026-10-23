/**
 * Call statuses that cannot accept a new task (POST /tasks).
 * Shared by the board picker and call-detail « New task » CTA.
 */
export const NO_NEW_TASK = new Set([
  'intake_received', 'triage_pending', 'triage_clarify', 'triage_failed', 'closed',
]);
