/** Tasks: focus one day inside the filter range (or whole range). */
import type { Lang } from '../../i18n';
import { t } from '../../i18n';
import styles from './TaskDayStrip.module.css';

interface Props {
  lang: Lang;
  startDate: string;
  endDate: string;
  /** null = whole range */
  selectedDay: string | null;
  onSelectDay: (day: string | null) => void;
}

function shiftDay(ymd: string, delta: number): string {
  const d = new Date(`${ymd}T12:00:00`);
  d.setDate(d.getDate() + delta);
  return d.toISOString().slice(0, 10);
}

function clamp(ymd: string, start: string, end: string): string {
  if (ymd < start) return start;
  if (ymd > end) return end;
  return ymd;
}

export default function TaskDayStrip({
  lang, startDate, endDate, selectedDay, onSelectDay,
}: Props) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    return null;
  }

  const day = selectedDay ? clamp(selectedDay, startDate, endDate) : null;
  const canPrev = day != null && day > startDate;
  const canNext = day != null && day < endDate;

  return (
    <div className={styles.strip} data-testid="task-day-strip" role="group" aria-label={t(lang, 'Jour', 'Day')}>
      <button
        type="button"
        className={`${styles.toggle} ${day == null ? styles.toggleActive : ''}`}
        onClick={() => onSelectDay(null)}
      >
        {t(lang, 'Toute la plage', 'Full range')}
      </button>

      <div className={styles.dayNav}>
        <button
          type="button"
          className={styles.arrow}
          disabled={!canPrev}
          aria-label={t(lang, 'Jour précédent', 'Previous day')}
          onClick={() => day && onSelectDay(shiftDay(day, -1))}
        >
          ‹
        </button>
        <input
          type="date"
          className={styles.date}
          min={startDate}
          max={endDate}
          value={day ?? ''}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) onSelectDay(null);
            else onSelectDay(clamp(v, startDate, endDate));
          }}
          aria-label={t(lang, 'Jour', 'Day')}
        />
        <button
          type="button"
          className={styles.arrow}
          disabled={!canNext}
          aria-label={t(lang, 'Jour suivant', 'Next day')}
          onClick={() => day && onSelectDay(shiftDay(day, 1))}
        >
          ›
        </button>
      </div>
    </div>
  );
}
