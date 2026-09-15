/** Typed client wrappers for swarm.* JSON-RPC methods. */

import type { BridgeClient } from './client';
import * as echo from './echo-swarm';

export interface SwarmNode {
  node_id: string;
  name: string;
  role: 'leader' | 'architect' | 'coder' | 'critic' | 'arbiter' | 'researcher' | 'specialist';
  model: string;
  capabilities: string[];
  status: 'idle' | 'busy' | 'offline';
  created_at: number;
  last_heartbeat: number;
  metadata: Record<string, unknown>;
}

export interface SwarmTask {
  task_id: string;
  title: string;
  description: string;
  assigned_to: string;
  assigned_node_id: string | null;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'blocked';
  dependencies: string[];
  priority: number;
  result: string | null;
  created_at: number;
  started_at: number | null;
  completed_at: number | null;
}

export interface ConsensusVote {
  node_id: string;
  node_name: string;
  role: string;
  vote: 'approve' | 'reject' | 'abstain';
  confidence: number;
  rationale: string;
  timestamp: number;
}

export interface ConsensusDecision {
  proposal_id: string;
  proposal_text: string;
  passed: boolean;
  approval_ratio: number;
  total_votes: number;
  approvals: number;
  rejections: number;
  abstentions: number;
  votes: ConsensusVote[];
  decision_summary: string;
  timestamp: number;
}

export interface SwarmStatusSummary {
  status: string;
  nodes_count: number;
  active_nodes: SwarmNode[];
  leader: SwarmNode | null;
  dag_progress: {
    total: number;
    completed: number;
    failed: number;
    in_progress?: number;
    pending: number;
    pct: number;
  };
  tasks: SwarmTask[];
  recent_messages_count: number;
  recent_consensus_count: number;
}

function echoOr<T>(
  client: BridgeClient,
  local: () => T,
  method: string,
  params: Record<string, unknown>,
): Promise<T> {
  if (client.transportKind === 'echo') {
    try {
      return Promise.resolve(local());
    } catch (error) {
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }
  }
  return client.call<T>(method, params);
}

export function swarmGetStatus(client: BridgeClient): Promise<SwarmStatusSummary> {
  return echoOr(client, () => echo.echoSwarmGetStatus(), 'swarm.get_status', {});
}

export function swarmListNodes(client: BridgeClient): Promise<{
  status: string;
  nodes: SwarmNode[];
  total_nodes: number;
  leader_id: string | null;
}> {
  return echoOr(client, () => echo.echoSwarmListNodes(), 'swarm.list_nodes', {});
}

export function swarmSpawnNode(
  client: BridgeClient,
  name: string,
  role = 'specialist',
  model = 'gpt-4o',
  capabilities: string[] = [],
): Promise<{
  status: string;
  node: SwarmNode;
}> {
  return echoOr(
    client,
    () => echo.echoSwarmSpawnNode(name, role, model, capabilities),
    'swarm.spawn_node',
    { name, role, model, capabilities },
  );
}

export function swarmPlanWorkflow(
  client: BridgeClient,
  goal: string,
): Promise<{
  status: string;
  goal: string;
  tasks: SwarmTask[];
  total_tasks: number;
}> {
  return echoOr(client, () => echo.echoSwarmPlanWorkflow(goal), 'swarm.plan_workflow', { goal });
}

export function swarmExecuteStep(client: BridgeClient): Promise<{
  status: string;
  executed: number;
  is_complete: boolean;
  executed_tasks?: SwarmTask[];
  message?: string;
}> {
  return echoOr(client, () => echo.echoSwarmExecuteStep(), 'swarm.execute_step', {});
}

export function swarmRunAll(
  client: BridgeClient,
  goal?: string,
): Promise<{
  status: string;
  iterations: number;
  progress: {
    total: number;
    completed: number;
    failed: number;
    in_progress: number;
    pending: number;
    pct: number;
  };
  is_complete: boolean;
}> {
  return echoOr(client, () => echo.echoSwarmRunAll(goal), 'swarm.run_all', { goal });
}

export function swarmVoteConsensus(
  client: BridgeClient,
  proposal: string,
): Promise<{
  status: string;
  decision: ConsensusDecision;
}> {
  return echoOr(client, () => echo.echoSwarmVoteConsensus(proposal), 'swarm.vote_consensus', {
    proposal,
  });
}

export function swarmBroadcastMessage(
  client: BridgeClient,
  topic: string,
  message: string,
): Promise<{
  status: string;
  message: {
    message_id: string;
    sender_id: string;
    topic: string;
    payload: { message: string };
    timestamp: number;
  };
}> {
  return echoOr(
    client,
    () => echo.echoSwarmBroadcastMessage(topic, message),
    'swarm.broadcast_message',
    { topic, message },
  );
}

export function swarmReset(client: BridgeClient): Promise<{
  status: string;
  message: string;
}> {
  return echoOr(client, () => echo.echoSwarmReset(), 'swarm.reset', {});
}
