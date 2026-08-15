import { PlugZap, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { ApprovalDialog } from '@/components/conversation/approval-dialog';
import { ChatInput, type PendingAttachment } from '@/components/conversation/chat-input';
import { ChatTranscript } from '@/components/conversation/chat-transcript';
import { useBridge } from '@/lib/bridge/hooks';
import type { BridgeTurn } from '@/lib/bridge/types';
import { useConversationStore } from '@/stores/use-conversation-store';
import { useSessionStore } from '@/stores/use-session-store';
import type { MessageToolCall } from '@/types';

function id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
const EMPTY_MESSAGES: never[] = [];

export function ChatRoute() {
  const { sessionId = '' } = useParams<{ sessionId: string }>();
  const session = useSessionStore((state) => state.sessions.find((item) => item.id === sessionId));
  const setActiveSession = useSessionStore((state) => state.setActiveSession);
  const recordMessages = useSessionStore((state) => state.recordMessages);
  const messages = useConversationStore((state) => state.messages[sessionId] ?? EMPTY_MESSAGES);
  const draft = useConversationStore((state) => state.drafts[sessionId] ?? '');
  const { addMessage, appendToken, patchMessage, setDraft } = useConversationStore();
  const { call, stream, state: bridgeState, reconnect } = useBridge();
  const [streaming, setStreaming] = useState(false);

  useEffect(() => {
    setActiveSession(sessionId);
  }, [sessionId, setActiveSession]);

  const sessionTitle = session?.title ?? 'New session';
  const ensureRemote = useCallback(async () => {
    try {
      const existing = await call<unknown>('session.get', { session_id: sessionId });
      if (!existing) await call('session.create', { session_id: sessionId, title: sessionTitle });
    } catch {
      await call('session.create', { session_id: sessionId, title: sessionTitle });
    }
  }, [call, sessionTitle, sessionId]);

  useEffect(() => {
    if (bridgeState === 'ready' && sessionId) void ensureRemote();
  }, [bridgeState, ensureRemote, sessionId]);

  const send = useCallback(
    async (attachments: PendingAttachment[] = [], retryText?: string) => {
      const content = (retryText ?? draft).trim();
      if (!content || streaming || bridgeState !== 'ready') return;
      await ensureRemote();
      if (!retryText) {
        addMessage(sessionId, {
          id: id('user'),
          role: 'user',
          content,
          createdAt: Date.now(),
          status: 'complete',
          attachments,
        });
        setDraft(sessionId, '');
      }
      const assistantId = id('assistant');
      addMessage(sessionId, {
        id: assistantId,
        role: 'assistant',
        content: '',
        createdAt: Date.now(),
        status: 'streaming',
      });
      setStreaming(true);
      try {
        const turn = await stream<BridgeTurn>(
          'conversation.send',
          { session_id: sessionId, message: content, attachments },
          (chunk) => appendToken(sessionId, assistantId, chunk.token),
        );
        const toolCalls: MessageToolCall[] = (turn.tool_calls ?? []).map((tool, index) => ({
          id: `${assistantId}-tool-${index}`,
          name: tool.name,
          arguments: tool.arguments,
          result: tool.result,
          status: tool.allowed ? 'ok' : 'blocked',
          risk: tool.allowed ? 'safe' : 'dangerous',
        }));
        patchMessage(sessionId, assistantId, {
          content: turn.reply ?? '',
          status: 'complete',
          toolCalls,
        });
        recordMessages(sessionId, 2);
      } catch (error) {
        patchMessage(sessionId, assistantId, {
          role: 'error',
          content:
            error instanceof Error ? error.message : 'Dream could not complete this response.',
          status: 'error',
        });
        recordMessages(sessionId, 1);
      } finally {
        setStreaming(false);
      }
    },
    [
      addMessage,
      appendToken,
      bridgeState,
      draft,
      ensureRemote,
      patchMessage,
      recordMessages,
      sessionId,
      setDraft,
      stream,
      streaming,
    ],
  );

  const retry = useMemo(() => {
    const lastUser = [...messages].reverse().find((message) => message.role === 'user');
    return lastUser ? () => void send([], lastUser.content) : undefined;
  }, [messages, send]);

  if (!session)
    return (
      <div className="flex h-full items-center justify-center text-fg-secondary">
        Session not found. Start a new session from the sidebar.
      </div>
    );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <h2 className="sr-only">{session.title}</h2>
      {bridgeState === 'disconnected' && (
        <div
          role="alert"
          className="flex items-center justify-center gap-2 border-b border-danger-fg/30 bg-danger-bg px-3 py-2 text-danger-fg"
        >
          <PlugZap className="size-4" />
          Bridge disconnected.
          <button
            type="button"
            onClick={reconnect}
            className="inline-flex items-center gap-1 underline"
          >
            <RefreshCw className="size-3.5" />
            Retry
          </button>
        </div>
      )}
      <div className="min-h-0 flex-1">
        <ChatTranscript messages={messages} onRetry={retry} />
      </div>
      <ChatInput
        value={draft}
        onChange={(value) => setDraft(sessionId, value)}
        onSend={(files) => void send(files)}
        onStop={() => {
          void call('conversation.stop', { session_id: sessionId });
          setStreaming(false);
        }}
        streaming={streaming}
        disabled={bridgeState !== 'ready'}
      />
      <ApprovalDialog />
    </div>
  );
}
