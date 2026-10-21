/** Urgency dropdown — Générale!E (Niveau d'urgence): URGENT / Intermédiaire / Faible. */
export const URGENCY_LEVELS = ['URGENT', 'Intermédiaire', 'Faible'] as const;

export type UrgencyLevel = (typeof URGENCY_LEVELS)[number];

const URGENCY_EN: Record<UrgencyLevel, string> = {
  URGENT: 'Urgent',
  Intermédiaire: 'Medium',
  Faible: 'Low',
};

export function urgencyLabel(lang: 'fr' | 'en', value: string | null | undefined): string {
  if (!value || value === 'none') return lang === 'fr' ? 'Aucune' : 'None';
  if (lang === 'fr') {
    if (value === 'URGENT') return 'Urgent';
    if (value === 'Intermédiaire') return 'Intermédiaire';
    if (value === 'Faible') return 'Faible';
    // legacy
    if (value === 'AJD') return 'Urgent';
    if (value === 'ajd') return 'Intermédiaire';
    return value;
  }
  if (value in URGENCY_EN) return URGENCY_EN[value as UrgencyLevel];
  if (value === 'AJD') return 'Urgent';
  if (value === 'ajd') return 'Medium';
  return value;
}

export function urgencyOptions(lang: 'fr' | 'en'): { value: UrgencyLevel | null; label: string }[] {
  return [
    ...URGENCY_LEVELS.map((value) => ({ value, label: urgencyLabel(lang, value) })),
    { value: null, label: urgencyLabel(lang, null) },
  ];
}
