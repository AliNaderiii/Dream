/**
 * Typed wrappers for the `memory.*` RPC family.
 *
 * The bridge stores importance on a 0.0–1.0 scale while the UI speaks in whole
 * stars (0–10), so every crossing of that boundary goes through
 * {@link toStars} / {@link toImportance} rather than being open-coded.
 * Client-side validation mirrors `dream/bridge/methods.py` so obviously bad
 * input never leaves the renderer, but the server remains the authority.
 */

import type { BridgeClient } from './client';
import type {
  BridgeMemory,
  MemoryCountResult,
  MemoryDeleteResult,
  MemoryKind,
  MemoryListParams,
  MemoryListResult,
  MemoryMutationResult,
  MemorySearchResult,
} from './types';

/** Hard cap the backend enforces on memory content (bytes, UTF-8). */
export const MAX_MEMORY_CONTENT_BYTES = 50 * 1024;

/** Highest importance value the star control offers. */
export const MAX_STARS = 10;

/** Backend importance (0.0–1.0) → UI stars (0–10). */
export function toStars(importance: number): number {
  if (!Number.isFinite(importance)) return 0;
  return Math.max(0, Math.min(MAX_STARS, Math.round(importance * MAX_STARS)));
}

/** UI stars (0–10) → backend importance (0.0–1.0). */
export function toImportance(stars: number): number {
  if (!Number.isFinite(stars)) return 0;
  const clamped = Math.max(0, Math.min(MAX_STARS, stars));
  return Math.round((clamped / MAX_STARS) * 100) / 100;
}

/** UTF-8 byte length, matching the server's `len(content.encode("utf-8"))`. */
export function byteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}

/**
 * Client-side check for memory content. Returns an error message, or `null`
 * when the content is acceptable.
 */
export function validateMemoryContent(content: string): string | null {
  if (!content.trim()) return 'Content must not be empty.';
  const bytes = byteLength(content);
  if (bytes > MAX_MEMORY_CONTENT_BYTES) {
    return `Content is ${formatBytes(bytes)} — the limit is 50 KB.`;
  }
  return null;
}

/** Human-readable byte size for validation messages. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

/**
 * Strip markup from memory text before rendering.
 *
 * React already escapes interpolated strings, so this is defence in depth for
 * rows written before the server-side sanitiser landed: script/style blocks and
 * stray tags are removed so a stored `<script>` never reads as content.
 */
export function sanitizeMemoryText(text: string): string {
  return text
    .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, '')
    .replace(/\son\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(/javascript:/gi, '')
    .replace(/<[^>]+>/g, '')
    .trim();
}

/** Drops `undefined`/`null` entries so the RPC params stay minimal. */
function compact(params: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) out[key] = value;
  }
  return out;
}

/** Fetch one page of memories. `cursor` comes from the previous page. */
export function listMemories(
  client: BridgeClient,
  params: MemoryListParams = {},
): Promise<MemoryListResult> {
  const { cursor, ...rest } = params;
  return client.call<MemoryListResult>(
    'memory.list',
    compact({ ...rest, cursor: cursor ? Number(cursor) : undefined }),
  );
}

/** Per-kind counts for the filter tabs. */
export function countMemories(client: BridgeClient): Promise<MemoryCountResult> {
  return client.call<MemoryCountResult>('memory.count', {});
}

/** Relevance search across the store. */
export function searchMemories(
  client: BridgeClient,
  query: string,
  limit = 20,
): Promise<MemorySearchResult> {
  return client.call<MemorySearchResult>('memory.search', { query, limit });
}

/** Fetch a single memory, or `null` when it is gone. */
export function getMemory(client: BridgeClient, memoryId: number): Promise<BridgeMemory | null> {
  return client.call<BridgeMemory | null>('memory.get', { memory_id: memoryId });
}

/** Fields accepted when creating a memory. Importance is in stars (0–10). */
export interface CreateMemoryInput {
  content: string;
  kind: MemoryKind;
  stars?: number;
  tags?: string[];
  source?: string;
}

/** Create a memory. Rejects on client-side validation failure. */
export async function createMemory(
  client: BridgeClient,
  input: CreateMemoryInput,
): Promise<MemoryMutationResult> {
  const problem = validateMemoryContent(input.content);
  if (problem) throw new Error(problem);
  return client.call<MemoryMutationResult>(
    'memory.create',
    compact({
      content: input.content,
      kind: input.kind,
      importance: input.stars === undefined ? undefined : toImportance(input.stars),
      tags: input.tags,
      source: input.source ?? 'desktop',
    }),
  );
}

/** Fields accepted when updating a memory. Importance is in stars (0–10). */
export interface UpdateMemoryInput {
  content?: string;
  kind?: MemoryKind;
  stars?: number;
  tags?: string[];
}

/** Update a memory in place. Rejects on client-side validation failure. */
export async function updateMemory(
  client: BridgeClient,
  memoryId: number,
  input: UpdateMemoryInput,
): Promise<MemoryMutationResult> {
  if (input.content !== undefined) {
    const problem = validateMemoryContent(input.content);
    if (problem) throw new Error(problem);
  }
  return client.call<MemoryMutationResult>(
    'memory.update',
    compact({
      memory_id: memoryId,
      content: input.content,
      kind: input.kind,
      importance: input.stars === undefined ? undefined : toImportance(input.stars),
      tags: input.tags,
    }),
  );
}

/** Delete a memory — archived by default, `hard` erases the row. */
export function deleteMemory(
  client: BridgeClient,
  memoryId: number,
  hard = false,
): Promise<MemoryDeleteResult> {
  return client.call<MemoryDeleteResult>('memory.delete', { memory_id: memoryId, hard });
}
