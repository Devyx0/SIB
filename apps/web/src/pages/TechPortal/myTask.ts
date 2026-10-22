import type { RequestDetail, TaskOut } from '../../api/schema.d.ts';

/** Task statuses that are still the technician's own work (not ended attempts). */
export const MY_OPEN_TASK_STATUSES = ['queued', 'scheduled', 'en_route', 'arrived', 'working'] as const;
export const IN_PROGRESS_TASK_STATUSES = ['en_route', 'arrived', 'working'] as const;

const isOpen = (s: string) => (MY_OPEN_TASK_STATUSES as readonly string[]).includes(s);
const isInProgress = (s: string) => (IN_PROGRESS_TASK_STATUSES as readonly string[]).includes(s);

/**
 * The task the tech portal acts on for this call: the one in the URL if it is
 * mine, else my in-progress task, else my next open one.
 */
export function pickMyTask(
  req: RequestDetail | undefined,
  employeeId: number | undefined,
  taskId: number | null,
): TaskOut | null {
  if (!req || employeeId == null) return null;
  const mine = (req.tasks ?? []).filter(
    (t) => t.accepted_at != null && t.assigned_employee_id === employeeId,
  );
  return (
    (taskId != null ? mine.find((t) => t.task_id === taskId) : undefined)
    ?? mine.find((t) => isInProgress(t.status))
    ?? mine.find((t) => isOpen(t.status))
    ?? null
  );
}

export function taskIdParam(search: URLSearchParams): number | null {
  const v = Number(search.get('task'));
  return Number.isInteger(v) && v > 0 ? v : null;
}
