// A task has a name and a description, stored together in its one text
// column: the first line is the name, the rest the description.

export function splitTask(text: string | null | undefined): { name: string; details: string } {
  const s = (text ?? '').replace(/\r\n/g, '\n').trim();
  const nl = s.indexOf('\n');
  if (nl < 0) return { name: s, details: '' };
  return { name: s.slice(0, nl).trim(), details: s.slice(nl + 1).trim() };
}

export function joinTask(name: string, details: string): string {
  const n = name.replace(/\s+/g, ' ').trim();
  const d = details.trim();
  return d ? `${n}\n${d}` : n;
}
