/** In-memory echo fallback implementation for swarm.* bridge methods. */

import type { ConsensusDecision, SwarmNode, SwarmStatusSummary, SwarmTask } from './swarm';

const defaultNodes: SwarmNode[] = [
  {
    node_id: 'node_leader_01',
    name: 'Swarm Coordinator Leader',
    role: 'leader',
    model: 'gpt-4o',
    capabilities: ['orchestration', 'delegation', 'synthesis'],
    status: 'idle',
    created_at: Date.now() / 1000,
    last_heartbeat: Date.now() / 1000,
    metadata: {},
  },
  {
    node_id: 'node_arch_02',
    name: 'System Architect Node',
    role: 'architect',
    model: 'gpt-4o',
    capabilities: ['design', 'api_spec', 'architecture'],
    status: 'idle',
    created_at: Date.now() / 1000,
    last_heartbeat: Date.now() / 1000,
    metadata: {},
  },
  {
    node_id: 'node_coder_03',
    name: 'Core Code Engineer',
    role: 'coder',
    model: 'claude-3-5-sonnet',
    capabilities: ['python', 'typescript', 'refactoring'],
    status: 'idle',
    created_at: Date.now() / 1000,
    last_heartbeat: Date.now() / 1000,
    metadata: {},
  },
  {
    node_id: 'node_critic_04',
    name: 'Security & Quality Critic',
    role: 'critic',
    model: 'gpt-4o',
    capabilities: ['security_audit', 'code_review', 'verification'],
    status: 'idle',
    created_at: Date.now() / 1000,
    last_heartbeat: Date.now() / 1000,
    metadata: {},
  },
];

let state: {
  nodes: SwarmNode[];
  tasks: SwarmTask[];
  messages: Array<{
    message_id: string;
    sender_id: string;
    topic: string;
    payload: { message: string };
    timestamp: number;
  }>;
} = {
  nodes: [...defaultNodes],
  tasks: [],
  messages: [],
};

export function echoSwarmGetStatus(): SwarmStatusSummary {
  const completed = state.tasks.filter((t) => t.status === 'completed').length;
  const total = state.tasks.length;
  const pct = total > 0 ? (completed / total) * 100 : 100.0;

  return {
    status: 'healthy',
    nodes_count: state.nodes.length,
    active_nodes: state.nodes,
    leader: state.nodes.find((n) => n.role === 'leader') || state.nodes[0] || null,
    dag_progress: {
      total,
      completed,
      failed: 0,
      in_progress: 0,
      pending: total - completed,
      pct,
    },
    tasks: state.tasks,
    recent_messages_count: state.messages.length,
    recent_consensus_count: 1,
  };
}

export function echoSwarmListNodes(): {
  status: string;
  nodes: SwarmNode[];
  total_nodes: number;
  leader_id: string | null;
} {
  const leader = state.nodes.find((n) => n.role === 'leader');
  return {
    status: 'success',
    nodes: [...state.nodes],
    total_nodes: state.nodes.length,
    leader_id: leader?.node_id ?? null,
  };
}

export function echoSwarmSpawnNode(
  name: string,
  role = 'specialist',
  model = 'gpt-4o',
  capabilities: string[] = [],
): {
  status: string;
  node: SwarmNode;
} {
  if (!name || !name.trim()) {
    throw new Error('name must be a non-empty string');
  }

  const node: SwarmNode = {
    node_id: `node_${Math.random().toString(36).substring(2, 8)}`,
    name: name.trim(),
    role: role as SwarmNode['role'],
    model: model.trim(),
    capabilities,
    status: 'idle',
    created_at: Date.now() / 1000,
    last_heartbeat: Date.now() / 1000,
    metadata: {},
  };

  state.nodes.push(node);
  return {
    status: 'spawned',
    node,
  };
}

export function echoSwarmPlanWorkflow(goal: string): {
  status: string;
  goal: string;
  tasks: SwarmTask[];
  total_tasks: number;
} {
  if (!goal || !goal.trim()) {
    throw new Error('goal must be a non-empty string');
  }

  const now = Date.now() / 1000;
  const t1: SwarmTask = {
    task_id: `task_${Math.random().toString(36).substring(2, 8)}`,
    title: `Architecture spec for: ${goal.substring(0, 30)}`,
    description: `Design high-level architecture for ${goal}`,
    assigned_to: 'architect',
    assigned_node_id: 'node_arch_02',
    status: 'pending',
    dependencies: [],
    priority: 1,
    result: null,
    created_at: now,
    started_at: null,
    completed_at: null,
  };

  const t2: SwarmTask = {
    task_id: `task_${Math.random().toString(36).substring(2, 8)}`,
    title: `Implementation for: ${goal.substring(0, 30)}`,
    description: `Code implementation for ${goal}`,
    assigned_to: 'coder',
    assigned_node_id: 'node_coder_03',
    status: 'pending',
    dependencies: [t1.task_id],
    priority: 2,
    result: null,
    created_at: now,
    started_at: null,
    completed_at: null,
  };

  const t3: SwarmTask = {
    task_id: `task_${Math.random().toString(36).substring(2, 8)}`,
    title: `Security audit for: ${goal.substring(0, 30)}`,
    description: `Audit and review code for ${goal}`,
    assigned_to: 'critic',
    assigned_node_id: 'node_critic_04',
    status: 'pending',
    dependencies: [t2.task_id],
    priority: 3,
    result: null,
    created_at: now,
    started_at: null,
    completed_at: null,
  };

  state.tasks = [t1, t2, t3];

  return {
    status: 'planned',
    goal: goal.trim(),
    tasks: state.tasks,
    total_tasks: state.tasks.length,
  };
}

export function echoSwarmExecuteStep(): {
  status: string;
  executed: number;
  is_complete: boolean;
  executed_tasks: SwarmTask[];
} {
  const pending = state.tasks.find((t) => t.status === 'pending');
  if (pending) {
    pending.status = 'completed';
    pending.result = 'Step executed successfully by swarm agent.';
    pending.completed_at = Date.now() / 1000;
    return {
      status: 'executed',
      executed: 1,
      is_complete: state.tasks.every((t) => t.status === 'completed'),
      executed_tasks: [pending],
    };
  }

  return {
    status: 'executed',
    executed: 0,
    is_complete: true,
    executed_tasks: [],
  };
}

export function echoSwarmRunAll(goal?: string): {
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
} {
  if (goal) {
    echoSwarmPlanWorkflow(goal);
  }

  for (const t of state.tasks) {
    t.status = 'completed';
    t.result = 'Completed by automated swarm execution.';
  }

  return {
    status: 'completed',
    iterations: state.tasks.length,
    progress: {
      total: state.tasks.length,
      completed: state.tasks.length,
      failed: 0,
      in_progress: 0,
      pending: 0,
      pct: 100.0,
    },
    is_complete: true,
  };
}

export function echoSwarmVoteConsensus(proposal: string): {
  status: string;
  decision: ConsensusDecision;
} {
  if (!proposal || !proposal.trim()) {
    throw new Error('proposal must be a non-empty string');
  }

  const now = Date.now() / 1000;
  const decision: ConsensusDecision = {
    proposal_id: `prop_${Math.random().toString(36).substring(2, 8)}`,
    proposal_text: proposal.trim(),
    passed: true,
    approval_ratio: 1.0,
    total_votes: state.nodes.length,
    approvals: state.nodes.length,
    rejections: 0,
    abstentions: 0,
    votes: state.nodes.map((n) => ({
      node_id: n.node_id,
      node_name: n.name,
      role: n.role,
      vote: 'approve',
      confidence: 0.95,
      rationale: `Node ${n.name} approves the proposal based on structural coherence.`,
      timestamp: now,
    })),
    decision_summary: `The swarm council unanimously approved the proposal: '${proposal.trim()}'`,
    timestamp: now,
  };

  return {
    status: 'decided',
    decision,
  };
}

export function echoSwarmBroadcastMessage(
  topic: string,
  message: string,
): {
  status: string;
  message: {
    message_id: string;
    sender_id: string;
    topic: string;
    payload: { message: string };
    timestamp: number;
  };
} {
  if (!topic || !topic.trim()) {
    throw new Error('topic must be a non-empty string');
  }

  const msg = {
    message_id: `msg_${Math.random().toString(36).substring(2, 8)}`,
    sender_id: 'user_agent',
    topic: topic.trim(),
    payload: { message: message.trim() },
    timestamp: Date.now() / 1000,
  };

  state.messages.push(msg);

  return {
    status: 'published',
    message: msg,
  };
}

export function echoSwarmReset(): { status: string; message: string } {
  state = {
    nodes: [...defaultNodes],
    tasks: [],
    messages: [],
  };
  return {
    status: 'reset',
    message: 'Echo swarm cluster reset successfully.',
  };
}
