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
import { useEffect, useRef, useState } from 'react';
import type { DragEvent, FormEvent, KeyboardEvent, MouseEvent } from 'react';

import { Button } from '@/components/ui/button';
import { getBridgeClient } from '@/lib/bridge/client';
import type { BridgeTurn } from '@/lib/bridge/types';
import type { DockEdge, PaneState } from '@/stores/use-layout-store';
import { useLayoutStore } from '@/stores/use-layout-store';
import { usePaneChatStore } from '@/stores/use-pane-chat-store';
import { useProviderStore } from '@/stores/use-provider-store';
import type { Message, Provider } from '@/types';
import { cn } from '@/utils/cn';

const PANE_DRAG_TYPE = 'application/x-dream-pane';

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
  if (x < 0.25) return 'left';
  if (x > 0.75) return 'right';
  if (y < 0.5) return 'top';
  return 'bottom';
}

export function Pane({ pane, active }: PaneProps) {
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
        'relative flex size-full min-h-[200px] min-w-[300px] flex-col overflow-hidden bg-canvas',
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
        <GripVertical className="size-4 shrink-0 cursor-grab text-fg-muted" aria-hidden />
        {pane.type === 'chat' ? (
          <MessageSquare className="size-3.5 shrink-0 text-accent-text" aria-hidden />
        ) : (
          <Bot className="size-3.5 shrink-0 text-accent-text" aria-hidden />
        )}
        <span className="max-w-24 truncate text-caption font-medium">
          {pane.sessionId ? `Chat ${pane.sessionId.slice(-5)}` : 'New chat'}
        </span>

        <select
          ref={modelSelect}
          aria-label="Pane model"
          title="Quick provider switch (⌘P / Ctrl+P)"
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
          aria-label="Reasoning effort"
          value={String(pane.reasoningEffort)}
          disabled={
            !providers.find((provider) => provider.id === pane.providerId)?.supportsReasoning
          }
          onChange={(event) => configureSession({ reasoningEffort: Number(event.target.value) })}
          className="w-[4.6rem] rounded-xs border border-border-default bg-canvas px-1 py-0.5 text-caption text-fg-secondary disabled:opacity-50"
        >
          <option value="0">Auto</option>
          <option value="0.25">Low</option>
          <option value="0.65">Medium</option>
          <option value="1">High</option>
        </select>

        <Button
          variant="ghost"
          size="icon-sm"
          className="size-6"
          aria-label="Split pane right"
          title="Split right"
          onClick={() => addPane(pane.id, 'horizontal')}
        >
          <ArrowRightToLine aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-6"
          aria-label="Split pane below"
          title="Split below"
          onClick={() => addPane(pane.id, 'vertical')}
        >
          <ArrowDownToLine aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-6"
          aria-label="Maximize or restore pane"
          title="Maximize / restore (⌘⇧M)"
          onClick={() => toggleMaximize(pane.id)}
        >
          <Maximize2 aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-6"
          aria-label="Close pane"
          title="Close pane (⌘W)"
          onClick={() => closePane(pane.id)}
        >
          <X aria-hidden />
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
  const providers = useProviderStore((state) => state.providers);
  const updatePane = useLayoutStore((state) => state.updatePane);
  const ensure = usePaneChatStore((state) => state.ensure);
  const transcript = usePaneChatStore((state) => state.transcripts[pane.id]);
  const addMessage = usePaneChatStore((state) => state.addMessage);
  const beginStream = usePaneChatStore((state) => state.beginStream);
  const appendChunk = usePaneChatStore((state) => state.appendChunk);
  const finishStream = usePaneChatStore((state) => state.finishStream);
  const failStream = usePaneChatStore((state) => state.failStream);
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => ensure(pane.id), [ensure, pane.id]);
  useEffect(() => endRef.current?.scrollIntoView({ block: 'nearest' }), [transcript]);

  const switchProviderCommand = (text: string): boolean => {
    if (!text.toLowerCase().startsWith('/provider')) return false;
    const [, requested = '', requestedModel] = text.trim().split(/\s+/);
    const provider = providers.find(
      (item) =>
        item.id.toLowerCase() === requested.toLowerCase() ||
        item.name.toLowerCase() === requested.toLowerCase(),
    );
    if (!provider) {
      failStream(pane.id, `Provider “${requested || 'unknown'}” is not configured.`);
      return true;
    }
    const model =
      provider.enabledModelIds.find((item) => item === requestedModel) ??
      provider.enabledModelIds[0];
    if (!model) {
      failStream(pane.id, `${provider.name} has no enabled models.`);
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
      const result = await client.stream<BridgeTurn>(
        'conversation.send',
        { session_id: sessionId, message: text },
        { onChunk: (chunk) => appendChunk(pane.id, chunk.token) },
      );
      finishStream(pane.id, result.reply);
    } catch {
      failStream(pane.id, 'Message failed. Check the bridge and provider connection.');
    }
  };

  const stop = () => {
    if (!pane.sessionId) return;
    void getBridgeClient().call('conversation.stop', { session_id: pane.sessionId });
  };

  const messages = transcript?.messages ?? [];
  return (
    <div className="flex size-full min-h-0 flex-col">
      <div className="selectable min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-5">
        {messages.length === 0 && !transcript?.streaming && (
          <div className="mx-auto flex h-full max-w-sm flex-col items-center justify-center text-center text-fg-muted">
            <MessageSquare className="mb-3 size-8 text-accent-text" aria-hidden />
            <p className="font-medium text-fg-primary">Independent conversation</p>
            <p className="mt-1 text-caption">
              This pane has its own session, provider, model, and reasoning effort.
            </p>
            <code className="mt-3 rounded-sm bg-surface-2 px-2 py-1 text-caption">
              /provider openai
            </code>
          </div>
        )}
        {messages.map((message) => (
          <article
            key={message.id}
            className={cn(
              'max-w-[85%] rounded-lg px-3 py-2 text-body whitespace-pre-wrap',
              message.role === 'user'
                ? 'ms-auto bg-accent text-fg-inverse'
                : 'me-auto border border-border-default bg-surface text-fg-primary',
            )}
          >
            {message.content}
          </article>
        ))}
        {transcript?.streaming && (
          <article className="me-auto max-w-[85%] rounded-lg border border-border-default bg-surface px-3 py-2 whitespace-pre-wrap">
            {transcript.streaming}
            <span className="ms-0.5 inline-block h-4 w-0.5 animate-pulse bg-accent" />
          </article>
        )}
        {transcript?.error && (
          <p role="alert" className="rounded-md bg-danger-bg px-3 py-2 text-caption text-danger-fg">
            {transcript.error}
          </p>
        )}
        <div ref={endRef} />
      </div>

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
          placeholder="Message Dream…"
          aria-label="Message"
          className="selectable min-h-9 min-w-0 flex-1 resize-none rounded-md border border-border-default bg-canvas px-3 py-1.5 text-body outline-none focus:border-accent"
        />
        {transcript?.sending ? (
          <Button
            type="button"
            size="icon"
            variant="secondary"
            onClick={stop}
            aria-label="Stop response"
          >
            <Square aria-hidden />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            variant="primary"
            disabled={!input.trim()}
            aria-label="Send message"
          >
            <Send aria-hidden />
          </Button>
        )}
      </form>
    </div>
  );
}

function PanePlaceholder({ pane }: { pane: PaneState }) {
  return (
    <div className="flex size-full items-center justify-center text-center text-fg-muted">
      <div>
        <Bot className="mx-auto mb-2 size-8" aria-hidden />
        <p className="font-medium capitalize text-fg-primary">{pane.type} pane</p>
        <p className="text-caption">Content routing is isolated to this pane.</p>
      </div>
    </div>
  );
}

export { PANE_DRAG_TYPE };
