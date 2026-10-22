// A call's title as one short line about the issue. Calendar titles carry
// codes staff no longer need to read: employee initials (« CHGE »), urgency
// codes (« AJD », « URGENT »), a status tag (« [EN TRAITEMENT] ») and the
// unit / project head before the colon (« 1035-308 Pie XII: »). The place
// already shows on the call, so only the issue stays. Mirrors the backend's
// clean_issue_title (backend/triage/titles.py) for titles saved before it.

const TAG = /^\[[^\]]{1,30}\]\s*/;
const URGENCY = /^(?:AJD|URGENT|URG|INTERM[ÉE]DIAIRE|FAIBLE)\b[\s:–-]*/i;
// Operational words that look like initials but are not people.
const NOT_INITIALS = new Set([
  'ASNU', 'SDB', 'WC', 'AC', 'BBQ', 'LED', 'PVC', 'TAL', 'CVAC', 'NB', 'OK', 'GFCI', 'AMP', 'USB', 'TV', 'HD', 'NIP',
  'DOUBLON',
]);
const INITIALS = /^([A-Z]{2,4})(?:\/[A-Z]{2,4})*\b[\s:–-]+/;
const UNITISH = /\d+-\d+|^\d/;

export function cleanCallTitle(raw: string | null | undefined, projectName?: string | null): string {
  let t = (raw ?? '').trim();
  if (!t) return '';
  // Leading tags and codes, in any order, until none is left.
  for (let guard = 0; guard < 6; guard++) {
    const before = t;
    t = t.replace(TAG, '').replace(URGENCY, '');
    const m = t.match(INITIALS);
    if (m && !NOT_INITIALS.has(m[1])) t = t.slice(m[0].length);
    if (t === before) break;
  }
  // « 1035-308 Pie XII: Fuite » → « Fuite »; also « Projet X — Fuite ».
  const colon = t.match(/^(.+?)\s*:\s*(.+)$/);
  if (colon && (UNITISH.test(colon[1]) || (projectName && colon[1].toLowerCase().includes(projectName.toLowerCase())))) {
    t = colon[2];
  } else if (projectName) {
    const head = new RegExp(`^${projectName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*[:–—-]\\s*`, 'i');
    t = t.replace(head, '');
  }
  t = t.replace(/\s+/g, ' ').trim();
  t = t.charAt(0).toUpperCase() + t.slice(1);
  return t || (raw ?? '').trim();
}
