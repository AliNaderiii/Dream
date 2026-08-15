import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ChatInput } from './chat-input';
import { MarkdownMessage } from './markdown-message';
import { textDirection } from '@/utils/text-direction';

describe('conversation direction and markdown', () => {
  it('detects Persian and keeps English/code LTR', () => {
    expect(textDirection('سلام Dream 123')).toBe('rtl');
    expect(textDirection('Hello world')).toBe('ltr');
    expect(textDirection('`const فارسی = true` English')).toBe('ltr');
  });

  it('renders markdown without interpreting raw HTML', () => {
    const { container } = render(
      <MarkdownMessage content={'**safe** <script>alert(1)</script>\n\n```ts\nconst x = 1\n```'} />,
    );
    expect(screen.getByText('safe').tagName).toBe('STRONG');
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText(/<script>/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy code' })).toBeInTheDocument();
  });
});

describe('ChatInput', () => {
  it('sends on Enter, preserves Shift+Enter, and rejects whitespace', () => {
    const send = vi.fn();
    const change = vi.fn();
    const { rerender } = render(
      <ChatInput
        value="hello"
        onChange={change}
        onSend={send}
        onStop={vi.fn()}
        streaming={false}
      />,
    );
    fireEvent.keyDown(screen.getByLabelText('Message Dream'), { key: 'Enter', shiftKey: true });
    expect(send).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByLabelText('Message Dream'), { key: 'Enter' });
    expect(send).toHaveBeenCalledOnce();
    rerender(
      <ChatInput value="   " onChange={change} onSend={send} onStop={vi.fn()} streaming={false} />,
    );
    fireEvent.keyDown(screen.getByLabelText('Message Dream'), { key: 'Enter' });
    expect(send).toHaveBeenCalledOnce();
  });

  it('shows a stop button during streaming', () => {
    const stop = vi.fn();
    render(<ChatInput value="" onChange={vi.fn()} onSend={vi.fn()} onStop={stop} streaming />);
    fireEvent.click(screen.getByRole('button', { name: 'Stop generation' }));
    expect(stop).toHaveBeenCalledOnce();
  });
});
