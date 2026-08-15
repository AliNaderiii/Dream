import { ArrowDown, Bot, Check, Copy, RefreshCw, User } from 'lucide-react';
import { useState } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { useRef } from 'react';

import { MarkdownMessage } from './markdown-message';
import { ToolCallCard } from './tool-call-card';
import type { Message } from '@/types';
import { cn } from '@/utils/cn';
import { textDirection } from '@/utils/text-direction';

function relativeTime(timestamp: number): string {
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1_000));
  if (seconds < 45) return 'now';
  if (seconds < 3_600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3_600)}h ago`;
  return `${Math.floor(seconds / 86_400)}d ago`;
}

function MessageRow({ message, onRetry }: { message: Message; onRetry?: () => void }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';
  const isError = message.role === 'error';
  const direction = textDirection(message.content);
  const Icon = isUser ? User : Bot;
  return (
    <article
      tabIndex={0}
      aria-label={`${message.role} message`}
      className={cn(
        'group mx-auto flex w-full max-w-4xl gap-3 px-5 py-4',
        isUser && 'bg-surface-2/45',
        isError && 'bg-danger-bg/30',
      )}
    >
      <div
        className={cn(
          'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md',
          isUser
            ? 'bg-accent-soft text-accent-text'
            : isError
              ? 'bg-danger-bg text-danger-fg'
              : 'bg-surface-raised text-fg-secondary',
        )}
      >
        <Icon className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2 text-caption">
          <strong>{isUser ? 'You' : isError ? 'Error' : 'Dream'}</strong>
          <time
            className="text-fg-muted"
            title={new Date(message.createdAt).toLocaleString()}
            dateTime={new Date(message.createdAt).toISOString()}
          >
            {relativeTime(message.createdAt)}
          </time>
          {message.status === 'streaming' && (
            <span className="text-accent-text" aria-live="polite">
              Streaming
            </span>
          )}
        </div>
        <div dir={direction} className={cn(direction === 'rtl' ? 'text-right' : 'text-left')}>
          {message.status === 'streaming' && !message.content ? (
            <div className="typing-dots" role="status" aria-label="Dream is thinking">
              <span />
              <span />
              <span />
            </div>
          ) : (
            <MarkdownMessage content={message.content} />
          )}
          {message.status === 'streaming' && message.content && (
            <span className="streaming-cursor" aria-hidden />
          )}
        </div>
        {message.attachments?.map((file) => (
          <span
            key={file.name}
            className="mt-2 inline-flex rounded-md border border-border-default bg-surface px-2 py-1 text-caption"
          >
            📎 {file.name}
          </span>
        ))}
        {message.toolCalls?.map((call) => (
          <ToolCallCard key={call.id} call={call} />
        ))}
        {isError && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex items-center gap-1 rounded-md border border-danger-fg/30 px-2.5 py-1.5 text-caption text-danger-fg hover:bg-danger-bg"
          >
            <RefreshCw className="size-3.5" />
            Retry
          </button>
        )}
      </div>
      <button
        type="button"
        aria-label="Copy message"
        title="Copy message"
        onClick={() => {
          void navigator.clipboard?.writeText(message.content);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1_500);
        }}
        className="self-start rounded-sm p-1.5 text-fg-muted opacity-0 hover:bg-surface-raised hover:text-fg-primary group-hover:opacity-100 focus:opacity-100"
      >
        {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      </button>
    </article>
  );
}

export function ChatTranscript({
  messages,
  onRetry,
}: {
  messages: Message[];
  onRetry?: () => void;
}) {
  const virtuoso = useRef<VirtuosoHandle>(null);
  const [atBottom, setAtBottom] = useState(true);
  if (!messages.length)
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <div>
          <Bot className="mx-auto mb-3 size-9 text-accent-text" />
          <h2 className="text-h2 font-semibold">How can I help?</h2>
          <p className="mt-1 text-fg-secondary">
            Ask in English or فارسی. Markdown, code, and files are supported.
          </p>
        </div>
      </div>
    );
  return (
    <div className="relative h-full" role="log" aria-live="polite" aria-relevant="additions text">
      <Virtuoso
        ref={virtuoso}
        data={messages}
        computeItemKey={(_, message) => message.id}
        initialTopMostItemIndex={messages.length - 1}
        followOutput={(bottom) => (bottom ? 'smooth' : false)}
        atBottomStateChange={setAtBottom}
        itemContent={(_, message) => (
          <MessageRow message={message} onRetry={message.role === 'error' ? onRetry : undefined} />
        )}
      />
      {!atBottom && (
        <button
          type="button"
          onClick={() =>
            virtuoso.current?.scrollToIndex({ index: messages.length - 1, behavior: 'smooth' })
          }
          className="absolute bottom-4 start-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full border border-border-default bg-surface-raised px-3 py-2 text-caption shadow-e2"
        >
          <ArrowDown className="size-4" />
          Jump to bottom
        </button>
      )}
    </div>
  );
}
