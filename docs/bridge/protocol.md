# Dream Bridge Protocol — Specification

> The **Dream Bridge** is the JSON-RPC 2.0 link between the Tauri 2 desktop
> frontend (React/TypeScript) and Dream's Python agent core (`dream/` package).
> This document is the single source of truth for the wire protocol. It is
> **Prompt P-02, Item 1.2.1–1.2.8** (Protocol Design) and gate **G1**.

- **Status:** Stable
- **Protocol version:** `1.0`
- **Transport:** one process (the Python *sidecar*) speaking newline-delimited
  JSON over its **stdin** (frontend → sidecar) and **stdout** (sidecar →
  frontend). **stderr** is reserved for human-readable logs and must never carry
  protocol data.
- **Compatibility:** additive only within a major version. The Python core
  (`dream/`) is **100% backward compatible** — the bridge is a new layer above
  it and changes no existing public API.

---

## 1. Framing & versioning

### 1.1 Version header

On startup, the sidecar writes exactly one header line to **stdout** before any
other message:

```
DREAM-PROTOCOL: 1.0
```

The frontend reads this line first and verifies the major version. A mismatch
on the **major** number (`1` ≠ `2`) is fatal: the frontend must not send
requests and must surface a `PROTOCOL_VERSION` error to the UI. A minor-version
mismatch is ignored (additive).

### 1.2 Message framing

- Every message is **exactly one line of UTF-8 JSON**, terminated by `\n` (`U+000A`).
- Messages do **not** contain embedded raw newlines; JSON string escapes (`\n`)
  are used inside values. The boundary between messages is a literal `\n`.
- The maximum line length is **10 MiB** (10 × 1024 × 1024 bytes). A line that
  exceeds it is rejected with `INVALID_REQUEST` ("payload too large") and the
  connection stays alive (see §6).
- Empty lines are ignored (lenient skip). A trailing line without `\n` at EOF is
  parsed if non-empty.

### 1.3 Roles

| Direction | Who sends | Contains |
| --- | --- | --- |
| stdin  | Frontend | **Requests** and **notifications** |
| stdout | Sidecar  | **Responses**, **streaming notifications**, **server notifications** |

---

## 2. JSON-RPC 2.0 envelope

### 2.1 Request (frontend → sidecar)

```json
{"jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {}}
```

- `id` — integer or string, set by the frontend, unique among in-flight
  requests. **Must** be present on requests. A message missing `id` is a
  **notification** (§5.4) and receives no response.
- `method` — dotted name from §3.
- `params` — object (named parameters). Arrays are not used; all methods take an
  object. `params` may be omitted (treated as `{}`).

### 2.2 Successful response

```json
{"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sess_01J…"}}
```

- `id` echoes the request `id`.
- `result` — any JSON value (object unless noted).

### 2.3 Error response

```json
{"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "method not found", "data": {"method": "bogus"}}}
```

- `error.code` — numeric (see §4).
- `error.message` — short human-readable English string.
- `error.data` — optional, machine-readable detail. In **dev mode**
  (`DREAM_DEV=1`) it may include a `traceback` string for debugging; in
  production it is omitted or minimal.

A response carries exactly one of `result` or `error`, never both, never neither.

---

## 3. Methods

All methods are namespaced by subsystem. Parameters are shown as the `params`
object. **`*` = supports streaming** (§5).

### 3.1 `session.*` — conversation sessions

| Method | Params | Result |
| --- | --- | --- |
| `session.create` | `{title?: string, provider?: string, model?: string, reasoning_effort?: number}` | `{session_id, title, created_at}` |
| `session.list` | `{}` | `{sessions: Session[]}` |
| `session.get` | `{session_id}` | `Session` |
| `session.delete` | `{session_id}` | `{deleted: true}` |
| `session.rename` | `{session_id, title}` | `Session` |
| `session.configure` | `{session_id, provider, model, reasoning_effort}` | `Session` |

`Session = {id, title, created_at, updated_at, message_count, provider, model, reasoning_effort}`

A session holds one independent conversation context (its own history). All
sessions share the same **durable** memory store, so memories created in one
session are visible in others.

### 3.2 `conversation.*` — talking to the agent

| Method | Params | Result |
| --- | --- | --- |
| `conversation.send` * | `{session_id, message}` | `Turn` |
| `conversation.stop` | `{session_id}` | `{stopped: true}` |

`Turn` mirrors `dream.agent.Turn`:

```jsonc
{
  "reply": "Echo: hello",
  "tool_calls": [{"name": "get_datetime", "arguments": {}, "allowed": true, "result": "{...}"}],
  "memories_used":  [{/* Memory */}],
  "memories_created": [{/* Memory */}],
  "memories_superseded": [{/* Memory */}],
  "memories_merged": [{/* Memory */}],
  "memories_injected": [{/* Memory */}],
  "elapsed_seconds": 0.42,
  "extraction": {"status": "no_facts", "facts": [], "raw_text": ""},
  "memory_errors": []
}
```

`conversation.send` is **streaming**: while the agent works, the sidecar emits
`stream.chunk` notifications (§5.1) carrying the assistant text token-by-token,
then the final `Turn` as the `result`. `conversation.stop` requests early
termination of an in-flight generation (best-effort — see §5.3).

### 3.3 `provider.*` — model providers

| Method | Params | Result |
| --- | --- | --- |
| `provider.catalog` | `{}` | `{catalog: Record<string, CatalogEntry>}` |
| `provider.list` | `{}` | `{providers: Provider[], default: string}` |
| `provider.get` | `{id}` | `{provider: Provider}` |
| `provider.create` | `{id?, provider: ProviderConfig, credential?, set_default?}` | `{saved: true, provider, default}` |
| `provider.update` | `{id, provider: ProviderConfig, credential?, clear_credential?, set_default?}` | `{saved: true, provider, default}` |
| `provider.delete` | `{id}` | `{deleted: true, default}` |
| `provider.models` | `{id, force?}` | `{provider, models, error?}` |
| `provider.test` | `{id}` | `{ok: boolean, latency_ms?: number, detail?: string}` |
| `provider.oauth.begin` | `{id, redirect_uri}` | `{authorization_url, state}` |
| `provider.oauth.complete` | `{id, state, code}` | `{connected: true, provider, expires_in?}` |
| `provider.configure` | P-02 upsert shape | Alias of create/update for backward compatibility |

`Provider` includes non-secret metadata, enabled models, capabilities, connection status, and a
`credential_configured` boolean. `ProviderConfig` never returns a credential. A `credential`
request value goes directly to the OS keychain and is omitted from JSON persistence and every
response.

`provider.test` performs a minimal chat completion (instant for offline `echo`). Failures are
**not** RPC errors — they return `{ok: false, detail}` using fixed, credential-safe detail text.
Model lists are cached for fifteen minutes. OAuth requires state and an S256 PKCE verifier; access
and refresh tokens are stored only in the keychain.

### 3.4 `memory.*` — durable memory

| Method | Params | Result |
| --- | --- | --- |
| `memory.list` | `{cursor?, limit?, kind_filter?, search_query?, date_from?, date_to?, min_importance?, sort_by?, include_archived?}` | `{memories: Memory[], total, next_cursor, has_more}` |
| `memory.count` | `{kind_filter?}` | `{total, by_kind: {semantic, episodic, procedural}, archived}` |
| `memory.search` | `{query, kinds?, limit?}` | `{memories: Memory[]}` |
| `memory.get` | `{memory_id, include_archived?}` | `Memory \| null` |
| `memory.create` | `{content, kind?, importance?, tags?, source?}` | `{memory: Memory}` |
| `memory.update` | `{memory_id, content?, kind?, tags?, importance?}` | `{memory: Memory}` |
| `memory.delete` | `{memory_id, hard?}` | `{deleted: true}` |

`Memory = {id, kind, content, tags[], importance, created_at, last_used_at, use_count, source, archived, pinned, score}`

These consume — but never mutate — `MemoryStore` (`all`, `recall`, `get`,
`update_memory`, `remember`, `forget`). `memory.list` adds cursor pagination,
kind/search/date/importance filters, and `sort_by` (`relevance` |
`date_newest` | `date_oldest` | `importance`); `next_cursor` is a stringified
offset (or `null` when exhausted). `memory.create` sanitises HTML/script tags,
enforces a 50 KB cap, and stores `kind ∈ {semantic, episodic, procedural}` with
`importance ∈ [0.0, 1.0]` (the UI scales 0–10 stars to this range).

### 3.5 `skill.*` — skills

| Method | Params | Result |
| --- | --- | --- |
| `skill.list` | `{}` | `{skills: SkillEx[], problems: SkillProblem[]}` |
| `skill.get` | `{skill_id? \| query?}` | `{match: SkillDetail \| null}` |
| `skill.install` | `{name?, description?, steps[]?, content?, overwrite?}` | `{filename, status: "installed" \| "conflict", name, conflict?, existing_filename?}` |
| `skill.delete` / `skill.remove` | `{skill_id? \| name?}` | `{deleted: true, filename, name}` / `{removed: true, filename}` |
| `skill.enable` | `{skill_id}` | `{name, filename, enabled: true}` |
| `skill.disable` | `{skill_id}` | `{name, filename, enabled: false}` |
| `skill.export` | `{skill_id}` | `{name, filename, content}` |

`SkillEx = {name, description, steps[], filename, enabled}` (the `enabled` flag
is bridge-side state persisted to `data/bridge_disabled_skills.json`).
`SkillDetail = {name, description, steps[], filename, enabled, created_at, content}`
where `content` is the canonical rendered skill file for preview/export.
`SkillProblem = {filename, detail}`.

`skill_id` resolves from a filename (`skills/foo.txt`), a bare name (`foo`), or a
`skills/foo.txt` id. `skill.install` accepts either structured fields *or* a
pasted/imported `content` body (parsed via `parse_skill_text`); `overwrite:
false` (default) returns `status: "conflict"` when a same-named skill already
exists so the UI can offer overwrite/rename. Safety gate (100 KB cap, no
absolute paths / `..` traversal, no dangerous module imports) rejects malicious
content with `INVALID_PARAMS`. All file access is confined to the workspace root
via the core's `_safe_path` boundary.

### 3.6 `tool.*` — the tool registry

| Method | Params | Result |
| --- | --- | --- |
| `tool.list` | `{}` | `{tools: ToolInfo[]}` |
| `tool.execute` | `{name, arguments, approved?}` | `{status: "ok"\|"error", result?/\|error?}` |

`ToolInfo = {name, risk: "safe"\|"guarded"\|"dangerous", description, schema}`

`tool.execute` runs `dream.tools.execute`. **Dangerous** tools require explicit
approval: if `approved` is not `true`, the call returns an `APPROVAL_REQUIRED`
error carrying an `approval_id` (§5.2); the frontend resolves it via
`approval.resolve` and re-sends with `approved: true`. This keeps the approval
gate non-blocking — the synchronous agent loop is never wedged waiting on a UI.

### 3.7 `approval.*` — human-in-the-loop

| Method | Params | Result |
| --- | --- | --- |
| `approval.request` | `{name, arguments, context?}` | `{approval_id, risk, summary}` |
| `approval.resolve` | `{approval_id, allowed}` | `ToolResult \| {blocked: true, reason}` |

`approval.request` registers a pending approval for a tool call and returns its
id and risk tier (the sidecar computes a short, human-readable `summary`).
`approval.resolve` with `allowed: true` executes the tool (dangerous) and
returns its result; `allowed: false` returns the standard blocked payload. A
resolved approval cannot be reused.

### 3.8 `subagent.*` — isolated background agents

| Method | Params | Result |
| --- | --- | --- |
| `subagent.spawn` | `SpawnSpec` | `Subagent` |
| `subagent.pipeline` | `{stages: SpawnSpec[], name?, ...SpawnSpec}` | `{pipeline_id, subagents: Subagent[]}` |
| `subagent.list` | `{pipeline_id?, session_id?}` | `{subagents: Subagent[], active: number}` |
| `subagent.get` | `{subagent_id}` | `Subagent` (with `log`) |
| `subagent.status` | `{subagent_id}` | alias of `subagent.get` |
| `subagent.cancel` | `{subagent_id, grace_seconds?}` | `Subagent & {cancelled: true}` |
| `subagent.pause` | `{subagent_id}` | `Subagent` |
| `subagent.resume` | `{subagent_id}` | `Subagent` |
| `subagent.logs` * | `{subagent_id}` | `Subagent` (chunks are log entries) |

```jsonc
// SpawnSpec — only `prompt` is required (`message` is accepted as a legacy alias).
{
  "prompt": "Summarise the release notes",
  "name": "summariser",
  "context": "read-only text handed down from the parent",
  "system_prompt": "You are terse.",
  "provider": "echo",              // or "model_provider"
  "model_name": "gpt-4o-mini",
  "tools": ["calculate", "get_datetime"],   // subset of the parent registry
  "max_turns": 8, "max_tokens": 8000, "max_duration": 120,
  "session_id": "sess_…",          // parent session, for filtering only
  "allow_dangerous": false          // dangerous tools stay out unless set
}
```

`Subagent = {id, subagent_id, name, prompt, context, status, result?, error?,
progress, turn_count, token_count, elapsed, limit_hit?, tools, pipeline_id?,
pipeline_index?, created_at, started_at?, finished_at?, max_turns, max_tokens,
max_duration, log?}`

`status ∈ idle | running | paused | completed | failed | cancelled | timeout`.
`result` is the child's final reply **as a plain string**. `progress` is the
largest of the three budget ratios (turns, tokens, wall clock) in `0..1`.

Isolation (gate G4): each child runs in its own asyncio Task with its own
`Dream` instance, its own **ephemeral in-memory store**, and a tool registry
restricted to `tools`. It can neither read the parent's memories nor see its
sibling's state. `context` is the only channel from parent to child, and the
returned string is the only channel back.

`subagent.pipeline` chains stages: stage *n*'s result becomes stage *n+1*'s
`context`. Keys given alongside `stages` act as defaults for every stage. If a
stage fails or is cancelled, the remaining stages are skipped.

`subagent.cancel` signals the child, waits out a short grace period and then
kills the task; it only returns once the status is terminal, which is inside
the 2-second budget of gate G6. Exceeding `max_concurrent` children raises
`RESOURCE_EXHAUSTED (-32007)`.

`subagent.logs` streams the log: history is replayed first, then live lines
arrive as `stream.chunk` notifications of shape
`{subagent_id, entry: {ts, level, message}, token}` until the child finishes.

### 3.9 `schedule.*` — cron & natural-language schedules

| Method | Params | Result |
| --- | --- | --- |
| `schedule.create` | `{name, prompt, cron_expression? \| natural_language?, description?, session_id?, enabled?, max_runs?, require_approval?}` | `Schedule` |
| `schedule.list` | `{include_disabled?: boolean}` | `{schedules: Schedule[]}` |
| `schedule.get` | `{schedule_id}` | `Schedule & {runs: Run[]}` |
| `schedule.update` | `{schedule_id, ...fields}` | `Schedule` |
| `schedule.delete` | `{schedule_id}` | `{deleted: true, schedule_id}` |
| `schedule.toggle` | `{schedule_id, enabled?}` | `Schedule` |
| `schedule.history` | `{schedule_id?, limit?}` | `{runs: Run[]}` |
| `schedule.preview` | `{natural_language \| text}` | `{valid, cron_expression?, human?, next_run?, error?}` |
| `schedule.run_now` | `{schedule_id}` | `{schedule, run}` |
| `schedule.approve` | `{approval_id, allowed?}` | `{approval_id, allowed}` |

`Schedule = {id, schedule_id, name, description, cron_expression, human,
natural_language, prompt, session_id?, enabled, last_run?, next_run?,
created_at, max_runs?, run_count, exhausted, require_approval}`

`Run = {id, schedule_id, started_at, completed_at?, duration, status,
result_summary, error?}` with `status ∈ running | success | error |
approval_denied`.

Either `cron_expression` or `natural_language` must be supplied; prose is
translated by `dream.nl_schedule.nl_to_cron`, a **pattern matcher with no model
call** that understands English and Persian ("every weekday at 6 PM" →
`0 18 * * 1-5`, "هر روز ساعت ۹ صبح" → `0 9 * * *`). Unparseable prose is an
`INVALID_PARAMS` error rather than a guess; `schedule.preview` reports the same
failure as `{valid: false, error}` without raising, so the UI can show a live
cron preview while the user is still typing.

The daemon polls every 30 s, executes due schedules through the configured
session (creating a throwaway one if `session_id` is unset), then advances
`next_run` and appends a history row. Schedules with `require_approval: true`
register a pending approval and **block** until `schedule.approve` answers it;
a timeout, a cancellation or a missing UI all deny the run (fail-closed, gate
G11) and log it as `approval_denied`. When `run_count` reaches `max_runs` the
schedule is disabled and `next_run` is cleared.

### 3.10 `health.check` / `sidecar.version`

| Method | Params | Result |
| --- | --- | --- |
| `health.check` | `{}` | `{status: "ok", sessions, provider, uptime_seconds}` |
| `sidecar.version` | `{}` | `{protocol: "1.0", core: string, python: string, sidecar: string}` |

`health.check` is the **heartbeat**: the Rust supervisor pings it every 5 s; no
reply within 15 s is treated as a hang and triggers a restart (see the failure
recovery table in the master prompt).

---

### 3.11 `gateway.*` — multi-platform connectivity (Prompt P-07)

The connectivity gateway (see `docs/architecture/connectivity.md`) routes
Telegram, Discord, Slack, WhatsApp, Signal, and Email traffic through the
same Dream agent and memory store. The gateway runs its own asyncio
event-loop thread; every `gateway.*` handler ferries work across with
`submit_async`, so the bridge loop is never blocked by adapter I/O.

| Method | Params | Result |
| --- | --- | --- |
| `gateway.platforms` | `{}` | `{platforms: GatewayPlatform[]}` — the six-platform catalog (capabilities, fields) joined with **redacted** public config: `{name, label, description, privacy, max_message_length, supports_inline, supports_attachments, fields[], enabled, configured}` |
| `gateway.status` | `{}` | `{running, started_at, adapters: GatewayAdapterStatus[], linked_users, messages: {inbound, outbound}, rate_limit}` — `GatewayAdapterStatus = {platform, running, connected, last_activity, error, detail}` |
| `gateway.start` | `{}` | same as `gateway.status` — starts every enabled, configured adapter |
| `gateway.stop` | `{}` | same as `gateway.status` — stops every adapter (the loop stays up) |
| `gateway.configure` | `{platform, config}` | `{saved, platform, config}` — merges config for one platform (blank secrets keep the stored value) and restarts its adapter when running. The returned `config` is always **redacted**: secret values are `"••••••••"`, plus `enabled` / `configured` / `secret_fields` |
| `gateway.logs` | `{platform?, limit?}` | `{platform, entries: GatewayLogEntry[], total}` — newest-first, default 100 per platform. `GatewayLogEntry = {platform, direction: "in"\|"out", user_id, text, timestamp, message_id, attachments}`. **End-to-end-encrypted platforms (Signal) always have `text: ""`.** |
| `gateway.link_code` | `{platform}` | `{platform, code, issued_at, expires_at, user_id}` — single-use 6-digit code, 10-minute TTL; issuing again returns the pending code |
| `gateway.linked_users` | `{platform?}` | `{linked_users: [{platform, user_id, display_name, linked_at}]}` |
| `gateway.unlink_user` | `{platform, user_id}` | `{unlinked, platform, user_id}` |

Param validation mirrors the rest of the protocol: unknown platforms, missing
keys, or non-integer `limit` raise `INVALID_PARAMS` (-32602). Adapter
failures never fail the RPC — they surface in the per-adapter
`error`/`detail` fields of `gateway.status`.

---

### 3.12 `data.*` — data science pipeline (Prompt P-09)

The data-science pipeline (see `docs/architecture/data-science.md`) ingests
files into a dataset registry under `data/datasets/` and runs every heavy
operation (pandas/scipy/sklearn/matplotlib) inside the P-08 Docker sandbox.
Datasets are addressed by a 32-hex `dataset_id`, never by raw path.

| Method | Params | Result |
| --- | --- | --- |
| `data.load_data` | `{file_path, name?}` | `{dataset_id, name, filename, format, shape: [rows, cols], columns, dtypes, memory_bytes, preview}` — auto-detects CSV/TSV/Excel/JSON/YAML/XML/SQLite/Parquet; copies the source into the registry |
| `data.profile_data` | `{dataset_id, max_categories?: 20}` | `{row_count, column_count, duplicate_rows, missing_pct, sampled, columns: {name → {dtype, role, missing, mean, std, q1, median, q3, outliers_iqr, outliers_zscore, top_values?, histogram?}}}` — files > 100 MB use chunked aggregation (`sampled: true`) |
| `data.clean_data` | `{dataset_id, operations: CleanOp[]}` | `{rows_before, rows_after, shape, columns, dtypes, operations_applied, preview}` — writes `cleaned.csv`, which becomes the active file. `CleanOp` is a tagged union on `op`: `drop_na fill_na convert_dtype remove_duplicates rename_column drop_column filter_rows normalize_column encode_categorical handle_outliers` |
| `data.analyze_data` | `{dataset_id, analyses: Analysis[]}` | `{results: [{kind, status: "ok"\|"error", ...}]}` — `Analysis.kind` ∈ `correlation ttest anova chi_square linear_regression logistic_regression kmeans pca time_series_decompose`; one failed analysis never kills the batch |
| `data.auto_chart` | `{dataset_id, max_charts?: 6}` | `{charts: ChartSpec[]}` — deterministic rubric over (column role, cardinality); ranked by `score`, each with a human `reason` |
| `data.create_chart` | `{chart_spec: ChartSpec}` | `{chart_id, dataset_id, spec, files: {png, svg, pdf, html}, sizes}` — themes/palettes/sizes validated against strict allowlists; each export is quota-checked (5 MB) |
| `data.generate_report` | `{dataset_id, title, sections?}` | `{pdf_path, markdown_path, size_bytes, sections, charts_embedded}` — PDF ≤ 5 pages with extractable text; sections ⊆ `abstract data_summary methodology results discussion conclusion references` |
| `data.get_report` | `{dataset_id}` | `{markdown: string \| null}` — the report's markdown twin |
| `data.list_datasets` | `{}` | `{datasets: [{dataset_id, name, filename, format, created_at, shape, columns, cleaned}]}` |
| `data.get_dataset` | `{dataset_id}` | the full registry record |
| `data.delete_dataset` | `{dataset_id}` | `{deleted, dataset_id}` — removes files, the registry row, and the dataset's kernel |

Every validation failure — unknown op/analysis/chart tags, columns absent
from the schema, column names failing `^[A-Za-z_][A-Za-z0-9_]*$` (≤ 64
chars), out-of-range sizes — raises `INVALID_PARAMS` (-32602) **before** any
sandbox execution.

### 3.13 `notebook.*` — Jupyter integration (Prompt P-09)

Notebooks live at `data/datasets/{dataset_id}/notebooks/*.ipynb`. One kernel
per dataset (`jupyter_client`), started lazily and stopped on dataset delete
or sidecar shutdown. Only these methods touch `.ipynb` files.

| Method | Params | Result |
| --- | --- | --- |
| `notebook.create` | `{dataset_id, name, cells: [{type: "code"\|"markdown", source}]}` | `{notebook_path, dataset_id, name, cell_count}` |
| `notebook.execute` | `{path, kernel_id?}` | `{notebook_path, kernel_id, cells_executed, outputs: [{cell_index, outputs}]}` — runs every code cell in order, persisting outputs into the file |
| `notebook.run_cell` | `{path, cell_index}` | `{notebook_path, cell_index, cell_type, execution_count, outputs}` — markdown cells are a no-op, not an error |
| `notebook.read` | `{path}` | `{notebook_path, cells: [{cell_type, source, outputs?, execution_count?}]}` — outputs summarised: text truncated at 20 KB, images ≤ 4 MB base64, errors as `{ename, evalue, traceback}` |
| `notebook.open_lab` | `{path}` | `{url, already_running}` — spawns a token-guarded JupyterLab rooted at the datasets directory |

Notebook paths are confined to the datasets directory (escapes raise
`INVALID_PARAMS`). When `jupyter_client` or JupyterLab is not installed the
execution methods raise code `-32012` with an actionable message; file-level
methods (`create`/`read`) keep working.

---

## 4. Error taxonomy

JSON-RPC reserves `-32000` to `-32099` for implementation-defined server errors;
Dream uses that band for its own codes. Standard JSON-RPC codes keep their
canonical numbers.

| Code | Name | Meaning |
| --- | --- | --- |
| `-32700` | `PARSE_ERROR` | The line was not valid JSON. The line is skipped; the connection stays alive. |
| `-32600` | `INVALID_REQUEST` | Valid JSON but not a JSON-RPC 2.0 request (bad envelope, unknown `jsonrpc` version, payload too large, missing `method`). |
| `-32601` | `METHOD_NOT_FOUND` | The `method` is not a known method. |
| `-32602` | `INVALID_PARAMS` | The `params` failed validation (wrong type, missing required key, out of range). Includes which param. |
| `-32603` | `INTERNAL_ERROR` | An unexpected exception in the sidecar (full traceback in dev `data`). |
| `-32001` | `PROVIDER_ERROR` | A model provider call failed (HTTP error, malformed response). |
| `-32002` | `AUTH_ERROR` | Missing or rejected credentials for a provider. |
| `-32003` | `RATE_LIMITED` | The provider returned 429 / quota exhausted. |
| `-32004` | `CONTEXT_OVERFLOW` | The request exceeded the provider's context window. |
| `-32005` | `APPROVAL_REQUIRED` | A dangerous tool needs human approval before it runs. Carries `approval_id`. |
| `-32006` | `TOOL_ERROR` | A tool ran but raised an exception (the structured tool error is in `data`). |
| `-32007` | `RESOURCE_EXHAUSTED` | Backpressure: too many in-flight requests; the client should retry. |

Mapping from Python exceptions to codes (see `dream/bridge/errors.py`):

- `ValueError` from bad params, or `TypeError` → `INVALID_PARAMS`
- `KeyError` / missing key → `INVALID_PARAMS`
- `FileNotFoundError` / `PermissionError` (workspace boundary) → `TOOL_ERROR`
- HTTP/`URLError`/`TimeoutError` → `PROVIDER_ERROR`
- `PermissionError` carrying an auth signal → `AUTH_ERROR`
- Everything else → `INTERNAL_ERROR`

The mapping is a **deny-by-default** fallback: an unmapped exception is never
shown verbatim in production — only its type and a sanitised message appear.

---

## 5. Streaming & notifications

### 5.1 Streaming responses

A streaming method (marked `*` in §3) emits a sequence of **notifications**
**followed by** one final response for the original `id`:

```
→ {"jsonrpc":"2.0","id":7,"method":"conversation.send","params":{"session_id":"s1","message":"hi"}}
← {"jsonrpc":"2.0","method":"stream.start","params":{"id":7,"session_id":"s1"}}
← {"jsonrpc":"2.0","method":"stream.chunk","params":{"id":7,"session_id":"s1","token":"Echo"}}
← {"jsonrpc":"2.0","method":"stream.chunk","params":{"id":7,"session_id":"s1","token":": hi"}}
← {"jsonrpc":"2.0","method":"stream.end","params":{"id":7,"session_id":"s1"}}
← {"jsonrpc":"2.0","id":7,"result":{ … full Turn … }}
```

- `stream.*` notifications carry the **request `id`** in `params.id` so the
  frontend can route chunks to the right in-flight `stream()` call.
- `stream.start` / `stream.end` bracket the chunk stream; `stream.chunk` carries
  a `token` (a fragment of assistant text). Non-text events (tool calls,
  memories) may be carried as `stream.chunk` with an `event` discriminator
  (`"event": "tool_call"`) — the canonical text stream uses the default text
  token.
- If the method fails, the sidecar emits `stream.end` (if `stream.start` was
  sent) and then an **error response** for `id` — never a success `result`.
- A request that errors before `stream.start` produces only the error response.
- The final `result`/`error` is the authority: a missing final message means the
  stream is still open or was interrupted (the supervisor restart path, §6).

### 5.2 Approval during a tool execution

`APPROVAL_REQUIRED` carries `data.approval_id`. The flow is a normal error →
re-request cycle, not streaming, so the frontend logic is uniform with other
errors.

### 5.3 `conversation.stop`

`conversation.stop` is a notification-like best-effort control message: it is
sent as a normal request with its **own** `id` and returns `{stopped: true}` when
accepted. The in-flight `conversation.send` for that session is signalled to
abort at the next safe point; it then ends its stream and returns whatever
partial `Turn` it has.

### 5.4 Server notifications (no `id`)

The sidecar may emit notifications with **no** `id`:

| Method | Params | When |
| --- | --- | --- |
| `state` | `{state: "ready"\|"restarting"\|"draining"}` | Lifecycle transitions. |
| `log` | `{level, message}` | Optional forwarded stderr-style log line (dev only). |

---

## 6. Backpressure & failure recovery

### 6.1 Backpressure

- The sidecar processes requests **concurrently** (each offloaded to a worker
  thread for blocking core calls), bounded by a semaphore of **`N = 16`**
  concurrent handlers. Beyond that, requests queue.
- If the pending queue exceeds **128** requests, new requests are rejected with
  `RESOURCE_EXHAUSTED` rather than unbounded memory growth. The client retries
  with backoff.
- The frontend writer buffers requests and applies **write-time** backpressure
  by awaiting each line's flush; it never floods stdin faster than the sidecar
  reads.

### 6.2 Failure recovery (mirrors the master-prompt table)

| Scenario | Behaviour |
| --- | --- |
| Sidecar crashes | Supervisor auto-restarts (max 3: 2 s / 5 s / 10 s backoff). Pending requests are rejected with `INTERNAL_ERROR`; UI shows "Reconnecting…". |
| Sidecar hangs | Heartbeat (`health.check`) timeout 15 s → kill → restart. |
| Python exception in handler | Serialized as an RPC error (traceback in dev, sanitised message in prod). |
| Message too large (> 10 MiB) | `INVALID_REQUEST` "payload too large"; connection alive. |
| Unknown method | `METHOD_NOT_FOUND`. |
| Malformed JSON | `PARSE_ERROR`; line skipped; connection alive. |
| EOF on stdin | Graceful shutdown: drain in-flight requests (up to 5 s), close the store, exit 0. |

---

## 7. Security boundaries (gate G8)

- **No shell injection.** `tool.execute`/`run_shell` is gated behind
  `APPROVAL_REQUIRED`; method params are never interpolated into a shell by the
  bridge itself. `run_shell` is the only tool that shells out and is `dangerous`.
- **No path traversal.** All workspace access goes through `dream.tools._safe_path`,
  which rejects absolute paths, `..` escapes, and Windows reserved device names.
- **No credential leakage.** Provider API keys are never written to stdout,
  logs, or error `data`; `error.message` is sanitised of bearer tokens.
- **No privilege escalation.** The sidecar runs as the same OS user as the app;
  it performs no `setuid`/elevation and opens no privileged sockets.
- **Bounded input.** Line length (10 MiB), queue depth (128), and concurrency
  (16) are all capped to resist resource exhaustion.
- **Subagent containment.** A child agent gets an ephemeral in-memory store and
  an explicit tool subset, so it cannot read the parent's memories or reach the
  workspace through a tool the parent did not grant. `dangerous` tools are
  filtered out of every child registry unless the parent passes
  `allow_dangerous`, and children are bounded by turn, token and wall-clock
  budgets plus a global concurrency cap.
- **Scheduled runs are gated.** A schedule with `require_approval` cannot
  execute until a human resolves its approval; the gate fails **closed** on
  timeout, cancellation or a missing UI, and the denial is written to the
  execution history.

---

## 8. Versioning policy

- `MAJOR.MINOR`. A bump of `MAJOR` is breaking and requires a coordinated
  frontend+sidecar upgrade. `MINOR` adds methods/fields and is backward
  compatible (frontend ignores unknown fields).
- The protocol version is independent of the `dream/` package version
  (`sidecar.version.core`) and the sidecar build (`sidecar.version.sidecar`).

## 9. Reference implementation map

| Concern | Python | Rust | TypeScript |
| --- | --- | --- | --- |
| Framing & envelope | `dream/bridge/server.py` | `bridge/framing.rs` | `lib/bridge/client.ts` |
| Error taxonomy | `dream/bridge/errors.py` | `bridge/framing.rs` | `lib/bridge/errors.ts` |
| Method handlers | `dream/bridge/methods.py` | — (passthrough) | `lib/bridge/types.ts` |
| Streaming helpers | `dream/bridge/streams.py` | `bridge/dispatcher.rs` | `lib/bridge/client.ts` |
| Process supervision | — | `bridge/process.rs` | `lib/bridge/hooks.ts` (reconnect) |
| Connection state | — | `bridge/state.rs` | `lib/bridge/hooks.ts` |
| Subagent runtime | `dream/subagents.py` | — | `routes/subagents.tsx` |
| Scheduler & cron | `dream/scheduler.py`, `dream/cron.py`, `dream/nl_schedule.py` | — | `routes/schedules.tsx` |
| Connectivity gateway | `dream/connectivity/` (`gateway.py`, `adapters/`) | — | `lib/bridge/echo-gateway.ts`, `routes/connectivity.tsx` |
| Data science pipeline | `dream/skills/data_science.py`, `dream/skills/notebooks.py` | — | `lib/bridge/data-science.ts`, `lib/bridge/echo-data.ts`, `routes/data.tsx`, `routes/data.dataset.tsx` |
