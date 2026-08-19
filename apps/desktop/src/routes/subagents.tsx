/**
 * Subagent monitor (design wireframe 08).
 *
 * A collapsible list of children on the inline-start side, the selected
 * child's detail on the other. The list polls `subagent.list` while anything
 * is still running; the selected child's log arrives over the `subagent.logs`
 * stream, which the sidecar replays from the beginning on subscribe.
 */

import { Bot, ChevronDown, ChevronRight, Plus, RefreshCw, Scale } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { CouncilDialog } from '@/components/subagents/council-dialog';
import { CouncilWidget } from '@/components/subagents/council-widget';
import { SpawnDialog } from '@/components/subagents/spawn-dialog';
import { SubagentDetail } from '@/components/subagents/subagent-detail';
import { ProgressBar, SubagentStatusBadge } from '@/components/subagents/status-badge';
import { EmptyState } from '@/components/shared/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { useBridge } from '@/lib/bridge/hooks';
import type { BridgeLogEntry, BridgeSubagent, CouncilDto, RpcParams } from '@/lib/bridge/types';
import { isTerminalStatus } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';
import { formatDuration } from '@/utils/format';

/** How often to refresh the list while a child is still running. */
const POLL_MS = 500;

interface ToolRow {
  name: string;
  risk: string;
}

/** The child currently being followed: its snapshot and its streamed log. */
interface FollowedSubagent {
  id: string;
  agent: BridgeSubagent | null;
  log: BridgeLogEntry[];
}

/** One row in the list, collapsed to its essentials. */
function SubagentRow({
  agent,
  selected,
  onSelect,
}: {
  agent: BridgeSubagent;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected}
        className={cn(
          'flex w-full flex-col gap-1.5 rounded-lg border p-2.5 text-start transition-colors duration-fast',
          selected
            ? 'border-accent bg-accent-soft'
            : 'border-border-default bg-surface hover:bg-surface-2',
        )}
      >
        <span className="flex items-center justify-between gap-2">
          <span className="truncate text-body font-medium">{agent.name}</span>
          <SubagentStatusBadge status={agent.status} />
        </span>
        <ProgressBar
          value={agent.progress}
          status={agent.status}
          label={`${agent.name} progress`}
        />
        <span className="flex justify-between text-micro text-fg-muted">
          <span>
            {agent.turn_count}/{agent.max_turns} turns
          </span>
          <span className="tabular">{formatDuration(agent.elapsed)}</span>
        </span>
      </button>
    </li>
  );
}

export function SubagentsRoute() {
  const { t } = useTranslation('subagents');
  const { call, stream } = useBridge();

  const [agents, setAgents] = useState<BridgeSubagent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [followed, setFollowed] = useState<FollowedSubagent | null>(null);
  const [tools, setTools] = useState<string[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [councilDialogOpen, setCouncilDialogOpen] = useState(false);
  /** councils the user started here, keyed so a child's pipeline maps back. */
  const [councils, setCouncils] = useState<{ council_id: string; pipeline_id: string }[]>([]);
  const [listOpen, setListOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards against a late response from a superseded selection overwriting the
  // current one, and against setState after unmount.
  const liveRef = useRef(true);
  useEffect(() => {
    liveRef.current = true;
    return () => {
      liveRef.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    try {
      const result = await call<{ subagents: BridgeSubagent[] }>('subagent.list', {});
      if (liveRef.current) setAgents(result.subagents);
    } catch (err) {
      if (liveRef.current) setError(err instanceof Error ? err.message : String(err));
    }
  }, [call]);

  // Initial load: the roster and the tools this parent can delegate.
  useEffect(() => {
    const load = async () => {
      await refresh();
      try {
        const result = await call<{ tools: ToolRow[] }>('tool.list', {});
        if (liveRef.current) setTools(result.tools.map((t) => t.name));
      } catch {
        // A missing tool list only costs the spawn form its checkboxes.
      }
    };
    void load();
  }, [call, refresh]);

  const anyRunning = agents.some((a) => !isTerminalStatus(a.status));

  // Poll only while something can still change.
  useEffect(() => {
    if (!anyRunning) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [anyRunning, refresh]);

  // The selection is derived, not stored: a preference that falls back to the
  // newest child whenever the preferred one is gone (or never existed).
  const selectionLives = selectedId !== null && agents.some((a) => a.subagent_id === selectedId);
  const activeId = selectionLives ? selectedId : (agents[0]?.subagent_id ?? null);

  // Follow the selected child. `subagent.get` seeds the snapshot and
  // `subagent.logs` carries the log, which the sidecar replays from the start —
  // so the log comes from the stream alone and never doubles up.
  useEffect(() => {
    const id = activeId;
    if (!id) return;
    let current = true;

    const seed = async () => {
      try {
        const agent = await call<BridgeSubagent>('subagent.get', { subagent_id: id });
        if (!current) return;
        setFollowed((prev) => (prev?.id === id ? { ...prev, agent } : { id, agent, log: [] }));
      } catch {
        // The stream below still carries everything worth showing.
      }
    };

    const follow = async () => {
      try {
        const final = await stream<BridgeSubagent>(
          'subagent.logs',
          { subagent_id: id },
          (chunk) => {
            const entry = chunk.entry;
            if (!current || !entry) return;
            setFollowed((prev) =>
              prev?.id === id
                ? { ...prev, log: [...prev.log, entry] }
                : { id, agent: null, log: [entry] },
            );
          },
        );
        if (!current) return;
        setFollowed((prev) =>
          prev?.id === id ? { ...prev, agent: final } : { id, agent: final, log: [] },
        );
      } catch {
        // A dropped stream leaves the last snapshot on screen.
      }
    };

    void seed();
    void follow();
    return () => {
      current = false;
    };
  }, [activeId, call, stream]);

  // The list carries fresher counters than the snapshot, so it wins on overlap.
  const followedNow = followed?.id === activeId ? followed : null;
  const listRow = agents.find((a) => a.subagent_id === activeId) ?? null;
  const detail: BridgeSubagent | null = followedNow?.agent
    ? { ...followedNow.agent, ...(listRow ?? {}) }
    : listRow;
  const log = followedNow?.log ?? [];
  // When the selected child belongs to a council this page started, the
  // detail pane becomes the three-column council widget.
  const activeCouncil = detail?.pipeline_id
    ? councils.find((c) => c.pipeline_id === detail.pipeline_id)
    : undefined;

  const control = async (method: string) => {
    if (!activeId) return;
    setBusy(true);
    setError(null);
    try {
      await call<BridgeSubagent>(method, { subagent_id: activeId });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (liveRef.current) setBusy(false);
    }
  };

  const spawn = async (stages: RpcParams[], pipelineName: string) => {
    if (stages.length === 1) {
      const agent = await call<BridgeSubagent>('subagent.spawn', stages[0]);
      setSelectedId(agent.subagent_id);
    } else {
      const result = await call<{ subagents: BridgeSubagent[] }>('subagent.pipeline', {
        name: pipelineName,
        stages,
      });
      const head = result.subagents[0];
      if (head) setSelectedId(head.subagent_id);
    }
    await refresh();
  };

  const runCouncil = async (topic: string) => {
    setBusy(true);
    setError(null);
    try {
      const result = await call<CouncilDto>('council.run', { prompt: topic });
      if (result.refusal) {
        setError(result.refusal);
        return;
      }
      setCouncils((prev) => [
        ...prev,
        { council_id: result.council_id, pipeline_id: result.pipeline_id },
      ]);
      const head = result.members[0];
      if (head) setSelectedId(head.subagent_id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (liveRef.current) setBusy(false);
    }
  };

  const activeCount = useMemo(
    () => agents.filter((a) => !isTerminalStatus(a.status)).length,
    [agents],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-border-default px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-h2 font-semibold">{t('title')}</h2>
          {activeCount > 0 && <Badge variant="info">{activeCount} running</Badge>}
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void refresh()}
            aria-label={t('refresh')}
          >
            <RefreshCw aria-hidden />
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setCouncilDialogOpen(true)}>
            <Scale aria-hidden />
            {t('councilReview')}
          </Button>
          <Button size="sm" variant="primary" onClick={() => setDialogOpen(true)}>
            <Plus aria-hidden />
            {t('newSubagent')}
          </Button>
        </div>
      </header>

      {error && (
        <p
          role="alert"
          className="border-b border-danger-fg/30 bg-danger-bg px-4 py-2 text-caption text-danger-fg"
        >
          {error}
        </p>
      )}

      {agents.length === 0 ? (
        <EmptyState
          icon={Bot}
          title={t('noSubagents')}
          description={t('noSubagentsDesc')}
          action={{ label: t('spawn'), onClick: () => setDialogOpen(true) }}
        />
      ) : (
        <div className="flex min-h-0 flex-1">
          <div
            className={cn(
              'flex shrink-0 flex-col border-e border-border-default bg-canvas transition-all duration-normal',
              listOpen ? 'w-72' : 'w-12',
            )}
          >
            <button
              type="button"
              onClick={() => setListOpen((v) => !v)}
              aria-expanded={listOpen}
              aria-label={listOpen ? t('collapseList') : t('expandList')}
              className="flex items-center gap-1.5 px-3 py-2 text-caption font-medium text-fg-secondary hover:text-fg-primary"
            >
              {listOpen ? (
                <ChevronDown className="size-4" aria-hidden />
              ) : (
                <ChevronRight className="size-4" aria-hidden />
              )}
              {listOpen && <span>{agents.length} total</span>}
            </button>
            {listOpen && (
              <ul
                aria-label="Subagents"
                className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto p-2 pt-0"
              >
                {agents.map((agent) => (
                  <SubagentRow
                    key={agent.subagent_id}
                    agent={agent}
                    selected={agent.subagent_id === activeId}
                    onSelect={() => setSelectedId(agent.subagent_id)}
                  />
                ))}
              </ul>
            )}
          </div>

          <div className="min-w-0 flex-1 overflow-y-auto p-4">
            {detail ? (
              activeCouncil ? (
                <CouncilWidget councilId={activeCouncil.council_id} />
              ) : (
                <SubagentDetail
                  agent={detail}
                  log={log}
                  busy={busy}
                  onCancel={() => void control('subagent.cancel')}
                  onPause={() => void control('subagent.pause')}
                  onResume={() => void control('subagent.resume')}
                />
              )
            ) : (
              <p className="text-body text-fg-secondary">{t('selectPrompt')}</p>
            )}
          </div>
        </div>
      )}

      <SpawnDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        availableTools={tools}
        onSpawn={spawn}
      />
      <CouncilDialog
        open={councilDialogOpen}
        onOpenChange={setCouncilDialogOpen}
        onRun={runCouncil}
      />
    </div>
  );
}
