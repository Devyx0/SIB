// One timeline for a request's history: visits, follow-up notes, dispatcher
// decisions (with who decided and what changed) and status changes, newest
// first under day headings. Replaces the three separate lists.
//
// Merging rules:
// - one dispatch save writes one justification row per changed field with the
//   same text — rows by the same person, with the same text, within a few
//   seconds become one entry listing each change;
// - a closeout comment is stored on the visit, as a follow-up note and (for
//   outcomes 3/4) as a closeout justification — it is shown once, on the visit;
// - status changes that a visit or a decision already explains are folded in.
import { useMemo, useState } from 'react';
import type { FollowupEntry, JustificationEntry, StatusChange, VisitEntry } from '../api/schema.d.ts';
import { closeoutOutcomeLabel, sourceCalendarLabel, statusLabel, t } from '../i18n';
import type { Lang } from '../i18n';
import { urgencyLabel } from '../lib/urgencyLevels';
import { VisitPhoto, formatDurationMinutes } from './RequestSections';
import styles from './HistoryTimeline.module.css';

type Kind = 'decision' | 'followup' | 'visit' | 'status';
type Filter = 'all' | 'decision' | 'followup' | 'visit';

interface Change { label: string; before: string; after: string }

interface Item {
  key: string;
  kind: Kind;
  /** Sort key, ms. Follow-ups (date only) sort at the end of their day. */
  at: number;
  day: string; // YYYY-MM-DD, Toronto
  time: string | null;
  who: string | null;
  title: string;
  detail?: string | null;
  changes?: Change[];
  text?: string | null;
  textNote?: string | null;
  photos?: number[];
}

const TZ = 'America/Toronto';
const GROUP_WINDOW_MS = 5_000;
const FOLD_WINDOW_MS = 10_000;
const COLLAPSED = 10;

const DECISION_LABELS: Record<string, [string, string]> = {
  assign: ['Assignation', 'Assignment'],
  reschedule: ['Date prévue', 'Scheduled date'],
  urgency: ['Urgence', 'Urgency'],
  follow_up_date: ['Prochain suivi', 'Next follow-up'],
  next_steps: ['Prochaines étapes', 'Next steps'],
  cost: ['Coût estimé', 'Estimated cost'],
  route: ['Acheminement', 'Routing'],
  closeout: ['Clôture', 'Closeout'],
};

const locale = (lang: Lang) => (lang === 'fr' ? 'fr-CA' : 'en-CA');
const L = (lang: Lang, pair: [string, string] | undefined, fallback: string) =>
  pair ? pair[lang === 'fr' ? 0 : 1] : fallback;

function dayOf(iso: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(new Date(iso));
}

function timeOf(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(locale(lang), { timeZone: TZ, hour: '2-digit', minute: '2-digit' })
    .format(new Date(iso));
}

/** 'YYYY-MM-DD' as a calendar date, with the year only when it isn't this year. */
export function formatEntryDate(ymd: string | null | undefined, lang: Lang): string {
  if (!ymd) return '—';
  const [y, m, d] = ymd.slice(0, 10).split('-').map(Number);
  const sameYear = y === new Date().getFullYear();
  return new Intl.DateTimeFormat(locale(lang), {
    day: 'numeric', month: 'short', ...(sameYear ? {} : { year: 'numeric' }),
  }).format(new Date(y, m - 1, d));
}

function dayHeading(day: string, lang: Lang): string {
  const today = dayOf(new Date().toISOString());
  const yesterday = dayOf(new Date(Date.now() - 86_400_000).toISOString());
  if (day === today) return t(lang, "Aujourd'hui", 'Today');
  if (day === yesterday) return t(lang, 'Hier', 'Yesterday');
  return formatEntryDate(day, lang);
}

/** End of a calendar day in ms, so a dated note sorts after that day's timed events. */
function endOfDay(ymd: string): number {
  const [y, m, d] = ymd.split('-').map(Number);
  return new Date(y, m - 1, d, 23, 59, 59, 999).getTime();
}

const norm = (s: string | null | undefined) => (s ?? '').trim().replace(/\s+/g, ' ').toLowerCase();

function money(v: unknown, lang: Lang): string {
  return v == null || v === '' ? '—'
    : Number(v).toLocaleString(locale(lang), { style: 'currency', currency: 'CAD' });
}

function short(s: unknown, n = 90): string {
  if (s == null || s === '') return '—';
  const str = String(s).replace(/\s+/g, ' ').trim();
  return str.length > n ? `${str.slice(0, n - 1)}…` : str;
}

/** Before → after values of one decision, in words. */
function decisionChange(e: JustificationEntry, lang: Lang): Change {
  const b = e.before_value ?? {};
  const a = e.after_value ?? {};
  const label = L(lang, DECISION_LABELS[e.decision_type], e.decision_type);
  const nobody = t(lang, 'Personne', 'Nobody');
  const none = t(lang, 'Aucune', 'None');
  switch (e.decision_type) {
    case 'assign': {
      const who = (v: Record<string, unknown>) =>
        (v.assigned_employee_name as string | undefined)
        ?? (v.assigned_employee_id != null ? `#${v.assigned_employee_id}` : nobody);
      return { label, before: who(b), after: who(a) };
    }
    case 'reschedule':
      return { label, before: formatEntryDate(b.start_date as string, lang), after: formatEntryDate(a.start_date as string, lang) };
    case 'urgency': {
      const tier = (v: Record<string, unknown>) =>
        urgencyLabel(lang, (v.urgency_tier as string | null) ?? null);
      const weather = a.weather ? t(lang, ' (météo)', ' (weather)') : '';
      return { label, before: tier(b), after: tier(a) + weather };
    }
    case 'follow_up_date':
      return { label, before: formatEntryDate(b.next_follow_up_date as string, lang),
               after: formatEntryDate(a.next_follow_up_date as string, lang) };
    case 'next_steps':
      return { label, before: short(b.next_steps), after: short(a.next_steps) };
    case 'cost':
      return { label, before: money(b.estimated_cost, lang), after: money(a.estimated_cost, lang) };
    case 'route':
      return { label, before: sourceCalendarLabel(lang, b.source_calendar as string),
               after: sourceCalendarLabel(lang, a.source_calendar as string) };
    case 'closeout':
      return { label, before: b.status ? statusLabel(lang, String(b.status)) : '—',
               after: a.status ? statusLabel(lang, String(a.status)) : closeoutOutcomeLabel(lang, a.closeout_outcome as string) };
    default:
      return { label, before: short(JSON.stringify(b)), after: short(JSON.stringify(a)) };
  }
}

function visitDetail(v: VisitEntry, lang: Lang): string {
  const parts = [`${t(lang, 'En route', 'En route')} ${timeOf(v.en_route_at, lang)}`];
  if (v.arrived_at) {
    parts.push(`${t(lang, 'arrivé', 'arrived')} ${timeOf(v.arrived_at, lang)}`
      + (v.travel_minutes != null ? ` (${formatDurationMinutes(v.travel_minutes)} ${t(lang, 'de trajet', 'travel')})` : ''));
  }
  if (v.closeout_at) {
    const onSite = v.on_site_minutes ?? (v.arrived_at ? null : v.duration_minutes);
    parts.push(`${t(lang, 'clôturé', 'closed')} ${timeOf(v.closeout_at, lang)}`
      + (onSite != null ? ` (${formatDurationMinutes(onSite)} ${v.arrived_at ? t(lang, 'sur place', 'on site') : t(lang, 'au total', 'total')})` : ''));
  }
  return parts.join(' · ');
}

export function buildTimeline(
  { visits, followups, decisions, statusChanges }: {
    visits: VisitEntry[]; followups: FollowupEntry[]; decisions: JustificationEntry[]; statusChanges: StatusChange[];
  },
  lang: Lang,
): Item[] {
  const items: Item[] = [];

  // Visits; their closeout comments are the ones repeated elsewhere.
  const visitComments = new Map<string, Set<string>>(); // day → comments
  const visitTimes: number[] = [];
  for (const v of visits) {
    const at = new Date(v.en_route_at).getTime();
    for (const ts of [v.en_route_at, v.arrived_at, v.closeout_at]) if (ts) visitTimes.push(new Date(ts).getTime());
    if (v.closeout_comment && v.closeout_at) {
      const day = dayOf(v.closeout_at);
      if (!visitComments.has(day)) visitComments.set(day, new Set());
      visitComments.get(day)!.add(norm(v.closeout_comment));
    }
    items.push({
      key: `v${v.visit_id}`, kind: 'visit', at, day: dayOf(v.en_route_at), time: timeOf(v.en_route_at, lang),
      who: v.employee_name ?? `#${v.employee_id}`,
      title: v.outcome ? closeoutOutcomeLabel(lang, v.outcome)
        : v.arrived_at ? t(lang, 'Sur place', 'On site') : t(lang, 'En route', 'En route'),
      detail: visitDetail(v, lang),
      text: v.closeout_comment,
      photos: v.photo_ids,
    });
  }
  const repeatsVisit = (day: string, text: string | null | undefined) =>
    !!text && !!visitComments.get(day)?.has(norm(text));

  // Decisions, grouped per save.
  const sorted = [...decisions].sort((x, y) => x.created_at.localeCompare(y.created_at) || x.id - y.id);
  const groups: { rows: JustificationEntry[]; at: number }[] = [];
  for (const e of sorted) {
    const at = new Date(e.created_at).getTime();
    const last = groups[groups.length - 1];
    const head = last?.rows[0];
    if (last && head.employee_id === e.employee_id && norm(head.justification_text) === norm(e.justification_text)
        && at - last.at <= GROUP_WINDOW_MS) {
      last.rows.push(e);
    } else {
      groups.push({ rows: [e], at });
    }
  }
  const decisionItems: Item[] = [];
  const decisionBy = new Map<Item, number>(); // item → who decided
  for (const g of groups) {
    const head = g.rows[0];
    const day = dayOf(head.created_at);
    // A closeout justification only repeats the visit (outcome + comment).
    if (g.rows.every((r) => r.decision_type === 'closeout') && repeatsVisit(day, head.justification_text)) continue;
    const item: Item = {
      key: `d${head.id}`, kind: 'decision', at: g.at, day, time: timeOf(head.created_at, lang),
      who: head.employee_name ?? `#${head.employee_id}`,
      title: g.rows.length > 1
        ? t(lang, `Répartition modifiée (${g.rows.length} changements)`, `Dispatch updated (${g.rows.length} changes)`)
        : L(lang, DECISION_LABELS[head.decision_type], head.decision_type),
      changes: g.rows.map((r) => decisionChange(r, lang)),
      text: head.justification_text,
      textNote: head.input_method === 'voice' ? t(lang, 'dicté', 'dictated') : null,
    };
    decisionItems.push(item);
    decisionBy.set(item, head.employee_id);
  }

  // Status changes: folded into the visit or decision that explains them.
  for (const s of statusChanges) {
    const at = new Date(s.changed_at).getTime();
    if (visitTimes.some((vt) => Math.abs(vt - at) <= FOLD_WINDOW_MS)) continue;
    const change: Change = {
      label: t(lang, 'Statut', 'Status'),
      before: s.status_from ? statusLabel(lang, s.status_from) : '—',
      after: s.status_to ? statusLabel(lang, s.status_to) : '—',
    };
    const owner = decisionItems.find((d) => decisionBy.get(d) === s.employee_id && Math.abs(d.at - at) <= FOLD_WINDOW_MS);
    if (owner) { owner.changes = [...(owner.changes ?? []), change]; continue; }
    items.push({
      key: `s${s.id}`, kind: 'status', at, day: dayOf(s.changed_at), time: timeOf(s.changed_at, lang),
      who: s.employee_name, title: t(lang, 'Changement de statut', 'Status change'), changes: [change],
    });
  }
  items.push(...decisionItems);

  // Follow-up notes (legacy log + notes added from the board).
  for (const f of followups) {
    if (!f.entry_date) continue;
    if (repeatsVisit(f.entry_date, f.entry_text)) continue;
    items.push({
      key: `f${f.followup_id}`, kind: 'followup', at: endOfDay(f.entry_date),
      day: f.entry_date, time: null, who: f.entered_by_initials,
      title: t(lang, 'Note de suivi', 'Follow-up note'), text: f.entry_text,
    });
  }

  // Newest first; ties (same-day notes) keep the later-written one on top.
  const order = new Map(items.map((item, i) => [item, i]));
  return items.sort((x, y) => y.at - x.at || order.get(y)! - order.get(x)!);
}

const FILTERS: { id: Filter; fr: string; en: string; kinds: Kind[] }[] = [
  { id: 'all', fr: 'Tout', en: 'All', kinds: ['decision', 'status', 'followup', 'visit'] },
  { id: 'decision', fr: 'Décisions', en: 'Decisions', kinds: ['decision', 'status'] },
  { id: 'followup', fr: 'Suivis', en: 'Follow-ups', kinds: ['followup'] },
  { id: 'visit', fr: 'Visites', en: 'Visits', kinds: ['visit'] },
];

const KIND_LABEL: Record<Kind, [string, string]> = {
  decision: ['Décision', 'Decision'],
  status: ['Statut', 'Status'],
  followup: ['Suivi', 'Follow-up'],
  visit: ['Visite', 'Visit'],
};

export default function HistoryTimeline({ requestId, visits, followups, decisions, statusChanges = [], lang }: {
  requestId: number;
  visits: VisitEntry[];
  followups: FollowupEntry[];
  decisions: JustificationEntry[];
  statusChanges?: StatusChange[];
  lang: Lang;
}) {
  const [filter, setFilter] = useState<Filter>('all');
  const [expanded, setExpanded] = useState(false);
  const all = useMemo(
    () => buildTimeline({ visits, followups, decisions, statusChanges }, lang),
    [visits, followups, decisions, statusChanges, lang],
  );
  const counts = Object.fromEntries(FILTERS.map((f) => [f.id, all.filter((i) => f.kinds.includes(i.kind)).length]));
  const active = FILTERS.find((f) => f.id === filter)!;
  const filtered = all.filter((i) => active.kinds.includes(i.kind));
  const shown = expanded ? filtered : filtered.slice(0, COLLAPSED);

  const days: { day: string; items: Item[] }[] = [];
  for (const item of shown) {
    const last = days[days.length - 1];
    if (last?.day === item.day) last.items.push(item); else days.push({ day: item.day, items: [item] });
  }

  return (
    <section className={styles.wrap} data-testid="history-timeline" aria-labelledby={`history-${requestId}`}>
      <div className={styles.head}>
        <h3 id={`history-${requestId}`} className={styles.heading}>{t(lang, 'Historique', 'History')}</h3>
        {all.length > 0 && (
          <div className={styles.filters} role="group" aria-label={t(lang, 'Filtrer l’historique', 'Filter history')}>
            {FILTERS.filter((f) => f.id === 'all' || counts[f.id] > 0).map((f) => (
              <button key={f.id} type="button" aria-pressed={filter === f.id} data-testid={`history-filter-${f.id}`}
                      className={`${styles.chip} ${filter === f.id ? styles.chipActive : ''}`}
                      onClick={() => { setFilter(f.id); setExpanded(false); }}>
                {t(lang, f.fr, f.en)} <span className={styles.count}>{counts[f.id]}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {all.length === 0 ? (
        <p className={styles.empty}>{t(lang, 'Aucun historique pour le moment.', 'No history yet.')}</p>
      ) : (
        <ol className={styles.days}>
          {days.map((d) => (
            <li key={d.day} className={styles.day}>
              <h4 className={styles.dayHeading}>{dayHeading(d.day, lang)}</h4>
              <ol className={styles.items}>
                {d.items.map((item) => (
                  <li key={item.key} className={`${styles.item} ${styles[item.kind]}`}
                      data-testid="history-item" data-kind={item.kind}>
                    <span className={styles.dot} aria-hidden="true" />
                    <div className={styles.meta}>
                      <span className={styles.kind}>{L(lang, KIND_LABEL[item.kind], item.kind)}</span>
                      {item.time && <span>{item.time}</span>}
                      {item.who && <span className={styles.who}>{item.who}</span>}
                    </div>
                    <p className={styles.title}>{item.title}</p>
                    {item.detail && <p className={styles.detail}>{item.detail}</p>}
                    {item.changes && item.changes.length > 0 && (
                      <dl className={styles.changes}>
                        {item.changes.map((c, i) => (
                          <div key={i} className={styles.change}>
                            <dt>{c.label}</dt>
                            <dd>
                              <span className={styles.before}>{c.before}</span>
                              <span className={styles.arrow} aria-label={t(lang, 'devient', 'becomes')}>→</span>
                              <span className={styles.after}>{c.after}</span>
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    {item.text && (
                      <blockquote className={styles.text}>
                        {item.text}
                        {item.textNote && <span className={styles.textNote}> — {item.textNote}</span>}
                      </blockquote>
                    )}
                    {item.photos && item.photos.length > 0 && (
                      <div className={styles.photos}>
                        {item.photos.map((pid) => <VisitPhoto key={pid} requestId={requestId} attachmentId={pid} />)}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            </li>
          ))}
        </ol>
      )}

      {filtered.length > COLLAPSED && (
        <button type="button" className={styles.more} onClick={() => setExpanded((x) => !x)} data-testid="history-more">
          {expanded ? t(lang, 'Afficher moins', 'Show less')
                    : t(lang, `Voir tout l’historique (${filtered.length})`, `Show all history (${filtered.length})`)}
        </button>
      )}
    </section>
  );
}
