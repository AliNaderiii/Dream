import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient, type BridgeClient } from './client';
import {
  dialecticAddBelief,
  dialecticDebateTurn,
  dialecticDetectTensions,
  dialecticLinkBeliefs,
  dialecticObserve,
  dialecticQuery,
  dialecticReconcileTension,
  dialecticReset,
  dialecticSnapshot,
} from './dialectic';
import { resetEchoDialectic } from './echo-dialectic';

describe('Dialectic Bridge Client', () => {
  let client: BridgeClient;

  beforeEach(() => {
    resetBridgeClient();
    resetEchoDialectic();
    client = getBridgeClient();
  });

  it('observes and queries statements', async () => {
    const obs = await dialecticObserve(
      client,
      'Memory consolidation prevents prompt drift',
      'cognition',
    );
    expect(obs.status).toBe('observed');
    expect(obs.belief.statement).toContain('Memory consolidation');

    const query = await dialecticQuery(client, 'Memory');
    expect(query.status).toBe('ok');
    expect(query.count).toBeGreaterThanOrEqual(1);
  });

  it('adds beliefs, links contradiction, and detects tensions', async () => {
    const b1 = await dialecticAddBelief(
      client,
      'Fast reactive streaming is optimal',
      'networking',
      0.85,
    );
    const b2 = await dialecticAddBelief(
      client,
      'Deep batch processing is required',
      'networking',
      0.9,
    );

    const link = await dialecticLinkBeliefs(
      client,
      b1.belief.belief_id,
      b2.belief.belief_id,
      'contradicts',
    );
    expect(link.status).toBe('linked');

    const tensions = await dialecticDetectTensions(client);
    expect(tensions.count).toBeGreaterThanOrEqual(1);

    const tensionId = tensions.tensions[0].tension_id;
    const reconciled = await dialecticReconcileTension(
      client,
      tensionId,
      'Adaptive streaming with buffered micro-batches',
    );
    expect(reconciled.status).toBe('reconciled');
    expect(reconciled.nuanced_belief.statement).toContain('Adaptive streaming');
  });

  it('runs 3-agent dialectic debate turn and takes snapshot', async () => {
    const debate = await dialecticDebateTurn(
      client,
      'Hybrid LLM Semantic Router v3.0',
      'performance',
    );
    expect(debate.status).toBe('completed');
    expect(debate.thesis).toBeDefined();
    expect(debate.antithesis).toBeDefined();
    expect(debate.synthesis).toBeDefined();
    expect(debate.graph_snapshot.nodes_count).toBeGreaterThanOrEqual(3);

    const snap = await dialecticSnapshot(client);
    expect(snap.top_beliefs.length).toBeGreaterThanOrEqual(3);

    const reset = await dialecticReset(client);
    expect(reset.status).toBe('reset');
    const emptySnap = await dialecticSnapshot(client);
    expect(emptySnap.nodes_count).toBe(0);
  });
});
