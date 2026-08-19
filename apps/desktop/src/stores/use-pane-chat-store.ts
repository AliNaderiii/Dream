/** Ephemeral transcript state isolated by pane id. Durable sessions live in Python. */

import { create } from 'zustand';

import type { Message, PendingApproval, ToolCardEntry } from '@/types';

interface PaneTranscript {
  messages: Message[];
  streaming: string;
  sending: boolean;
  error: string | null;
  /** Pending approval dialog for this pane, if any (S07). */
  pendingApproval: PendingApproval | null;
  /** Set of tool names the user chose "always allow" for this session (S07). */
  alwaysAllowTools: Set<string>;
  /** Tool cards accumulated during the current streaming turn (S07). */
  currentToolCards: ToolCardEntry[];
}

interface PaneChatState {
  transcripts: Record<string, PaneTranscript>;
  ensure: (paneId: string) => void;
  addMessage: (paneId: string, message: Message) => void;
  beginStream: (paneId: string) => void;
  appendChunk: (paneId: string, token: string) => void;
  finishStream: (paneId: string, content: string) => void;
  failStream: (paneId: string, message: string) => void;
  /** Add a tool card to the streaming transcript (S07). */
  addToolCard: (paneId: string, card: ToolCardEntry) => void;
  /** Update a tool card's status/result (S07). */
  updateToolCard: (paneId: string, cardId: string, changes: Partial<ToolCardEntry>) => void;
  /** Set or clear the pending approval dialog for a pane (S07). */
  setPendingApproval: (paneId: string, approval: PendingApproval | null) => void;
  /** Mark a tool as "always allow" for this session/pane (S07). */
  alwaysAllowTool: (paneId: string, toolName: string) => void;
  /** Check if a tool is in the always-allow set for a pane (S07). */
  isAlwaysAllowed: (paneId: string, toolName: string) => boolean;
}

const emptyTranscript = (): PaneTranscript => ({
  messages: [],
  streaming: '',
  sending: false,
  error: null,
  pendingApproval: null,
  alwaysAllowTools: new Set<string>(),
  currentToolCards: [],
});

export const usePaneChatStore = create<PaneChatState>()((set, get) => ({
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
  addToolCard: (paneId, card) =>
    set((state) => {
      const transcript = state.transcripts[paneId] ?? emptyTranscript();
      return {
        transcripts: {
          ...state.transcripts,
          [paneId]: {
            ...transcript,
            currentToolCards: [...transcript.currentToolCards, card],
          },
        },
      };
    }),
  updateToolCard: (paneId, cardId, changes) =>
    set((state) => {
      const transcript = state.transcripts[paneId] ?? emptyTranscript();
      const updated = transcript.currentToolCards.map((c) =>
        c.id === cardId ? { ...c, ...changes } : c,
      );
      return {
        transcripts: {
          ...state.transcripts,
          [paneId]: { ...transcript, currentToolCards: updated },
        },
      };
    }),
  setPendingApproval: (paneId, approval) =>
    set((state) => {
      const transcript = state.transcripts[paneId] ?? emptyTranscript();
      return {
        transcripts: {
          ...state.transcripts,
          [paneId]: { ...transcript, pendingApproval: approval },
        },
      };
    }),
  alwaysAllowTool: (paneId, toolName) =>
    set((state) => {
      const transcript = state.transcripts[paneId] ?? emptyTranscript();
      const next = new Set(transcript.alwaysAllowTools);
      next.add(toolName);
      return {
        transcripts: {
          ...state.transcripts,
          [paneId]: { ...transcript, alwaysAllowTools: next },
        },
      };
    }),
  isAlwaysAllowed: (paneId, toolName) => {
    const transcript = get().transcripts[paneId];
    return transcript?.alwaysAllowTools.has(toolName) ?? false;
  },
}));
