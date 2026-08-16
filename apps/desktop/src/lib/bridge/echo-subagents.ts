/**
 * In-memory subagent and schedule runtimes for the echo transport.
 *
 * The Python sidecar owns the real behaviour; this file exists so the
 * subagent monitor and the scheduler screens are fully exercisable in `npm run
 * dev` and in unit tests with no sidecar running. It reproduces the observable
 * contract of `dream/subagents.py` and `dream/scheduler.py` — the same wire
 * shapes, the same status vocabulary, the same pipeline chaining — with a
 * simulated child that emits a log line per turn on a timer.
 */

import { describeCron, nextRunAfter } from '@/lib/schedule/cron';
import { nlToCron, ScheduleParseError } from '@/lib/schedule/nl-to-cron';

import { BridgeRpcError } from './errors';
import type {
  BridgeLogEntry,
  BridgeSchedule,
  BridgeScheduleRun,
  BridgeSubagent,
  RpcParams,
  SchedulePreview,
  SubAgentStatus,
} from './types';
import { isTerminalStatus, RPC_ERROR } from './types';

/** Sidecar defaults, mirrored from `dream/subagents.py`. */
const DEFAULT_MAX_TURNS = 8;
const DEFAULT_MAX_TOKENS = 20_000;
const DEFAULT_MAX_DURATION = 120;
const DEFAULT_TOOLS = ['calculate', 'get_datetime', 'remember_fact', 'search_memory'];

/** Simulated pacing: one turn every `STEP_MS`, `ECHO_TURNS` turns per child. */
const STEP_MS = 200;
const ECHO_TURNS = 3;
const TOKENS_PER_TURN = 180;

let counter = 0;

const nextId = (prefix: string): string => `${prefix}_${(++counter).toString(16).padStart(6, '0')}`;

/** Seconds since the epoch, matching the sidecar's float timestamps. */
const now = (): number => Date.now() / 1000;

function invalidParams(message: string): BridgeRpcError {
  return new BridgeRpcError({ code: RPC_ERROR.INVALID_PARAMS, message });
}

function str(params: RpcParams, key: string, fallback = ''): string {
  const value = params[key];
  return typeof value === 'string' ? value : fallback;
}

function num(params: RpcParams, key: string, fallback: number): number {
  const value = params[key];
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : fallback;
}

/** Internal bookkeeping the wire shape does not carry. */
interface EchoAgentState {
  agent: BridgeSubagent;
  /** Spawn order. `created_at` has millisecond resolution and ties too easily. */
  seq: number;
  timer: ReturnType<typeof setTimeout> | null;
  pausedAt: number | null;
  pausedSeconds: number;
  watchers: Set<(entry: BridgeLogEntry | null) => void>;
}

export class EchoSubagentRuntime {
  private states = new Map<string, EchoAgentState>();
  /** Remaining stages per pipeline, spawned as each predecessor finishes. */
  private pipelines = new Map<string, RpcParams[]>();
  private spawnSeq = 0;

  /** Spawns one child. Fire-and-forget: the result arrives via `get`/`logs`. */
  spawn(
    params: RpcParams,
    pipelineId: string | null = null,
    index: number | null = null,
  ): BridgeSubagent {
    const prompt = str(params, 'prompt') || str(params, 'message');
    if (!prompt.trim()) throw invalidParams('prompt must be a non-empty string');
    const rawTools = params['tools'];
    if (rawTools !== undefined && !Array.isArray(rawTools)) {
      throw invalidParams('tools must be an array of strings');
    }

    const id = nextId('sub');
    const agent: BridgeSubagent = {
      subagent_id: id,
      id,
      name: str(params, 'name') || `subagent ${id.slice(-4)}`,
      parent_session_id: str(params, 'parent_session_id') || str(params, 'session_id') || null,
      model_provider: str(params, 'model_provider') || str(params, 'provider') || 'echo',
      model_name: str(params, 'model_name') || 'echo',
      system_prompt: str(params, 'system_prompt'),
      tools: Array.isArray(rawTools) ? rawTools.map(String) : [...DEFAULT_TOOLS],
      prompt,
      context: str(params, 'context'),
      status: 'running',
      created_at: now(),
      started_at: now(),
      finished_at: null,
      max_turns: num(params, 'max_turns', DEFAULT_MAX_TURNS),
      max_tokens: num(params, 'max_tokens', DEFAULT_MAX_TOKENS),
      max_duration: num(params, 'max_duration', DEFAULT_MAX_DURATION),
      turn_count: 0,
      token_count: 0,
      result: null,
      error: null,
      pipeline_id: pipelineId,
      pipeline_index: index,
      limit_hit: null,
      elapsed: 0,
      progress: 0,
      log: [],
    };
    const state: EchoAgentState = {
      agent,
      seq: ++this.spawnSeq,
      timer: null,
      pausedAt: null,
      pausedSeconds: 0,
      watchers: new Set(),
    };
    this.states.set(id, state);
    this.append(state, 'info', `spawned with ${agent.tools.length} tools`);
    this.schedule(state);
    return this.snapshot(state, false);
  }

  /** Spawns a chain; each stage starts when its predecessor produces a result. */
  spawnPipeline(params: RpcParams): { pipeline_id: string; subagents: BridgeSubagent[] } {
    const stages = params['stages'];
    if (!Array.isArray(stages) || stages.length === 0) {
      throw invalidParams('stages must be a non-empty array');
    }
    const shared: RpcParams = { ...params };
    delete shared['stages'];
    delete shared['name'];

    const pipelineId = nextId('pipe');
    const queued = stages.map((stage, index) => {
      if (typeof stage !== 'object' || stage === null || Array.isArray(stage)) {
        throw invalidParams(`stages[${index}] must be an object`);
      }
      return { ...shared, ...(stage as RpcParams) };
    });
    // Validate every stage before starting any of them, so a typo in the last
    // stage does not leave a half-run pipeline behind.
    for (const stage of queued) {
      const prompt = str(stage, 'prompt') || str(stage, 'message');
      if (!prompt.trim()) throw invalidParams('prompt must be a non-empty string');
    }

    const [first, ...rest] = queued as [RpcParams, ...RpcParams[]];
    this.pipelines.set(pipelineId, rest);
    const head = this.spawn(first, pipelineId, 0);
    return { pipeline_id: pipelineId, subagents: [head] };
  }

  list(params: RpcParams): { subagents: BridgeSubagent[]; active: number } {
    let states = [...this.states.values()].sort((a, b) => b.seq - a.seq);
    const pipelineId = str(params, 'pipeline_id');
    if (pipelineId) states = states.filter((s) => s.agent.pipeline_id === pipelineId);
    const sessionId = str(params, 'session_id');
    if (sessionId) states = states.filter((s) => s.agent.parent_session_id === sessionId);
    return {
      subagents: states.map((s) => this.snapshot(s, false)),
      active: [...this.states.values()].filter((s) => !isTerminalStatus(s.agent.status)).length,
    };
  }

  get(params: RpcParams): BridgeSubagent {
    return this.snapshot(this.require(params), true);
  }

  /** Cancellation is immediate here; the sidecar's grace period cannot apply. */
  cancel(params: RpcParams): BridgeSubagent {
    const state = this.require(params);
    if (!isTerminalStatus(state.agent.status)) {
      this.finish(state, 'cancelled', null, 'cancelled by user');
    }
    return { ...this.snapshot(state, false), cancelled: true } as BridgeSubagent & {
      cancelled: boolean;
    };
  }

  pause(params: RpcParams): BridgeSubagent {
    const state = this.require(params);
    if (state.agent.status !== 'running') {
      throw invalidParams(
        `subagent '${state.agent.id}' is not running (status ${state.agent.status})`,
      );
    }
    state.agent.status = 'paused';
    state.pausedAt = now();
    this.clearTimer(state);
    this.append(state, 'info', 'paused');
    return this.snapshot(state, false);
  }

  resume(params: RpcParams): BridgeSubagent {
    const state = this.require(params);
    if (state.agent.status !== 'paused') {
      throw invalidParams(
        `subagent '${state.agent.id}' is not paused (status ${state.agent.status})`,
      );
    }
    state.agent.status = 'running';
    if (state.pausedAt !== null) state.pausedSeconds += now() - state.pausedAt;
    state.pausedAt = null;
    this.append(state, 'info', 'resumed');
    this.schedule(state);
    return this.snapshot(state, false);
  }

  /**
   * Replays the log so far, then streams new lines until the child stops.
   * Resolves with the final agent, mirroring the sidecar's `Stream` contract.
   */
  async follow(
    params: RpcParams,
    onEntry: (entry: BridgeLogEntry, subagentId: string) => void,
  ): Promise<BridgeSubagent> {
    const state = this.require(params);
    const subagentId = state.agent.subagent_id;
    for (const entry of state.agent.log ?? []) onEntry(entry, subagentId);
    if (isTerminalStatus(state.agent.status)) return this.snapshot(state, false);

    await new Promise<void>((resolve) => {
      const watcher = (entry: BridgeLogEntry | null): void => {
        if (entry === null) {
          state.watchers.delete(watcher);
          resolve();
          return;
        }
        onEntry(entry, subagentId);
      };
      state.watchers.add(watcher);
    });
    return this.snapshot(state, false);
  }

  /** Stops every timer — used by tests and on teardown. */
  dispose(): void {
    for (const state of this.states.values()) this.clearTimer(state);
    this.states.clear();
    this.pipelines.clear();
  }

  // ----------------------------------------------------------------- //

  private require(params: RpcParams): EchoAgentState {
    const id = str(params, 'subagent_id') || str(params, 'id');
    if (!id) throw invalidParams('subagent_id must be a non-empty string');
    const state = this.states.get(id);
    if (!state) throw invalidParams(`no subagent with id '${id}'`);
    return state;
  }

  private schedule(state: EchoAgentState): void {
    this.clearTimer(state);
    state.timer = setTimeout(() => {
      state.timer = null;
      this.step(state);
    }, STEP_MS);
  }

  private step(state: EchoAgentState): void {
    const { agent } = state;
    if (agent.status !== 'running') return;
    agent.turn_count += 1;
    agent.token_count += TOKENS_PER_TURN;
    this.append(state, 'info', `turn ${agent.turn_count}: thinking about ${agent.prompt}`);

    if (agent.turn_count >= agent.max_turns) {
      // Limits are enforced by the sidecar too; reproducing them here keeps
      // the badge and the "limit hit" copy exercisable without one.
      this.finish(state, 'timeout', null, null, 'turns');
      return;
    }
    if (agent.token_count >= agent.max_tokens) {
      this.finish(state, 'timeout', null, null, 'tokens');
      return;
    }
    if (agent.turn_count >= ECHO_TURNS) {
      const context = agent.context ? `${agent.context} | ` : '';
      this.finish(state, 'completed', `Echo: ${context}${agent.prompt}`);
      return;
    }
    this.schedule(state);
  }

  private finish(
    state: EchoAgentState,
    status: SubAgentStatus,
    result: string | null = null,
    error: string | null = null,
    limitHit: string | null = null,
  ): void {
    const { agent } = state;
    this.clearTimer(state);
    agent.status = status;
    agent.finished_at = now();
    agent.result = result;
    agent.error = error;
    agent.limit_hit = limitHit;
    this.append(state, status === 'completed' ? 'info' : 'warn', `finished: ${status}`);
    for (const watcher of [...state.watchers]) watcher(null);
    state.watchers.clear();
    if (status === 'completed') this.advancePipeline(agent);
  }

  /** Hands a completed stage's result to the next one as its context. */
  private advancePipeline(agent: BridgeSubagent): void {
    if (!agent.pipeline_id) return;
    const remaining = this.pipelines.get(agent.pipeline_id);
    if (!remaining || remaining.length === 0) {
      this.pipelines.delete(agent.pipeline_id);
      return;
    }
    const [next, ...rest] = remaining as [RpcParams, ...RpcParams[]];
    this.pipelines.set(agent.pipeline_id, rest);
    this.spawn(
      { ...next, context: agent.result ?? '' },
      agent.pipeline_id,
      (agent.pipeline_index ?? 0) + 1,
    );
  }

  private append(state: EchoAgentState, level: string, message: string): void {
    const entry: BridgeLogEntry = { ts: now(), level, message };
    state.agent.log = [...(state.agent.log ?? []), entry];
    for (const watcher of [...state.watchers]) watcher(entry);
  }

  private clearTimer(state: EchoAgentState): void {
    if (state.timer !== null) {
      clearTimeout(state.timer);
      state.timer = null;
    }
  }

  /** Recomputes the derived fields the sidecar calculates on serialisation. */
  private snapshot(state: EchoAgentState, includeLog: boolean): BridgeSubagent {
    const { agent } = state;
    const end = agent.finished_at ?? now();
    const paused = state.pausedSeconds + (state.pausedAt === null ? 0 : now() - state.pausedAt);
    const elapsed = agent.started_at === null ? 0 : Math.max(0, end - agent.started_at - paused);
    const progress = isTerminalStatus(agent.status)
      ? 1
      : Math.min(
          1,
          Math.max(
            agent.turn_count / agent.max_turns,
            agent.token_count / agent.max_tokens,
            elapsed / agent.max_duration,
          ),
        );
    const snapshot: BridgeSubagent = { ...agent, elapsed, progress };
    if (includeLog) snapshot.log = [...(agent.log ?? [])];
    else delete snapshot.log;
    return snapshot;
  }
}

// --------------------------------------------------------------------------- //
// Schedules
// --------------------------------------------------------------------------- //

const SUMMARY_LIMIT = 500;

export class EchoScheduleRuntime {
  private schedules = new Map<string, BridgeSchedule>();
  private runs: BridgeScheduleRun[] = [];
  private nextRunId = 1;

  create(params: RpcParams): BridgeSchedule {
    const name = str(params, 'name');
    if (!name.trim()) throw invalidParams('name must be a non-empty string');
    const prompt = str(params, 'prompt');
    if (!prompt.trim()) throw invalidParams('prompt must be a non-empty string');

    const natural = str(params, 'natural_language') || null;
    const cron = this.resolveCron(str(params, 'cron_expression') || null, natural, true);
    const id = nextId('sch');
    const enabled = params['enabled'] === undefined ? true : Boolean(params['enabled']);
    const maxRuns = typeof params['max_runs'] === 'number' ? params['max_runs'] : null;
    const schedule: BridgeSchedule = {
      schedule_id: id,
      id,
      name,
      description: str(params, 'description'),
      cron_expression: cron,
      natural_language: natural,
      human: describeCron(cron),
      prompt,
      session_id: str(params, 'session_id') || null,
      enabled,
      last_run: null,
      next_run: enabled ? nextRunAfter(cron, new Date()).getTime() / 1000 : null,
      created_at: now(),
      max_runs: maxRuns,
      run_count: 0,
      require_approval: Boolean(params['require_approval']),
      exhausted: false,
    };
    this.schedules.set(id, schedule);
    return { ...schedule };
  }

  list(params: RpcParams): { schedules: BridgeSchedule[] } {
    const includeDisabled =
      params['include_disabled'] === undefined ? true : Boolean(params['include_disabled']);
    const rows = [...this.schedules.values()]
      .filter((s) => includeDisabled || s.enabled)
      .sort((a, b) => a.created_at - b.created_at);
    return { schedules: rows.map((s) => ({ ...s })) };
  }

  get(params: RpcParams): BridgeSchedule {
    const schedule = this.require(params);
    return { ...schedule, runs: this.historyFor(schedule.id) };
  }

  update(params: RpcParams): BridgeSchedule {
    const schedule = this.require(params);
    if ('name' in params) schedule.name = str(params, 'name', schedule.name);
    if ('description' in params) schedule.description = str(params, 'description');
    if ('prompt' in params) schedule.prompt = str(params, 'prompt', schedule.prompt);
    if ('session_id' in params) schedule.session_id = str(params, 'session_id') || null;
    if ('enabled' in params) schedule.enabled = Boolean(params['enabled']);
    if ('require_approval' in params)
      schedule.require_approval = Boolean(params['require_approval']);
    if ('max_runs' in params) {
      schedule.max_runs = typeof params['max_runs'] === 'number' ? params['max_runs'] : null;
    }
    if ('cron_expression' in params || 'natural_language' in params) {
      const natural =
        'natural_language' in params
          ? str(params, 'natural_language') || null
          : schedule.natural_language;
      const cron = this.resolveCron(
        'cron_expression' in params ? str(params, 'cron_expression') || null : null,
        natural,
        true,
      );
      schedule.cron_expression = cron;
      schedule.natural_language = natural;
      schedule.human = describeCron(cron);
    }
    schedule.next_run = schedule.enabled
      ? nextRunAfter(schedule.cron_expression, new Date()).getTime() / 1000
      : null;
    return { ...schedule };
  }

  delete(params: RpcParams): { deleted: boolean; schedule_id: string } {
    const schedule = this.require(params);
    this.schedules.delete(schedule.id);
    this.runs = this.runs.filter((r) => r.schedule_id !== schedule.id);
    return { deleted: true, schedule_id: schedule.id };
  }

  toggle(params: RpcParams): BridgeSchedule {
    const schedule = this.require(params);
    const enabled = params['enabled'];
    schedule.enabled =
      enabled === undefined || enabled === null ? !schedule.enabled : Boolean(enabled);
    schedule.next_run = schedule.enabled
      ? nextRunAfter(schedule.cron_expression, new Date()).getTime() / 1000
      : null;
    return { ...schedule };
  }

  history(params: RpcParams): { runs: BridgeScheduleRun[] } {
    const scheduleId = str(params, 'schedule_id') || str(params, 'id');
    if (scheduleId) this.require(params);
    const limit = num(params, 'limit', 50);
    const rows = (scheduleId ? this.historyFor(scheduleId) : [...this.runs]).slice(0, limit);
    return { runs: rows };
  }

  /** Never throws: the user is mid-sentence and this runs per keystroke. */
  preview(params: RpcParams): SchedulePreview {
    const natural = str(params, 'natural_language') || str(params, 'text') || null;
    const explicit = str(params, 'cron_expression') || null;
    try {
      const cron = this.resolveCron(explicit, natural);
      return {
        valid: true,
        cron_expression: cron,
        human: describeCron(cron),
        next_run: nextRunAfter(cron, new Date()).getTime() / 1000,
        natural_language: natural,
        error: null,
      };
    } catch (err) {
      return {
        valid: false,
        cron_expression: null,
        human: null,
        next_run: null,
        natural_language: natural,
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }

  runNow(params: RpcParams): { schedule: BridgeSchedule; run: BridgeScheduleRun } {
    const schedule = this.require(params);
    const started = now();
    const run: BridgeScheduleRun = {
      id: this.nextRunId++,
      schedule_id: schedule.id,
      started_at: started,
      completed_at: started,
      duration: 0,
      result_summary: `Echo: ${schedule.prompt}`.slice(0, SUMMARY_LIMIT),
      status: schedule.require_approval ? 'approval_denied' : 'success',
    };
    this.runs.unshift(run);
    schedule.run_count += 1;
    schedule.last_run = started;
    if (schedule.max_runs !== null && schedule.run_count >= schedule.max_runs) {
      schedule.exhausted = true;
      schedule.enabled = false;
      schedule.next_run = null;
    } else if (schedule.enabled) {
      schedule.next_run = nextRunAfter(schedule.cron_expression, new Date()).getTime() / 1000;
    }
    return { schedule: { ...schedule }, run };
  }

  // ----------------------------------------------------------------- //

  private require(params: RpcParams): BridgeSchedule {
    const id = str(params, 'schedule_id') || str(params, 'id');
    if (!id) throw invalidParams('schedule_id must be a non-empty string');
    const schedule = this.schedules.get(id);
    if (!schedule) throw invalidParams(`no schedule with id '${id}'`);
    return schedule;
  }

  private historyFor(scheduleId: string): BridgeScheduleRun[] {
    return this.runs.filter((r) => r.schedule_id === scheduleId).map((r) => ({ ...r }));
  }

  /**
   * An explicit cron expression wins; prose is translated.
   *
   * `throwAsRpc` is set on the CRUD paths, where an unparseable schedule is a
   * caller error and must surface as `invalid_params`; `preview` leaves it off
   * and reports the parse failure in its payload instead.
   */
  private resolveCron(cron: string | null, natural: string | null, throwAsRpc = false): string {
    try {
      if (cron && cron.trim()) return nlToCron(cron);
      if (natural && natural.trim()) return nlToCron(natural);
      throw new ScheduleParseError('a schedule needs either a cron expression or a description');
    } catch (err) {
      if (throwAsRpc && err instanceof ScheduleParseError) throw invalidParams(err.message);
      throw err;
    }
  }
}
