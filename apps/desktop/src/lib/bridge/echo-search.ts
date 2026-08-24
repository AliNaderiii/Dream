/**
 * Echo runtime for the `search.sessions.*` family — the browser/test
 * stand-in for `dream.session_search.SessionSearchIndex`.
 *
 * Mirrors the kernel's laws, not its SQL:
 *
 * - both text sides pass through the shared Persian normalizer, so a query
 *   typed with Arabic code points finds a conversation transcribed with
 *   Farsi ones (and the snippet keeps the *stored* spelling);
 * - a title match outranks a body match (×3, like the kernel's bm25
 *   column weights);
 * - a corrupt index refuses every read with the bilingual fail-closed
 *   message; `rebuild` re-derives from the content rows and answers the
 *   document count;
 * - a query that normalises to no tokens fails closed, never lists
 *   everything.
 */

import { normalizeFa } from '@/lib/schedule/normalize-fa';

import { BridgeRpcError } from './errors';
import type { RpcParams } from './types';

/** Wire shape of one search hit (mirrors `asdict(SessionHit)`). */
export interface EchoSessionHit {
  session_id: string;
  title: string;
  snippet: string;
  score: number;
  matched_in_title: boolean;
  updated_at: number;
  source: string;
}

interface EchoDoc {
  sessionId: string;
  title: string;
  body: string;
  updatedAt: number;
  source: string;
}

const SNIPPET_WIDTH = 110;

function invalid(message: string): BridgeRpcError {
  return new BridgeRpcError({ code: -32602, message });
}

/** Bilingual fail-closed refusal for a corrupt index; nothing was wiped. */
function corruptRefusal(): BridgeRpcError {
  return invalid(
    // Gloss: «ایندکس جست‌وجوی نشست‌ها خوانا نیست یا ساختارش خراب است و تا
    // بازسازی نشود جست‌وجو انجام نمی‌شود؛ هیچ داده‌ای بی‌صدا پاک نشد.»
    '\u0627\u06cc\u0646\u062f\u06a9\u0633 \u062c\u0633\u062a\u200c\u0648\u062c\u0648 ' +
      '\u0646\u0634\u0633\u062a\u200c\u0647\u0627 \u062e\u0648\u0627\u0646\u0627 ' +
      '\u0646\u06cc\u0633\u062a \u06cc\u0627 \u0633\u0627\u062e\u062a\u0627\u0631\u0634 ' +
      '\u062e\u0631\u0627\u0628 \u0627\u0633\u062a \u0648 \u062a\u0627 \u0628\u0627\u0632' +
      '\u0633\u0627\u0632\u06cc \u0646\u0634\u0648\u062f \u062c\u0633\u062a\u200c\u0648' +
      '\u062c\u0648 \u0627\u0646\u062c\u0627\u0645 \u0646\u0645\u06cc\u200c\u0634\u0648' +
      '\u062f\u061b \u0647\u06cc\u0686 \u062f\u0627\u062f\u0647\u200c\u0627\u06cc ' +
      '\u0628\u06cc\u200c\u0635\u062f\u0627 \u067e\u0627\u06a9 \u0646\u0634\u062f. ' +
      'The session search index is unreadable or corrupt; search stays disabled ' +
      'until it is rebuilt. Nothing was silently deleted. Rebuild it to recover.',
  );
}

function tokensOf(query: string): string[] {
  const seen = new Set<string>();
  const tokens: string[] = [];
  for (const raw of query.match(/[\p{L}\p{N}]+/gu) ?? []) {
    for (const token of normalizeFa(raw).split(/\s+/)) {
      if (token && !seen.has(token)) {
        seen.add(token);
        tokens.push(token);
      }
    }
  }
  return tokens;
}

function wordHits(word: string, tokens: readonly string[]): boolean {
  const normalised = normalizeFa(word);
  return tokens.some((token) => normalised.includes(token));
}

/** Word-aligned snippet of *original* text with `[...]` around matched words. */
function extractSnippet(original: string, tokens: readonly string[]): string {
  if (!original.trim() || tokens.length === 0) return clipPlain(original);
  const words = original.match(/\S+/g) ?? [];
  const flags = words.map((word) => wordHits(word, tokens));
  if (!flags.some(Boolean)) return clipPlain(original);
  const first = flags.indexOf(true);
  let start = first;
  let end = first;
  while (words[end] !== undefined && words.slice(start, end + 1).join(' ').length < SNIPPET_WIDTH) {
    if (end < words.length - 1) end += 1;
    else if (start > 0) start -= 1;
    else break;
  }
  const segment: string[] = [];
  for (let i = start; i <= end; i += 1) {
    segment.push(flags[i] ? `[${words[i]}]` : words[i]);
  }
  let snippet = segment.join(' ');
  if (start > 0) snippet = `… ${snippet}`;
  if (end < words.length - 1) snippet = `${snippet} …`;
  return snippet;
}

function clipPlain(original: string): string {
  if (original.length <= SNIPPET_WIDTH) return original;
  const head = original.slice(0, SNIPPET_WIDTH);
  const cut = head.lastIndexOf(' ');
  return `${cut > 0 ? head.slice(0, cut) : head}…`;
}

const NOW = 1_780_000_000;

function seedDocs(): EchoDoc[] {
  return [
    {
      sessionId: 'sess-bridge',
      title: 'Bridge rollout runbook',
      body: 'Rolled out the JSON-RPC sidecar today; the bridge supervisor stayed green throughout.',
      updatedAt: NOW - 100,
      source: 'desktop',
    },
    {
      sessionId: 'sess-books',
      title: 'Book notes',
      // Farsi spelling (keheh + Farsi yeh) — an Arabic-spelled query hits it.
      body: 'دربارهٔ کتاب‌های تاریخ ایران حرف زدیم و فهرست خواندنی‌ها را بستیم.',
      updatedAt: NOW - 200,
      source: 'desktop',
    },
    {
      sessionId: 'sess-budget',
      title: 'Quarterly budget review',
      body: 'The bridge line item moved to the infrastructure envelope.',
      updatedAt: NOW - 300,
      source: 'cli',
    },
  ];
}

/** Lazily-created echo runtime for the session-search bridge family. */
export class EchoSearchRuntime {
  private docs: EchoDoc[] = seedDocs();
  private corrupt = false;

  handles(method: string): boolean {
    return method.startsWith('search.sessions.');
  }

  /** Test hook: simulate a corrupt index (fails closed until rebuilt). */
  setCorrupt(corrupt: boolean): void {
    this.corrupt = corrupt;
  }

  handle(method: string, params: RpcParams): unknown {
    switch (method) {
      case 'search.sessions.status':
        if (this.corrupt) throw corruptRefusal();
        return { healthy: true, documents: this.docs.length };
      case 'search.sessions.rebuild':
        this.corrupt = false;
        return { rebuilt: this.docs.length };
      case 'search.sessions.snippet_rules':
        return { normalized: true, highlight: 'original word boundaries', max_width_chars: 110 };
      case 'search.sessions.query':
        return { results: this.query(params) };
      default:
        return invalid(`unknown search method ${method}`);
    }
  }

  private query(params: RpcParams): EchoSessionHit[] {
    const query = params['query'];
    if (typeof query !== 'string') throw invalid('query must be a string');
    if (this.corrupt) throw corruptRefusal();
    const tokens = tokensOf(query);
    if (tokens.length === 0) {
      throw invalid(
        // Gloss: «عبارت جست‌وجو بعد از نرمال‌سازی خالی است.»
        '\u0639\u0628\u0627\u0631\u062a \u062c\u0633\u062a\u200c\u0648\u062c\u0648 ' +
          '\u0628\u0639\u062f \u0627\u0632 \u0646\u0631\u0645\u0627\u0644\u200c\u0633' +
          '\u0627\u0632\u06cc \u062e\u0627\u0644\u06cc \u0627\u0633\u062a. ' +
          'Query normalizes to no searchable tokens.',
      );
    }
    const hits: EchoSessionHit[] = [];
    for (const doc of this.docs) {
      // Whole-token matching, like the kernel's FTS5 MATCH over normalised
      // columns: a short token never matches inside a longer word.
      const titleWords = new Set(tokensOf(doc.title));
      const bodyWords = new Set(tokensOf(doc.body));
      const titleHits = tokens.filter((token) => titleWords.has(token)).length;
      const bodyHits = tokens.filter((token) => bodyWords.has(token)).length;
      if (titleHits + bodyHits === 0) continue;
      const snippet = extractSnippet(doc.body, tokens);
      const fallback =
        titleHits > 0 && !snippet.includes('[') ? extractSnippet(doc.title, tokens) : snippet;
      hits.push({
        session_id: doc.sessionId,
        title: doc.title,
        snippet: fallback,
        score: 3 * titleHits + bodyHits,
        matched_in_title: titleHits > 0,
        updated_at: doc.updatedAt,
        source: doc.source,
      });
    }
    hits.sort((a, b) => b.score - a.score || b.updated_at - a.updated_at);
    return hits;
  }
}
