import type { CommandItem } from '@/hooks/use-keyboard-shortcuts';

/** Script-safe normalization for English/Persian command matching. */
export function normalizeCommandText(value: string): string {
  return value
    .normalize('NFKC')
    .replace(/[\u064B-\u065F\u0670]/g, '')
    .replace(/[يى]/g, 'ی')
    .replace(/ك/g, 'ک')
    .toLocaleLowerCase()
    .trim();
}

/** Lower is better; Infinity means no ordered-subsequence match. */
export function fuzzyScore(needle: string, haystack: string): number {
  if (!needle) return 0;
  const exact = haystack.indexOf(needle);
  if (exact >= 0) return exact;

  let cursor = 0;
  let gap = 0;
  let first = -1;
  for (let index = 0; index < haystack.length && cursor < needle.length; index += 1) {
    if (haystack[index] === needle[cursor]) {
      if (first < 0) first = index;
      cursor += 1;
    } else if (cursor > 0) gap += 1;
  }
  return cursor === needle.length ? 100 + first + gap : Number.POSITIVE_INFINITY;
}

export function searchCommands(commands: CommandItem[], query: string): CommandItem[] {
  const needle = normalizeCommandText(query);
  if (!needle) return commands;

  return commands
    .map((command, order) => {
      const target = normalizeCommandText(
        [command.description, command.category, ...(command.keywords ?? [])].join(' '),
      );
      return { command, order, score: fuzzyScore(needle, target) };
    })
    .filter((entry) => Number.isFinite(entry.score))
    .sort((a, b) => a.score - b.score || a.order - b.order)
    .map((entry) => entry.command);
}
