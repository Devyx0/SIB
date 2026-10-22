/** Élément dropdown — atomic values from Générale!F (Catégories). Stored in French. */
export const TAXONOMY_ELEMENTS = [
  'Affichage',
  'Arbres',
  'Ascenseur',
  'Asphalte',
  'Avis RBQ',
  'Balcons/Terrasses',
  'Béton',
  'Chaudières de chauffage',
  'Chauffage',
  'Chauffe-eau - GAZ',
  'Clôture',
  'Conteneur',
  'Crépi',
  'Détecteur CO2',
  'Drains',
  'Éclairage',
  'Électricité',
  'Égouts',
  'Escalier',
  'Espace commun',
  'Extermination',
  'Extérieur',
  'Façia',
  'Fournaise',
  'Génératrice',
  'Gicleurs',
  'Gouttières',
  'Incendie',
  "Infiltration d'eau",
  'Intercom',
  'Lignage',
  'Maçonnerie',
  'Majeure',
  'Muret de soutènement',
  'Pancarte',
  'Peinture',
  'Piscine',
  'Rangement',
  'Sécurité',
  'Stationnement',
  'Thermopompe',
  'Toitures',
  'Ventilation',
] as const;

export type TaxonomyElement = (typeof TAXONOMY_ELEMENTS)[number];

const ELEMENT_EN: Record<TaxonomyElement, string> = {
  Affichage: 'Signage',
  Arbres: 'Trees',
  Ascenseur: 'Elevator',
  Asphalte: 'Asphalt',
  'Avis RBQ': 'RBQ notice',
  'Balcons/Terrasses': 'Balconies/Terraces',
  Béton: 'Concrete',
  'Chaudières de chauffage': 'Heating boilers',
  Chauffage: 'Heating',
  'Chauffe-eau - GAZ': 'Water heater — GAS',
  Clôture: 'Fence',
  Conteneur: 'Container',
  Crépi: 'Stucco',
  'Détecteur CO2': 'CO2 detector',
  Drains: 'Drains',
  Éclairage: 'Lighting',
  Électricité: 'Electrical',
  Égouts: 'Sewers',
  Escalier: 'Stairway',
  'Espace commun': 'Common area',
  Extermination: 'Pest control',
  Extérieur: 'Exterior',
  Façia: 'Fascia',
  Fournaise: 'Furnace',
  Génératrice: 'Generator',
  Gicleurs: 'Sprinklers',
  Gouttières: 'Gutters',
  Incendie: 'Fire',
  "Infiltration d'eau": 'Water infiltration',
  Intercom: 'Intercom',
  Lignage: 'Line marking',
  Maçonnerie: 'Masonry',
  Majeure: 'Major works',
  'Muret de soutènement': 'Retaining wall',
  Pancarte: 'Sign',
  Peinture: 'Paint',
  Piscine: 'Pool',
  Rangement: 'Storage',
  Sécurité: 'Security',
  Stationnement: 'Parking',
  Thermopompe: 'Heat pump',
  Toitures: 'Roofing',
  Ventilation: 'Ventilation',
};

export function taxonomyElementLabel(lang: 'fr' | 'en', value: string): string {
  if (lang === 'fr') return value;
  return ELEMENT_EN[value as TaxonomyElement] ?? value;
}

/** Options sorted for the active language (value stays French). */
export function taxonomyElementOptions(lang: 'fr' | 'en'): { value: string; label: string }[] {
  const opts = TAXONOMY_ELEMENTS.map((value) => ({
    value,
    label: taxonomyElementLabel(lang, value),
  }));
  const loc = lang === 'fr' ? 'fr' : 'en';
  return opts.sort((a, b) => a.label.localeCompare(b.label, loc));
}
