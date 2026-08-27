/** One isolated pane: model controls, docking surface, and routed content. */

import {
  ArrowDownToLine,
  ArrowRightToLine,
  Bot,
  GripVertical,
  Maximize2,
  MessageSquare,
  Send,
  Square,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { DragEvent, FormEvent, KeyboardEvent, MouseEvent } from 'react';

import { ApprovalDialog } from '@/components/chat/approval-dialog';
import { CompactionBar } from '@/components/chat/compaction-bar';
import { resolveApprovalOnBridge } from '@/components/chat/approval-policy';
import { CouncilButton } from '@/components/chat/council-button';
import { VirtualMessageList } from '@/components/chat/virtual-message-list';
import { paneChatItems } from '@/components/panes/pane-chat-model';
import { dockEdgeAt } from '@/components/panes/pane-geometry';
import { Button } from '@/components/ui/button';
import { getBridgeClient } from '@/lib/bridge/client';
import { useTranslation } from '@/lib/i18n';
import { createFrameBatcher } from '@/lib/performance/frame-batcher';
import { RPC_ERROR } from '@/lib/bridge/types';
import type { BridgeTurn } from '@/lib/bridge/types';
import type { DockEdge, PaneState } from '@/stores/use-layout-store';
import { useLayoutStore } from '@/stores/use-layout-store';
import { usePaneChatStore } from '@/stores/use-pane-chat-store';
import { useProviderStore } from '@/stores/use-provider-store';
import { SafeIcon } from '@/utils/icons';
import type { ApprovalDecision, Message, Provider, ToolCardEntry } from '@/types';
import { cn } from '@/utils/cn';

const PANE_DRAG_TYPE = 'application/x-dream-pane';

/** Module-level typed resolver map — replaces the previous `window as any` hack. */
const approvalResolvers = new Map<string, (decision: ApprovalDecision) => void>();

interface PaneProps {
  pane: PaneState;
  active: boolean;
}

function selectedModelValue(pane: PaneState, providers: Provider[]): string {
  const provider = providers.find((item) => item.id === pane.providerId);
  const model = provider?.enabledModelIds.includes(pane.modelName)
    ? pane.modelName
    : provider?.enabledModelIds[0];
  return model ? `${pane.providerId}::${model}` : '';
}

function dockEdge(event: DragEvent<HTMLElement>): DockEdge {
  const rect = event.currentTarget.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width;
  const y = (event.clientY - rect.top) / rect.height;
  return dockEdgeAt(x, y, document.documentElement.dir === 'rtl');
}

export function Pane({ pane, active }: PaneProps) {
  const { t } = useTranslation('chat');
  const providers = useProviderStore((state) => state.providers);
  const setActivePane = useLayoutStore((state) => state.setActivePane);
  const addPane = useLayoutStore((state) => state.addPane);
  const closePane = useLayoutStore((state) => state.closePane);
  const toggleMaximize = useLayoutStore((state) => state.toggleMaximize);
  const updatePane = useLayoutStore((state) => state.updatePane);
  const dockPane = useLayoutStore((state) => state.dockPane);
  const [overEdge, setOverEdge] = useState<DockEdge | null>(null);
  const modelSelect = useRef<HTMLSelectElement>(null);

  const configureSession = (changes: Partial<PaneState>) => {
    updatePane(pane.id, changes);
    if (pane.sessionId) {
      void getBridgeClient()
        .call('session.configure', {
          session_id: pane.sessionId,
          provider: changes.providerId ?? pane.providerId,
          model: changes.modelName ?? pane.modelName,
          reasoning_effort: changes.reasoningEffort ?? pane.reasoningEffort,
        })
        .catch(() => {
          // The pane selection is still valid and persisted; a restarting
          // sidecar receives it when this pane next creates/sends a session.
        });
    }
  };

  useEffect(() => {
    const quickProvider = (event: globalThis.KeyboardEvent) => {
      if (!active || (!event.metaKey && !event.ctrlKey) || event.key.toLowerCase() !== 'p') return;
      event.preventDefault();
      modelSelect.current?.focus();
      modelSelect.current?.showPicker?.();
    };
    window.addEventListener('keydown', quickProvider);
    return () => window.removeEventListener('keydown', quickProvider);
  }, [active]);

  const onHeaderDoubleClick = (event: MouseEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest('button, select')) return;
    toggleMaximize(pane.id);
  };

  return (
    <section
      className={cn(
        'relative flex size-full min-h-pane-min-block min-w-pane-min-inline flex-col overflow-hidden bg-canvas',
        active && 'ring-1 ring-inset ring-accent',
      )}
      onPointerDown={() => setActivePane(pane.id)}
      onDragOver={(event) => {
        if (!event.dataTransfer.types.includes(PANE_DRAG_TYPE)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        setOverEdge(dockEdge(event));
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOverEdge(null);
      }}
      onDrop={(event) => {
        event.preventDefault();
        const moving = event.dataTransfer.getData(PANE_DRAG_TYPE);
        if (moving && overEdge) dockPane(moving, pane.id, overEdge);
        setOverEdge(null);
      }}
      data-pane-id={pane.id}
    >
      <header
        draggable
        onDragStart={(event) => {
          event.dataTransfer.setData(PANE_DRAG_TYPE, pane.id);
          event.dataTransfer.effectAllowed = 'move';
        }}
        onDoubleClick={onHeaderDoubleClick}
        className="flex h-10 shrink-0 items-center gap-1 border-b border-border-default bg-surface px-1.5"
      >
        <SafeIcon
          icon={GripVertical}
          className="size-4 shrink-0 cursor-grab text-fg-muted"
          aria-hidden
        />
        {pane.type === 'chat' ? (
          <SafeIcon
            icon={MessageSquare}
            className="size-3.5 shrink-0 text-accent-text"
            aria-hidden
          />
        ) : (
          <SafeIcon icon={Bot} className="size-3.5 shrink-0 text-accent-text" aria-hidden />
        )}
        <span className="max-w-24 truncate text-caption font-medium">
          {pane.sessionId
            ? t('pane.header.session', { id: pane.sessionId.slice(-5) })
            : t('pane.header.newChat')}
        </span>

        <select
          ref={modelSelect}
          aria-label={t('pane.header.model')}
          title={t('pane.header.quickProvider')}
          value={selectedModelValue(pane, providers)}
          onChange={(event) => {
            const [providerId, modelName] = event.target.value.split('::');
            if (providerId && modelName) configureSession({ providerId, modelName });
          }}
          className="ms-auto min-w-0 max-w-48 rounded-xs border border-border-default bg-canvas px-1.5 py-0.5 text-caption text-fg-primary"
        >
          {providers.flatMap((provider) =>
            provider.enabledModelIds.map((model) => (
              <option key={`${provider.id}:${model}`} value={`${provider.id}::${model}`}>
                {provider.name} · {model}
              </option>
            )),
          )}
        </select>

        <select
          aria-label={t('pane.header.reasoning')}
          value={String(pane.reasoningEffort)}
          disabled={
            !providers.find((provider) => provider.id === pane.providerId)?.supportsReasoning
          }
          onChange={(event) => configureSession({ reasoningEffort: Number(event.target.value) })}
          className="w-[4.6rem] rounded-xs border border-border-default bg-canvas px-1 py-0.5 text-caption text-fg-secondary disabled:opacity-50"
        >
          <option value="0">{t('pane.header.effort.auto')}</option>
          <option value="0.25">{t('pane.header.effort.low')}</option>
          <option value="0.65">{t('pane.header.effort.medium')}</option>
          <option value="1">{t('pane.header.effort.high')}</option>
        </select>

        <Button
          variant="ghost"
          size="icon-sm"
          className="size-6"
          aria-label={t('pane.header.splitEnd')}
          title={t('pane.header.splitEnd')}
          onClick={() => addPane(pane.id, 'horizontal')}
        >
          <SafeIcon icon={ArrowRightToLine} className="rtl:-scale-x-100" aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-6"
          aria-label={t('pane.header.splitBelow')}
          title={t('pane.header.splitBelow')}
          onClick={() => addPane(pane.id, 'vertical')}
        >
          <SafeIcon icon={ArrowDownToLine} aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-6"
          aria-label={t('pane.header.maximize')}
          title={t('pane.header.maximizeShortcut')}
          onClick={() => toggleMaximize(pane.id)}
        >
          <SafeIcon icon={Maximize2} aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-6"
          aria-label={t('pane.header.close')}
          title={t('pane.header.closeShortcut')}
          onClick={() => closePane(pane.id)}
        >
          <SafeIcon icon={X} aria-hidden />
        </Button>
      </header>

      <div className="min-h-0 flex-1">
        {pane.type === 'chat' ? <PaneChat pane={pane} /> : <PanePlaceholder pane={pane} />}
      </div>

      {overEdge && (
        <div
          className={cn(
            'pointer-events-none absolute z-30 m-1 rounded-md border-2 border-accent bg-accent-soft/70',
            overEdge === 'left' && 'inset-y-10 start-0 w-1/2',
            overEdge === 'right' && 'inset-y-10 end-0 w-1/2',
            overEdge === 'top' && 'inset-x-0 top-10 h-[calc(50%-1.25rem)]',
            overEdge === 'bottom' && 'inset-x-0 bottom-0 h-[calc(50%-1.25rem)]',
          )}
        />
      )}
    </section>
  );
}

function PaneChat({ pane }: { pane: PaneState }) {
  const { t } = useTranslation('chat');
  const providers = useProviderStore((state) => state.providers);
  const updatePane = useLayoutStore((state) => state.updatePane);
  const ensure = usePaneChatStore((state) => state.ensure);
  const transcript = usePaneChatStore((state) => state.transcripts[pane.id]);
  const addMessage = usePaneChatStore((state) => state.addMessage);
  const beginStream = usePaneChatStore((state) => state.beginStream);
  const appendChunk = usePaneChatStore((state) => state.appendChunk);
  const finishStream = usePaneChatStore((state) => state.finishStream);
  const failStream = usePaneChatStore((state) => state.failStream);
  const setPendingApproval = usePaneChatStore((state) => state.setPendingApproval);
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const followTail = useRef(true);
  const scrollFrame = useRef<number | null>(null);
  const scheduleTailScroll = useCallback(() => {
    if (!followTail.current || scrollFrame.current !== null) return;
    scrollFrame.current = requestAnimationFrame(() => {
      endRef.current?.scrollIntoView({ block: 'nearest' });
      scrollFrame.current = null;
    });
  }, []);
  const [streamBatcher] = useState(() =>
    createFrameBatcher((chunk) => appendChunk(pane.id, chunk)),
  );

  useEffect(() => ensure(pane.id), [ensure, pane.id]);
  useEffect(
    () => () => {
      streamBatcher.cancel();
      if (scrollFrame.current !== null) cancelAnimationFrame(scrollFrame.current);
    },
    [streamBatcher],
  );
  useEffect(
    () => scheduleTailScroll(),
    [scheduleTailScroll, transcript?.messages.length, transcript?.streaming],
  );

  const switchProviderCommand = (text: string): boolean => {
    if (!text.toLowerCase().startsWith('/provider')) return false;
    const [, requested = '', requestedModel] = text.trim().split(/\s+/);
    const provider = providers.find(
      (item) =>
        item.id.toLowerCase() === requested.toLowerCase() ||
        item.name.toLowerCase() === requested.toLowerCase(),
    );
    if (!provider) {
      failStream(pane.id, t('pane.providerMissing', { provider: requested || t('pane.unknown') }));
      return true;
    }
    const model =
      provider.enabledModelIds.find((item) => item === requestedModel) ??
      provider.enabledModelIds[0];
    if (!model) {
      failStream(pane.id, t('pane.noModels', { provider: provider.name }));
      return true;
    }
    updatePane(pane.id, { providerId: provider.id, modelName: model });
    if (pane.sessionId) {
      void getBridgeClient().call('session.configure', {
        session_id: pane.sessionId,
        provider: provider.id,
        model,
        reasoning_effort: pane.reasoningEffort,
      });
    }
    return true;
  };

  /**
   * Execute a conversation.send with approval-retry support (S07).
   *
   * When the bridge returns APPROVAL_REQUIRED, we show the dialog; once the
   * user decides, we resolve the approval on the bridge. Only Allow once
   * proceeds. Always Allow / YOLO are refused.
   */
  const sendWithApproval = async (
    sessionId: string,
    text: string,
    client: ReturnType<typeof getBridgeClient>,
  ): Promise<BridgeTurn> => {
    const MAX_RETRIES = 3;
    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      try {
        const result = await client.stream<BridgeTurn>(
          'conversation.send',
          { session_id: sessionId, message: text },
          { onChunk: (chunk) => streamBatcher.push(chunk.token) },
        );
        return result;
      } catch (err: unknown) {
        const code =
          typeof err === 'object' && err !== null && 'code' in err
            ? (err as { code: number }).code
            : undefined;
        if (code !== RPC_ERROR.APPROVAL_REQUIRED) throw err;

        // Extract approval details from the error data.
        const data =
          typeof err === 'object' && err !== null && 'data' in err
            ? (err as { data: Record<string, unknown> }).data
            : {};
        const rawApprovalId = data['approval_id'];
        const rawToolName = data['name'] ?? data['tool_name'];
        const rawSummary = data['summary'];
        const rawRisk = data['risk'];
        const approvalId = typeof rawApprovalId === 'string' ? rawApprovalId : '';
        const toolName = typeof rawToolName === 'string' ? rawToolName : t('pane.unknownTool');
        const argsSummary = typeof rawSummary === 'string' ? rawSummary : '';
        const risk = typeof rawRisk === 'string' ? rawRisk : 'dangerous';

        // Show the approval dialog and wait for a decision.
        const decision = await new Promise<ApprovalDecision>((resolve) => {
          setPendingApproval(pane.id, {
            approvalId,
            toolName,
            argsSummary,
            risk,
            paneId: pane.id,
          });
          approvalResolvers.set(pane.id, resolve);
        });
        setPendingApproval(pane.id, null);

        if (decision !== 'allow_once') {
          void resolveApprovalOnBridge(client, approvalId, 'deny').catch(() => {});
          const blockedCard: ToolCardEntry = {
            id: `tc-blocked-${Date.now()}`,
            name: toolName,
            argsSummary,
            status: 'blocked',
            resultExcerpt: t('approval.blockedByUser'),
          };
          addMessage(pane.id, {
            id: `tool-${Date.now()}-${pane.id}`,
            role: 'assistant',
            content: '',
            createdAt: Date.now(),
            toolCards: [blockedCard],
          });
          throw new Error('Tool call denied by user');
        }

        void resolveApprovalOnBridge(client, approvalId, decision).catch(() => {});
      }
    }
    throw new Error('Approval retry limit reached');
  };

  const send = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || transcript?.sending) return;
    setInput('');
    if (switchProviderCommand(text)) return;

    const userMessage: Message = {
      id: `user-${Date.now()}-${pane.id}`,
      role: 'user',
      content: text,
      createdAt: Date.now(),
    };
    addMessage(pane.id, userMessage);
    beginStream(pane.id);

    const client = getBridgeClient();
    let sessionId = pane.sessionId;
    try {
      if (sessionId) {
        try {
          await client.call('session.get', { session_id: sessionId });
        } catch {
          sessionId = null;
        }
      }
      if (!sessionId) {
        const created = await client.call<{ session_id: string }>('session.create', {
          provider: pane.providerId,
          model: pane.modelName,
          reasoning_effort: pane.reasoningEffort,
        });
        sessionId = created.session_id;
        updatePane(pane.id, { sessionId });
      }
      const result = await sendWithApproval(sessionId, text, client);
      // The final result is authoritative; discard a pending visual-only token batch.
      streamBatcher.cancel();

      // Build tool cards from the turn's tool_calls (S07).
      const toolCards: ToolCardEntry[] = (result.tool_calls ?? []).map((tc, index) => ({
        id: `tc-${Date.now()}-${index}`,
        name: tc.name,
        argsSummary: JSON.stringify(tc.arguments ?? {}).slice(0, 160),
        status: tc.allowed === false ? ('blocked' as const) : ('ok' as const),
        resultExcerpt: (tc.result ?? '').slice(0, 200),
      }));

      // If there are tool cards, attach them to the assistant message.
      if (toolCards.length > 0) {
        addMessage(pane.id, {
          id: `tool-${Date.now()}-${pane.id}`,
          role: 'assistant',
          content: '',
          createdAt: Date.now(),
          toolCards,
        });
      }

      finishStream(pane.id, result.reply);
    } catch (err) {
      streamBatcher.cancel();
      // Don't double-report if we already handled it (blocked tool).
      const msg =
        err instanceof Error && err.message === 'Tool call denied by user'
          ? ''
          : t('pane.messageFailed');
      if (msg) failStream(pane.id, msg);
      else {
        // Still clear the sending state.
        finishStream(pane.id, '');
      }
    }
  };

  const stop = () => {
    if (!pane.sessionId) return;
    void getBridgeClient().call('conversation.stop', { session_id: pane.sessionId });
  };

  const handleApprovalDecision = (decision: ApprovalDecision) => {
    const resolve = approvalResolvers.get(pane.id);
    if (resolve) {
      resolve(decision);
      approvalResolvers.delete(pane.id);
    }
  };

  const messages = transcript?.messages ?? [];
  const chatItems = paneChatItems(messages, transcript?.streaming, pane.id);

  return (
    <div className="flex size-full min-h-0 flex-col">
      {/* Approval dialog overlay (S07) */}
      {transcript?.pendingApproval && (
        <ApprovalDialog approval={transcript.pendingApproval} onDecision={handleApprovalDecision} />
      )}

      <CompactionBar sessionId={pane.sessionId} />

      <VirtualMessageList
        items={chatItems}
        label={t('messageLabel')}
        scrollRef={scrollRef}
        onScroll={() => {
          const node = scrollRef.current;
          if (node) {
            followTail.current = node.scrollHeight - node.scrollTop - node.clientHeight < 64;
          }
        }}
        footer={
          <>
            {messages.length === 0 && !transcript?.streaming && (
              <div className="mx-auto flex h-full max-w-sm flex-col items-center justify-center text-center text-fg-muted">
                <SafeIcon
                  icon={MessageSquare}
                  className="mb-3 size-8 text-accent-text"
                  aria-hidden
                />
                <p className="font-medium text-fg-primary">{t('pane.independentTitle')}</p>
                <p className="mt-1 text-caption">{t('pane.independentDesc')}</p>
                <code className="mt-3 rounded-sm bg-surface-2 px-2 py-1 text-caption">
                  /provider openai
                </code>
              </div>
            )}
            {transcript?.error && (
              <p
                role="alert"
                className="rounded-md bg-danger-bg px-3 py-2 text-caption text-danger-fg"
              >
                {transcript.error}
              </p>
            )}
            <div ref={endRef} />
          </>
        }
      />

      <form
        onSubmit={(event) => void send(event)}
        className="flex shrink-0 gap-2 border-t border-border-default bg-surface p-2"
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event: KeyboardEvent<HTMLTextAreaElement>) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          rows={1}
          placeholder={t('inputPlaceholder')}
          aria-label={t('messageLabel')}
          dir="auto"
          className="selectable min-h-9 min-w-0 flex-1 resize-none rounded-md border border-border-default bg-canvas px-3 py-1.5 text-body outline-none focus:border-accent"
        />
        {transcript?.sending ? (
          <Button
            type="button"
            size="icon"
            variant="secondary"
            onClick={stop}
            aria-label={t('stop')}
          >
            <SafeIcon icon={Square} aria-hidden />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            variant="primary"
            disabled={!input.trim()}
            aria-label={t('send')}
          >
            <SafeIcon icon={Send} aria-hidden />
          </Button>
        )}
        <CouncilButton
          input={input}
          messages={transcript?.messages ?? []}
          disabled={transcript?.sending}
        />
      </form>
    </div>
  );
}

function PanePlaceholder({ pane }: { pane: PaneState }) {
  const { t } = useTranslation('chat');
  return (
    <div className="flex size-full items-center justify-center text-center text-fg-muted">
      <div>
        <SafeIcon icon={Bot} className="mx-auto mb-2 size-8" aria-hidden />
        <p className="font-medium text-fg-primary">
          {t('pane.placeholderTitle', { type: t(`pane.type.${pane.type}`) })}
        </p>
        <p className="text-caption">{t('pane.placeholderDescription')}</p>
      </div>
    </div>
  );
}

export { PANE_DRAG_TYPE };
