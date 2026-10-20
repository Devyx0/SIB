import { useState } from 'react';
import type { Lang } from '../i18n';
import { t } from '../i18n';
import styles from './RangeCalendar.module.css';

// Month calendar for picking a date range: first click sets the start,
// second click the end (in either order). While choosing the end, days more
// than `maxDays` away are disabled. Dates are plain YYYY-MM-DD strings.

interface Props {
  lang: Lang;
  start: string;
  end: string;
  maxDays?: number;
  /** Called once both ends are chosen. */
  onChange: (start: string, end: string) => void;
}

const pad = (n: number) => String(n).padStart(2, '0');
const ymd = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;
function parse(s: string): [number, number, number] {
  const [y, m, d] = s.split('-').map(Number);
  return [y, m - 1, d];
}
function dayDiff(a: string, b: string): number {
  const [ay, am, ad] = parse(a);
  const [by, bm, bd] = parse(b);
  return Math.round((Date.UTC(by, bm, bd) - Date.UTC(ay, am, ad)) / 86400000);
}

export default function RangeCalendar({ lang, start, end, maxDays = 31, onChange }: Props) {
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
  const [view, setView] = useState(() => {
    const [y, m] = parse(end || today);
    return { y, m };
  });
  const [anchor, setAnchor] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);

  const locale = lang === 'fr' ? 'fr-CA' : 'en-CA';
  const monthLabel = new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' })
    .format(new Date(view.y, view.m, 1));
  const weekdays = Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(locale, { weekday: 'narrow' }).format(new Date(2024, 0, 1 + i))); // Mon…Sun
  const longDay = new Intl.DateTimeFormat(locale, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  const firstDow = (new Date(view.y, view.m, 1).getDay() + 6) % 7; // Monday = 0
  const daysInMonth = new Date(view.y, view.m + 1, 0).getDate();
  const cells: Array<string | null> = [
    ...Array.from({ length: firstDow }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => ymd(view.y, view.m, i + 1)),
  ];

  // While choosing the end, preview the range up to the hovered day.
  const [lo, hi] = anchor
    ? [anchor, hover ?? anchor].sort()
    : [start, end];

  function pick(day: string) {
    if (!anchor) {
      setAnchor(day);
      return;
    }
    const [a, b] = [anchor, day].sort();
    setAnchor(null);
    setHover(null);
    onChange(a, b);
  }

  function shift(delta: number) {
    setView(({ y, m }) => {
      const d = new Date(y, m + delta, 1);
      return { y: d.getFullYear(), m: d.getMonth() };
    });
  }

  return (
    <div className={styles.cal} data-testid="range-calendar">
      <div className={styles.head}>
        <button type="button" className={styles.nav} onClick={() => shift(-1)} aria-label={t(lang, 'Mois précédent', 'Previous month')}>
          <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.5 4.5L7 10l5.5 5.5" /></svg>
        </button>
        <span className={styles.month} aria-live="polite">{monthLabel}</span>
        <button type="button" className={styles.nav} onClick={() => shift(1)} aria-label={t(lang, 'Mois suivant', 'Next month')}>
          <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M7.5 4.5L13 10l-5.5 5.5" /></svg>
        </button>
      </div>

      <div className={styles.grid} role="grid" aria-label={monthLabel}>
        {weekdays.map((w, i) => <span key={i} className={styles.dow} aria-hidden="true">{w}</span>)}
        {cells.map((day, i) => {
          if (!day) return <span key={`e${i}`} />;
          const tooFar = !!anchor && Math.abs(dayDiff(anchor, day)) > maxDays - 1;
          const inRange = lo && hi && day >= lo && day <= hi;
          const isEdge = day === lo || day === hi;
          return (
            <button
              key={day}
              type="button"
              className={[
                styles.day,
                inRange ? styles.inRange : '',
                isEdge ? styles.edge : '',
                day === lo ? styles.rangeStart : '',
                day === hi ? styles.rangeEnd : '',
                day === today ? styles.today : '',
              ].join(' ')}
              disabled={tooFar}
              aria-pressed={isEdge}
              aria-label={longDay.format(new Date(...(parse(day) as [number, number, number])))}
              onClick={() => pick(day)}
              onMouseEnter={() => anchor && setHover(day)}
              data-day={day}
            >
              {Number(day.slice(8))}
            </button>
          );
        })}
      </div>

      <p className={styles.hint} aria-live="polite">
        {anchor
          ? t(lang, 'Choisissez la date de fin', 'Pick the end date')
          : t(lang, `Choisissez la date de début (${maxDays} jours max)`, `Pick the start date (${maxDays} days max)`)}
      </p>
    </div>
  );
}
