export type Lang = 'fr' | 'en';

export const t = (lang: Lang, fr: string, en: string): string =>
  lang === 'fr' ? fr : en;

const _ROLE_LABELS: Record<string, readonly [string, string]> = {
  technician:  ['Technicien',    'Technician'],
  contractor:  ['Sous-traitant', 'Subcontractor'],
  coordinator: ['Coordonnateur', 'Coordinator'],
  director:    ['Directeur',     'Director'],
};

export function roleLabel(lang: Lang, role: string): string {
  const pair = _ROLE_LABELS[role];
  return pair ? pair[lang === 'fr' ? 0 : 1] : role;
}

const _TIME_ESTIMATE_LABELS: Record<string, readonly [string, string]> = {
  UNDER_30_MIN:  ['< 30 min',         '< 30 min'],
  MIN30_TO_1H:   ['30 min – 1h',      '30 min – 1h'],
  H1_TO_2H:      ['1h – 2h',          '1h – 2h'],
  H2_TO_4H:      ['2h – 4h',          '2h – 4h'],
  HALF_DAY_PLUS: ['Demi-journée+',    'Half day+'],
  TBD_ON_SITE:   ['Soumission requise', 'Quote required'],
};

export function timeEstimateLabel(lang: Lang, bucket: string | null | undefined): string {
  if (!bucket) return '—';
  const pair = _TIME_ESTIMATE_LABELS[bucket];
  return pair ? pair[lang === 'fr' ? 0 : 1] : bucket;
}

const _SOURCE_CALENDAR_LABELS: Record<string, readonly [string, string]> = {
  main:   ['Calendrier principal', 'Main calendar'],
  st_maj: ['Butler/Majordome',     'Butler/Majordome'],
};

export function sourceCalendarLabel(lang: Lang, calendar: string | null | undefined): string {
  if (!calendar) return '—';
  const pair = _SOURCE_CALENDAR_LABELS[calendar];
  return pair ? pair[lang === 'fr' ? 0 : 1] : calendar;
}

export function statusLabel(lang: Lang, status: string): string {
  const map: Record<string, readonly [string, string]> = {
    intake_received:  ['Reçu',           'Received'],
    triage_pending:   ['En triage',      'Pending triage'],
    triaged:          ['Trié',           'Triaged'],
    triage_clarify:   ['Clarification',  'Clarification'],
    triage_proposal:  ['Proposition',    'Proposal'],
    triage_failed:    ['Triage échoué',  'Triage failed'],
    en_route:         ['En route',       'En route'],
    closed:           ['Fermé',          'Closed'],
  };
  const pair = map[status];
  return pair ? pair[lang === 'fr' ? 0 : 1] : status;
}
