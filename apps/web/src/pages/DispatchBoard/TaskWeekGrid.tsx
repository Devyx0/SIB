/** Week calendar of accepted tasks (due day). Used by the Tasks board calendar view. */
import { dueDay } from '../../lib/taskDates';
import { urgencyLabel } from '../../lib/urgencyLevels';
import { statusLabel, t, type Lang } from '../../i18n';
import type { TaskListItem } from '../../api/schema.d.ts';
import styles from './TaskWeekGrid.module.css';

export function addDays(ymd: string, delta: number): string {
  const d = new Date(`${ymd}T12:00:00`);
  d.setDate(d.getDate() + delta);
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

export function mondayOf(ymd: string): string {
  const dow = new Date(`${ymd}T12:00:00`).getDay();
  return addDays(ymd, dow === 0 ? -6 : 1 - dow);
}

export function torontoYmd(d = new Date()): string {
  return d.toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
}

function dayLabel(ymd: string, lang: Lang): string {
  return new Date(`${ymd}T12:00:00`).toLocaleDateString(lang === 'fr' ? 'fr-CA' : 'en-CA', {
    weekday: 'short', day: 'numeric', month: 'short',
  });
}

function TaskChip({
  row, lang, selected, onSelect,
}: {
  row: TaskListItem;
  lang: Lang;
  selected: boolean;
  onSelect: () => void;
}) {
  const urgency = row.urgency_tier ?? row.request_urgency_tier;
  const where = [row.building_address, row.unit_label ? `app. ${row.unit_label}` : null]
    .filter(Boolean).join(', ');
  return (
    <button
      type="button"
      className={`${styles.task} ${selected ? styles.taskSelected : ''} ${urgency === 'URGENT' ? styles.taskUrgent : ''}`}
      onClick={onSelect}
      data-testid={`cal-task-${row.task_id}`}
    >
      <span className={styles.taskDesc}>{row.description}</span>
      {where && <span className={styles.taskMeta}>{where}</span>}
      <span className={styles.taskMeta}>
        {[
          row.assigned_employee_name,
          urgency ? urgencyLabel(lang, urgency) : null,
          statusLabel(lang, row.status),
        ].filter(Boolean).join(' · ')}
      </span>
    </button>
  );
}

interface Props {
  lang: Lang;
  weekStart: string;
  datedRows: TaskListItem[];
  undatedRows: TaskListItem[];
  selectedTaskId: number | null;
  onSelect: (row: TaskListItem) => void;
  onShiftWeek: (deltaWeeks: number) => void;
  onToday: () => void;
  isLoading?: boolean;
  isError?: boolean;
}

export default function TaskWeekGrid({
  lang, weekStart, datedRows, undatedRows, selectedTaskId,
  onSelect, onShiftWeek, onToday, isLoading, isError,
}: Props) {
  const today = torontoYmd();
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const byDay = new Map<string, TaskListItem[]>();
  for (const row of datedRows) {
    const day = dueDay(row.due_at);
    if (!day) continue;
    const list = byDay.get(day);
    if (list) list.push(row);
    else byDay.set(day, [row]);
  }

  return (
    <div className={styles.wrap} data-testid="task-week-grid">
      <div className={styles.toolbar}>
        <button type="button" className={styles.todayBtn} onClick={onToday} data-testid="cal-today">
          {t(lang, "Aujourd'hui", 'Today')}
        </button>
        <button type="button" className={styles.arrow} aria-label={t(lang, 'Semaine précédente', 'Previous week')} onClick={() => onShiftWeek(-1)}>
          ‹
        </button>
        <span className={styles.range}>{dayLabel(days[0], lang)} – {dayLabel(days[6], lang)}</span>
        <button type="button" className={styles.arrow} aria-label={t(lang, 'Semaine suivante', 'Next week')} onClick={() => onShiftWeek(1)}>
          ›
        </button>
      </div>

      {isLoading && <p className={styles.muted}>{t(lang, 'Chargement…', 'Loading…')}</p>}
      {isError && <p className={styles.error}>{t(lang, 'Impossible de charger les tâches', 'Could not load tasks')}</p>}

      {!isLoading && !isError && undatedRows.length > 0 && (
        <section className={styles.sansDate} data-testid="sans-date">
          <h2>{t(lang, `Sans date (${undatedRows.length})`, `No date (${undatedRows.length})`)}</h2>
          <div className={styles.sansDateList}>
            {undatedRows.map((row) => (
              <TaskChip
                key={row.task_id}
                row={row}
                lang={lang}
                selected={selectedTaskId === row.task_id}
                onSelect={() => onSelect(row)}
              />
            ))}
          </div>
        </section>
      )}

      <div className={styles.grid} data-testid="week-grid">
        {days.map((day) => {
          const rows = byDay.get(day) ?? [];
          const isToday = day === today;
          return (
            <section
              key={day}
              className={`${styles.day} ${isToday ? styles.dayToday : ''}`}
              data-testid={`day-${day}`}
            >
              <h2>
                {dayLabel(day, lang)}
                {isToday && <span className={styles.todayPill}>{t(lang, "Auj.", 'Today')}</span>}
              </h2>
              {rows.length === 0 && (
                <p className={styles.emptyDay}>{t(lang, 'Aucune tâche', 'No tasks')}</p>
              )}
              {rows.map((row) => (
                <TaskChip
                  key={row.task_id}
                  row={row}
                  lang={lang}
                  selected={selectedTaskId === row.task_id}
                  onSelect={() => onSelect(row)}
                />
              ))}
            </section>
          );
        })}
      </div>
    </div>
  );
}
