# Dream — Master Checklist

> Source of truth for phase gating. A phase item is checked only when its gate
> artifacts exist in the repository and have been reviewed. No frontend code is
> written before Phase 0 is signed off (Gate G9).

Legend: `[x]` complete · `[~]` in progress · `[ ]` not started

---

## Phase 0 — UI/UX Design (Prompt P-00) `docs/design/`

### 0.1 Research, Personas & User Flows
- [x] 0.1.1 Study existing Dream CLI (`cli.py`) and Tkinter desktop (`desktop.py`) — capabilities inventory
- [x] 0.1.2 Reference-app study: Hermes Agent, Open Science Desktop, DeepAnalyze
- [x] 0.1.3 Competitor study: ChatGPT desktop, Claude desktop, Cursor, VS Code, Linear, Notion
- [x] 0.1.4 Personas defined (4): privacy-conscious researcher, data analyst, power user, Persian-speaking user
- [x] 0.1.5 User workflows documented (task inventory)
- [x] 0.1.6 Primary flow mapped: launch → configure provider → converse → tool use → result
- [x] 0.1.7 Secondary flows: project / memory / subagent, data science, settings, mobile gateway, RTL
- [x] **Gate G1 — Research complete** → `docs/design/research.md`
- [x] **Gate G2 — Flows approved** → `docs/design/user-flows/`

### 0.2 Wireframes & Design System
- [x] 0.2.1 Low-fidelity wireframes, all 17 screens → `docs/design/wireframes/` (SVG)
- [x] 0.2.2 Color palette (light + dark), protanopia/deuteranopia-safe semantics
- [x] 0.2.3 Typography scale — Inter (Latin) + Vazirmatn (Persian/Arabic), matched x-height
- [x] 0.2.4 Spacing / radius / shadow / elevation / motion tokens
- [x] 0.2.5 Component library specification (buttons → skeletons, Shadcn/ui-mappable)
- [x] 0.2.6 Icon set selected: Lucide (ISC license) + usage rules
- [x] 0.2.7 Tokens exported for tooling → `docs/design/tokens/` (Tokens Studio JSON + CSS custom properties)
- [x] **Gate G3 — Wireframes approved** → `docs/design/wireframes/`
- [x] **Gate G4 — Design system complete** → `docs/design/design-system.md`

### 0.3 High-Fidelity Prototype, Motion, A11y, RTL, Sign-off
- [x] 0.3.1 High-fidelity interactive prototype — core screens, both themes → `docs/design/prototype/`
- [x] 0.3.2 RTL Persian variants (live direction/language toggle in prototype)
- [x] 0.3.3 Responsive mobile/tablet behavior (prototype is responsive; resize or use device toolbar)
- [x] 0.3.4 Micro-interaction & motion specs → `docs/design/animation-specs.md`
- [x] 0.3.5 Empty / loading / error states designed (see prototype "States" controls + design-system.md)
- [x] **Gate G5 — Mockups approved** (hi-fi prototype stands in for static mockups)
- [x] **Gate G6 — Prototype functional** (click-through of main flows)
- [x] **Gate G7 — Accessibility pass** → `docs/design/accessibility-audit.md` (WCAG 2.1 AA)
- [x] **Gate G8 — RTL verified** (mirroring rules + overflow checks documented)
- [ ] **Gate G9 — Final client sign-off** → `docs/design/approval-signoff.md` (awaiting client)

---

## Phase 1 — Desktop Shell (Prompt P-01) — Tauri 2 + React + Tailwind + Shadcn/ui
- [x] 1.1 Scaffold Tauri 2 app; import design tokens from `docs/design/tokens/`
- [x] 1.2 App shell: title bar, activity rail, session sidebar, status bar
- [x] 1.3 Theme engine (light/dark/system) + direction engine (LTR/RTL) from day one
- [x] 1.4 Multi-pane layout manager (2/3/4 panes, drag handles, keyboard resize)
- [~] 1.5 IPC bridge to Python core (sidecar or service) — **P-02**: JSON-RPC
  bridge implemented across Python (`dream/bridge/`), Rust (`src-tauri/src/bridge/`),
  and TypeScript (`src/lib/bridge/`); spec at `docs/bridge/protocol.md`. Python +
  frontend tested green; Rust written pending CI compile. See `docs/STATUS.md` (P-02).

## Phase 2 — Conversation & Memory (Prompt P-02)
- [ ] 2.1 Conversation view: streaming, tool-call cards, approval dialog
- [ ] 2.2 Session manager (list, search, date groups)
- [ ] 2.3 Memory explorer + timeline; reminders
- [ ] 2.4 Skills manager

### 2.5 Subagent system (Prompt P-06)
- [x] 2.5.1 Architecture of record → `docs/architecture/subagents.md` (Gate G1)
- [x] 2.5.2 `SubAgent` data model + lifecycle (idle → running → paused →
  completed/failed/cancelled/timeout) — `dream/subagents.py` (Gate G2)
- [x] 2.5.3 Resource limits enforced: max turns, max tokens, max wall clock,
  whichever trips first (Gate G3)
- [x] 2.5.4 Isolation: own asyncio Task, own `Dream`, ephemeral in-memory store,
  restricted tool registry — no parent memory access (Gate G4)
- [x] 2.5.5 `SubAgentManager`: spawn / get / list / cancel / pause / resume,
  graceful cancellation with grace period then force kill
- [x] 2.5.6 Pipeline chaining — each stage's result becomes the next's context (Gate G5)
- [x] 2.5.7 RPC: `subagent.spawn|pipeline|list|get|status|cancel|pause|resume|logs`
  with log streaming and cancel under 2 s (Gate G6)
- [ ] 2.5.8 Subagent dashboard UI: status badges, progress bars, detail view,
  live log, cancel/pause/resume, spawn dialog, pipeline builder (Gate G6)

### 2.6 Scheduler (Prompt P-06)
- [x] 2.6.1 `Schedule` + `ScheduleRun` models and CRUD over `MemoryStore` — `dream/scheduler.py`
- [x] 2.6.2 Cron engine (5-field parse, `next_run_after`, human descriptions) — `dream/cron.py`
- [x] 2.6.3 `nl_to_cron` pattern matcher, 20+ English and Persian phrasings, no
  model call — `dream/nl_schedule.py` (Gate G7)
- [x] 2.6.4 Scheduler daemon: 30 s poll, session reuse, fail-closed approval gate (Gate G8)
- [x] 2.6.5 Execution history with status and duration (Gate G10)
- [x] 2.6.6 RPC: `schedule.create|list|get|update|delete|toggle|history|preview|run_now|approve`
- [ ] 2.6.7 Scheduler UI: schedule cards, live cron preview, history timeline,
  edit/delete confirmation (Gate G9)
- [x] 2.6.8 Security: children cannot reach parent files or memory; scheduled
  dangerous tools require approval (Gate G11)

## Phase 3 — Multi-Platform Connectivity (Prompt P-07)

> Numbering follows the P-07 master prompt (3.1.1–3.6.7); the adjacent
> P-03 "Projects, Subagents & Provenance" phase keeps its own numbering.

### 3.1 Gateway architecture (Gate G1)
- [x] 3.1.1 `PlatformAdapter` ABC contract (classvars, start/stop, send, typing, status)
- [x] 3.1.2 Normalised `IncomingMessage` model with attachments + raw escape hatch
- [x] 3.1.3 Rate-limit gate counter `{platform, user_id, minute}` — default 20/min, per-platform configurable
- [x] 3.1.4 Architecture of record → `docs/architecture/connectivity.md` (Gate G1)

### 3.2 Core modules
- [x] 3.2.1 `models.py` — Attachment/IncomingMessage/PlatformStatus/LinkedUser/MessageLogEntry
- [x] 3.2.2 `base.py` — adapter ABC + word-boundary `split_text()`
- [x] 3.2.3 `ratelimit.py` — fixed-minute window, pruning, per-platform limits
- [x] 3.2.4 `config.py` — per-platform JSON, atomic 0600 writes, secret redaction (`*token*`, `*secret*`, password, key)
- [x] 3.2.5 `auth.py` — single-use, time-bounded link codes (constant-time compare) + persisted linked users
- [x] 3.2.6 `sessions.py` — (platform, user_id) → Dream, persisted JSON index
- [x] 3.2.7 `messagelog.py` — per-platform ring buffer (JSONL); e2e (Signal) rows carry empty text
- [x] 3.2.8 `websocket.py` — minimal async RFC 6455 client (shared by Discord + Slack)

### 3.3 Gateway (Gate G2)
- [x] 3.3.1 Owns adapters, sessions, auth, rate limiter, message log, status aggregator
- [x] 3.3.2 Dedicated asyncio event-loop thread; `start_loop` / `submit` / `submit_async`
- [x] 3.3.3 `register_adapter` / `start_all` / `stop_all` / `adapter_status`
- [x] 3.3.4 `route_message` pipeline: log → pre-auth commands → auth → rate → command → agent → split → send (Gate G4)
- [x] 3.3.5 Second `route_message` reuses the same Dream instance (Gate G5)

### 3.4 Platform adapters (Gate G3)
- [x] 3.4.1 Telegram — long-polling getUpdates; /start /help /new_session /status /link; 4096-char split
- [x] 3.4.2 Discord — gateway WS (Op 10→2→11, compress:false) + REST; Deferred Op-5 ack + PATCH follow-up; threads; uploads; 2000-char split
- [x] 3.4.3 Slack — Socket Mode via shared WS client; envelope acks; response_url replies; 4000-char split
- [x] 3.4.4 WhatsApp — Cloud API webhook (ThreadingHTTPServer), verify-token GET, optional HMAC; two-step media; 4096-char split
- [x] 3.4.5 Signal — signal-cli receive --json loop; binary fail-fast; send --message-from-stdin; privacy e2e (content never logged, Gate G11)
- [x] 3.4.6 Email — IMAP IDLE (raw-socket) + poll fallback; HTML→text; SMTP threads (In-Reply-To/References); reply-loop guards

### 3.5 Bridge integration & tests (Gates G4–G9, G11)
- [x] 3.5.1 `gateway.*` methods registered in `dream/bridge/methods.py` (start/stop/status/configure/logs/link_code/linked_users/unlink_user/platforms)
- [x] 3.5.2 Protocol documentation → `docs/bridge/protocol.md` §3.11
- [x] 3.5.3 Python suite: 55 new tests (models, ratelimit, sessions, gateway, websocket round-trip, one adapter test per platform with fake transports, bridge RPCs); full suite 1327 passed

### 3.6 Frontend (Gates G7 + G8)
- [x] 3.6.1 `routes/connectivity.tsx` settings page with six platform cards
- [x] 3.6.2 `components/connectivity/platform-card.tsx` — status badge, enable toggle, Configure expand
- [x] 3.6.3 `components/connectivity/platform-config.tsx` — per-platform forms; secrets hidden by default
- [x] 3.6.4 `components/connectivity/message-log.tsx` — last-100-per-platform viewer
- [x] 3.6.5 `stores/use-connectivity-store.ts` — Zustand store; all actions through the bridge
- [x] 3.6.6 Route registered in `App.tsx`; Radio icon added to the activity rail
- [x] 3.6.7 Echo transport: `gateway.*` handlers + types, so dev/tests need no sidecar; 245 frontend tests, tsc/lint/prettier/build green

## Phase 3 — Projects, Subagents & Provenance (Prompt P-03 / P-10)
- [ ] 3.1 Project dashboard; file browser
- [ ] 3.2 Subagent monitor
- [x] 3.3 Run history / provenance viewer — **P-10**: Full tamper-evident SHA-256 provenance logging, artifact sidecar linking, lineage graph & timeline UI, and reproducibility ZIP export.

## Phase 4 — Data Science Workbench (Prompt P-04 / P-09)

### 4.1 Data Loading & Registry (Task 1)
- [x] 4.1.1 `load_data` tool: ingest into `data/datasets/{id}/`, registry by `dataset_id` (uuid), never raw paths
- [x] 4.1.2 All 8 formats: CSV, TSV, Excel (.xlsx/.xls), JSON, YAML, XML, SQLite, Parquet
- [x] 4.1.3 Auto-detect from extension; content sniffing for ambiguous extensions (magic bytes + delimiter counting)
- [x] 4.1.4 Size bounds: 500 MB ingestion cap; > 100 MB profiled via chunked aggregation
- [x] 4.1.5 `data.list_datasets` / `data.get_dataset` / `data.delete_dataset` registry RPCs
- [x] **Gate G1 — Data loading** → one fixture per format in `tests/test_data_science_io.py`

### 4.2 Profiling & Cleaning (Task 1)
- [x] 4.2.1 `profile_data`: per-column stats (numeric/categorical/datetime/text/boolean), missing %, duplicates, histograms
- [x] 4.2.2 Outlier detection: IQR fences and z-score, verified on synthetic ground-truth fixtures
- [x] 4.2.3 `clean_data` with all 10 ops: drop_na, fill_na, convert_dtype, remove_duplicates, rename_column, drop_column, filter_rows, normalize_column, encode_categorical, handle_outliers
- [x] 4.2.4 Validation: column regex `^[A-Za-z_][A-Za-z0-9_]*$` ≤ 64 chars, schema membership, tagged-union checks, schema tracking across renames/drops
- [x] 4.2.5 `cleaned.csv` becomes the active file; dtypes re-applied on reload
- [x] **Gate G2 — Profiling** → within 1e-9 of hand-computed reference (`tests/test_data_science_profile.py`)
- [x] **Gate G3 — Cleaning** → 10 ops round-trip with explicit invariants (`tests/test_data_science_clean.py`)

### 4.3 Statistical Analysis (Task 1)
- [x] 4.3.1 `analyze_data`: correlation, ttest, anova, chi_square, linear_regression, logistic_regression, kmeans, pca, time_series_decompose
- [x] 4.3.2 Type checks: 2-level categorical for t-test, parseable datetime for time series, numeric coercion, target ∉ features
- [x] 4.3.3 Per-analysis error isolation — one failure never kills the batch
- [x] **Gate G4 — Analysis** → agrees with scipy references to 1e-9 (`tests/test_data_science_analyze.py`)

### 4.4 Visualization (Task 2)
- [x] 4.4.1 `create_chart`: 9 chart types (line, bar, scatter, histogram, box, heatmap, pie, area, bubble)
- [x] 4.4.2 `auto_chart`: deterministic ranked suggestions from (role, cardinality) rubric
- [x] 4.4.3 Themes (default/minimal/dark/ggplot/seaborn, graceful fallback) + strict palette allowlist + custom hex colors
- [x] 4.4.4 Sizing bounds (200–4096 × 150–4096, dpi ∈ {72,96,150,300}); 5 MB per-export quota enforced
- [x] 4.4.5 Exports: PNG/SVG/PDF via matplotlib, interactive HTML via Plotly payload — all rendered in the sandbox
- [x] **Gate G5 — Charts** → every type renders under quota; auto-select ground truth (`tests/test_data_science_charts.py`)

### 4.5 Reports & Notebooks (Tasks 1 & 3)
- [x] 4.5.1 `generate_report`: PDF ≤ 5 pages with extractable title, sections (abstract…references), numeric table, embedded charts + markdown twin
- [x] 4.5.2 DOI references are static text; report generation never touches the network
- [x] 4.5.3 `notebook.create` / `read`: nbformat-v4 JSON on the host, paths confined to the datasets directory
- [x] 4.5.4 `notebook.execute` / `run_cell`: jupyter_client kernels, one per dataset, outputs persisted + summarised
- [x] 4.5.5 `notebook.open_lab`: token-guarded JupyterLab spawn; R kernel used when installed, quiet Python fallback otherwise
- [x] **Gate G6 — Reports** → pypdf extracts the title (`tests/test_data_science_report.py`)
- [x] **Gate G7 — Notebooks** → create/execute/read/open-lab with live kernel (`tests/test_notebooks_kernel.py`)

### 4.6 Bridge, Frontend & Quality (Tasks 4–6)
- [x] 4.6.1 RPC families `data.*` (11 methods) + `notebook.*` (5 methods) in `dream/bridge/methods.py`; protocol §3.12–3.13
- [x] 4.6.2 Typed wrapper `apps/desktop/src/lib/bridge/data-science.ts` + DTOs in `types.ts`
- [x] 4.6.3 Deterministic echo runtime (`echo-data.ts`): seeded 1k-row sales-2024 CSV, chart spec, notebook outputs, report markdown
- [x] 4.6.4 Workbench routes `/data` + `/data/:datasetId` (Preview/Profile/Charts/Notebook/Report tabs) registered in `App.tsx`, nav in activity rail
- [x] 4.6.5 Preview grid: TanStack Table with sort/filter/paginate/column-resize/row-hover/cell-copy
- [x] 4.6.6 Tests: 170+ new Python tests across 8 files; vitest wrapper + component render suites; ≥ 80% coverage on new modules
- [x] 4.6.7 Security: all execution sandboxed, params via `_params.json` (no code interpolation), allowlists everywhere, sizes bounded
- [x] **Gate G8 — Workbench UI** → sort/filter/paginate/copy/export in `routes/data.test.tsx`
- [x] **Gate G9/G10 — Security & performance** → 1 MB CSV < 3 s, profile < 10 s, chart < 3 s (`tests/test_data_science_perf.py`)

## Phase 5 — Providers, MCP & Web Gateway (Prompt P-05 / P-10)
- [x] 5.1 Provider configuration + connection test — **P-10**: Model provider manager with ACP backends, OpenAI, Ollama, and Echo.
- [x] 5.2 MCP server configuration — **P-10**: Multi-server MCP manager (stdio, SSE, WebSocket), tool discovery, resource access, and settings UI.
- [ ] 5.3 Web gateway (mobile/tablet responsive) + authentication

## Phase 3.7–3.9 — Docker Sandbox, Chrome Control & Web Gateway (Prompt P-08)
### Docker Sandbox Core (Task 1)
- [x] 1.1 Implement ``DockerSandbox`` class with ``run_code``, ``run_notebook``, ``install_packages``
- [x] 1.2 Docker image management: auto-pull, base images (python:3.12-slim, rocker/r-ver:4.4)
- [x] 1.3 Container lifecycle: create, resource limits, execute, auto-remove, timeout
- [x] 1.4 Security hardening: seccomp, --cap-drop=ALL, no-new-privileges, read-only fs, network disabled, swap disabled, PIDs limit, user namespace
- [x] 1.5 Result extraction: stdout/stderr capture, output file detection (images, CSVs, etc.)
- [x] 1.6 Docker readiness check at startup
- [x] 1.7 RPC methods registered: ``sandbox.run_code``, ``sandbox.run_notebook``, ``sandbox.install_packages``, ``sandbox.status``
- [x] **Gate G1 — Docker executes** → `dream/docker_sandbox.py`
- [x] **Gate G2 — Docker security** → seccomp profile, no capabilities, no network, no-new-privileges

### Docker Sandbox UI (Task 2)
- [x] 2.1 Sandbox configuration in settings: enable/disable, default resource limits, image selection
- [x] 2.2 Sandbox status indicator (Docker available/unavailable/error)
- [x] 2.3 Execution result display in chat: return code, stdout, stderr, output files
- [x] 2.4 Approval gate for first execution
- [x] **Gate** — Sandbox settings render, status visible, results displayed

### Chrome Browser Control (Task 3)
- [x] 3.1 ``BrowserController`` class: attach, launch, navigate, get_content, execute_js, fill_form, click, screenshot, get_cookies, close
- [x] 3.2 User's real Chrome attachment via CDP (preserves sessions/logins)
- [x] 3.3 Isolated browser mode (temporary user data dir, incognito-equivalent)
- [x] 3.4 Page interaction: navigation, content extraction, form filling, screenshot, cookie inspection
- [x] 3.5 Security: user approval per session, no profile copying, local screenshots, 5-minute timeout
- [x] 3.6 RPC methods registered: ``browser.*`` (attach, launch, navigate, screenshot, etc.)
- [x] **Gate G4 — Chrome attaches** → `dream/browser_controller.py`
- [x] **Gate G5 — Browser control** → navigation, content extraction, form fill, screenshot
- [x] **Gate G6 — Browser security** → approval required, local-only screenshots, no cookie transmission

### Browser Control UI (Task 4)
- [x] 4.1 Browser session approval dialog (URL, purpose, Allow Once / Allow Domain / Deny)
- [x] 4.2 Browser status indicator (Chrome attached/isolated/offline)
- [x] 4.3 Screenshot display in chat (thumbnail, click to expand)
- [x] **Gate** — Approval dialog, screenshots, status indicator

### Web Gateway (Task 5)
- [x] 5.1 FastAPI HTTP server with routes for /, /api/chat, /api/sessions
- [x] 5.2 Serve the React SPA (single-page app)
- [x] 5.3 Token authentication: one-time setup token, token scopes (read/write)
- [x] 5.4 Read-only vs. full-access mode enforcement
- [x] 5.5 LAN discovery via mDNS/Bonjour (dream.local)
- [x] 5.6 TLS support (self-signed cert generation)
- [x] 5.7 CORS and security headers (CSP, HSTS, X-Frame-Options)
- [x] 5.8 Connection indicator in desktop app
- [x] **Gate G7 — Gateway serves UI** → `dream/gateway_server.py`
- [x] **Gate G8 — Gateway auth** → token verification, scope enforcement
- [x] **Gate G9 — LAN discovery** → mDNS advertisement
- [x] **Gate G10 — TLS works** → self-signed cert generation

### Gateway Settings UI (Task 6)
- [x] 6.1 Gateway settings page: enable/disable, port, token display/regenerate, TLS toggle, LAN-only toggle
- [x] 6.2 Active connections list
- [x] 6.3 QR code for easy mobile connection
- [x] **Gate** — Settings render, token management works, connections visible, QR code
