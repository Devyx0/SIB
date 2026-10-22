import { parseAiNotes, hasAiNoteContent } from '../lib/aiNotes';
import { t, type Lang } from '../i18n';
import styles from './AiNotesSections.module.css';

interface Props {
  lang: Lang;
  problemSummary?: string | null;
  otherNotes?: string | null;
  aiImportantNotes?: string[] | null;
  aiNextSteps?: string[] | null;
  /** When true, omit the outer card title (parent already has one). */
  embedded?: boolean;
  /** Skip the « Résumé » bullets (the call popup's header already says it). */
  hideSummary?: boolean;
  className?: string;
}

function Section({ title, items, testId }: { title: string; items: string[]; testId: string }) {
  if (items.length === 0) return null;
  return (
    <div className={styles.section} data-testid={testId}>
      <h4 className={styles.heading}>{title}</h4>
      <ul className={styles.list}>
        {items.map((item, i) => (
          <li key={`${i}-${item.slice(0, 24)}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

/** Bullet Summary / Important notes / Next steps for AI triage output. */
export default function AiNotesSections({
  lang, problemSummary, otherNotes, aiImportantNotes, aiNextSteps, embedded, className, hideSummary,
}: Props) {
  const parsed = parseAiNotes(otherNotes, problemSummary, aiImportantNotes, aiNextSteps);
  const sections = hideSummary ? { ...parsed, summary: [] } : parsed;
  if (!hasAiNoteContent(sections)) return null;

  return (
    <div className={`${styles.wrap} ${className ?? ''}`} data-testid="ai-notes-sections">
      {!embedded && (
        <h3 className={styles.title}>{t(lang, 'Résumé IA', 'AI summary')}</h3>
      )}
      <Section
        title={t(lang, 'Résumé', 'Summary')}
        items={sections.summary}
        testId="ai-notes-summary"
      />
      <Section
        title={t(lang, 'Notes importantes', 'Important notes')}
        items={sections.important}
        testId="ai-notes-important"
      />
      <Section
        title={t(lang, 'Prochaines étapes', 'Next steps')}
        items={sections.next}
        testId="ai-notes-next"
      />
    </div>
  );
}
