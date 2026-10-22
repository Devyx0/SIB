import { Link } from 'react-router-dom';
import { useTasks } from '../../hooks/useTasks';
import type { MeResponse, TaskListItem } from '../../api/schema.d.ts';
import type { Lang } from '../../i18n';
import { t, statusLabel } from '../../i18n';
import { urgencyLabel } from '../../lib/urgencyLevels';
import { dueDay } from '../../lib/taskDates';
import TechHeader from './TechHeader';
import { elapsedLabel } from './elapsed';
import { IN_PROGRESS_TASK_STATUSES, MY_OPEN_TASK_STATUSES } from './myTask';
import styles from './TechPortal.module.css';

interface Props {
  lang: Lang;
  onToggleLang: () => void;
  me: MeResponse | null;
  onSignOut: () => void;
}

function todayToronto(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
}

const inProgress = (r: TaskListItem) => (IN_PROGRESS_TASK_STATUSES as readonly string[]).includes(r.status);

function TaskRow({ row, lang }: { row: TaskListItem; lang: Lang }) {
  const urgency = row.urgency_tier ?? row.request_urgency_tier;
  return (
    <Link to={`/tech/appels/${row.request_id}?task=${row.task_id}`} className={styles.callRow}>
      <div className={styles.callRowTop}>
        <span className={styles.callDate}>{dueDay(row.due_at) ?? t(lang, 'Sans date', 'No date')}</span>
        <span className={styles.statusBadge} data-status={row.status}>
          {statusLabel(lang, row.status)}
        </span>
        {urgency && urgency !== 'none' && (
          <span className={styles.urgencyBadge}>{urgencyLabel(lang, urgency)}</span>
        )}
      </div>
      <div className={styles.callTitle}>{row.request_title ?? `#${row.request_id}`}</div>
      <div className={styles.callAddress}>{row.description}</div>
      <div className={styles.callAddress}>
        {row.building_address ?? '—'}
        {row.unit_label ? `, app. ${row.unit_label}` : ''}
      </div>
    </Link>
  );
}

function Section({ title, rows, lang }: { title: string; rows: TaskListItem[]; lang: Lang }) {
  if (rows.length === 0) return null;
  return (
    <>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {rows.map((r) => <TaskRow key={r.task_id} row={r} lang={lang} />)}
    </>
  );
}

export default function TechList({ lang, me, onSignOut, onToggleLang }: Props) {
  // My open tasks, any date.
  const params = me
    ? { assigned_employee_id: me.employee_id, status: [...MY_OPEN_TASK_STATUSES] }
    : null;
  const { data, isPending, isError } = useTasks(params);

  const today = todayToronto();
  const all = data?.items ?? [];
  const current = all.filter(inProgress);
  const rest = all.filter((r) => !inProgress(r));
  const overdue = rest.filter((r) => { const d = dueDay(r.due_at); return d != null && d < today; });
  const dueToday = rest.filter((r) => dueDay(r.due_at) === today);
  const upcoming = rest.filter((r) => { const d = dueDay(r.due_at); return d != null && d > today; });
  const undated = rest.filter((r) => r.due_at == null);

  // From en_route on a task can no longer be edited, so updated_at is when it entered its status.
  const since = current[0] ? elapsedLabel(current[0].updated_at) : null;

  return (
    <div className={styles.page}>
      <TechHeader lang={lang} me={me} onSignOut={onSignOut} onToggleLang={onToggleLang} />
      <main className={styles.main}>
        {isPending && <p className={styles.muted}>{t(lang, 'Chargement…', 'Loading…')}</p>}
        {isError && <p className={styles.error}>{t(lang, 'Erreur de chargement', 'Failed to load')}</p>}

        {current.length > 0 && (
          <section className={styles.openCall}>
            <div className={styles.openCallBanner}>
              {t(lang, 'Appel en cours — à clôturer avant le prochain', 'Open call — close it before the next one')}
              {since && (current[0].status === 'en_route'
                ? <> · {t(lang, 'En route depuis', 'En route for')} {since}</>
                : <> · {t(lang, 'Arrivé depuis', 'Arrived for')} {since}</>)}
            </div>
            {current.map((r) => <TaskRow key={r.task_id} row={r} lang={lang} />)}
          </section>
        )}

        {data && all.length === 0 && (
          <p className={styles.muted}>{t(lang, 'Aucun appel assigné', 'No assigned calls')}</p>
        )}

        <Section title={t(lang, 'En retard', 'Overdue')} rows={overdue} lang={lang} />
        <Section title={t(lang, "Aujourd'hui", 'Today')} rows={dueToday} lang={lang} />
        <Section title={t(lang, 'À venir', 'Upcoming')} rows={upcoming} lang={lang} />
        <Section title={t(lang, 'Sans date', 'No date')} rows={undated} lang={lang} />
      </main>
    </div>
  );
}
