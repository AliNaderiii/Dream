import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { Message } from '@/types';

interface ConversationState {
  messages: Record<string, Message[]>;
  drafts: Record<string, string>;
  setMessages: (sessionId: string, messages: Message[]) => void;
  addMessage: (sessionId: string, message: Message) => void;
  patchMessage: (sessionId: string, messageId: string, patch: Partial<Message>) => void;
  appendToken: (sessionId: string, messageId: string, token: string) => void;
  setDraft: (sessionId: string, draft: string) => void;
  clear: (sessionId: string) => void;
}

export const useConversationStore = create<ConversationState>()(
  persist(
    (set) => ({
      messages: {},
      drafts: {},
      setMessages: (sessionId, messages) =>
        set((state) => ({ messages: { ...state.messages, [sessionId]: messages } })),
      addMessage: (sessionId, message) =>
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: [...(state.messages[sessionId] ?? []), message],
          },
        })),
      patchMessage: (sessionId, messageId, patch) =>
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: (state.messages[sessionId] ?? []).map((message) =>
              message.id === messageId ? { ...message, ...patch } : message,
            ),
          },
        })),
      appendToken: (sessionId, messageId, token) =>
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: (state.messages[sessionId] ?? []).map((message) =>
              message.id === messageId ? { ...message, content: message.content + token } : message,
            ),
          },
        })),
      setDraft: (sessionId, draft) =>
        set((state) => ({ drafts: { ...state.drafts, [sessionId]: draft } })),
      clear: (sessionId) =>
        set((state) => {
          const messages = { ...state.messages };
          delete messages[sessionId];
          return { messages };
        }),
    }),
    {
      name: 'dream-conversations-v1',
      partialize: (state) => ({ messages: state.messages, drafts: state.drafts }),
    },
  ),
);
