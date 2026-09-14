/** Typed client wrappers for reasoning.* JSON-RPC methods. */

import type { BridgeClient } from './client';
import * as echo from './echo-reasoning';

export interface ThoughtNode {
  node_id: string;
  parent_id: string | null;
  thought_content: string;
  score: number;
  depth: number;
  status: 'unexplored' | 'expanded' | 'evaluated' | 'pruned' | 'selected' | 'dead_end';
  eval_rationale: string;
  children_count: number;
  visits: number;
  created_at: number;
}

export interface MetacognitiveEvaluation {
  evaluation_id: string;
  coherence_score: number;
  depth_score: number;
  hallucination_risk: number;
  critique_notes: string;
  suggested_action: string;
  timestamp: number;
}

export interface ReasoningTrajectory {
  trajectory_id: string;
  goal: string;
  strategy: string;
  root_node_id: string;
  total_nodes: number;
  selected_path: string[];
  final_answer: string;
  confidence: number;
  created_at: number;
  updated_at: number;
  nodes?: ThoughtNode[];
}

export interface TreeStatsResult {
  status: string;
  total_trajectories: number;
  active_trajectory_id: string | null;
  active_nodes_count: number;
  pruned_nodes_count: number;
  max_tree_depth: number;
  confidence: number;
  trajectory: ReasoningTrajectory | null;
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

export function reasoningPlanTree(
  client: BridgeClient,
  goal: string,
  strategy = 'tree_of_thought',
): Promise<{
  status: string;
  trajectory_id: string;
  root_node_id: string;
  trajectory: ReasoningTrajectory;
}> {
  return echoOr(client, () => echo.echoReasoningPlanTree(goal, strategy), 'reasoning.plan_tree', {
    goal,
    strategy,
  });
}

export function reasoningExpandBranch(
  client: BridgeClient,
  trajectoryId: string,
  parentNodeId: string,
  thoughts: string[],
): Promise<{
  status: string;
  trajectory_id: string;
  parent_node_id: string;
  nodes: ThoughtNode[];
}> {
  return echoOr(
    client,
    () => echo.echoReasoningExpandBranch(trajectoryId, parentNodeId, thoughts),
    'reasoning.expand_branch',
    { trajectory_id: trajectoryId, parent_node_id: parentNodeId, thoughts },
  );
}

export function reasoningStepCritique(
  client: BridgeClient,
  trajectoryId: string,
  nodeId: string,
): Promise<{
  status: string;
  node_id: string;
  score: number;
  critique: MetacognitiveEvaluation;
}> {
  return echoOr(
    client,
    () => echo.echoReasoningStepCritique(trajectoryId, nodeId),
    'reasoning.step_critique',
    { trajectory_id: trajectoryId, node_id: nodeId },
  );
}

export function reasoningMctsSearch(
  client: BridgeClient,
  trajectoryId: string,
  candidateThoughts?: string[],
): Promise<{
  status: string;
  trajectory_id: string;
  expanded_parent_id: string;
  new_nodes_count: number;
  evaluated_nodes: ThoughtNode[];
}> {
  return echoOr(
    client,
    () => echo.echoReasoningMctsSearch(trajectoryId, candidateThoughts),
    'reasoning.mcts_search',
    { trajectory_id: trajectoryId, candidate_thoughts: candidateThoughts },
  );
}

export function reasoningBacktrack(
  client: BridgeClient,
  trajectoryId: string,
  minThreshold = 0.35,
): Promise<{
  status: string;
  trajectory_id: string;
  pruned_nodes_count: number;
  active_nodes_count: number;
  best_path: string[];
}> {
  return echoOr(
    client,
    () => echo.echoReasoningBacktrack(trajectoryId, minThreshold),
    'reasoning.backtrack',
    { trajectory_id: trajectoryId, min_threshold: minThreshold },
  );
}

export function reasoningSynthesizeSolution(
  client: BridgeClient,
  trajectoryId: string,
): Promise<{
  status: string;
  trajectory_id: string;
  goal: string;
  confidence: number;
  selected_path: string[];
  final_answer: string;
  steps: ThoughtNode[];
}> {
  return echoOr(
    client,
    () => echo.echoReasoningSynthesizeSolution(trajectoryId),
    'reasoning.synthesize_solution',
    { trajectory_id: trajectoryId },
  );
}

export function reasoningGetTreeStats(
  client: BridgeClient,
  trajectoryId?: string,
): Promise<TreeStatsResult> {
  return echoOr(
    client,
    () => echo.echoReasoningGetTreeStats(trajectoryId),
    'reasoning.get_tree_stats',
    { trajectory_id: trajectoryId },
  );
}

export function reasoningReset(client: BridgeClient): Promise<{ status: string; message: string }> {
  return echoOr(client, () => echo.echoReasoningReset(), 'reasoning.reset', {});
}
