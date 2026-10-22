/** Urgency dropdown — stored values (Générale!E): URGENT / Intermédiaire / Faible.
 *  Shown on the staff scale: Urgent (high) · Normal (medium) · Non urgent (routine).
 *  « Urgence majeure » (level 1) needs a 4th stored value; not added yet. */
export const URGENCY_LEVELS = ['URGENT', 'Intermédiaire', 'Faible'] as const;

export type UrgencyLevel = (typeof URGENCY_LEVELS)[number];

const URGENCY_FR: Record<UrgencyLevel, string> = {
  URGENT: 'Urgent',
  Intermédiaire: 'Normal',
  Faible: 'Non urgent',
};

const URGENCY_EN: Record<UrgencyLevel, string> = {
  URGENT: 'High urgency',
  Intermédiaire: 'Medium urgency',
  Faible: 'Routine',
};

export function urgencyLabel(lang: 'fr' | 'en', value: string | null | undefined): string {
  if (!value || value === 'none') return lang === 'fr' ? 'Aucune' : 'None';
  const labels = lang === 'fr' ? URGENCY_FR : URGENCY_EN;
  if (value in labels) return labels[value as UrgencyLevel];
  // legacy codes
  if (value === 'AJD') return labels.URGENT;
  if (value === 'ajd') return labels['Intermédiaire'];
  return value;
}

export function urgencyOptions(lang: 'fr' | 'en'): { value: UrgencyLevel | null; label: string }[] {
  return [
    ...URGENCY_LEVELS.map((value) => ({ value, label: urgencyLabel(lang, value) })),
    { value: null, label: urgencyLabel(lang, null) },
  ];
}
