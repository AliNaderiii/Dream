/** Ephemeral transcript state isolated by pane id. Durable sessions live in Python. */

import { create } from 'zustand';

import type { Message } from '@/types';

interface PaneTranscript {
  messages: Message[];
  streaming: string;
  sending: boolean;
  error: string | null;
}

interface PaneChatState {
  transcripts: Record<string, PaneTranscript>;
  ensure: (paneId: string) => void;
  addMessage: (paneId: string, message: Message) => void;
  beginStream: (paneId: string) => void;
  appendChunk: (paneId: string, token: string) => void;
  finishStream: (paneId: string, content: string) => void;
  failStream: (paneId: string, message: string) => void;
}

const emptyTranscript = (): PaneTranscript => ({
  messages: [],
  streaming: '',
  sending: false,
  error: null,
});

export const usePaneChatStore = create<PaneChatState>()((set) => ({
  transcripts: {},
  ensure: (paneId) =>
    set((state) =>
      state.transcripts[paneId]
        ? state
        : { transcripts: { ...state.transcripts, [paneId]: emptyTranscript() } },
    ),
  addMessage: (paneId, message) =>
    set((state) => {
      const transcript = state.transcripts[paneId] ?? emptyTranscript();
      return {
        transcripts: {
          ...state.transcripts,
          [paneId]: { ...transcript, messages: [...transcript.messages, message], error: null },
        },
      };
    }),
  beginStream: (paneId) =>
    set((state) => {
      const transcript = state.transcripts[paneId] ?? emptyTranscript();
      return {
        transcripts: {
          ...state.transcripts,
          [paneId]: { ...transcript, streaming: '', sending: true, error: null },
        },
      };
    }),
  appendChunk: (paneId, token) =>
    set((state) => {
      const transcript = state.transcripts[paneId] ?? emptyTranscript();
      return {
        transcripts: {
          ...state.transcripts,
          [paneId]: { ...transcript, streaming: transcript.streaming + token },
        },
      };
    }),
  finishStream: (paneId, content) =>
    set((state) => {
      const transcript = state.transcripts[paneId] ?? emptyTranscript();
      const message: Message = {
        id: `assistant-${Date.now()}-${paneId}`,
        role: 'assistant',
        content,
        createdAt: Date.now(),
      };
      return {
        transcripts: {
          ...state.transcripts,
          [paneId]: {
            ...transcript,
            messages: [...transcript.messages, message],
            streaming: '',
            sending: false,
          },
        },
      };
    }),
  failStream: (paneId, message) =>
    set((state) => {
      const transcript = state.transcripts[paneId] ?? emptyTranscript();
      return {
        transcripts: {
          ...state.transcripts,
          [paneId]: { ...transcript, streaming: '', sending: false, error: message },
        },
      };
    }),
}));
