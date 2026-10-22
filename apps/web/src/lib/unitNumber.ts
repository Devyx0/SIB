// The unit's own number, without the building in front of it. Unit codes
// carry the building: « 1580-204 Perigord » or « 315-518 Saint-Jean » is
// apartment 204 / 518 of that building, whose address shows right beside it.
// Free-text units (« Espace commun — 530 Claude-Martin ») keep their words
// and lose the address parts: « Espace commun ».

const CODE = /^\s*\d+[A-Za-z]?\s*-\s*([0-9A-Za-z]+)\b/;
// Pieces that only point at the building: an address, « immeuble … », « locataire du … ».
const ADDRESS_PART = /\d|^(immeuble|bâtiment|batiment|locataire|au|du)\b/i;

function withoutAddress(s: string): string {
  const parts = s.split(/\s+[—–-]\s+|[,;()]/).map((p) => p.trim()).filter(Boolean);
  const kept = parts.filter((p) => !ADDRESS_PART.test(p));
  return kept.length ? kept.join(' · ') : parts[0] ?? s;
}

export function unitNumberOf(...candidates: (string | null | undefined)[]): string | null {
  for (const raw of candidates) {
    const s = raw?.trim();
    if (!s) continue;
    const m = s.match(CODE);
    if (m) return m[1];
    // Already just a number (« 204 », « 3B »).
    if (!/\s/.test(s)) return s;
  }
  // Nothing code-shaped: the first value, minus the address in it.
  const first = candidates.map((c) => c?.trim()).find(Boolean);
  return first ? withoutAddress(first) : null;
}
