import type { Lang } from '../../i18n';

const locale = (lang: Lang) => (lang === 'fr' ? 'fr-CA' : 'en-CA');

/** 'YYYY-MM-DD' as a calendar date — parsed locally so it never shifts a day. */
export function parseDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function fmtDate(iso: string | null | undefined, lang: Lang): string | null {
  if (!iso) return null;
  return parseDate(iso).toLocaleDateString(locale(lang), { year: 'numeric', month: 'long', day: 'numeric' });
}

export function fmtTime(hms: string | null | undefined): string | null {
  return hms ? hms.slice(0, 5) : null;
}

export function fmtMoney(amount: string | number | null | undefined, lang: Lang): string | null {
  if (amount === null || amount === undefined || amount === '') return null;
  return Number(amount).toLocaleString(locale(lang), { style: 'currency', currency: 'CAD' });
}

/** Case- and accent-insensitive search key. */
export function norm(s: string | null | undefined): string {
  return (s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

export function matches(q: string, ...fields: (string | null | undefined)[]): boolean {
  const needle = norm(q.trim());
  return needle === '' || fields.some((f) => norm(f).includes(needle));
}

export function plural(n: number, lang: Lang, fr: [string, string], en: [string, string]): string {
  const [one, many] = lang === 'fr' ? fr : en;
  return `${n.toLocaleString(locale(lang))} ${n === 1 ? one : many}`;
}
