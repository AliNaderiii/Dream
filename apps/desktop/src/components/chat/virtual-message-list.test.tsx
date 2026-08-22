import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { type ChatListItem, VirtualMessageList } from '@/components/chat/virtual-message-list';

const items: ChatListItem[] = Array.from({ length: 500 }, (_, index) => ({
  message: {
    id: `message-${index}`,
    role: index % 2 === 0 ? 'user' : 'assistant',
    content: `Message ${index} ${'variable content '.repeat((index % 7) + 1)}`,
    createdAt: 1_700_000_000_000 + index,
  },
}));

describe('VirtualMessageList', () => {
  it('mounts fewer than 60 rows for 500 variable-height messages', () => {
    const { container } = render(<VirtualMessageList items={items} label="Conversation" />);
    const rows = container.querySelectorAll('[data-message-index]');
    console.info(`message_fixture_rows=500 mounted_message_rows=${rows.length}`);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(60);
    expect(screen.getByText(/Message 499/)).toBeInTheDocument();
  });

  it('keeps the live streaming row in the same bounded feed', () => {
    const withStreaming = [
      ...items,
      {
        message: {
          id: 'streaming',
          role: 'assistant' as const,
          content: 'Live streamed response',
          createdAt: 1_700_000_001_000,
        },
        streaming: true,
      },
    ];
    const { container } = render(
      <VirtualMessageList items={withStreaming} label="Streaming conversation" />,
    );
    const feed = screen.getByRole('feed', { name: 'Streaming conversation' });
    Object.defineProperties(feed, {
      scrollHeight: { configurable: true, value: 64_128 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });
    feed.scrollTop = feed.scrollHeight;
    fireEvent.scroll(feed);
    expect(screen.getByText('Live streamed response')).toBeInTheDocument();
    expect(container.querySelectorAll('[data-message-index]').length).toBeLessThan(60);
  });
});
