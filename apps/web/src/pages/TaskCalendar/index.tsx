import { Link, useSearchParams } from 'react-router-dom';
import { useTasks } from '../../hooks/useTasks';
import { dueDay } from '../../lib/taskDates';
import type { Lang } from '../../i18n';
import { t } from '../../i18n';
import styles from './index.module.css';

function addDays(ymd: string, delta: number): string {
  const d = new Date(`${ymd}T12:00:00`);
  d.setDate(d.getDate() + delta);
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function mondayOf(ymd: string): string {
  const dow = new Date(`${ymd}T12:00:00`).getDay();
  return addDays(ymd, dow === 0 ? -6 : 1 - dow);
}

function torontoYmd(d = new Date()): string {
  return d.toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
}

function dayLabel(ymd: string, lang: Lang): string {
  return new Date(`${ymd}T12:00:00`).toLocaleDateString(lang === 'fr' ? 'fr-CA' : 'en-CA', {
    weekday: 'short', day: 'numeric', month: 'short',
  });
}

export default function TaskCalendar({ lang }: { lang: Lang }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const anchor = searchParams.get('start_date');
  const weekStart = anchor && /^\d{4}-\d{2}-\d{2}$/.test(anchor) ? mondayOf(anchor) : mondayOf(torontoYmd());
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const tasksQuery = useTasks({ start_date: weekStart, end_date: days[6] });
  // A date range cannot see null due_at (BETWEEN excludes NULL). Queued tasks are the undated set.
  const undatedQuery = useTasks({ status: ['queued'] });
  const undated = (undatedQuery.data?.items ?? []).filter((row) => row.due_at == null);

  const byDay = new Map<string, { task_id: number; description: string }[]>();
  for (const row of tasksQuery.data?.items ?? []) {
    const day = dueDay(row.due_at);
    if (!day) continue;
    const list = byDay.get(day);
    if (list) list.push(row);
    else byDay.set(day, [row]);
  }

  function shiftWeek(deltaWeeks: number) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('start_date', addDays(weekStart, deltaWeeks * 7));
      return next;
    });
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>{t(lang, 'Calendrier', 'Calendar')}</h1>
          <p className={styles.subtitle}>
            {t(lang, "Tâches acceptées par date d'échéance", 'Accepted tasks by due date')}
          </p>
        </div>
        <div className={styles.nav}>
          <Link to="/tasks" className={styles.listLink}>
            {t(lang, 'Liste', 'List')}
          </Link>
          <button type="button" className={styles.arrow} aria-label={t(lang, 'Semaine précédente', 'Previous week')} onClick={() => shiftWeek(-1)}>
            ‹
          </button>
          <span className={styles.range}>{dayLabel(days[0], lang)} – {dayLabel(days[6], lang)}</span>
          <button type="button" className={styles.arrow} aria-label={t(lang, 'Semaine suivante', 'Next week')} onClick={() => shiftWeek(1)}>
            ›
          </button>
        </div>
      </header>

      {undated.length > 0 && (
        <section className={styles.sansDate} data-testid="sans-date">
          <h2>{t(lang, `Sans date (${undated.length})`, `No date (${undated.length})`)}</h2>
          {undated.map((row) => (
            <p key={row.task_id} className={styles.task}>{row.description}</p>
          ))}
        </section>
      )}

      <div className={styles.grid} data-testid="week-grid">
        {days.map((day) => (
          <section key={day} className={styles.day} data-testid={`day-${day}`}>
            <h2>{dayLabel(day, lang)}</h2>
            {(byDay.get(day) ?? []).map((row) => (
              <p key={row.task_id} className={styles.task}>{row.description}</p>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
