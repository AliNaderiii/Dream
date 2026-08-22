import type { Message } from '@/types';

export interface PaneChatListItem {
  message: Message;
  streaming?: boolean;
}

/** Builds the virtual feed model without mutating settled transcript data. */
export function paneChatItems(
  messages: readonly Message[],
  streaming: string | undefined,
  paneId: string,
): PaneChatListItem[] {
  const items: PaneChatListItem[] = messages.map((message) => ({ message }));
  if (!streaming) return items;
  items.push({
    message: {
      id: `streaming-${paneId}`,
      role: 'assistant',
      content: streaming,
      createdAt: 0,
    },
    streaming: true,
  });
  return items;
}
