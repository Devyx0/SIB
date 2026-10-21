/** Task due dates: the UI works in local days (America/Toronto), the API in due_at timestamps. */

export function dueDay(dueAt: string | null | undefined): string | null {
  if (!dueAt) return null;
  return new Date(dueAt).toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
}

/** Naive local timestamp — the API reads it in the platform timezone. */
export function dueAtFromDay(day: string): string {
  return `${day}T08:00:00`;
}
