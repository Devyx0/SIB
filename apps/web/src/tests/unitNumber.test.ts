import { describe, it, expect } from 'vitest';
import { unitNumberOf } from '../lib/unitNumber';

describe('unitNumberOf', () => {
  it('keeps only the unit, not the building it belongs to', () => {
    expect(unitNumberOf('1580-204 Perigord')).toBe('204');
    expect(unitNumberOf('315-518 Saint-Jean')).toBe('518');
    expect(unitNumberOf('10-101')).toBe('101');
    expect(unitNumberOf('204')).toBe('204');
    expect(unitNumberOf(null, '1035-308 Pie XII')).toBe('308');
    expect(unitNumberOf(null, null)).toBeNull();
  });

  it('keeps the words of free-text units and drops the address in them', () => {
    expect(unitNumberOf('Espace commun — stationnement, locataire du 315-409 Saint-Jean')).toBe('Espace commun · stationnement');
    expect(unitNumberOf('Espace commun — 530 Claude-Martin')).toBe('Espace commun');
    expect(unitNumberOf("Espace commun (cage d'escalier), immeuble 846 Ch Ste-Foy")).toBe("Espace commun · cage d'escalier");
    expect(unitNumberOf('Espace commun')).toBe('Espace commun');
    expect(unitNumberOf('1050')).toBe('1050');
  });
});
