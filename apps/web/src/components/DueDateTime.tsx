import Select from './Select';
import { t } from '../i18n';
import type { Lang } from '../i18n';
import styles from './DueDateTime.module.css';

// Due date + time: a date field and a time picker (every 30 minutes, 6:00–20:00).
// Value is « YYYY-MM-DDTHH:MM » ('' = no date); picking a day starts at 08:00.

const TIMES = Array.from({ length: 29 }, (_, i) => {
  const m = 6 * 60 + i * 30;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
});

export default function DueDateTime({ value, onChange, lang, disabled = false, testId, inputClassName = '' }: {
  value: string;
  onChange: (slot: string) => void;
  lang: Lang;
  disabled?: boolean;
  testId?: string;
  inputClassName?: string;
}) {
  const day = value.slice(0, 10);
  const time = value.length > 10 ? value.slice(11, 16) : (day ? '08:00' : '');
  const times = time && !TIMES.includes(time) ? [...TIMES, time].sort() : TIMES;
  return (
    <span className={styles.wrap}>
      <input
        type="date"
        className={`${inputClassName} ${styles.date}`}
        value={day}
        disabled={disabled}
        aria-label={t(lang, 'Date prévue', 'Due date')}
        data-testid={testId}
        onChange={(e) => onChange(e.target.value ? `${e.target.value}T${time || '08:00'}` : '')}
      />
      <span className={styles.time}>
        <svg className={styles.clock} viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" fill="none"
             stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="10" cy="10" r="7.5" /><path d="M10 6v4l2.5 2" />
        </svg>
        <Select
          className={`${inputClassName} ${styles.timeSelect}`}
          value={time}
          disabled={disabled || !day}
          aria-label={t(lang, 'Heure prévue', 'Due time')}
          data-testid={testId ? `${testId}-time` : undefined}
          onChange={(e) => onChange(`${day}T${e.target.value}`)}
        >
          {!day && <option value="">--:--</option>}
          {times.map((tm) => <option key={tm} value={tm}>{tm}</option>)}
        </Select>
      </span>
    </span>
  );
}
