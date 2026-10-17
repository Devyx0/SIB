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
