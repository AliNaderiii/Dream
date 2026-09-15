import { describe, expect, it } from 'vitest';
import { BridgeClient, EchoBridgeTransport } from './client';
import {
  evalsCompareHermes,
  evalsDistillDpo,
  evalsEvolveGeneration,
  evalsGetEvolutionStatus,
  evalsListSuites,
  evalsReset,
  evalsRunSuite,
} from './evals';

const mockClient = new BridgeClient(new EchoBridgeTransport());

describe('Evals Bridge Client (Echo Mode)', () => {
  it('lists benchmark suites and runs Persian core suite', async () => {
    const listRes = await evalsListSuites(mockClient);
    expect(listRes.status).toBe('success');
    expect(listRes.total_suites).toBeGreaterThanOrEqual(4);

    const runRes = await evalsRunSuite(mockClient, 'persian_core');
    expect(runRes.status).toBe('completed');
    expect(runRes.report.overall_pass_rate).toBe(1.0);
    expect(runRes.report.results.length).toBeGreaterThan(0);
  });

  it('runs comparative benchmark proving Dream superiority over Hermes', async () => {
    const comp = await evalsCompareHermes(mockClient);
    expect(comp.status).toBe('completed');
    expect(comp.overall_winner).toBe('Dream');
    expect(comp.dream_composite_score).toBeGreaterThan(comp.hermes_composite_score);
    expect(comp.dream_composite_score).toBeGreaterThan(comp.openclaw_composite_score);
    expect(comp.dimensions.length).toBe(6);
    expect(comp.win_rate_percentage).toBe(100.0);
  });

  it('distills DPO preference pairs for model fine-tuning', async () => {
    const dpo = await evalsDistillDpo(mockClient, 3);
    expect(dpo.status).toBe('distilled');
    expect(dpo.total_pairs).toBe(3);
    expect(dpo.pairs[0].prompt).toBeDefined();
    expect(dpo.pairs[0].chosen).toBeDefined();
    expect(dpo.pairs[0].rejected).toBeDefined();
    expect(dpo.pairs[0].reward_delta).toBeGreaterThan(0);
  });

  it('manages genetic self-evolution and strategy gene pool', async () => {
    const status = await evalsGetEvolutionStatus(mockClient);
    expect(status.status).toBe('healthy');
    expect(status.leaderboard.length).toBeGreaterThanOrEqual(3);

    const evolved = await evalsEvolveGeneration(mockClient, 2);
    expect(evolved.status).toBe('evolved');
    expect(evolved.top_strategy).toBeDefined();
  });

  it('resets evals state cleanly', async () => {
    const resetRes = await evalsReset(mockClient);
    expect(resetRes.status).toBe('reset');
  });
});
