// Phone numbers read the same everywhere: « 819 329-3727 ». A leading
// country code (+1 / 1) is dropped; anything that isn't a 10-digit North
// American number (extensions, foreign numbers) is shown as typed.

export function formatPhone(raw: string | null | undefined): string {
  const s = (raw ?? '').trim();
  if (!s) return '';
  let d = s.replace(/\D/g, '');
  if (d.length === 11 && d.startsWith('1')) d = d.slice(1);
  if (d.length !== 10) return s;
  return `${d.slice(0, 3)} ${d.slice(3, 6)}-${d.slice(6)}`;
}

/** tel: link target — digits only, so every phone app can dial it. */
export function telHref(raw: string | null | undefined): string {
  const d = (raw ?? '').replace(/[^\d+]/g, '');
  return `tel:${d}`;
}
