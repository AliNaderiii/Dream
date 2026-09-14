/** Vitest suite for reasoning bridge client wrappers and echo offline fallback. */

import { beforeEach, describe, expect, it } from 'vitest';
import { getBridgeClient, resetBridgeClient, type BridgeClient } from './client';
import { resetEchoReasoning } from './echo-reasoning';
import {
  reasoningBacktrack,
  reasoningExpandBranch,
  reasoningGetTreeStats,
  reasoningMctsSearch,
  reasoningPlanTree,
  reasoningReset,
  reasoningStepCritique,
  reasoningSynthesizeSolution,
} from './reasoning';

describe('Tree-of-Thought & MCTS Reasoning Bridge Client', () => {
  let client: BridgeClient;

  beforeEach(async () => {
    resetBridgeClient();
    resetEchoReasoning();
    client = getBridgeClient();
    await reasoningReset(client);
  });

  it('initializes a new thought tree for a goal', async () => {
    const res = await reasoningPlanTree(client, 'بهینه‌سازی معماری چندعاملی', 'tree_of_thought');
    expect(res.status).toBe('initialized');
    expect(res.trajectory_id).toBeDefined();
    expect(res.root_node_id).toBeDefined();
    expect(res.trajectory.total_nodes).toBe(1);
  });

  it('expands candidate hypotheses and performs self-critique', async () => {
    const plan = await reasoningPlanTree(client, 'طراحی پایپ‌لاین تحلیل داده');
    const exp = await reasoningExpandBranch(client, plan.trajectory_id, plan.root_node_id, [
      'شاخه الف: بهینه‌سازی بار پردازشی',
      'شاخه ب: پردازش توزیع‌شده ناهمگام',
    ]);
    expect(exp.status).toBe('expanded');
    expect(exp.nodes.length).toBe(2);

    const critique = await reasoningStepCritique(client, plan.trajectory_id, exp.nodes[0].node_id);
    expect(critique.status).toBe('critiqued');
    expect(critique.score).toBeGreaterThanOrEqual(0.7);
    expect(critique.critique.coherence_score).toBeGreaterThan(0);
  });

  it('executes MCTS search rollout and gets stats', async () => {
    const plan = await reasoningPlanTree(client, 'مسئله ارزیابی MCTS');
    const mcts = await reasoningMctsSearch(client, plan.trajectory_id);
    expect(mcts.status).toBe('searched');
    expect(mcts.new_nodes_count).toBeGreaterThanOrEqual(1);

    const stats = await reasoningGetTreeStats(client, plan.trajectory_id);
    expect(stats.status).toBe('healthy');
    expect(stats.active_nodes_count).toBeGreaterThanOrEqual(1);
  });

  it('prunes branches and synthesizes solution', async () => {
    const plan = await reasoningPlanTree(client, 'تست سنتز راهکار نهایی');
    await reasoningMctsSearch(client, plan.trajectory_id);

    const backtrack = await reasoningBacktrack(client, plan.trajectory_id, 0.2);
    expect(backtrack.status).toBe('backtracked');

    const synth = await reasoningSynthesizeSolution(client, plan.trajectory_id);
    expect(synth.status).toBe('synthesized');
    expect(synth.confidence).toBeGreaterThan(0.5);
    expect(synth.final_answer.length).toBeGreaterThan(0);
  });
});
