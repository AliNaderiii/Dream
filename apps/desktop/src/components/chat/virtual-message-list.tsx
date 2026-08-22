import { type ReactNode, type RefObject, useCallback } from 'react';

import { ToolCard } from '@/components/chat/tool-card';
import type { PaneChatListItem } from '@/components/panes/pane-chat-model';
import { VariableVirtualList } from '@/components/shared/variable-virtual-list';
import { cn } from '@/utils/cn';

export type ChatListItem = PaneChatListItem;

interface VirtualMessageListProps {
  items: readonly ChatListItem[];
  label: string;
  scrollRef?: RefObject<HTMLDivElement | null>;
  onScroll?: () => void;
  footer?: ReactNode;
}

export function VirtualMessageList({
  items,
  label,
  scrollRef,
  onScroll,
  footer,
}: VirtualMessageListProps) {
  const getKey = useCallback((item: ChatListItem) => item.message.id, []);
  const renderItem = useCallback(
    (item: ChatListItem, index: number) => (
      <article
        aria-posinset={index + 1}
        aria-setsize={items.length}
        aria-live={item.streaming ? 'polite' : undefined}
        aria-busy={item.streaming || undefined}
        data-message-index={index}
        className="pb-3"
      >
        {item.message.toolCards && item.message.toolCards.length > 0 && (
          <div className="mb-1 space-y-1">
            {item.message.toolCards.map((card) => (
              <ToolCard key={card.id} card={card} />
            ))}
          </div>
        )}
        {item.message.content && (
          <div
            className={cn(
              'max-w-[85%] rounded-lg px-3 py-2 text-body whitespace-pre-wrap',
              item.message.role === 'user'
                ? 'ms-auto bg-accent text-fg-inverse'
                : 'me-auto border border-border-default bg-surface text-fg-primary',
              item.streaming && 'streaming-sweep',
            )}
          >
            {item.message.content}
            {item.streaming && (
              <span className="ms-0.5 inline-block h-4 w-0.5 bg-accent" aria-hidden />
            )}
          </div>
        )}
      </article>
    ),
    [items.length],
  );

  return (
    <VariableVirtualList
      items={items}
      getKey={getKey}
      renderItem={renderItem}
      estimatedItemSize={128}
      viewportSize={640}
      overscan={6}
      threshold={100}
      tailFollow
      className="min-h-0 flex-1 overflow-y-auto px-4 py-3"
      ariaLabel={label}
      listRef={scrollRef}
      onScroll={onScroll}
      footer={footer}
    />
  );
}
