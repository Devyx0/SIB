/** Task due dates: the UI works in local days (America/Toronto), the API in due_at timestamps. */

export function dueDay(dueAt: string | null | undefined): string | null {
  if (!dueAt) return null;
  return new Date(dueAt).toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
}

/** Naive local timestamp — the API reads it in the platform timezone. */
export function dueAtFromDay(day: string): string {
  return `${day}T08:00:00`;
}

/** « YYYY-MM-DDTHH:MM » in the platform timezone — a due date with its time. */
export function dueSlot(dueAt: string | null | undefined): string | null {
  if (!dueAt) return null;
  const d = new Date(dueAt);
  if (Number.isNaN(d.getTime())) return null;
  const day = d.toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
  const time = d.toLocaleTimeString('en-GB', { timeZone: 'America/Toronto', hour: '2-digit', minute: '2-digit', hour12: false });
  return `${day}T${time}`;
}

/** A day alone is scheduled at 08:00, as before the time picker existed. */
export function dueAtFromSlot(slot: string): string {
  return slot.length === 10 ? `${slot}T08:00:00` : `${slot.slice(0, 16)}:00`;
}

/** « 2026-10-25 08:30 » for justification rows and read-only views. */
export function fmtSlot(slot: string | null | undefined): string {
  return slot ? slot.replace('T', ' ') : '';
}
