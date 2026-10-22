import { describe, it, expect } from 'vitest';
import { formatPhone, telHref } from '../lib/phone';

describe('formatPhone', () => {
  it('shows every North American number as « 819 329-3727 », without +1 / 1', () => {
    expect(formatPhone('+1 819-329-3727')).toBe('819 329-3727');
    expect(formatPhone('1-819-329-3727')).toBe('819 329-3727');
    expect(formatPhone('(819) 329-3727')).toBe('819 329-3727');
    expect(formatPhone('8193293727')).toBe('819 329-3727');
    expect(formatPhone('819 329 3727')).toBe('819 329-3727');
  });

  it('leaves other numbers as typed and empties stay empty', () => {
    expect(formatPhone('819 329-3727 poste 12')).toBe('819 329-3727 poste 12');
    expect(formatPhone('+33 1 42 68 53 00')).toBe('+33 1 42 68 53 00');
    expect(formatPhone(null)).toBe('');
  });

  it('dials digits only', () => {
    expect(telHref('819 329-3727')).toBe('tel:8193293727');
  });
});
