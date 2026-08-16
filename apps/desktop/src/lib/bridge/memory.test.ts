import { describe, expect, it } from 'vitest';

import { BridgeClient, EchoBridgeTransport } from '@/lib/bridge/client';
import {
  byteLength,
  countMemories,
  createMemory,
  deleteMemory,
  formatBytes,
  listMemories,
  sanitizeMemoryText,
  toImportance,
  toStars,
  updateMemory,
  validateMemoryContent,
} from '@/lib/bridge/memory';

function client(): BridgeClient {
  return new BridgeClient(new EchoBridgeTransport());
}

describe('importance conversion', () => {
  it('maps the 0.0–1.0 backend scale onto ten stars', () => {
    expect(toStars(0)).toBe(0);
    expect(toStars(0.5)).toBe(5);
    expect(toStars(1)).toBe(10);
    expect(toStars(0.83)).toBe(8);
  });

  it('round-trips whole stars back to importance', () => {
    expect(toImportance(0)).toBe(0);
    expect(toImportance(5)).toBe(0.5);
    expect(toImportance(10)).toBe(1);
    expect(toStars(toImportance(7))).toBe(7);
  });

  it('clamps out-of-range input instead of throwing', () => {
    expect(toStars(4)).toBe(10);
    expect(toImportance(-3)).toBe(0);
    expect(toStars(Number.NaN)).toBe(0);
  });
});

describe('validateMemoryContent', () => {
  it('accepts ordinary prose', () => {
    expect(validateMemoryContent('The user prefers dark mode.')).toBeNull();
  });

  it('rejects empty content', () => {
    expect(validateMemoryContent('   ')).toMatch(/empty/i);
  });

  it('rejects content over the 50 KB cap', () => {
    const oversized = 'x'.repeat(50 * 1024 + 1);
    expect(validateMemoryContent(oversized)).toMatch(/50 KB/);
  });

  it('counts multi-byte characters as UTF-8 bytes', () => {
    expect(byteLength('سلام')).toBe(8);
    expect(formatBytes(2048)).toBe('2.0 KB');
  });
});

describe('sanitizeMemoryText', () => {
  it('strips script blocks and inline handlers', () => {
    expect(sanitizeMemoryText('hi<script>alert(1)</script>')).toBe('hi');
    expect(sanitizeMemoryText('<div onclick="x()">note</div>')).toBe('note');
    expect(sanitizeMemoryText('javascript:alert(1)')).toBe('alert(1)');
  });

  it('leaves Persian prose untouched', () => {
    expect(sanitizeMemoryText('کاربر فارسی را ترجیح می‌دهد')).toBe('کاربر فارسی را ترجیح می‌دهد');
  });
});

describe('memory RPC wrappers over the echo transport', () => {
  it('pages with the returned cursor', async () => {
    const c = client();
    const first = await listMemories(c, { limit: 4 });
    expect(first.memories).toHaveLength(4);
    expect(first.has_more).toBe(true);
    expect(first.next_cursor).toBe('4');

    const second = await listMemories(c, { limit: 4, cursor: first.next_cursor });
    expect(second.memories[0]?.id).not.toBe(first.memories[0]?.id);
    expect(second.total).toBe(first.total);
  });

  it('filters by kind, search text and importance', async () => {
    const c = client();
    const semantic = await listMemories(c, { kind_filter: 'semantic', limit: 50 });
    expect(semantic.memories.every((m) => m.kind === 'semantic')).toBe(true);

    const searched = await listMemories(c, { search_query: 'bridge', limit: 50 });
    expect(searched.memories.length).toBeGreaterThan(0);
    expect(searched.memories.every((m) => m.content.toLowerCase().includes('bridge'))).toBe(true);

    const important = await listMemories(c, { min_importance: 0.8, limit: 50 });
    expect(important.memories.every((m) => m.importance >= 0.8)).toBe(true);
  });

  it('honours the sort selector', async () => {
    const c = client();
    const oldest = await listMemories(c, { sort_by: 'date_oldest', limit: 50 });
    const stamps = oldest.memories.map((m) => m.created_at);
    expect([...stamps].sort((a, b) => a - b)).toEqual(stamps);

    const byImportance = await listMemories(c, { sort_by: 'importance', limit: 50 });
    const scores = byImportance.memories.map((m) => m.importance);
    expect([...scores].sort((a, b) => b - a)).toEqual(scores);
  });

  it('creates, updates and deletes a memory', async () => {
    const c = client();
    const before = await countMemories(c);

    const created = await createMemory(c, {
      content: 'A brand new fact.',
      kind: 'semantic',
      stars: 8,
    });
    expect(created.memory.importance).toBeCloseTo(0.8);

    const updated = await updateMemory(c, created.memory.id, { content: 'Revised.', stars: 2 });
    expect(updated.memory.content).toBe('Revised.');
    expect(toStars(updated.memory.importance)).toBe(2);

    await deleteMemory(c, created.memory.id);
    const after = await countMemories(c);
    expect(after.total).toBe(before.total);
    expect(after.archived).toBe(before.archived + 1);
  });

  it('refuses oversized content before hitting the bridge', async () => {
    const c = client();
    await expect(
      createMemory(c, { content: 'x'.repeat(50 * 1024 + 1), kind: 'semantic' }),
    ).rejects.toThrow(/50 KB/);
  });
});
