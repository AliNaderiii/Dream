import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { EchoBridgeTransport } from '@/lib/bridge/client';
import { RPC_ERROR } from '@/lib/bridge/types';
import type {
  BridgeSchedule,
  BridgeScheduleRun,
  BridgeSubagent,
  SchedulePreview,
} from '@/lib/bridge/types';

/** Polls `get` until the child reaches a terminal state, or the budget runs out. */
async function settle(
  t: EchoBridgeTransport,
  subagentId: string,
  budgetMs = 4000,
): Promise<BridgeSubagent> {
  const deadline = Date.now() + budgetMs;
  for (;;) {
    const agent = await t.request<BridgeSubagent>('poll', 'subagent.get', {
      subagent_id: subagentId,
    });
    if (agent.finished_at !== null) return agent;
    if (Date.now() > deadline) throw new Error(`subagent ${subagentId} never finished`);
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

describe('EchoBridgeTransport subagents', () => {
  let t: EchoBridgeTransport;

  beforeEach(() => {
    t = new EchoBridgeTransport();
  });

  afterEach(() => {
    t.dispose();
  });

  it('spawns a subagent that runs to completion and captures its result', async () => {
    const spawned = await t.request<BridgeSubagent>('1', 'subagent.spawn', {
      prompt: 'summarise the notes',
      name: 'Summariser',
    });
    expect(spawned.status).toBe('running');
    expect(spawned.subagent_id).toMatch(/^sub_/);
    expect(spawned.tools).toContain('calculate');

    const done = await settle(t, spawned.subagent_id);
    expect(done.status).toBe('completed');
    expect(done.result).toBe('Echo: summarise the notes');
    expect(done.progress).toBe(1);
    expect(done.turn_count).toBeGreaterThan(0);
    expect(done.token_count).toBeGreaterThan(0);
  });

  it('rejects a spawn with no prompt', async () => {
    await expect(t.request('1', 'subagent.spawn', { name: 'nameless' })).rejects.toMatchObject({
      code: RPC_ERROR.INVALID_PARAMS,
    });
  });

  it('cancels a running subagent and leaves it terminal', async () => {
    const spawned = await t.request<BridgeSubagent>('1', 'subagent.spawn', { prompt: 'long task' });
    const cancelled = await t.request<BridgeSubagent & { cancelled: boolean }>(
      '2',
      'subagent.cancel',
      { subagent_id: spawned.subagent_id },
    );
    expect(cancelled.cancelled).toBe(true);
    expect(cancelled.status).toBe('cancelled');
    expect(cancelled.error).toBe('cancelled by user');

    // A cancelled child must stay cancelled rather than drift to completed.
    await new Promise((resolve) => setTimeout(resolve, 400));
    const after = await t.request<BridgeSubagent>('3', 'subagent.get', {
      subagent_id: spawned.subagent_id,
    });
    expect(after.status).toBe('cancelled');
  });

  it('reports a limit hit when the turn budget runs out first', async () => {
    const spawned = await t.request<BridgeSubagent>('1', 'subagent.spawn', {
      prompt: 'runaway',
      max_turns: 1,
    });
    const done = await settle(t, spawned.subagent_id);
    expect(done.status).toBe('timeout');
    expect(done.limit_hit).toBe('turns');
  });

  it('pauses and resumes, and refuses the transitions that make no sense', async () => {
    const spawned = await t.request<BridgeSubagent>('1', 'subagent.spawn', { prompt: 'pausable' });
    const paused = await t.request<BridgeSubagent>('2', 'subagent.pause', {
      subagent_id: spawned.subagent_id,
    });
    expect(paused.status).toBe('paused');

    await expect(
      t.request('3', 'subagent.pause', { subagent_id: spawned.subagent_id }),
    ).rejects.toMatchObject({ code: RPC_ERROR.INVALID_PARAMS });

    const resumed = await t.request<BridgeSubagent>('4', 'subagent.resume', {
      subagent_id: spawned.subagent_id,
    });
    expect(resumed.status).toBe('running');

    await expect(
      t.request('5', 'subagent.resume', { subagent_id: spawned.subagent_id }),
    ).rejects.toMatchObject({ code: RPC_ERROR.INVALID_PARAMS });
  });

  it('lists subagents newest first with an active count', async () => {
    const first = await t.request<BridgeSubagent>('1', 'subagent.spawn', { prompt: 'one' });
    const second = await t.request<BridgeSubagent>('2', 'subagent.spawn', { prompt: 'two' });
    const listed = await t.request<{ subagents: BridgeSubagent[]; active: number }>(
      '3',
      'subagent.list',
      {},
    );
    expect(listed.subagents.map((s) => s.subagent_id)).toEqual([
      second.subagent_id,
      first.subagent_id,
    ]);
    expect(listed.active).toBe(2);
    // The list view omits logs; the detail view carries them.
    expect(listed.subagents[0]?.log).toBeUndefined();
    expect(
      (await t.request<BridgeSubagent>('4', 'subagent.get', { subagent_id: first.subagent_id }))
        .log,
    ).toBeInstanceOf(Array);
  });

  it('chains a pipeline, passing each result on as the next context', async () => {
    const pipeline = await t.request<{ pipeline_id: string; subagents: BridgeSubagent[] }>(
      '1',
      'subagent.pipeline',
      { name: 'Research', stages: [{ prompt: 'gather' }, { prompt: 'refine' }] },
    );
    expect(pipeline.pipeline_id).toMatch(/^pipe_/);
    expect(pipeline.subagents).toHaveLength(1);

    await settle(t, pipeline.subagents[0].subagent_id);
    // The second stage is spawned only once the first produced a result.
    const listed = await t.request<{ subagents: BridgeSubagent[] }>('2', 'subagent.list', {
      pipeline_id: pipeline.pipeline_id,
    });
    expect(listed.subagents).toHaveLength(2);
    const stageTwo = listed.subagents.find((s) => s.pipeline_index === 1);
    expect(stageTwo?.context).toBe('Echo: gather');
    const finished = await settle(t, stageTwo!.subagent_id);
    expect(finished.result).toBe('Echo: Echo: gather | refine');
  });

  it('rejects a pipeline with no stages', async () => {
    await expect(t.request('1', 'subagent.pipeline', { stages: [] })).rejects.toMatchObject({
      code: RPC_ERROR.INVALID_PARAMS,
    });
  });

  it('streams log lines and resolves with the finished agent', async () => {
    const spawned = await t.request<BridgeSubagent>('1', 'subagent.spawn', { prompt: 'chatty' });
    const lines: string[] = [];
    const final = await t.request<BridgeSubagent>(
      '2',
      'subagent.logs',
      { subagent_id: spawned.subagent_id },
      (chunk) => lines.push(chunk.token),
    );
    expect(lines[0]).toContain('spawned');
    expect(lines.some((line) => line.startsWith('turn 1'))).toBe(true);
    expect(lines.at(-1)).toBe('finished: completed');
    expect(final.status).toBe('completed');
  });
});

describe('EchoBridgeTransport schedules', () => {
  let t: EchoBridgeTransport;

  beforeEach(() => {
    t = new EchoBridgeTransport();
  });

  it('creates a schedule from prose and renders it back', async () => {
    const created = await t.request<BridgeSchedule>('1', 'schedule.create', {
      name: 'Morning digest',
      prompt: 'Summarise my inbox',
      natural_language: 'every day at 9 AM',
    });
    expect(created.cron_expression).toBe('0 9 * * *');
    expect(created.human).toBe('every day at 9:00 AM');
    expect(created.enabled).toBe(true);
    expect(created.next_run).toBeGreaterThan(Date.now() / 1000);
  });

  it('requires a name, a prompt, and something to schedule on', async () => {
    for (const params of [
      { prompt: 'x', natural_language: 'every day at 9 AM' },
      { name: 'x', natural_language: 'every day at 9 AM' },
      { name: 'x', prompt: 'x' },
    ]) {
      await expect(t.request('1', 'schedule.create', params)).rejects.toMatchObject({
        code: RPC_ERROR.INVALID_PARAMS,
      });
    }
  });

  it('previews prose without throwing on nonsense', async () => {
    const good = await t.request<SchedulePreview>('1', 'schedule.preview', {
      text: 'every 15 minutes',
    });
    expect(good).toMatchObject({ valid: true, cron_expression: '*/15 * * * *' });

    const bad = await t.request<SchedulePreview>('2', 'schedule.preview', {
      text: 'sometime soon',
    });
    expect(bad.valid).toBe(false);
    expect(bad.cron_expression).toBeNull();
    expect(bad.error).toMatch(/could not understand/);
  });

  it('toggles, updates and deletes', async () => {
    const created = await t.request<BridgeSchedule>('1', 'schedule.create', {
      name: 'Nightly',
      prompt: 'Back up',
      natural_language: 'every day at midnight',
    });
    const off = await t.request<BridgeSchedule>('2', 'schedule.toggle', {
      schedule_id: created.id,
    });
    expect(off.enabled).toBe(false);
    expect(off.next_run).toBeNull();

    const renamed = await t.request<BridgeSchedule>('3', 'schedule.update', {
      schedule_id: created.id,
      name: 'Nightly backup',
      natural_language: 'every day at 2 AM',
      enabled: true,
    });
    expect(renamed.name).toBe('Nightly backup');
    expect(renamed.cron_expression).toBe('0 2 * * *');

    const deleted = await t.request<{ deleted: boolean }>('4', 'schedule.delete', {
      schedule_id: created.id,
    });
    expect(deleted.deleted).toBe(true);
    expect((await t.request<{ schedules: unknown[] }>('5', 'schedule.list', {})).schedules).toEqual(
      [],
    );
  });

  it('records execution history with a status and a duration', async () => {
    const created = await t.request<BridgeSchedule>('1', 'schedule.create', {
      name: 'Hourly ping',
      prompt: 'ping',
      natural_language: 'every hour',
    });
    const executed = await t.request<{ schedule: BridgeSchedule; run: BridgeScheduleRun }>(
      '2',
      'schedule.run_now',
      { schedule_id: created.id },
    );
    expect(executed.run.status).toBe('success');
    expect(executed.run.result_summary).toBe('Echo: ping');
    expect(executed.run.duration).not.toBeNull();
    expect(executed.schedule.run_count).toBe(1);
    expect(executed.schedule.last_run).not.toBeNull();

    const history = await t.request<{ runs: BridgeScheduleRun[] }>('3', 'schedule.history', {
      schedule_id: created.id,
    });
    expect(history.runs).toHaveLength(1);
    const detail = await t.request<BridgeSchedule>('4', 'schedule.get', {
      schedule_id: created.id,
    });
    expect(detail.runs).toHaveLength(1);
  });

  it('records approval_denied when the schedule is gated', async () => {
    const created = await t.request<BridgeSchedule>('1', 'schedule.create', {
      name: 'Gated',
      prompt: 'delete everything',
      natural_language: 'every day at 9 AM',
      require_approval: true,
    });
    const executed = await t.request<{ run: BridgeScheduleRun }>('2', 'schedule.run_now', {
      schedule_id: created.id,
    });
    expect(executed.run.status).toBe('approval_denied');
  });

  it('disables a schedule once it exhausts its run budget', async () => {
    const created = await t.request<BridgeSchedule>('1', 'schedule.create', {
      name: 'One-shot',
      prompt: 'once',
      natural_language: 'every day at 9 AM',
      max_runs: 1,
    });
    const executed = await t.request<{ schedule: BridgeSchedule }>('2', 'schedule.run_now', {
      schedule_id: created.id,
    });
    expect(executed.schedule.exhausted).toBe(true);
    expect(executed.schedule.enabled).toBe(false);
    expect(executed.schedule.next_run).toBeNull();
  });

  it('rejects operations on an unknown schedule', async () => {
    await expect(t.request('1', 'schedule.get', { schedule_id: 'nope' })).rejects.toMatchObject({
      code: RPC_ERROR.INVALID_PARAMS,
    });
  });
});
