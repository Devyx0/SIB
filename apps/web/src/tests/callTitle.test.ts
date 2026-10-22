import { describe, it, expect } from 'vitest';
import { cleanCallTitle } from '../lib/callTitle';

describe('cleanCallTitle', () => {
  it('drops employee initials, urgency codes and the unit / project head', () => {
    expect(cleanCallTitle('CHGE AJD 1035-308 Pie XII: Fuite sous évier')).toBe('Fuite sous évier');
    expect(cleanCallTitle('[EN TRAITEMENT] ajd 3140-501 Cèdres: fourmis cuisine')).toBe('Fourmis cuisine');
    expect(cleanCallTitle('URGENT 125-103 Cèdres: Pas de chauffage')).toBe('Pas de chauffage');
    expect(cleanCallTitle('MAKA/CHGE Projet Cartier - Porte brisée', 'Projet Cartier')).toBe('Porte brisée');
    expect(cleanCallTitle("[DÉMO] Fuite sous l'évier de cuisine")).toBe("Fuite sous l'évier de cuisine");
  });

  it('keeps titles that are already plain, and operational words', () => {
    expect(cleanCallTitle('Changer ampoule SDB')).toBe('Changer ampoule SDB');
    expect(cleanCallTitle('AC ne fonctionne pas')).toBe('AC ne fonctionne pas');
    expect(cleanCallTitle('DOUBLON POTENTIEL fuite')).toBe('DOUBLON POTENTIEL fuite');
    expect(cleanCallTitle(null)).toBe('');
  });
});
