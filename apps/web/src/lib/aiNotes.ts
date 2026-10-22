/** Parse AI triage notes into Summary / Important / Next bullet sections. */

export type AiNoteSections = {
  summary: string[];
  important: string[];
  next: string[];
};

type SectionKey = keyof AiNoteSections;

const HEADER: { key: SectionKey; re: RegExp }[] = [
  { key: 'summary', re: /^(#{1,3}\s*)?(summary|résumé)\s*:?\s*$/i },
  { key: 'important', re: /^(#{1,3}\s*)?(important(\s+notes?)?|notes?\s+importantes?)\s*:?\s*$/i },
  { key: 'next', re: /^(#{1,3}\s*)?(next(\s+steps?)?|prochaines?\s+étapes?)\s*:?\s*$/i },
];

function pushBullet(list: string[], line: string) {
  const cleaned = line.replace(/^[-*•]\s+/, '').trim();
  if (cleaned) list.push(cleaned);
}

/** Split free text into bullets (existing `-` lines, or one bullet per non-empty line). */
function linesToBullets(text: string): string[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return [];
  if (lines.some((l) => /^[-*•]\s+/.test(l))) {
    return lines.map((l) => l.replace(/^[-*•]\s+/, '').trim()).filter(Boolean);
  }
  return lines;
}

/**
 * Build display sections from DB arrays + optional legacy other_notes parse.
 * Prefer ai_important_notes / ai_next_steps when present.
 */
export function parseAiNotes(
  otherNotes: string | null | undefined,
  problemSummary?: string | null,
  aiImportant?: string[] | null,
  aiNext?: string[] | null,
): AiNoteSections {
  const out: AiNoteSections = { summary: [], important: [], next: [] };
  if (problemSummary?.trim()) {
    out.summary.push(...linesToBullets(problemSummary.trim()));
  }

  const hasArrays =
    (aiImportant != null && aiImportant.length > 0) ||
    (aiNext != null && aiNext.length > 0);
  if (hasArrays) {
    out.important.push(...(aiImportant ?? []).map((s) => s.trim()).filter(Boolean));
    out.next.push(...(aiNext ?? []).map((s) => s.trim()).filter(Boolean));
    return out;
  }

  const raw = (otherNotes ?? '').trim();
  if (!raw) return out;

  const lines = raw.split(/\r?\n/);
  let current: SectionKey | null = null;
  let sawHeader = false;
  const orphan: string[] = [];

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;
    const hdr = HEADER.find((h) => h.re.test(line));
    if (hdr) {
      current = hdr.key;
      sawHeader = true;
      continue;
    }
    if (current) pushBullet(out[current], line);
    else orphan.push(line);
  }

  if (!sawHeader) {
    out.important.push(...linesToBullets(raw));
  } else if (orphan.length) {
    out.important.unshift(...linesToBullets(orphan.join('\n')));
  }
  return out;
}

export function hasAiNoteContent(sections: AiNoteSections): boolean {
  return sections.summary.length + sections.important.length + sections.next.length > 0;
}
