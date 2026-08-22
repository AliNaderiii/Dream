import { describe, expect, it } from 'vitest';

import { paneChatItems } from '@/components/panes/pane-chat-model';
import type { Message } from '@/types';

const settled: Message[] = [
  { id: 'user-1', role: 'user', content: 'Question', createdAt: 1 },
  { id: 'assistant-1', role: 'assistant', content: 'Answer', createdAt: 2 },
];

describe('paneChatItems', () => {
  it('preserves settled message identity without a provisional row', () => {
    const items = paneChatItems(settled, '', 'pane-1');
    expect(items.map((item) => item.message)).toEqual(settled);
    expect(items.some((item) => item.streaming)).toBe(false);
  });

  it('appends one deterministic streaming row after settled messages', () => {
    const items = paneChatItems(settled, 'Live answer', 'pane-1');
    expect(items).toHaveLength(3);
    expect(items[2]).toEqual({
      message: {
        id: 'streaming-pane-1',
        role: 'assistant',
        content: 'Live answer',
        createdAt: 0,
      },
      streaming: true,
    });
    expect(settled).toHaveLength(2);
  });
});
