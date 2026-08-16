# Subagents & the Natural-Language Scheduler — Architecture

> **Prompt P-06 · Phase 2.5 (Subagent system) + Phase 2.6 (Scheduler).**
> This document is gate **G1**: it is the design of record for
> `dream/subagents.py`, `dream/scheduler.py`, their bridge surface
> (`subagent.*`, `schedule.*`) and the two desktop screens that drive them.

- **Status:** Implemented
- **Layer:** new modules *above* the existing `dream/` core. No existing public
  API changes semantics, so the pre-existing Python suite stays green.
- **Related specs:** [`docs/bridge/protocol.md`](../bridge/protocol.md) §3.8 and
  §3.10, [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).

---

## 1. Why these two features share one document

A subagent is *work delegated in space* (a second agent, running beside the
conversation). A schedule is *work delegated in time* (the same agent, run
later without a human present). They share one substrate:

- both start a Dream turn **nobody is watching**, so both need hard resource
  limits and a fail-closed approval story;
- both produce a **history record** the UI reads back (`SubAgent.result`,
  `schedule_runs`);
- both are driven from the sidecar's asyncio loop and surfaced over the same
  JSON-RPC bridge.

---

## 2. Subagent system

### 2.1 Data model

```python
@dataclass
class SubAgent:
    id: str                     # "sub_<hex>"
    name: str
    parent_session_id: str | None
    model_provider: str         # "echo" | "openai" | "ollama"
    model_name: str
    system_prompt: str
    tools: list[str]            # the granted subset, already filtered
    status: str                 # idle|running|paused|completed|failed|cancelled|timeout
    created_at: float
    started_at: float | None
    finished_at: float | None
    max_turns: int
    max_tokens: int
    max_duration: float         # seconds of *active* wall clock
    turn_count: int
    token_count: int
    result: str | None
    error: str | None
    # execution extras
    prompt: str                 # the initial instruction from the parent
    context: str                # read-only context handed down
    pipeline_id: str | None
    limit_hit: str | None       # "turns" | "tokens" | "duration"
    log: list[LogEntry]         # ts, level, message
```

`status` is a closed set (`SUBAGENT_STATUSES`). The lifecycle is:

```
idle ──spawn──> running ──┬── completed        (model answered)
                          ├── failed           (exception inside the turn)
                          ├── cancelled        (parent asked to stop)
                          └── timeout          (turns | tokens | duration)
                 ▲   │
          resume │   │ pause
                 └ paused
```

`paused` is only reachable from `running`, and `resume` only from `paused`;
both are no-ops (returning the current snapshot) once the agent is terminal.

### 2.2 Communication contract

| Direction | Mechanism | Notes |
| --- | --- | --- |
| parent → child | initial `prompt` + read-only `context` string | fire-and-forget: `spawn()` returns as soon as the task is scheduled |
| child → parent | the task's return value, captured into `SubAgent.result` | the parent polls `subagent.get` or subscribes to `subagent.logs` |
| child → parent (progress) | append-only `log` + a per-subscriber `asyncio.Queue` | drives live log streaming in the UI |
| child ↛ parent | **nothing** | the child cannot read the parent's store, history, or approvals |

The context is embedded in the child's first user message under an explicit
`<context>` fence, never merged into the parent's conversation history.

### 2.3 Isolation

Four walls, in order of importance:

1. **Task isolation.** Every subagent is one `asyncio.Task` on the sidecar's
   loop — not a thread and not a process. Blocking work (the provider HTTP
   call) is pushed to `asyncio.to_thread`, so the loop stays responsive and a
   `Task.cancel()` detaches the subagent immediately.
2. **Store isolation.** Each subagent constructs its own
   `MemoryStore(":memory:")`. It is destroyed when the run ends. The parent's
   `data/dream.db` is never opened by the child, so a child that calls
   `remember_fact` writes into a database that dies with it.
3. **Registry isolation.** `dream.tools.REGISTRY` is a *process-global* dict,
   and `Dream.__init__` registers memory/reminder closures bound to *its* store
   into it. Naively building a second `Dream` would therefore silently re-point
   the parent's `remember_fact` at the child's ephemeral database. The subagent
   runtime avoids this with a **snapshot / capture / restore** dance held under
   `dream.subagents.REGISTRY_LOCK`:

   ```
   snapshot = dict(REGISTRY)
   child = Dream(store=ephemeral, backend=child_backend)   # mutates REGISTRY
   captured = dict(REGISTRY)                               # child's closures
   REGISTRY.clear(); REGISTRY.update(snapshot)             # parent restored
   child_tools = {n: t for n, t in captured.items() if n in granted}
   ```

   The child then dispatches through `child_tools` — a private table — using
   the new optional `registry=` argument on `dream.tools.execute()` and
   `dream.tools.openai_schemas()`. The global registry is untouched for the
   whole life of the subagent, so N subagents can run concurrently without
   interfering with each other or with the parent.
4. **Tool isolation.** The parent names the tools it grants. Unknown names are
   dropped; `dangerous` tools are dropped unless the spec sets
   `allow_dangerous=True`, and even then the child's `ApprovalPolicy` has no
   approver, so `dream.tools.execute` stays fail-closed. The default grant is
   `DEFAULT_TOOL_GRANT` (arithmetic, clock, and the child's own ephemeral
   memory tools) — never the filesystem, shell, network, or email.

> **Known pre-existing hazard (documented, not introduced here).** The lock only
> helps callers that take it. `BridgeMethods._new_dream()` also constructs
> `Dream` objects; if it ever does so *concurrently* with a subagent spawn, the
> last writer wins for the memory-tool closures. `REGISTRY_LOCK` is exported so
> that seam can be closed when session construction is made concurrent.

### 2.4 Execution engine

The subagent runs a slim, explicit agent loop rather than calling `Dream.run()`.
That is a deliberate trade: `Dream.run()` reads the *global* registry
(`openai_schemas()` / `execute()` with no registry argument) and therefore
cannot honour a per-agent tool grant, and it offers no seam for per-iteration
pause/cancel/limit checks. The loop is ~60 lines and reuses the core's own
approval policy and tool executor.

```
gate()                      # pause barrier + cancel check + limit check
response = await to_thread(backend.chat, messages, schemas(child_tools))
turn_count += 1 ; token_count += estimate(prompt) + estimate(completion)
if no tool calls:  result = content ; status = completed ; stop
for each tool call: policy.allows() → execute(..., registry=child_tools)
append tool results to messages ; loop
```

**Limits** are checked at every gate and by a watchdog task:

| Limit | Enforced by | Terminal status |
| --- | --- | --- |
| `max_turns` | gate, before each provider call | `timeout`, `limit_hit="turns"` |
| `max_tokens` | gate, after accounting each turn | `timeout`, `limit_hit="tokens"` |
| `max_duration` | 50 ms watchdog on *active* elapsed time | `timeout`, `limit_hit="duration"` |

"Active elapsed" excludes time spent `paused`, so pausing an agent for review
does not burn its wall-clock budget. Token counts are *estimates*
(`len(text) / 4`, floor 1) because not every backend reports usage; the field is
documented as an estimate everywhere it is surfaced.

**Cancellation** is graceful-then-forced, and bounded so the UI can promise
"cancel takes effect in under two seconds" (gate G6):

1. `cancel()` sets the stop event and wakes any pause barrier → the loop exits
   at its next gate, typically within microseconds;
2. the manager waits `grace_seconds` (default `2.0`) for the task to finish;
3. if the task is still inside a provider call, `Task.cancel()` detaches it. The
   orphaned worker thread finishes into the void; its result is discarded.

The subagent is marked `cancelled` in all three cases, and `cancel()` returns
only after the status is final.

### 2.5 Pipeline chaining

`SubAgentManager.spawn_pipeline([spec, ...])` returns immediately with a
`pipeline_id` and the ids of every stage (all `idle` except the first). A driver
task runs the stages **sequentially**, and each stage's `result` becomes the
next stage's `context`:

```
stage[i].context = (spec.context + "\n\n" if spec.context else "") + stage[i-1].result
```

If a stage ends non-`completed`, the remaining stages are marked `cancelled`
with `error="upstream stage did not complete"`. Cancelling the pipeline cancels
the running stage and skips the rest.

### 2.6 RPC surface

| Method | Params | Result |
| --- | --- | --- |
| `subagent.spawn` | `{name?, prompt, context?, provider?, model?, system_prompt?, tools?, max_turns?, max_tokens?, max_duration?, session_id?, allow_dangerous?}` | `SubAgent` |
| `subagent.list` | `{}` | `{subagents: SubAgent[]}` |
| `subagent.get` | `{subagent_id}` | `SubAgent` |
| `subagent.status` | `{subagent_id}` | `SubAgent` — 1.0 alias of `get` |
| `subagent.cancel` | `{subagent_id, grace_seconds?}` | `SubAgent` |
| `subagent.pause` | `{subagent_id}` | `SubAgent` |
| `subagent.resume` | `{subagent_id}` | `SubAgent` |
| `subagent.logs` | `{subagent_id, follow?}` | streaming; chunks `{event:"log", ...}`, final `SubAgent` |
| `subagent.pipeline` | `{stages: Spec[], name?}` | `{pipeline_id, subagents: SubAgent[]}` |

`subagent.spawn` also accepts the legacy P-02 parameter `message` as an alias of
`prompt`, so the 1.0 clients keep working.

---

## 3. Scheduler

### 3.1 Data model

Two SQLite tables, created lazily by `ensure_schedule_tables(store)` in the same
idempotent `CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` style the reminder
tables use. They live in the shared `data/dream.db`, scoped by `user_id`.

```sql
CREATE TABLE schedules (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'local',
    name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    cron_expression TEXT NOT NULL, natural_language TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL, session_id TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run REAL, next_run REAL, created_at REAL NOT NULL,
    max_runs INTEGER, run_count INTEGER NOT NULL DEFAULT 0,
    require_approval INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE schedule_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id TEXT NOT NULL, started_at REAL NOT NULL,
    completed_at REAL, result_summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,          -- running|success|error|approval_denied
    FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE
);
```

`max_runs = NULL` means unlimited. `next_run` is recomputed from the cron
expression on create, on update, and after every execution.

### 3.2 `nl_to_cron` — pattern matching, no model call

`nl_to_cron(text) -> str` is pure pattern matching (gate G7 forbids an external
AI call). It is compositional rather than a lookup table of phrases:

1. **Normalise** with `dream.memory.normalize_fa` — NFKC, Persian/Arabic digit
   folding (`۹` → `9`), character unification, ZWNJ → space — then lowercase.
   One normaliser means the Persian and English paths share every downstream
   rule.
2. **Interval?** `every N minutes|hours|days` / `هر N دقیقه|ساعت|روز` →
   `*/N` in the matching field (and zeros below it).
3. **Time of day?** `at 9`, `at 9:30`, `9 am`, `9pm`, `18:00`, `noon`,
   `midnight` / `ساعت ۹`, `۹ صبح`, `۹ شب`, `ظهر`, `نیمه شب`. Persian
   day-part words (`صبح` morning, `ظهر` noon, `بعدازظهر`/`عصر` afternoon,
   `شب` night) map to the same 12-hour disambiguation as `am`/`pm`.
4. **Day scope?** weekday names (English and Persian, including the Persian
   week that starts on Saturday), `weekday`/`روز کاری`, `weekend`/`آخر هفته`,
   `first day of month`/`اول هر ماه`, `the Nth`/`روز N ام`, `week`, `month`,
   `year`.
5. **Compose** the five fields; unmatched text raises `ValueError` so the UI can
   say "I could not read that" instead of scheduling something wrong.

The Iranian working week is Saturday–Wednesday, so `روزهای کاری` yields
`6,0,1,2,3` while the English `weekday` yields the ISO `1-5`. That asymmetry is
intentional and documented in the module.

Worked examples (all covered by tests):

| Input | Cron |
| --- | --- |
| `every day at 9 AM` | `0 9 * * *` |
| `every weekday at 6 PM` | `0 18 * * 1-5` |
| `every monday at 10:30` | `30 10 * * 1` |
| `every 2 hours` | `0 */2 * * *` |
| `every first day of month` | `0 0 1 * *` |
| `every 15 minutes` | `*/15 * * * *` |
| `هر روز ساعت ۹ صبح` | `0 9 * * *` |
| `هر دوشنبه ساعت ۱۰:۳۰` | `30 10 * * 1` |
| `هر ۱۵ دقیقه` | `*/15 * * * *` |

`describe_cron(expr) -> str` is the inverse for display, and
`schedule.preview` exposes both to the UI so the "add schedule" form can show a
live cron + human reading as the user types.

### 3.3 Cron evaluation

A small five-field evaluator (`parse_cron`, `cron_matches`, `next_run_after`)
supporting `*`, `*/n`, `a-b`, `a-b/n` and comma lists, with `0`/`7` both meaning
Sunday. It follows the Vixie-cron rule that when **both** day-of-month and
day-of-week are restricted the match is a union, not an intersection.
`next_run_after` walks forward minute by minute with a four-year bound and
raises if nothing matches (an impossible date such as `0 0 30 2 *`).

### 3.4 Daemon

`SchedulerDaemon(store, runner, *, poll_interval=30.0, ...)`:

```
while running:
    await tick()                      # never raises; logs and continues
    await sleep(poll_interval)        # interruptible via the stop event
```

`tick()` selects enabled schedules whose `next_run <= now` and whose `max_runs`
is not exhausted, and launches one task per schedule so a slow run cannot delay
the next poll. Each task:

1. writes a `schedule_runs` row with `status="running"`;
2. if `require_approval`, registers an approval, pushes an
   `approval.required` notification and awaits the decision with a bounded
   timeout (default 300 s) — a denial or a timeout closes the run as
   `approval_denied` and the prompt never reaches a model;
3. otherwise (or once approved) calls `runner(schedule)`, which spawns a new
   session — or reuses `schedule.session_id` when set — and runs the prompt;
4. closes the run row with `success` + a truncated summary, or `error` + the
   exception text, and always advances `last_run`, `run_count` and `next_run`.

The runner is injected, which is what keeps the daemon unit-testable with a
fake clock and no model provider.

### 3.5 Security posture (gate G11)

- Schedule executions build their Dream with the default `ApprovalPolicy`, whose
  `ask` is `None`. `ApprovalPolicy.allows()` therefore denies every `dangerous`
  tool, and `dream.tools.execute` refuses to run one without
  `approved=True`. An unattended schedule can never shell out or send mail.
- `require_approval=True` additionally gates the *whole run* behind a human
  decision, with the notification carrying the schedule name and prompt.
- Subagents inherit the same policy plus the tool-grant filter of §2.3.

### 3.6 RPC surface

| Method | Params | Result |
| --- | --- | --- |
| `schedule.create` | `{name, prompt, cron_expression? \| natural_language?, description?, session_id?, enabled?, max_runs?, require_approval?}` | `Schedule` |
| `schedule.list` | `{include_disabled?}` | `{schedules: Schedule[]}` |
| `schedule.get` | `{schedule_id}` | `Schedule` |
| `schedule.update` | `{schedule_id, ...fields}` | `Schedule` |
| `schedule.delete` | `{schedule_id}` | `{deleted: true, schedule_id}` |
| `schedule.toggle` | `{schedule_id, enabled?}` | `Schedule` |
| `schedule.history` | `{schedule_id?, limit?}` | `{runs: ScheduleRun[]}` |
| `schedule.preview` | `{natural_language? \| cron_expression?}` | `{cron_expression, human, next_run, valid, error?}` |
| `schedule.run_now` | `{schedule_id}` | `{run: ScheduleRun}` |

`Schedule` on the wire carries the stored columns plus derived `human` (from
`describe_cron`) and `next_run`.

---

## 4. Frontend

### 4.1 Subagent dashboard (`/subagents`)

- A collapsible panel per subagent: colour-coded status badge (idle grey,
  running blue + animated dot, paused amber, completed green, failed/timeout
  red, cancelled neutral), a progress bar driven by
  `max(turn_count/max_turns, token_count/max_tokens, elapsed/max_duration)`, and
  the pause / resume / cancel controls.
- Expanding shows the detail view: configuration (provider, model, granted
  tools, limits), live counters (turns, estimated tokens, elapsed), the result,
  and a live log console fed by `subagent.logs` streaming chunks.
- A spawn dialog collects name, provider/model, system prompt, tool grant
  (checkbox list from `tool.list`, dangerous tools visibly flagged) and limits.
- A drag-and-drop pipeline builder orders staged specs (HTML5 drag events, with
  keyboard "move up/down" alternatives for accessibility) and submits them to
  `subagent.pipeline`.

### 4.2 Scheduler (`/schedules`)

- Cards: name, human-readable schedule, the cron expression in an `ltr-island`,
  next run, last run, run count, an enable/disable switch, and edit/delete with
  a confirm step.
- The add/edit form takes natural language, calls `schedule.preview` (debounced)
  and shows the cron plus its human reading and next fire time live, with an
  "advanced" escape hatch for typing cron directly.
- An execution-history timeline groups runs by day with per-run status, duration
  and summary.

### 4.3 Echo fallback

`EchoBridgeTransport` answers every `subagent.*` and `schedule.*` method
in-memory (including a TypeScript mirror of `nlToCron`/`describeCron`) so the UI
is fully exercisable with `npm run dev` and in vitest without a sidecar. The
mirror is intentionally a subset: the Python implementation is authoritative and
is what the packaged app talks to.

---

## 5. Testing strategy

| Gate | Covered by |
| --- | --- |
| G2 lifecycle | `tests/test_subagents.py` — spawn→complete→result, spawn→cancel, spawn→timeout, pause/resume |
| G3 limits | turn, token and duration exhaustion each assert `status="timeout"` and `limit_hit` |
| G4 isolation | child writes to `remember_fact` are invisible to the parent store; the global `REGISTRY` is byte-identical before and after; two concurrent subagents keep separate stores |
| G5 pipelines | three-stage chain asserts each stage's context contains the previous result |
| G6 dashboard | `subagents.test.tsx` — status badges, log streaming, cancel button issues the RPC |
| G7 NL patterns | `tests/test_scheduler.py::test_nl_patterns` — 20+ English and Persian phrases |
| G8 firing + approval | fake-clock `tick()` tests: fires when due, honours `max_runs`, `approval_denied` on denial |
| G9 history | run rows carry status, timestamps and duration |
| G10 scheduler UI | `schedules.test.tsx` |
| G11 security | dangerous tools filtered from grants; approval-less policy denies them; subagent cannot reach the parent store |
