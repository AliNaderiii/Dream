import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient, type BridgeClient } from './client';
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
} from './swarm';

describe('Swarm Neural Mesh Bridge Client (Echo transport)', () => {
  let client: BridgeClient;

  beforeEach(async () => {
    resetBridgeClient();
    client = getBridgeClient();
    await swarmReset(client);
  });

  it('retrieves swarm status and lists registered nodes', async () => {
    const status = await swarmGetStatus(client);
    expect(status.status).toBe('healthy');
    expect(status.nodes_count).toBeGreaterThanOrEqual(1);

    const nodes = await swarmListNodes(client);
    expect(nodes.status).toBe('success');
    expect(nodes.nodes.length).toBeGreaterThanOrEqual(1);
  });

  it('spawns a new specialized agent node in the cluster', async () => {
    const res = await swarmSpawnNode(client, 'Data Engineer Node', 'coder', 'gpt-4o', [
      'data_pipeline',
      'sql',
    ]);
    expect(res.status).toBe('spawned');
    expect(res.node.name).toBe('Data Engineer Node');
    expect(res.node.role).toBe('coder');
  });

  it('plans a task DAG workflow and executes steps', async () => {
    const plan = await swarmPlanWorkflow(client, 'طراحی میکروسرویس پیام‌رسان');
    expect(plan.status).toBe('planned');
    expect(plan.tasks.length).toBe(3);

    const stepRes = await swarmExecuteStep(client);
    expect(stepRes.status).toBe('executed');
  });

  it('runs all tasks to completion and reaches consensus', async () => {
    const runRes = await swarmRunAll(client, 'پیاده‌سازی ماژول استدلال موازی');
    expect(runRes.status).toBe('completed');
    expect(runRes.is_complete).toBe(true);

    const consensus = await swarmVoteConsensus(client, 'تصویب تغییر ساختار داده‌های حافظه');
    expect(consensus.status).toBe('decided');
    expect(consensus.decision.passed).toBe(true);
    expect(consensus.decision.votes.length).toBeGreaterThanOrEqual(1);
  });

  it('broadcasts inter-agent messages on the neural bus', async () => {
    const msg = await swarmBroadcastMessage(client, 'agent.event.sync', 'Sync completed');
    expect(msg.status).toBe('published');
    expect(msg.message.topic).toBe('agent.event.sync');
  });
});
