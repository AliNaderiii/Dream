/**
 * Snippet parsing and normalised matching for session search (MEM Stage F).
 *
 * The kernel's snippet wraps every matched word in ASCII ``[...]`` markers and
 * slices the original text — so highlighting the user's own spelling is a
 * *parsing* problem, not an HTML problem: segments are plain text, rendered
 * through React (never markup). ``[[`` / ``]]`` are the kernel's escaped
 * literal brackets; an unbalanced ``[`` degrades to plain text instead of
 * blanking the snippet.
 *
 * Matching runs through the shared Persian normalizer
 * (`@/lib/schedule/normalize-fa`): a query typed with Arabic code points hits
 * a conversation transcribed with Farsi ones, and the snippet keeps the
 * stored spelling.
 */

import { normalizeFa } from '@/lib/schedule/normalize-fa';

/** One parsed run of a snippet: verbatim text plus a highlight flag. */
export interface SnippetSegment {
  text: string;
  highlight: boolean;
}

// Sentinels for escaped literal brackets; impossible in kernel snippets.
const ESCAPED_OPEN = '\u0001';
const ESCAPED_CLOSE = '\u0002';

function unmask(text: string): string {
  return text.replaceAll(ESCAPED_OPEN, '[').replaceAll(ESCAPED_CLOSE, ']');
}

/** Split a kernel snippet into plain and highlighted runs. Text only. */
export function parseSnippet(snippet: string): SnippetSegment[] {
  if (!snippet) return [];
  const masked = snippet.replaceAll('[[', ESCAPED_OPEN).replaceAll(']]', ESCAPED_CLOSE);
  const segments: SnippetSegment[] = [];
  let plain = '';
  let index = 0;
  while (index < masked.length) {
    const ch = masked[index];
    if (ch === '[') {
      const end = masked.indexOf(']', index + 1);
      if (end === -1) {
        // Unbalanced marker: literal bracket, never a blanked snippet.
        plain += '[';
        index += 1;
        continue;
      }
      if (plain) {
        segments.push({ text: unmask(plain), highlight: false });
        plain = '';
      }
      segments.push({ text: unmask(masked.slice(index + 1, end)), highlight: true });
      index = end + 1;
      continue;
    }
    plain += ch;
    index += 1;
  }
  if (plain) segments.push({ text: unmask(plain), highlight: false });
  return segments;
}

/** Whether any run of a parsed snippet carries a highlight. */
export function hasHighlight(segments: readonly SnippetSegment[]): boolean {
  return segments.some((segment) => segment.highlight);
}

/**
 * Query → normalised, de-duplicated tokens through the shared normalizer.
 * Word extraction mirrors the kernel's ``[^\W_]+`` regex: punctuation-only
 * input tokenises to nothing, Persian/Arabic-Indic digits fold to ASCII.
 */
export function tokenizeQuery(query: string): string[] {
  const seen = new Set<string>();
  const tokens: string[] = [];
  const words = query.match(/[\p{L}\p{N}]+/gu) ?? [];
  for (const raw of words) {
    for (const token of normalizeFa(raw).split(/\s+/)) {
      if (token && !seen.has(token)) {
        seen.add(token);
        tokens.push(token);
      }
    }
  }
  return tokens;
}

/** Whether a verbatim word carries one of the query's normalised tokens. */
function wordMatches(word: string, tokens: readonly string[]): boolean {
  const normalised = normalizeFa(word);
  return tokens.some((token) => normalised.includes(token));
}

/**
 * Mark matched words of *original* text with ``[...]`` (kernel convention),
 * keeping the stored spelling. Used where the dialog must highlight a title
 * the kernel did not snippet.
 */
export function markMatches(text: string, query: string): string {
  const tokens = tokenizeQuery(query);
  if (!text.trim() || tokens.length === 0) return text;
  let marked = false;
  const replaced = text
    .split(/(\s+)/)
    .map((piece) => {
      if (/^\s+$/.test(piece) || !piece) return piece;
      if (!wordMatches(piece, tokens)) return piece;
      marked = true;
      return `[${piece}]`;
    })
    .join('');
  return marked ? replaced : text;
}
