import { ApiError } from '../../api/client';
import type { Patch } from '../../api/client';
import { t } from '../../i18n';
import type { Lang } from '../../i18n';

type Value = string | number | boolean | null | undefined;

const blank = (v: Value) => (typeof v === 'string' ? v.trim() || null : v ?? null);

/**
 * What an edit sends: only the fields the user changed, and what they saw for
 * those fields (the server refuses with STALE_DATA if it changed since).
 */
export function diff<T extends object>(original: T, draft: T): Patch<T> {
  const before = original as Record<string, Value>;
  const after = draft as Record<string, Value>;
  const changes: Record<string, Value> = {};
  const current: Record<string, Value> = {};
  for (const key of Object.keys(after)) {
    if (blank(after[key]) !== blank(before[key])) {
      changes[key] = blank(after[key]);
      current[key] = blank(before[key]);
    }
  }
  return { changes, current } as Patch<T>;
}

export const isEmptyPatch = (p: Patch<object>) => Object.keys(p.changes).length === 0;

export function errorText(err: unknown, lang: Lang): string {
  if (err instanceof ApiError || (err && typeof err === 'object' && 'code' in err)) {
    const e = err as ApiError;
    if (e.code === 'STALE_DATA') {
      return t(lang, 'Modifié entre-temps par quelqu’un d’autre — rechargez la page.',
                     'Changed by someone else in the meantime — reload the page.');
    }
    if (e.code === 'VALIDATION_FAILED' || e.code === 'HTTP_422') {
      return t(lang, 'Vérifiez les champs : une valeur est invalide ou manquante.',
                     'Check the fields: a value is invalid or missing.');
    }
    if (e.message) return e.message;
  }
  return t(lang, 'L’enregistrement a échoué. Réessayez.', 'Saving failed. Try again.');
}
