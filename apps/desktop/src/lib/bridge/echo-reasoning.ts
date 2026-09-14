/** Echo / offline fallback for reasoning.* JSON-RPC methods. */

import type {
  MetacognitiveEvaluation,
  ReasoningTrajectory,
  ThoughtNode,
  TreeStatsResult,
} from './reasoning';

let mockNodes: Record<string, ThoughtNode> = {};
let mockActiveTrajectory: ReasoningTrajectory | null = null;
let mockTrajCounter = 0;

export function resetEchoReasoning(): void {
  mockNodes = {};
  mockActiveTrajectory = null;
  mockTrajCounter = 0;
}

export function echoReasoningPlanTree(
  goal = 'بهینه‌سازی شبکه عامل‌های چندگانه',
  strategy = 'tree_of_thought',
): {
  status: string;
  trajectory_id: string;
  root_node_id: string;
  trajectory: ReasoningTrajectory;
} {
  mockTrajCounter += 1;
  const tid = `traj-${mockTrajCounter.toString().padStart(3, '0')}`;
  const rootId = `node-root-${mockTrajCounter}`;

  const rootNode: ThoughtNode = {
    node_id: rootId,
    parent_id: null,
    thought_content: `هدف: ${goal}`,
    score: 1.0,
    depth: 0,
    status: 'selected',
    eval_rationale: 'گره ریشه درخت استدلال استراتژیک',
    children_count: 0,
    visits: 1,
    created_at: Date.now() / 1000,
  };

  mockNodes = { [rootId]: rootNode };

  mockActiveTrajectory = {
    trajectory_id: tid,
    goal,
    strategy,
    root_node_id: rootId,
    total_nodes: 1,
    selected_path: [rootId],
    final_answer: '',
    confidence: 1.0,
    created_at: Date.now() / 1000,
    updated_at: Date.now() / 1000,
    nodes: [rootNode],
  };

  return {
    status: 'initialized',
    trajectory_id: tid,
    root_node_id: rootId,
    trajectory: mockActiveTrajectory,
  };
}

export function echoReasoningExpandBranch(
  _trajectoryId: string,
  parentNodeId: string,
  thoughts: string[] = [],
): {
  status: string;
  trajectory_id: string;
  parent_node_id: string;
  nodes: ThoughtNode[];
} {
  const created: ThoughtNode[] = [];
  const parent = mockNodes[parentNodeId];
  const depth = (parent?.depth ?? 0) + 1;

  for (const t of thoughts) {
    const nid = `node-${Math.random().toString(16).slice(2, 8)}`;
    const node: ThoughtNode = {
      node_id: nid,
      parent_id: parentNodeId,
      thought_content: t,
      score: 0.75,
      depth,
      status: 'unexplored',
      eval_rationale: 'شاخه پیشنهادی جهت ارزیابی MCTS',
      children_count: 0,
      visits: 0,
      created_at: Date.now() / 1000,
    };
    mockNodes[nid] = node;
    created.push(node);
  }

  if (parent) {
    parent.children_count += created.length;
    parent.status = 'expanded';
  }

  if (mockActiveTrajectory) {
    mockActiveTrajectory.total_nodes = Object.keys(mockNodes).length;
    mockActiveTrajectory.nodes = Object.values(mockNodes);
  }

  return {
    status: 'expanded',
    trajectory_id: mockActiveTrajectory?.trajectory_id ?? 'traj-001',
    parent_node_id: parentNodeId,
    nodes: created,
  };
}

export function echoReasoningStepCritique(
  _trajectoryId: string,
  nodeId: string,
): {
  status: string;
  node_id: string;
  score: number;
  critique: MetacognitiveEvaluation;
} {
  const node = mockNodes[nodeId];
  const score = node ? 0.88 : 0.5;
  if (node) {
    node.score = score;
    node.status = 'evaluated';
    node.eval_rationale = 'تحلیل خودبازتابی: فرضیه منسجم و سازگار با محدودیت‌های سیستمی';
  }

  return {
    status: 'critiqued',
    node_id: nodeId,
    score,
    critique: {
      evaluation_id: `eval-${Math.random().toString(16).slice(2, 8)}`,
      coherence_score: 0.9,
      depth_score: 0.85,
      hallucination_risk: 0.05,
      critique_notes: 'تحلیل خودبازتابی: فرضیه منسجم و سازگار با محدودیت‌های سیستمی',
      suggested_action: 'continue_exploration',
      timestamp: Date.now() / 1000,
    },
  };
}

export function echoReasoningMctsSearch(
  _trajectoryId: string,
  candidateThoughts?: string[],
): {
  status: string;
  trajectory_id: string;
  expanded_parent_id: string;
  new_nodes_count: number;
  evaluated_nodes: ThoughtNode[];
} {
  const rootId = mockActiveTrajectory?.root_node_id || 'node-root-1';
  const thoughts = candidateThoughts || [
    'تحلیل متغیرهای معماری و ارزیابی ریسک',
    'آزمون تجربی و بهینه‌سازی توان عملیاتی',
  ];
  const exp = echoReasoningExpandBranch(
    mockActiveTrajectory?.trajectory_id ?? 'traj-001',
    rootId,
    thoughts,
  );

  return {
    status: 'searched',
    trajectory_id: mockActiveTrajectory?.trajectory_id ?? 'traj-001',
    expanded_parent_id: rootId,
    new_nodes_count: exp.nodes.length,
    evaluated_nodes: exp.nodes,
  };
}

export function echoReasoningBacktrack(
  _trajectoryId: string,
  minThreshold = 0.35,
): {
  status: string;
  trajectory_id: string;
  pruned_nodes_count: number;
  active_nodes_count: number;
  best_path: string[];
} {
  let pruned = 0;
  for (const n of Object.values(mockNodes)) {
    if (n.depth > 0 && n.score < minThreshold) {
      n.status = 'pruned';
      pruned += 1;
    }
  }

  const activeNodes = Object.values(mockNodes).filter((n) => n.status !== 'pruned');
  return {
    status: 'backtracked',
    trajectory_id: mockActiveTrajectory?.trajectory_id ?? 'traj-001',
    pruned_nodes_count: pruned,
    active_nodes_count: activeNodes.length,
    best_path: mockActiveTrajectory?.selected_path ?? [],
  };
}

export function echoReasoningSynthesizeSolution(_trajectoryId: string): {
  status: string;
  trajectory_id: string;
  goal: string;
  confidence: number;
  selected_path: string[];
  final_answer: string;
  steps: ThoughtNode[];
} {
  const active = Object.values(mockNodes).filter((n) => n.status !== 'pruned');
  return {
    status: 'synthesized',
    trajectory_id: mockActiveTrajectory?.trajectory_id ?? 'traj-001',
    goal: mockActiveTrajectory?.goal ?? 'مسئله فرضی',
    confidence: 0.92,
    selected_path: active.map((n) => n.node_id),
    final_answer: 'سنتز راهکار نهایی بر پایه درخت استدلال MCTS و ارزیابی چندمعیاره.',
    steps: active,
  };
}

export function echoReasoningGetTreeStats(_trajectoryId?: string): TreeStatsResult {
  if (!mockActiveTrajectory) {
    echoReasoningPlanTree();
  }

  const all = Object.values(mockNodes);
  const active = all.filter((n) => n.status !== 'pruned');
  const pruned = all.filter((n) => n.status === 'pruned');

  return {
    status: 'healthy',
    total_trajectories: mockTrajCounter || 1,
    active_trajectory_id: mockActiveTrajectory?.trajectory_id ?? 'traj-001',
    active_nodes_count: active.length,
    pruned_nodes_count: pruned.length,
    max_tree_depth: Math.max(...all.map((n) => n.depth), 0),
    confidence: mockActiveTrajectory?.confidence ?? 0.9,
    trajectory: mockActiveTrajectory,
  };
}

export function echoReasoningReset(): { status: string; message: string } {
  resetEchoReasoning();
  return { status: 'reset', message: 'Reasoning trees cleared.' };
}
