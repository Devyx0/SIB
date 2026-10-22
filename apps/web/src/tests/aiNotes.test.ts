import { describe, expect, it } from 'vitest';
import { parseAiNotes, hasAiNoteContent } from '../lib/aiNotes';

describe('parseAiNotes', () => {
  it('puts problem_summary into Summary', () => {
    const s = parseAiNotes(null, 'Fuite sous le lavabo');
    expect(s.summary).toEqual(['Fuite sous le lavabo']);
    expect(s.important).toEqual([]);
    expect(s.next).toEqual([]);
  });

  it('parses IMPORTANT / NEXT headers into sections', () => {
    const s = parseAiNotes(
      `IMPORTANT:
- RÉQUÉRANT ABSENT
- Accès par keybox H
NEXT:
- Couper l'eau
- Remplacer joint`,
      'Fuite évier',
    );
    expect(s.summary).toEqual(['Fuite évier']);
    expect(s.important).toEqual(['RÉQUÉRANT ABSENT', 'Accès par keybox H']);
    expect(s.next).toEqual(["Couper l'eau", 'Remplacer joint']);
  });

  it('accepts French section headers', () => {
    const s = parseAiNotes(
      `Notes importantes:
- bail anglais
Prochaines étapes:
- Appeler le locataire`,
    );
    expect(s.important).toEqual(['bail anglais']);
    expect(s.next).toEqual(['Appeler le locataire']);
  });

  it('treats legacy free-form other_notes as Important bullets', () => {
    const s = parseAiNotes('Plomberie d’abord, puis plancher une fois sec.');
    expect(s.important).toEqual(['Plomberie d’abord, puis plancher une fois sec.']);
    expect(s.next).toEqual([]);
  });

  it('splits multi-line legacy notes into bullets', () => {
    const s = parseAiNotes('Ligne une\nLigne deux');
    expect(s.important).toEqual(['Ligne une', 'Ligne deux']);
  });

  it('prefers DB arrays over other_notes parse', () => {
    const s = parseAiNotes(
      'IMPORTANT:\n- ignored legacy',
      'Titre',
      ['RÉQUÉRANT ABSENT'],
      ["Couper l'eau"],
    );
    expect(s.summary).toEqual(['Titre']);
    expect(s.important).toEqual(['RÉQUÉRANT ABSENT']);
    expect(s.next).toEqual(["Couper l'eau"]);
  });

  it('hasAiNoteContent is false when empty', () => {
    expect(hasAiNoteContent(parseAiNotes(null, null))).toBe(false);
    expect(hasAiNoteContent(parseAiNotes('IMPORTANT:\n- x'))).toBe(true);
  });
});
