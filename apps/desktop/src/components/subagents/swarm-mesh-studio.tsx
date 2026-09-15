/**
 * Multi-Agent Swarm Neural Mesh Studio Component.
 *
 * Provides visual node topology management, collaborative task DAG planning,
 * consensus deliberation & voting, and event bus messaging.
 */

import {
  CheckCircle2,
  Cpu,
  GitFork,
  MessageSquare,
  Network,
  Play,
  Plus,
  RefreshCw,
  Scale,
  Shield,
  Trash2,
  Users,
  Vote,
  XCircle,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs } from '@/components/ui/tabs';
import { useTranslation } from '@/lib/i18n';
import { useBridge } from '@/lib/bridge/hooks';
import {
  swarmBroadcastMessage,
  swarmExecuteStep,
  swarmGetStatus,
  swarmListNodes,
  swarmPlanWorkflow,
  swarmReset,
  swarmRunAll,
  swarmSpawnNode,
  swarmVoteConsensus,
  type ConsensusDecision,
  type SwarmNode,
  type SwarmStatusSummary,
  type SwarmTask,
} from '@/lib/bridge/swarm';

const ROLES = [
  { id: 'leader', label: 'Leader' },
  { id: 'architect', label: 'Architect' },
  { id: 'coder', label: 'Coder' },
  { id: 'critic', label: 'Critic' },
  { id: 'arbiter', label: 'Arbiter' },
  { id: 'specialist', label: 'Specialist' },
];

export function SwarmMeshStudio() {
  const { t } = useTranslation('subagents');
  const { client } = useBridge();

  const [activeTab, setActiveTab] = useState<string>('topology');
  const [status, setStatus] = useState<SwarmStatusSummary | null>(null);
  const [nodes, setNodes] = useState<SwarmNode[]>([]);
  const [leaderId, setLeaderId] = useState<string | null>(null);

  // Spawn node state
  const [newNodeName, setNewNodeName] = useState('');
  const [newNodeRole, setNewNodeRole] = useState('specialist');
  const [newNodeModel, setNewNodeModel] = useState('gpt-4o');

  // Workflow DAG state
  const [goalInput, setGoalInput] = useState(
    'طراحی و پیاده‌سازی سیستم ارکستراسیون عامل‌های هوشمند',
  );
  const [tasks, setTasks] = useState<SwarmTask[]>([]);
  const [planning, setPlanning] = useState(false);
  const [executing, setExecuting] = useState(false);

  // Consensus state
  const [proposalInput, setProposalInput] = useState(
    'تصویب پروتکل ارتباطی مش عصبی برای انتقال پیام‌های بین‌عاملی',
  );
  const [consensusDecision, setConsensusDecision] = useState<ConsensusDecision | null>(null);
  const [voting, setVoting] = useState(false);

  // Event bus state
  const [busTopic, setBusTopic] = useState('cluster.event.notice');
  const [busMessage, setBusMessage] = useState('All swarm nodes synchronized successfully.');
  const [recentEvents, setRecentEvents] = useState<
    Array<{ topic: string; message: string; timestamp: number }>
  >([]);

  const [alertMsg, setAlertMsg] = useState<string | null>(null);

  const refreshState = useCallback(async () => {
    try {
      const [statusRes, nodesRes] = await Promise.all([
        swarmGetStatus(client),
        swarmListNodes(client),
      ]);
      setStatus(statusRes);
      setNodes(nodesRes.nodes);
      setLeaderId(nodesRes.leader_id);
      if (statusRes.tasks && statusRes.tasks.length > 0) {
        setTasks(statusRes.tasks);
      }
    } catch {
      // Offline fallback
    }
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const [statusRes, nodesRes] = await Promise.all([
          swarmGetStatus(client),
          swarmListNodes(client),
        ]);
        if (!cancelled) {
          setStatus(statusRes);
          setNodes(nodesRes.nodes);
          setLeaderId(nodesRes.leader_id);
          if (statusRes.tasks && statusRes.tasks.length > 0) {
            setTasks(statusRes.tasks);
          }
        }
      } catch {
        // Ignored
      }
    };
    void init();
    return () => {
      cancelled = true;
    };
  }, [client]);

  const handleSpawnNode = async () => {
    if (!newNodeName.trim()) return;
    try {
      await swarmSpawnNode(client, newNodeName.trim(), newNodeRole, newNodeModel);
      setNewNodeName('');
      await refreshState();
      setAlertMsg(`Agent node '${newNodeName}' spawned.`);
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    }
  };

  const handlePlanWorkflow = async () => {
    if (!goalInput.trim() || planning) return;
    setPlanning(true);
    setAlertMsg(null);
    try {
      const res = await swarmPlanWorkflow(client, goalInput.trim());
      setTasks(res.tasks);
      await refreshState();
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setPlanning(false);
    }
  };

  const handleExecuteStep = async () => {
    if (executing) return;
    setExecuting(true);
    try {
      await swarmExecuteStep(client);
      await refreshState();
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setExecuting(false);
    }
  };

  const handleRunAllTasks = async () => {
    if (executing) return;
    setExecuting(true);
    try {
      await swarmRunAll(client, goalInput.trim());
      await refreshState();
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setExecuting(false);
    }
  };

  const handleVoteConsensus = async () => {
    if (!proposalInput.trim() || voting) return;
    setVoting(true);
    setAlertMsg(null);
    try {
      const res = await swarmVoteConsensus(client, proposalInput.trim());
      setConsensusDecision(res.decision);
      await refreshState();
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setVoting(false);
    }
  };

  const handleBroadcastMessage = async () => {
    if (!busTopic.trim() || !busMessage.trim()) return;
    try {
      await swarmBroadcastMessage(client, busTopic.trim(), busMessage.trim());
      setRecentEvents((prev) => [
        { topic: busTopic.trim(), message: busMessage.trim(), timestamp: Date.now() / 1000 },
        ...prev.slice(0, 9),
      ]);
      setAlertMsg(`Message broadcasted on topic '${busTopic}'.`);
      await refreshState();
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    }
  };

  const handleResetCluster = async () => {
    try {
      await swarmReset(client);
      setTasks([]);
      setConsensusDecision(null);
      setRecentEvents([]);
      await refreshState();
      setAlertMsg(t('clusterReset'));
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : String(err));
    }
  };

  const tabs = [
    {
      id: 'topology',
      label: t('tabMeshTopology'),
      content: (
        <div className="flex flex-col gap-4">
          {/* Spawn Node Bar */}
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border-default bg-surface p-3">
            <input
              type="text"
              placeholder="Agent Name (e.g. Data Scientist)"
              value={newNodeName}
              onChange={(e) => setNewNodeName(e.target.value)}
              className="h-8 flex-1 min-w-44 rounded-md border border-border-default bg-surface-2 px-2.5 text-body outline-none"
            />
            <select
              value={newNodeRole}
              onChange={(e) => setNewNodeRole(e.target.value)}
              className="h-8 rounded-md border border-border-default bg-surface-2 px-2 text-caption outline-none"
            >
              {ROLES.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
            <select
              value={newNodeModel}
              onChange={(e) => setNewNodeModel(e.target.value)}
              className="h-8 rounded-md border border-border-default bg-surface-2 px-2 text-caption outline-none"
            >
              <option value="gpt-4o">GPT-4o</option>
              <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
              <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
              <option value="ollama/qwen2.5">Ollama (Qwen 2.5)</option>
            </select>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleSpawnNode()}
              disabled={!newNodeName.trim()}
            >
              <Plus className="mr-1 size-4" />
              {t('spawnNode')}
            </Button>
          </div>

          {/* Nodes Cards Grid */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {nodes.map((n) => {
              const isLeader = n.node_id === leaderId || n.role === 'leader';
              return (
                <div
                  key={n.node_id}
                  className="flex flex-col justify-between rounded-lg border border-border-default bg-surface p-3.5 hover:border-accent"
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {isLeader ? (
                          <Shield className="size-4 text-warning-fg" />
                        ) : (
                          <Cpu className="size-4 text-accent" />
                        )}
                        <span className="truncate text-body font-bold">{n.name}</span>
                      </div>
                      <Badge variant={isLeader ? 'warning' : 'neutral'}>
                        {n.role.toUpperCase()}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-1.5 text-caption text-fg-muted">
                      <span>Model: {n.model}</span> ·{' '}
                      <span className="flex items-center gap-1">
                        <span
                          className={`size-2 rounded-full ${
                            n.status === 'idle' ? 'bg-success-fg' : 'bg-warning-fg'
                          }`}
                        />
                        {n.status}
                      </span>
                    </div>

                    {n.capabilities.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {n.capabilities.map((c) => (
                          <span
                            key={c}
                            className="rounded-xs bg-surface-2 px-1.5 py-0.5 font-mono text-caption text-fg-secondary"
                          >
                            {c}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ),
    },
    {
      id: 'dag',
      label: t('tabWorkflowDag'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border-default bg-surface p-3">
            <input
              type="text"
              value={goalInput}
              onChange={(e) => setGoalInput(e.target.value)}
              placeholder="High-level goal for swarm planning..."
              className="h-8 flex-1 min-w-60 rounded-md border border-border-default bg-surface-2 px-2.5 text-body outline-none"
            />
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handlePlanWorkflow()}
              disabled={planning || !goalInput.trim()}
            >
              {planning ? (
                <RefreshCw className="mr-1 size-4 animate-spin" />
              ) : (
                <GitFork className="mr-1 size-4" />
              )}
              {t('planDag')}
            </Button>
            {tasks.length > 0 && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleExecuteStep()}
                  disabled={executing}
                >
                  <Play className="mr-1 size-4" />
                  {t('executeStep')}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleRunAllTasks()}
                  disabled={executing}
                >
                  <CheckCircle2 className="mr-1 size-4" />
                  {t('runAllSteps')}
                </Button>
              </>
            )}
          </div>

          {/* Task DAG List */}
          {tasks.length > 0 && (
            <div className="flex flex-col gap-2.5">
              {tasks.map((task, idx) => (
                <div
                  key={task.task_id}
                  className="flex flex-col gap-1.5 rounded-lg border border-border-default bg-surface p-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="flex size-5 items-center justify-center rounded-full bg-surface-2 text-caption font-bold">
                        {idx + 1}
                      </span>
                      <span className="text-body font-medium">{task.title}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="neutral">{task.assigned_to}</Badge>
                      <Badge
                        variant={
                          task.status === 'completed'
                            ? 'success'
                            : task.status === 'in_progress'
                              ? 'warning'
                              : 'neutral'
                        }
                      >
                        {task.status}
                      </Badge>
                    </div>
                  </div>
                  <p className="text-caption text-fg-secondary">{task.description}</p>
                  {task.result && (
                    <div className="mt-1 rounded-md bg-surface-2 p-2 font-mono text-caption text-success-fg">
                      Result: {task.result}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ),
    },
    {
      id: 'consensus',
      label: t('tabConsensus'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface p-3.5">
            <span className="text-caption font-medium text-fg-secondary">
              {t('proposalPlaceholder')}
            </span>
            <textarea
              value={proposalInput}
              onChange={(e) => setProposalInput(e.target.value)}
              rows={3}
              className="w-full resize-y rounded-md border border-border-default bg-surface-2 p-2.5 text-body text-fg-primary outline-none"
            />
            <div className="flex justify-end">
              <Button
                variant="primary"
                size="sm"
                onClick={() => void handleVoteConsensus()}
                disabled={voting || !proposalInput.trim()}
              >
                {voting ? (
                  <RefreshCw className="mr-1.5 size-4 animate-spin" />
                ) : (
                  <Vote className="mr-1.5 size-4" />
                )}
                {t('voteConsensus')}
              </Button>
            </div>
          </div>

          {consensusDecision && (
            <div className="flex flex-col gap-3 rounded-lg border border-border-default bg-surface p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Scale className="size-5 text-accent" />
                  <h3 className="text-h3 font-bold">Consensus Decision</h3>
                </div>
                <Badge variant={consensusDecision.passed ? 'success' : 'danger'}>
                  {consensusDecision.passed ? (
                    <CheckCircle2 className="mr-1 size-3.5" />
                  ) : (
                    <XCircle className="mr-1 size-3.5" />
                  )}
                  {consensusDecision.passed ? t('consensusPassed') : t('consensusRejected')}
                </Badge>
              </div>

              <p className="text-body font-medium">{consensusDecision.decision_summary}</p>

              <div className="flex items-center gap-4 text-caption text-fg-muted">
                <span>Approval Ratio: {(consensusDecision.approval_ratio * 100).toFixed(0)}%</span>
                <span>Approvals: {consensusDecision.approvals}</span>
                <span>Rejections: {consensusDecision.rejections}</span>
              </div>

              {/* Votes Details */}
              <div className="flex flex-col gap-2 mt-2">
                {consensusDecision.votes.map((vote) => (
                  <div
                    key={vote.node_id}
                    className="flex flex-col gap-1 rounded-md bg-surface-2 p-2.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-caption font-bold">
                        {vote.node_name} ({vote.role})
                      </span>
                      <Badge variant={vote.vote === 'approve' ? 'success' : 'danger'}>
                        {vote.vote.toUpperCase()}
                      </Badge>
                    </div>
                    <p className="text-caption text-fg-secondary">{vote.rationale}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ),
    },
    {
      id: 'eventbus',
      label: t('tabEventBus'),
      content: (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border-default bg-surface p-3">
            <input
              type="text"
              value={busTopic}
              onChange={(e) => setBusTopic(e.target.value)}
              placeholder="Topic (e.g. system.sync)"
              className="h-8 w-48 rounded-md border border-border-default bg-surface-2 px-2.5 text-body outline-none"
            />
            <input
              type="text"
              value={busMessage}
              onChange={(e) => setBusMessage(e.target.value)}
              placeholder="Event message payload..."
              className="h-8 flex-1 min-w-48 rounded-md border border-border-default bg-surface-2 px-2.5 text-body outline-none"
            />
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleBroadcastMessage()}
              disabled={!busTopic.trim() || !busMessage.trim()}
            >
              <MessageSquare className="mr-1 size-4" />
              {t('broadcastMessage')}
            </Button>
          </div>

          <div className="flex flex-col gap-2">
            {recentEvents.map((evt, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-md bg-surface p-2.5 border border-border-default"
              >
                <div className="flex items-center gap-2">
                  <Badge variant="neutral">{evt.topic}</Badge>
                  <span className="text-body">{evt.message}</span>
                </div>
                <span className="text-caption text-fg-muted font-mono">
                  {new Date(evt.timestamp * 1000).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border-default pb-3">
        <div>
          <h2 className="text-h1 font-bold">{t('swarmStudio')}</h2>
          <p className="text-body text-fg-secondary">{t('swarmSubtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => void handleResetCluster()}>
            <Trash2 className="mr-1.5 size-4" />
            {t('clusterReset')}
          </Button>
        </div>
      </header>

      {alertMsg && (
        <div className="rounded-md bg-accent-bg p-2.5 text-caption text-accent-fg">{alertMsg}</div>
      )}

      {/* Cluster Metrics */}
      {status && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface p-2.5">
            <Users className="size-5 text-accent" />
            <div className="flex flex-col">
              <span className="text-caption text-fg-muted">{t('totalNodes')}</span>
              <span className="text-body font-bold">{status.nodes_count}</span>
            </div>
          </div>
          <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface p-2.5">
            <Network className="size-5 text-success-fg" />
            <div className="flex flex-col">
              <span className="text-caption text-fg-muted">Leader</span>
              <span className="text-body font-bold truncate">
                {status.leader ? status.leader.name : 'Elected'}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface p-2.5">
            <GitFork className="size-5 text-warning-fg" />
            <div className="flex flex-col">
              <span className="text-caption text-fg-muted">DAG Tasks</span>
              <span className="text-body font-bold">
                {status.dag_progress.completed}/{status.dag_progress.total}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2.5 rounded-lg border border-border-default bg-surface p-2.5">
            <Scale className="size-5 text-fg-muted" />
            <div className="flex flex-col">
              <span className="text-caption text-fg-muted">Consensus Rate</span>
              <span className="text-body font-bold">{status.dag_progress.pct.toFixed(0)}%</span>
            </div>
          </div>
        </div>
      )}

      <Tabs
        label="Swarm Mesh Studio Tabs"
        items={tabs}
        value={activeTab}
        onValueChange={setActiveTab}
      />
    </div>
  );
}
