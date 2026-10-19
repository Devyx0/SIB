// Elapsed time since en route, for the pinned banner and call view.
export function elapsedLabel(enRouteAt: string | null): string | null {
  if (!enRouteAt) return null;
  const mins = Math.max(0, Math.floor((Date.now() - new Date(enRouteAt).getTime()) / 60000));
  if (mins < 60) return `${mins} min`;
  return `${Math.floor(mins / 60)} h ${String(mins % 60).padStart(2, '0')}`;
}
