# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Release notes for each tag are rendered from the matching section below.

## Unreleased

## [5.12.0] - 2026-09-25

### Added — research publication and episodic memory operations, batch 11

- **پژوهش — ویرایش و انتشار واقعی:**
  - `research.modify` is now available in the desktop UI while a plan is
    awaiting approval. The user enters explicit JSON changes (or
    `{"replan": true}`); no hidden planner mutation occurs.
  - `research.export` is available after a COMPLETE report and calls the
    core's real `publish()` checkpoint. The UI does not invent a file path
    or claim an export artifact the engine did not return.
- **حافظهٔ اپیزودیک — دو عمل واقعی:**
  - `episodic.compress_session` turns the selected working session's real
    turns into a durable Tier-1 `EpisodeRecord`, with domain and bounded
    working-memory input preserved by the core.
  - `episodic.consolidate` runs the real Tier-3 persona consolidation over
    existing episodes and returns the updated persona/mastery result.
  - Both actions require an explicit button; no automatic compression or
    consolidation was added.
- Browser-honest tests cover the new bridge helpers, research actions, and
  memory operations. Evidence remains user-triggered only.

### Zero-simulation verdict

- All four connected methods use existing real engine state and durable
  records. No synthetic report, fake episode, fake persona, or pretend file
  export was added.

### Tests

- 123 frontend tests, 19 files; 4254 Python tests remain the baseline.

## [5.11.0] - 2026-09-25

### Added — explicit references and command palette, batch 10

- **مراجع و فرمان‌ها** added as a fourth real Agent Mode workbench.
  The UI exposes four approval-free, explicit tools:
  - `workspace.refs_parse`: parses only user-written `@file`,
    `#conversation`, `/command`, and `!shell` references; it does not
    open, fetch, or execute anything automatically.
  - `workspace.refs_file`: previews a relative path through the real
    registered workspace service; root selection is explicit and the
    core's safe preview/redaction rules remain in force.
  - `workspace.refs_conversation`: resolves the explicit session ID
    into a conversation reference; no conversation is silently loaded.
  - `workspace.commands_list`: reads the real Persian/English command
    palette from `agentmodes.refs.COMMAND_PALETTE`.
- Browser-honest tests cover the fourth tab, each bridge helper, and
  the no-fake-result/no-auto-open behavior.

### Zero-simulation verdict

- No chat parser, auto-file opening, auto-conversation loading, or shell
  execution was added. The user must choose every action explicitly.
- `agentmodes.refs` and the workspace preview service are real and
  bounded; the UI surfaces their output without inventing content.

### Tests

- 118 frontend tests, 18 files after adding the references workbench;
  4254 Python tests remain the baseline.

## [5.10.0] - 2026-09-25

### Added — honest diagram review, batch 9

- **بازبینی نمودار واقعی در نمای بینایی.** Added `vision.inspect_diagram`
  to the desktop bridge and a Persian UI workbench accepting user-provided
  Mermaid or SVG source. The core parser returns actual structural evidence:
  Mermaid type, node/edge counts, Persian-label detection, or SVG element
  counts and validity. No image understanding is claimed; the UI says so.
- Evidence remains user-triggered only: the diagram evidence drawer never
  opens automatically.
- **Zero-simulation verdict recorded:** `vision.decompose_video` calls
  `extract_from_simulated_video` whenever real frames are absent; it stays
  unwired. `vision.analyze_image` and `vision.ground_ui_elements` consume
  descriptors rather than decoding pixels; they stay unwired as image
  perception features. Existing `vision.capture_screen` remains wired because
  it performs real GDI capture, OCR, and immediate temp-file deletion.

### Tests

- 115 frontend tests after adding honest diagram-review coverage and bridge
  guards; full Python suite remains unchanged.

## [5.9.0] - 2026-09-24

### Added — the complete data studio, batch 8 (real engines only)

- **استودیوی دادهٔ کامل.** The Data view grew three real capabilities —
  five new bridge helpers:
  - «کشف مجموعه‌داده»: Persian-aware dataset discovery over the Dream
    workspace (`dataqa.discover`) — bounded schema profiling (500-row
    samples, ≤2000 files, ≤500MB), Persian/English synonym families
    (فروش/درآمد/مبلغ…), honest limitations per candidate, and one
    click to start a session from a discovered dataset
    (`sessions.create {dataset_id}`);
  - «نشست‌های ذخیره‌شده»: persisted-session management — open a past
    session with its last grounded answers (`sessions.get`), delete
    with its chart assets (`sessions.delete`);
  - «نمودار»: a REAL SVG chart, built by the core ONLY from executed
    evidence (`dataqa.chart`) — quota-bounded (32/session, 4MB dir,
    512KB SVG), honest refusal when the latest answer does not
    support a consistent chart, with an evidence chain for the chart
    itself.
- **Zero-simulation verdict, recorded:** the `system.*` telemetry
  domain stays unwired — its device numbers are invented constants
  (hardcoded 16GB VRAM / 32GB RAM, per-backend tps/latency tables, a
  fixed 450/200 GB/s bandwidth, and a decorative
  `sha256_verified_golden_release_dream_v4` "signature"), and
  `get_golden_release_info` is a static marketing checklist
  (readiness 100.0, "verified" swarm) that contradicts the recorded
  verdicts. Wiring it would surface fake numbers; it joins the
  unwired-by-design list.

### Tests

- Browser-honest data-studio tests (new file) + bridge guards for the
  five new helpers; 113 frontend tests total (was 106); Python suite
  unchanged.

## [5.8.0] - 2026-09-24

### Added — agent mode, batch 7 (real engines only)

- **حالت ایجنت (Agent Mode).** A new AGENT view with three real
  workbenches — six new bridge helpers:
  - «هدف»: an objective plus YOUR acceptance criteria; the core verifies
    each criterion with an honest RULE-BASED evaluator — real filenames
    under registered workspace roots (bounded walk), listing-cap
    compliance, impossible markers (network, live market,…) refused —
    and reports "unable" out loud when a criterion is not locally
    verifiable (`workspace.agentmode_goal/report/stop`).
  - «پوسته»: guarded !shell with a real subprocess — propose, see the
    risk tier (safe/guarded/dangerous), approve, execute: network off
    (PATH=/usr/bin:/bin), guarded commands path-confined to a
    registered workspace root, dangerous commands NEVER spawn even if
    approved (`workspace.shell_propose/execute`).
  - «وضعیت زنده»: the live registry of recent goals and subagent
    bookkeeping, with a real stop that cancels through engine tokens
    (`workspace.agentmode_status/stop`).
- **Zero-simulation verdicts, recorded:** `agentmode_plan` /
  `agentmode_continue` draft three FIXED template steps and mark them
  done without doing any work (`executed: true` with nothing performed)
  — simulated execution, unwired by design.

### Tests

- Browser-honest agent-view tests + bridge guards for the six new
  helpers; 106 frontend tests total (was 99); Python suite unchanged.

## [5.7.0] - 2026-09-24

### Added — spaces, batch 6 (real engines only)

- **فضاها (Spaces).** A new SPACES view on the real space service — ten
  new `space.*` / `liveloop.arm_draft` bridge helpers:
  - durable project spaces (persisted in `data/spaces.json`) with
    language and risk-ceiling choices, and folders attached IN PLACE
    through the workspace import (nothing is copied);
  - a per-space instruction doc — pasted text or a picked file —
    scanned by the REAL prompt-injection detector; suspicious docs are
    quarantined, never silently obeyed;
  - the specialized-role catalog with effective risk ceilings per
    space (a role can never widen grants above the space ceiling);
  - automation rules: natural language parsed into a real cron
    expression (`nl_to_cron`), `!shell` snippets risk-classified
    (dangerous shell is never scheduled), and an approved draft can be
    ARMED onto the real scheduler via `liveloop.arm_draft` — every
    later fire still requires explicit approval
    (`require_approval=true`), stated in the UI.
- **Zero-simulation verdicts, recorded:** `space.ask` and
  `liveloop.role_turn` return templated local briefings (the core says
  `hosted: false`) and stay unwired; `space.run_draft` only records
  and is superseded in the UI by the real scheduler arming.

### Fixed

- The v5.6.0 sidebar was missing the RUNTIME nav group (a lost edit),
  so the runtimes view was reachable only via `#/runtimes`. The
  «موتورها» sidebar entry is restored, and the nav now reads
  agent / memory / spaces / tools / runtime / channels.

### Tests

- Browser-honest spaces-view tests + bridge guards for the ten new
  helpers; 99 frontend tests total (was 93); Python suite unchanged.

## [5.6.0] - 2026-09-24

### Added — the runtimes matrix, batch 5 (real engines only)

- **موتورها (Runtimes).** A new RUNTIME view wired to the real provider
  hubs service — nine new `providerhubs.*` bridge helpers:
  - the active route (`hosted → aval → ollama → byok → echo`) as resolved
    deterministically and offline by the router, with the full priority
    chain and the Persian routing sentence;
  - the six local runtimes (Ollama, vLLM, SGLang, llama.cpp, LM Studio,
    generic) with honest detection/health chips, bounded connection
    probes (latency comes back; secrets are never sent), real model
    listings from each endpoint, and a persisted per-runtime model
    selection;
  - the optional tool gateway: master and per-tool toggles with the
    keychain status — tokens stay in the OS keychain and are refused
    over RPC by design;
  - the provider catalog (local + cloud) with live search.
- **Zero-simulation verdicts, recorded:** the evals engine defaults to a
  mock agent runner (`_default_mock_runner`) and stays unwired without
  a real runner; `space.ask` and `liveloop.role_turn` return templated
  local briefings and stay unwired; the workroom is real but thin
  (drafts are never sent by design); GWS is real (owner-authorized
  read-only Gmail/Calendar/Drive) but needs Google OAuth credentials
  and `DREAM_ALLOW_NETWORK` — deferred to a later phase with its
  prerequisites stated. `space.*` itself (durable spaces, instruction
  docs with injection scanning, cron-parsed automation drafts) and
  `liveloop.arm_draft` (arming approved drafts onto the real scheduler)
  are real and are candidates for the next batch.

### Tests

- Browser-honest runtimes-view tests + bridge guards for the nine new
  helpers; 92 frontend tests total (was 87); Python suite unchanged.

## [5.5.0] - 2026-09-23

### Added — thinking workbenches, batch 4 (real engines only)

- **تفکر (Thinking).** A new AGENT view with two real workbenches:
  - «درخت استدلال»: a user-driven Tree-of-Thoughts — you write the
    candidate thoughts, the core keeps the tree (plan/expand/critique/
    MCTS-step/prune/synthesize) and scores nodes with an honestly
    labelled RULE-BASED evaluator (length/coherence/depth — not an
    LLM); the winning path is synthesized with a confidence score.
  - «مدل ذهنی»: a real dialectic belief graph — register beliefs with
    confidence, detect tensions with the rule-based opposite-pairs
    matcher, and reconcile contradictions with YOUR nuanced statement;
    keyword query and full snapshot included.
- **Zero-simulation verdicts, recorded:** the swarm engine (task results
  are string templates, consensus is `simulate_mock_deliberation`) and
  the templated 3-agent `dialectic.debate_turn` stay unwired by design.

### Tests

- Browser-honest thinking-view tests + bridge guards for all twelve new
  helpers; 87 frontend tests total (was 81); Python suite unchanged.

## [5.4.0] - 2026-09-23

### Added — the real browser, wired end to end

- **مرورگر (Browser) tab in Web.** The real Playwright/CDP
  `BrowserController` exposed through twelve new `webbrowser.*` bridge
  methods — the legacy mock `browser.*` engine stays unwired by design.
  Attach to your own Chrome (CDP, port 9222 — sessions and logins
  preserved) or launch a fresh isolated Chrome; navigate, click, type,
  re-extract content, and take full-page screenshots.
- **SEC-03 in the UI.** Every navigation raises a single-use approval
  card (15-minute TTL), the per-session quota (20 navigations) and the
  fail-closed blocklist state are surfaced live, and approvals are
  issued only by you — no bypass exists.
- New optional extra for the sidecar: `pip install ".[browser]"`
  (playwright). The full Windows installer bundles it; without it the
  UI answers honestly with an install hint.
- Tests: 18 new Python bridge tests (honest availability, validation,
  approval-gated navigation mapping), browser-honest web-tab tests and
  bridge guards; 82 frontend tests total (was 77).

## [5.3.0] - 2026-09-23

### Added — wiring the core to the UI, batch 2 (real engines only)

- **وب (Web).** Human-in-the-loop web reading on the real `browse.*`
  bridge: propose a URL, approve it yourself, and only then does the
  core fetch it — SSRF-guarded, prompt-injection-scanned, excerpts and
  followable links, every step evidenced. No YOLO, no auto-fetch.
  Note: the legacy `browser.*` extension methods drive a mock engine
  (fake pages for every backend); per the zero-simulation rule they
  stay unwired until the real Playwright/CDP `BrowserController` is
  exposed through the bridge.
- **کد (Code).** Real Python execution in the core sandbox
  (`sandbox.run_code`): stateful namespace across runs, captured
  stdout/stderr, generated artifacts, live status, and session reset —
  with the executor's security blocklist stated in the UI.
- Navigation: AGENT now lists گفتگو، پژوهش، وب; TOOLS adds کد.

### Tests

- Browser-honest view tests for web + code, bridge guard tests for all
  nine new helpers; 76 frontend tests total (was 70); Python suite
  unchanged (4236).

## [5.2.0] - 2026-09-23

### Added — wiring the core to the UI, batch 1

- **فایل‌ها (Files).** A new tools view wired to the real `workspace.*`
  bridge methods: register a folder through the native dialog
  (`workspace.roots_register` — an explicit user action, nothing is ever
  scanned silently), browse it with a breadcrumb (`workspace.files_list`,
  bounded and symlink-safe), and preview file contents
  (`workspace.files_preview`, with an honest truncated flag and a clear
  "no text preview" state for binaries).
- **بینایی (Vision).** The v4 screen-OCR studio, rebuilt on v5: one real
  action captures the screen (Windows GDI via `vision.capture_screen`),
  extracts Persian text with the core OCR engine, and deletes the
  screenshot immediately — the privacy promise (P-14: screen pixels
  never persist) is stated in the UI. Results export to a Persian PDF
  via the existing report engine.
- Navigation: TOOLS now lists سند، داده، صدا، بینایی، فایل‌ها.

### Remaining core domains (next batches)

- Browser automation (10 methods), multi-agent swarm (9), reasoning /
  dialectic (17), sandboxed code execution (7), duplex live loop,
  provider hubs, remote gateway, evals — all present in the core, not
  yet wired to the UI.

## [5.1.1] - 2026-09-23

### Fixed

- **The ghost panel in the middle of every view.** The evidence drawer's
  closed-state CSS transforms were swapped between LTR and RTL: in the
  RTL app the "closed" drawer rested 400px INSIDE the viewport — an
  empty dead panel floating over the middle of every section, blocking
  clicks, impossible to dismiss, and reappearing parked mid-screen after
  pressing its close button. The drawer now hides fully off-screen
  (positive physical X in LTR, negative in RTL) and is additionally
  `visibility: hidden` while closed. Regression-tested in
  `shell/drawer.test.js`.
- **The drawer never opens itself anymore.** Evidence is strictly
  on-demand: document, voice, and research results now carry a
  «شواهد» button instead of popping the drawer open after an operation.
- **The chat tools menu started visible** on entering the chat view; it
  now starts hidden like every other popover.

## [5.1.0] - 2026-09-23

### Added

- **Real speech — Dream can talk now.** Text-to-speech with two honest
  engines, wired end to end through the bridge (`tts.engines`,
  `tts.voices`, `tts.synthesize`). The legacy sine-wave "synthesizer" in
  `dream/speech/engine.py` stays unwired by design; nothing simulated
  ships.
- **Online neural engine (edge-tts).** Microsoft neural voices — Farid
  (male) and Dilara (female), `fa-IR` — free, no API key, needs internet.
  Verified end to end: a sentence of Persian becomes a real MP3 in ~2s.
- **Offline engine (Piper).** Fully local VITS voices from the pinned
  `rhasspy/piper-voices` revision — five Persian medium voices (Reza,
  Amir, Ganji, Ganji-Adabi, Gyro). The bundled voice is pre-downloaded by
  the full installer; other voices download on first use (pinned
  revision, atomic download). Verified: ~10x realtime synthesis on CPU,
  real WAV output.
- **Voice studio, both directions.** The voice view now has two tabs:
  «گفتار به متن» (unchanged faster-whisper flow) and «متن به گفتار» —
  engine and voice pickers with honest availability badges, speed
  control, an inline player, and per-synthesis evidence (engine, voice,
  latency, bytes, file path).
- **Chat read-aloud.** Every agent reply has a «گفتن» button that speaks
  it with the configured engine; one voice at a time, honest errors in
  the chat log.
- **Speech settings.** A new settings section picks the default engine,
  voice, and speed, with live availability read from the real core.
- **Installer.** The full Windows installer additionally bundles the
  `tts` extra and the pinned offline Persian Piper voice (~63 MB) next to
  the Whisper model, so the full install speaks fully offline; its
  completeness check now requires both. New optional dependency extra:
  `pip install ".[tts]"`.
- **CSP.** `media-src 'self' asset: http://asset.localhost data: blob:`
  for in-app audio playback.

### Tests

- Python: 27 new bridge/engine tests (validation, honest unavailability,
  routing with faked engines, WAV container, text normalisation,
  data-URI helper) — engine backends faked so no test needs the network.
- Frontend: voice-view tests (tabs, honest browser-preview notice, no
  audio element without a real result), tts bridge-guard tests, and
  installer pin tests (bundle-sidecar).

## [5.0.1] - 2026-09-23

### Fixed

- **Window controls for the frameless window.** 5.0.0 shipped the custom
  chrome without minimize / maximize / close buttons. The topbar is now the
  titlebar: it is draggable (`data-tauri-drag-region`) and carries caption
  buttons — mirrored to the left corner per RTL convention — that call the
  same audited Rust window commands the shell has always exposed
  (`minimize_window`, `toggle_maximize`, `close_window`). Buttons are hidden
  in browser previews, where there is no window to control.

## [5.0.0] - 2026-09-22

The workbench release: the desktop UI is rebuilt from scratch as a
framework-free ES-module app wired to the real Python core.

### Added

- **New agent workbench UI (HTML/CSS/JS, no framework).** Grouped navigation
  (agent / memory / tools / channels), first-run wizard with an honest core
  check, dark "Atelier" luxury theme (warm black + champagne gold) with an
  ivory light theme, and an evidence drawer: every output can show the chain
  that produced it.
- **Real chat (BYOK).** The conversation talks directly to the user's model —
  local Ollama or any OpenAI-compatible endpoint — with a typing indicator,
  12-turn context, and per-reply evidence (model, latency, memory state).
  Every turn is recorded into the agent's episodic memory when the core is
  available. The Python core deliberately exposes no LLM-chat RPC (gateway
  credentials never travel over the bridge).
- **Wired tools.** Document (OCR: general/invoice/receipt/id_card, fields
  table, Persian PDF report), Data (dataqa sessions, grounded answers with
  evidence tables and the analysis code chain), Voice (real transcription
  with an honest engine badge + PDF), Telegram (report bot start/stop with
  live status, engine, and event log), Memory (L0..L3 tier stats and
  timeline search), and Research (create → plan → explicit approval →
  report, human-in-the-loop by design).
- **New quality gates.** 49 frontend unit tests (DOM helpers, store, model
  client, bridge guards) plus a CI-able accessibility gate: WCAG contrast
  ratios computed from the real design tokens, RTL/fa document structure,
  and aria-hidden icon checks. The performance gate now measures a real
  JSDOM cold start of the built bundle (~54 KB of JS, cold start ~50 ms).

### Removed

- **The legacy React application** (routes, stores, echo/simulated bridge
  layers, 130 test files, i18n, Tailwind, Radix, Ladle) — roughly 250 npm
  packages and ~239 KB of React chunks replaced by ~54 KB of vanilla JS.
  The simulated `echo-*` layers are gone by design: every value the UI
  shows now comes from the real core or is labelled as unavailable.

### Known notes

- Browser previews show honest "unavailable" states — the Python core only
  runs inside the installed desktop app.
- The full Windows installer (~200 MB) bundles faster-whisper + the `base`
  model for fully offline speech-to-text; the standard installer stays lean
  (~22 MB).

## [4.2.0] - 2026-09-21

The offline release: a second Windows installer that carries real
speech-to-text — faster-whisper and the `base` model — with no `pip install`
and no internet required.

### Added

- **Full Windows installer (`*_full_x64-setup.exe`).** Same app as the
  standard `-setup.exe`, plus the `stt` extra (faster-whisper, CPU/int8) and
  the pinned `base` Whisper model (~148 MB) bundled next to the embedded
  CPython sidecar. Voice notes in the Telegram bot and the `stt.transcribe`
  bridge run fully offline out of the box.
- **Bundled-model resolution.** `WhisperTranscriber` now prefers a local model
  directory (`DREAM_WHISPER_MODELS_DIR`, or `<python>/models/` in the sidecar)
  before falling back to a Hugging Face download; other sizes (tiny/small/…)
  still download on first use when online.
- The release workflow builds and attaches both installers with per-file
  SHA-256 checksums, and `workflow_dispatch` accepts a `build_full` input to
  exercise the full build without cutting a release.

### Known notes

- The full installer is roughly 200 MB (the standard one is ~22 MB); both are
  attached to the same release — pick whichever fits.
- Linux installers are unchanged (UI shell; install Dream from the repository
  with `pip install -e ".[stt]"` for real STT).

## [4.1.0] - 2026-09-21

The "real pipeline" release: every studio in the desktop app now talks to the
Python core, and the whole chain — screen, document, voice, Telegram — ends in
a properly shaped Persian PDF.

### Added

- **Business Data Studio.** Natural-language Q&A over organisational data
  with grounded evidence tables and KPI cards (`dataqa.ask` over
  `data.load_data` datasets; CSV/JSON/SQLite), plus real CSV ingestion in the
  UI.
- **Document OCR.** `ocr.extract` bridge with Persian text cleaning,
  block/table detection, and invoice key-value fields; a real workspace file
  browser for the vision studio; and real screen-capture OCR via
  `vision.capture_screen` (Windows GDI, screenshot deleted immediately).
- **Persian PDF report engine.** `pdf.export_report` renders A4 Persian
  reports with real HarfBuzz shaping and the embedded Vazirmatn font (OFL) —
  joined letterforms, RTL tables, KPI blocks, and per-page footers. New
  runtime dependencies `fpdf2` and `uharfbuzz`, bundled in the Windows
  installer. Print-safe export (print dialog → Save as PDF) from the studios.
- **Telegram report bot.** Long-polling bot where photo → Persian OCR and
  text → structured report both return a Persian PDF in the same chat;
  `reportbot.start` / `reportbot.stop` / `reportbot.status` bridge methods
  with token redaction, a bounded event log, and an optional relay API base
  URL for filtered networks. Voice messages use real transcription when the
  optional `stt` extra is installed, otherwise the clearly-labelled built-in
  engine.
- **Real speech-to-text (optional).** `pip install ".[stt]"` adds
  faster-whisper (CPU, int8) behind the `stt.transcribe` bridge; the report
  bot prefers it when present.

### Fixed

- **Frontend lint.** All 13 remaining ESLint warnings resolved — the project
  now lints at zero warnings.

### Known notes

- The Windows installer bundles base dependencies only, so voice
  transcription in installed builds uses the built-in engine; install
  `pip install ".[stt]"` next to the installer for real faster-whisper
  transcription.
- The Windows installer is unsigned — SmartScreen may warn (unchanged).
- Test suites: 4,204 Python tests and 882 frontend tests, green across nine
  consecutive deployments.

## [4.0.0] - 2026-09-15

Golden master: 52 verified subsystems and the desktop shell with the embedded
CPython sidecar. Details in the
[v4.0.0 release](https://github.com/AliNaderiii/Dream/releases/tag/v4.0.0).

## [0.4.6] - 2026-08-27

Non-streaming chat completions so local OpenAI-compatible gateways that
default to SSE work with the desktop pane.

### Fixed

- **Chat completions.** Requests send `stream: false` and expect one JSON
  object with `choices[0].message`. Streaming `chunk` bodies no longer
  surface as an unexpected error.

### Known notes

- Bridge protocol version stays `0.1.0`.
- The Windows installer is unsigned — SmartScreen warns.
- YOLO, signed-in Chrome, and computer-use of the Windows desktop stay off.

## [0.4.5] - 2026-08-27

Named Space bots, Allow once, forest accent, skill drafts, bot groups,
HITL page reads, and a company workroom on top of 0.4.4.

### Added

- **Space bots (B1).** Named roster with geometric avatars, isolated memory,
  and no YOLO.
- **Allow once (B2).** Chat approval is Allow once or Deny. Always Allow is
  refused.
- **Forest accent (B3).** Default desktop accent is forest.
- **Experience drafts (B4).** Capture a skill draft from a bot turn. Nothing
  is written until you approve.
- **Bot groups (B5).** Two to six Space bots, hard cap of three rounds.
- **Browse HITL (B6).** Queue a public http(s) URL. Fetch only after Allow
  once. Localhost, credentials, Chrome profiles, and computer-use are refused.
- **Workroom (C1).** Company room with up to eight seats. VIP is a label.
  Drafts never send.

### Known notes

- Live hosted role turns are not wired; use the chat pane.
- Live gold prices are not Instant Answer.
- Bridge protocol version stays `0.1.0`.
- The Windows installer is unsigned — SmartScreen warns.
- WebView2 may download during install.
- YOLO, signed-in Chrome, and computer-use of the Windows desktop stay off.

## [0.4.4] - 2026-08-27

Honest web search fallback and read-only Google Workspace OAuth on top of 0.4.3.

### Added

- **Google Workspace (P12).** Owner OAuth for read-only Gmail, Calendar, and
  Drive. Tokens stay in the OS keychain. Sending mail is refused. Loopback
  redirect only; WAN hosts are allow-listed.

### Fixed

- **Search honesty.** An empty DuckDuckGo Instant Answer is no longer reported
  as a network outage. Wikipedia public opensearch is used when Instant Answer
  is empty. `DREAM_ALLOW_NETWORK` is still required.

### Known notes

- Live hosted role turns are not wired; use the chat pane.
- Live gold prices are not Instant Answer; use a public URL with `read_page`
  or a later browser cut.
- Bridge protocol version stays `0.1.0`.
- The Windows installer is unsigned — SmartScreen warns.
- WebView2 may download during install.

## [0.4.3] - 2026-08-26

Space, loopback remote gateway, and Live loops on top of the 0.4.2 sidecar hotfix.

### Added

- **Space (P10).** Specialized roles, instruction docs, and approval drafts.
  Web URLs are refused while `DREAM_ALLOW_NETWORK` is off.
- **Remote gateway (P9).** `dream-serve` binds `127.0.0.1:8765` by default.
  WAN / `0.0.0.0` is refused. Bearer only; query-string tokens are refused.
- **Live loops (P11).** Arm approved, non-dangerous Space drafts onto the
  scheduler with per-fire approval. Status bar names when Settings is Echo
  while a chat pane uses another provider.

### Known notes

- Live hosted role turns are not wired in this cut; use the chat pane.
- `search_web` / `read_page` stay off until `DREAM_ALLOW_NETWORK=true`.
- Bridge protocol version stays `0.1.0`.
- The Windows installer is unsigned — SmartScreen warns.
- WebView2 may download during install.
- Aval HTTP 429 is an account quota, not this cut.

## [0.4.2] - 2026-08-26

Windows sidecar daily-use hotfix on top of 0.4.1. Product version stays unified.

### Fixed

- **Windows sidecar UTF-8.** `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` are
  set on every sidecar spawn, including when `DREAM_SIDECAR_PYTHON` overrides
  discovery. Persian chat no longer raises `charmap`.
- **Writable data root.** The sidecar cwd is `%LOCALAPPDATA%\\Dream` (or
  `DREAM_HOME` / XDG), so relative `data/` files are never created under
  `Program Files`. Start Menu launches handshake without a custom shortcut.
- **`get_datetime` / Asia/Tehran.** `tzdata` is a runtime dependency and is
  smoked in the Windows sidecar bundle. Missing IANA data falls back to the
  host offset instead of raising `ZoneInfoNotFoundError`.
- **Warm-route CI budget.** Shared runners occasionally exceed the 300 ms
  warm-route assertion; the unit budget is 450 ms.

### Known notes

- The Windows installer is unsigned — SmartScreen warns.
- WebView2 may download during install.
- Aval / OpenRouter HTTP 429 is an account quota, not this patch.
- P5 parsers, P6 call sites, and P7 wiring remain documented residuals.

## [0.4.1] - 2026-08-26

Windows daily-use patch on top of 0.4.0. Product version stays unified.

### Fixed

- **Bundled sidecar discovery.** Stock NSIS installs find
  `{install}/resources/python/python.exe` next to `dream-desktop.exe` without
  setting `DREAM_SIDECAR_PYTHON`. Missed candidates are logged.
- **Single instance and tray teardown.** A second launch focuses the running
  window. Close (default) destroys the tray icon, kills the sidecar, and exits
  so icons do not stack in the notification area. Duplicate config-level tray
  builder removed. Settings `closeToTray` default matches Rust (`false`).
- **Layout containment.** Settings language row and disconnected banners wrap
  inside their own boxes instead of overlapping chips or actions.
- **Activity rail drawer.** Collapsed / expanded / hover-peek with a pin
  control; labels from existing `nav.*` keys; RTL logical layout.

### Known notes

- The Windows installer is unsigned — SmartScreen warns.
- WebView2 may download during install.
- Aval / OpenRouter HTTP 429 is an account quota, not this patch.
- P5 parsers, P6 call sites, and P7 wiring remain documented residuals.



First product cut that includes the P0–P8 local-first workbench on `main`
(research, data QA, workspace, provider hubs, security primitives,
reliability toolkit, and design-system tokens). The Python package and the
desktop shell are unified at **0.4.0** (they had drifted to 0.2.0 / 0.3.2).

### Added

- **Extension seam (P0).** Auto-discovered `dream/bridge/methods_*.py` plus
  the desktop `route-registry` so a new domain registers without editing the
  giant methods table. Route collisions are refused.
- **Deep research engine (P1) and workbench (P2).** Eleven `research.*`
  methods (`create` through `export`) and a bilingual workbench. Statuses
  include `IDLE`, `PLANNING`, `APPROVAL_PENDING`, `IN_PROGRESS`, `PROOFREAD`,
  `COMPILING`, `COMPLETE`, `FAILED`, `CANCELLED`. The UI must consume stream
  chunks `{event, cursor}` plus `research.status` — `Stream.final` is stale
  when `follow=true`. XSS: `stripHtmlTags` then `escapeHtml`.
- **Data QA (P3).** Eight `dataqa.*` handlers. The worker does not evaluate
  model-authored code.
- **Workspace and agent modes (P4).** In-place folder link (never copies);
  `..` and symlink paths refused; `/plan` then continue; `/goal` is honest
  about unmet work; `/stop` uses a cancellation token. Dangerous `!shell`
  never reaches subprocess, even with `approved=True`.
- **Provider hubs (P5).** Catalog, runtimes, health, models, route, gateway
  toggle, and parsers as a library. Tool-call parsers are **not** wired into
  the live chat loop.
- **Agentic security primitives (P6).** Code-exec policy, plan policy,
  authenticity checks, provider-gateway helpers, and an extended
  `tools/security_audit.py`. The host never executes model code; without
  Docker the path refuses. Call sites are **not** yet wired into
  research / dataqa / workspace.
- **Reliability toolkit (P7).** Cancellation, deadlines, and budgets;
  additive stream `delay` clamp and opt-in `stall_timeout`. Not yet wired
  into agent / research / reminders.
- **Design-system tokens (P8).** Focus ring, table, progress, and
  empty-state primitives on top of the existing theme.
- **Per-user permissions for linked identities (SEC Stage E).** Each
  linked chat identity carries a scope — chat only, safe tools, guarded
  tools, or full admin — enforced on every turn and manageable over the
  bridge (`gateway.set_user_scope`). Repeated dangerous-tool attempts are
  throttled per user, and gateway token checks are now constant-time.
- **Stronger isolation.** Scheduled (cron) dreams run without dangerous
  tools at all; subagent and council grant chains are pinned to minimal
  grants; unknown session ids are refused before dispatch; schedule
  storage is immune to traversal and injection shapes.
- **Hostile text is scanned before it reaches the model (SEC Stage D).**
  Files, web pages, MCP payloads, skill bodies, /learn sources, search
  snippets, and recalled memories pass an injection scanner: hidden
  Unicode is stripped, instruction-override patterns in English and
  Persian and fake tool-call shapes raise a visible bilingual warning,
  and the untouched original is quarantined for inspection.
- **Hardened transport boundary.** Every bridge method rejects malformed
  parameters before dispatch (audited by a property sweep and seeded
  fuzzing); gateway responses carry a strict CSP/frame-denial/nosniff
  header policy with HSTS over TLS; gateway tokens gain per-token rate
  limits and audited rotation.
- **Legacy window quarantined.** The old Tk desktop (`desktop.py`) no
  longer starts without `DREAM_ENABLE_LEGACY_DESKTOP=1`; the Tauri
  desktop is the supported surface.
- **MCP servers no longer inherit your environment (SEC Stage C).** MCP
  children receive a credential-free allowlist plus only the variables you
  explicitly map; network-transport servers default to egress-off and
  refuse to connect until you allow them; their tool descriptions are
  sanitized (hidden Unicode stripped, length capped) before the model ever
  sees them.
- **File-write safety floor and a deletion quarantine.** Note/skill writes
  now refuse sensitive paths (credentials, `.ssh`, system dirs, Dream's own
  stores) on every platform, including symlink, 8.3, and UNC tricks.
  Deleting a skill moves it into a size-capped quarantine you can restore —
  nothing is destroyed outright.
- **Secrets scrubbed from the trail.** Key-shaped values are redacted out
  of the message log, provenance records, bridge errors, and log lines.
- **Security floor for destructive commands (SEC Stage B).** A hardline,
  always-on blocklist now refuses filesystem-root wipes, disk formats, raw
  block-device writes, fork bombs, remote-piped shell installs, registry
  hive deletes, and their PowerShell/Windows variants — including quoted,
  case-shifted, variable-expanded, path-normalized, and homoglyph-obfuscated
  forms — before any approval happens; no mode or flag can override it.
- **Approval engine v2.** Dangerous shell commands gain an auxiliary risk
  assessor (strict schema, hard timeout, default-deny), `smart | manual |
  off` modes (off is an explicit opt-in with a persistent red banner and a
  status-bar indicator), deny-by-default cron/single-query contexts, and a
  durable, append-only approval history under `DREAM_APPROVAL_DB`.

- Conversation context accounting, deterministic offline compaction, `/compress`,
  and an optional once-per-session durable-memory nudge.
- Bridge endpoints for dual bounded memory stores, session-search status/query,
  explicit compaction, and nudge status.
- **Dream remembers you.** The memory explorer gains a bounded-stores tab: two
  fixed-size stores (agent notes and your profile) with a live
  `[67% — 1,474/2,200 chars]` capacity meter, an approval on every edit, and a
  notice that the session prompt was built from a snapshot frozen at session
  start.
- **Dream learns skills.** A learning workspace beside the skills manager:
  run/failure counts per skill, version history with a side-by-side diff,
  reference notes under `references/`, an approval inbox for proposed changes,
  and a `/learn` panel that turns a file, folder, the conversation or pasted
  notes into a skill — and refuses a web source up front while network tools
  are off.
- **Dream searches years of conversation.** Press Ctrl/⌘+P to search every
  past session. Persian search works regardless of spelling — type a word
  with Arabic letters and Dream finds the Farsi-spelled transcript, with the
  match highlighted in the spelling you used. A damaged index says so and
  offers a rebuild.
- **Dream never overflows its context.** Every compaction leaves a visible row
  in the transcript: before/after cost, share reclaimed, how many messages
  were preserved verbatim and what the summary kept. `/compress` works on
  demand, and a gentle memory nudge appears only when enabled, due, and not
  yet sent.

### Changed

- Version unified to **0.4.0** across `dream/__init__.py`, `pyproject.toml`,
  `apps/desktop/package.json`, `apps/desktop/src-tauri/Cargo.toml`, and
  `apps/desktop/src-tauri/tauri.conf.json`.
- GitHub Release notes now match the Windows installer: NSIS embeds
  CPython 3.12.10 plus a non-editable Dream kernel via `bundle-sidecar.mjs`.
  Linux installers still need system Python.

### Fixed

- Five bridge handlers that serialised frozen `slots=True` dataclasses through
  `__dict__` (which those dataclasses do not expose) — `search.sessions.query`,
  `skills.versions`, `skills.use_log`, `skills.propose` and the new
  `skills.learn_classify` — now serialise through `asdict`, pinned by a
  JSON-serialisability regression over non-empty rows of every MEM family.

### Known notes

- The Windows installer is **unsigned** — SmartScreen is expected to warn
  (`More info → Run anyway`). No Authenticode signature yet.
- WebView2 may be downloaded during installation if it is missing.
- Linux/macOS still use the system Python; the bundled runtime is Windows-only.
- Honest residuals, not claimed as live: P5 parsers in the chat loop; P6
  call sites in research/dataqa/workspace; P7 wiring into agent/research/
  reminders; P1 web-search-in-loop and sequential sections.

## [0.3.2] - 2026-08-21

### Fixed

- **S15 — `G is not a function` production crash fixed.** The `DashboardRoute`
  and `ChatRoute` both crashed immediately after launching the installed
  `Dream_0.3.1_x64-setup.exe`. The `FirstRunCard` component imported
  `Route as RouteIcon` from lucide-react, which could collide with
  react-router's `Route` after minification in the same non-lazy chunk.
  Replaced with `Navigation` and added a `SafeIcon` wrapper that returns
  `null` for non-function values, preventing the error in production builds.
- **S15 — Tray icon leak on Windows fixed.** Each launch of Dream from the
  Start menu was creating another tray icon under "Show hidden icons". The
  root causes were (1) multiple processes without single-instance enforcement
  and (2) the default close behavior hiding to tray. Fixed by adding
  `tauri-plugin-single-instance` so a second launch focuses the existing
  window, and changed the default `close_to_tray` to `false` so X quits the
  app cleanly.

### Changed

- **S15 — Echo fallback when sidecar is offline.** When the Python sidecar
  stays disconnected (never becomes `ready`), the UI previously blocked on
  the Tauri transport. The bridge client now automatically falls back to the
  `EchoBridgeTransport` when the sidecar emits `disconnected`, so the
  Dashboard, Chat, Memory and Skills screens render and function using
  in-memory echo data. When the sidecar recovers to `ready`, the client
  switches back automatically.
- Desktop version bumped to **0.3.2** (`apps/desktop/package.json`,
  `apps/desktop/src-tauri/tauri.conf.json`, `apps/desktop/src-tauri/Cargo.toml`).

## [0.3.1] - 2026-08-20

The first Windows installer a Release-only user can download, install, and run
end-to-end — no separate `pip install` required.

### Added

- **Windows NSIS embeds a CPython runtime + the Dream kernel.** At `tauri build`
  time a new `apps/desktop/scripts/bundle-sidecar.mjs` downloads the pinned
  CPython 3.12.10 Windows embeddable amd64 package from python.org (SHA-256
  verified), bootstraps pip, and installs the Dream package **non-editable**
  into `src-tauri/resources/python/`, which the NSIS bundle ships next to the
  app. The supervisor now prefers this bundled `python/python.exe` over PATH
  (`python`/`py`/`python3`), so a Release download can start the sidecar with
  no local Python.
- **Bundled interpreter is isolated from user site-packages.** Spawning the
  bundled CPython sets `PYTHONNOUSERSITE=1` and `PYTHONUTF8=1` so a host
  `pip install --user dream` cannot shadow the embedded kernel.

### Fixed

- **S13 crash fix ships in this installer.** The `Cannot read properties of
  undefined (reading 'dot')` crash and the Windows console flashing are fixed
  in the binaries this release installs (S13 is on `main`; the broken
  `v0.3.0` build is superseded).
- **Windows bundle script locates the embeddable `._pth` by directory
  listing.** The python.org 3.12.10 embeddable ships `python312._pth`
  (major+minor only), so `bundle-sidecar.mjs` now matches
  `/^python3\d+\._pth$/i` against the extracted files instead of deriving
  `python31210._pth` from the full version, which broke the Release job.
- **Windows bundle bootstraps `setuptools` and `wheel` after pip** so the non-isolated package install can import `setuptools.build_meta`.

### Changed

- Desktop version bumped to **0.3.1** (`apps/desktop/package.json`,
  `apps/desktop/src-tauri/tauri.conf.json`, `apps/desktop/src-tauri/Cargo.toml`).
  The Python package version is unchanged.

### Known notes

- The Windows installer is **unsigned** — SmartScreen is expected to warn
  (`More info → Run anyway`). No Authenticode signature yet.
- The WebView2 bootstrapper is unchanged and may be downloaded during install.
- Linux/macOS still use the system Python; the bundled runtime is Windows-only.

## [0.2.0] - 2026-08-17

Prompt P-11 — Internationalisation, Documentation, Security Audit & Release.

### Added

- **Internationalisation** — the desktop shell now ships eight languages
  (English, Persian, Simplified Chinese, Japanese, Spanish, German, French,
  Korean) via `react-i18next`, with a flag + native-name picker in Settings and
  the status bar, auto-detection from `navigator.language`, and a fallback to
  the key string (never a raw English value). Persian is the only
  right-to-left language and flips the whole shell via logical CSS properties.
  Locale-aware number/currency/date formatting uses the `Intl` API. Every route
  and shell component is migrated to `t()`/`useTranslation()`.
- **Developer tooling** — `apps/desktop/scripts/generate-locales.mjs`, the
  single source of truth for locale files (identical key trees across all
  eight languages guarantee 100% coverage).
- **Documentation** — `docs/user/` (quick-start, full 12-chapter manual, FAQ,
  troubleshooting, keyboard shortcuts) and `docs/dev/` (architecture with a
  Mermaid diagram, contributing guide, how-to guides for adding tools,
  providers, MCP connectors and platform adapters, and an API reference).
- **Security audit** — `docs/security/audit-report.md` plus a
  `tests/test_security_*.py` suite covering tool-risk enforcement, workspace
  confinement, gateway token scope, and a tracked-file credential scan.
- **Performance** — code-split routes (`React.lazy` + `Suspense`),
  `docs/performance-budget.md`, and a `.github/workflows/perf.yml` CI smoke
  that fails on bundle-size/cold-start regressions beyond 10%.
- **Release** — SHA-256 checksum generation in the release workflow.

### Changed

- Version bumped to **0.2.0** (`dream/__init__.py`, `pyproject.toml`,
  `apps/desktop/package.json`, `Cargo.toml`, `tauri.conf.json`).

### Fixed

- Two Bandit high findings resolved: the WebSocket handshake SHA-1 is now
  marked `usedforsecurity=False` (RFC 6455-mandated, not a security primitive),
  and the approval-gated `run_shell` tool documents its intentional
  `shell=True` with `# nosec B602`.

### Security

- `ruff` clean; `bandit` 0 critical / 0 high; `npm audit` 0 vulnerabilities;
  project Python dependencies free of known CVEs. See
  `docs/security/audit-report.md`.

## [Unreleased]

### Added

- **Desktop UI — complete operational workspaces.** Sessions, memory, skills,
  subagents, and scheduler now share truthful empty, structural loading,
  actionable retry, offline/reconnect, timeout, and cancellation behavior.
  Long sessions, chat transcripts, memory/skills rows, scheduler history, and
  subagent logs stay bounded after 100 items; chat keeps the newest and active
  streaming rows visible without mounting the whole transcript.
- **Desktop UI — accessible appearance system.** Light, Warm, and Dark themes
  support four accents, comfortable/dense modes, persistent 80–150% zoom,
  English LTR and Persian RTL, and an OS-aware plus in-app reduced-motion mode.
  Light muted text now measures 5.47:1 on canvas in every accent. Persian has
  zero English fallbacks for the completed UI stages.
- **Desktop UI — performance and accessibility gates.** Route, locale, pane,
  and vendor splitting keep every production chunk below 500kB. The desktop
  harness emits a JSON report guarding command-palette open, route changes,
  streaming long tasks, 500-message memory growth, and unhandled rejections;
  an owner-applied workflow patch adds CI upload, while axe coverage runs on
  all five operational workspaces.
- **S00 — Commercial kernel (`dream/commerce.py`).** Seven plans — `local`
  (unlimited, free, no ledger file), `guest` (free, 20 turns/day), `daily`,
  `individual_monthly`, `individual_yearly`, `team`, and `company` — all in
  IRR. Only free plans carry a numeric price (0); paid plans carry `null`
  with the honest note `TBD after cost measurement`. Usage is a JSON ledger
  (`DREAM_LEDGER`, default `data/dream-ledger.json`) written atomically;
  `Dream.run` consumes one turn per message only when a ledger is attached
  (`DREAM_PLAN` not `local`, or `DREAM_LEDGER` set), and metered plans fail
  closed: an unreadable, non-JSON, or malformed ledger refuses turns with a
  Persian sentence instead of silently granting unlimited usage. The guest
  ledger blocks the 21st turn with a Persian quota sentence. New CLI surface:
  `dream --plan`, `dream --usage`, and the in-session `/plan`, `/usage`
  commands (read-only, phone-allowed).
- **S00 — Model router (`dream/router.py`).** Fixed priority
  hosted → Ollama → BYOK → echo, resolved purely from configuration with no
  network probes. Every route carries an English and a Persian sentence
  stating whether data leaves the machine; `dream --route` and `/route`
  print it.
- **S00 — Product docs and samples.** `docs/PRODUCT.md` (honest product
  story, plans, metering, privacy), `examples/iranian-sales-sample.csv` (a
  hand-made Iranian sales extract with Persian headers) plus
  `examples/README.md`, and a rewritten top-level README describing Dream 0.2
  as a local-first Persian agent with a Tauri desktop shell.
- **S00 — Packaging extras.** `pyproject.toml` now ships `web`
  (`fastapi`, `uvicorn`) and `data` (`nbformat`) optional extras alongside
  the existing `dev` extra.
- `run.bat` and `check.bat` launchers for Windows: `run.bat` activates
  `.venv`, clears `OPENAI_BASE_URL`/`OPENAI_API_KEY`, prompts for the Ollama
  model (`qwen2.5:7b` by default, `qwen2.5:3b` optional), and starts
  `cli.py --backend ollama`; `check.bat` runs `doctor.py --backend ollama`.
  Both pause before closing and use CRLF, pure-ASCII batch syntax.
- After each turn the CLI prints one compact stderr line per tool call —
  `[tool] name(args) -> ok`, `-> error: …`, or `-> blocked: …` with long
  arguments truncated — plus `[memory] stored N fact(s)` when a turn stores
  memories. The `--quiet` flag suppresses these lines.
- `tools/memory_probe.py`, a committed diagnostic: it sends one fixed Persian
  fact-bearing sentence through a real Dream instance against a temporary
  database and prints the tool calls the model emitted, their exact
  arguments, each raw result, the memory count afterwards, and a one-line
  verdict naming the failure mode (`no tool call emitted`, `tool call
  failed`, or `memory stored successfully`). Runnable as
  `python tools/memory_probe.py --backend ollama`; exits 0 on success.

- **S01 — Commerce hardening.** Ledger reads and writes fail closed, writes
  are atomic and durable, concurrent users refresh state before counting, and
  routing consistently prefers local Ollama over BYOK when hosted is absent.
- **S02 — Iranian data workflows.** Persian/Arabic digit and text handling,
  Iranian CSV encoding coverage, and data-science ingestion/profile/cleaning,
  analysis, chart, report, and notebook workflows are available through the
  kernel and desktop workbench.
- **S03 — Telegram.** A long-polling Telegram front end supports local,
  expiring six-digit private-chat pairing, persisted paired chats, command
  parity and policy enforcement. The final live bot/network smoke remains
  owner-run with real credentials.
- **S04 — Desktop bridge and build.** The Tauri UI communicates with the
  Python kernel through a framed JSON-RPC sidecar, the Windows
  `run.bat` onboarding launcher activates `.venv`, clears provider env,
  prompts for the Ollama model and starts `cli.py --backend ollama`, and
  desktop CI/build and release packaging paths are present.
- **S05 — Plans in desktop.** Desktop settings show plan, usage, route and
  privacy information from the same commerce/router kernel used by the CLI;
  no paid IRR amount is invented.
- **S06 — Projects and Jalali scheduler.** Projects group sessions and link
  workspace folders without copying. The scheduler accepts Persian or English
  prose, previews cron, displays Jalali dates, exposes history and run controls,
  and queues approval-gated runs. The desktop TypeScript and production build
  were unblocked.
- **S07 — Conversation UX.** Chat renders streaming-aware tool cards with
  `ok`, `error`, `blocked`, and `pending` states. Dangerous calls open an
  approval dialog for allow once, session allowlist, or deny, and in-flight
  work can be stopped; approval remains fail closed.
- **S09 — Aval AI as the recommended Iranian cloud route.** Aval AI is a
  first-class provider row and a named router route (`aval`) with honest
  leave-the-machine sentences in English and Persian; detection is purely
  from configuration (`AVALAI_API_KEY`, Aval base URLs, or
  `DREAM_BACKEND=aval`/`avalai`) and never probes the network. The desktop
  catalog starts with Aval, and `dream --route` / `/route` print the new
  route.
- **S10 — Opt-in three-role council (`dream/council.py`).** A council is
  exactly three sequential children — proposer, critic, judge — run as one
  `SubAgentManager` pipeline; the judge's result is the winner. It is
  strictly opt-in (the demo and normal spawns never start one), defaults
  every member to the offline `echo` provider, grants only the default tool
  set (no filesystem/shell/network/mail, no approver), and a metered plan
  consumes the three member turns exactly once before spawn — children can
  never double-count. New bridge methods `council.run` / `council.get`, a
  three-column council widget on the desktop Subagents page, and
  `dream --council "topic"` on the CLI. `build_backend` now also accepts
  `aval` / `avalai` as OpenAI-compatible endpoints pointed at
  `api.avalai.ir`.
- **S11 — Iranian first-run + chat council button.** The dashboard
  first-run card adds Aval AI as the recommended hosted path (one account,
  many model families, served from the Iranian cloud at `api.avalai.ir`)
  with a plain leave-the-machine line — the offline echo and Ollama cards
  stay exactly as they were, BYOK remains an optional extra. The chat
  composer gets a compact opt-in Council review control that uses the
  current composer text (or the last user message) and calls `council.run`;
  Send / `conversation.send` never starts a council. After a successful
  run the user is taken to `/subagents` so the existing three-column
  council widget renders the run; a ledger `refusal` is shown inline
  instead of being swallowed. No new model ids, no invented IRR, no kernel
  change.
- **S12 — Windows installer that actually attaches + sidecar finds Python.**
  The desktop sidecar no longer assumes `python3`: when
  `DREAM_SIDECAR_PYTHON` is unset it tries `python`, `py` (the Windows
  launcher), then `python3`, skips interpreters that exit before the
  protocol handshake (Store stubs, wrong Python, missing `dream`), and
  logs an English and Persian explanation when none of them can start.
  `desktop-release.yml` now publishes — not drafts — the GitHub Release for
  every `v*` tag with the unsigned Windows NSIS installer attached (no
  Authenticode secrets required, SmartScreen may warn) and fails the job
  when the release ends up without installers. The desktop shell version
  was bumped to 0.3.0; the `v0.2.0` and `v0.2.1` releases shipped with zero
  assets, so 0.3.0 is the first release intended to carry a Windows NSIS
  built from current main.

### Changed

- Desktop shell version bumped to **0.3.0** (`apps/desktop/package.json`,
  `apps/desktop/src-tauri/tauri.conf.json`); the Python package version is
  unchanged.
- The system prompt no longer spends most of its length teaching the model
  when to call `remember_fact`: the extraction pass writes memory on its own,
  so the prompt now carries a short Persian instruction to *use* recalled
  memories instead — treat them as known and true, use them naturally without
  announcing it, and answer directly from them when they already hold the
  answer. `remember_fact` stays registered and keeps a single-line mention.
- The recalled-memory block markers are Persian, keeping the prompt in one
  language instead of wrapping Persian text in English headers.
- The conversational model call now sends an explicit `temperature` (default
  `0.3`), tunable through `DREAM_TEMPERATURE`; malformed or out-of-range
  values fall back to the default rather than raising. The extraction pass
  samples colder still (fixed `0.1`), so its output stays parseable JSON.

### Fixed

- A store error during the extraction write (for example a locked database)
  is no longer swallowed: `except (ValueError, Exception)` became a narrow
  `ValueError` skip for the unusable-fact case, and anything else is recorded
  on the turn and printed as `[memory] store failed: …`.
- The language rule is now unconditional: always reply in the language of the
  user's most recent message, reply in Persian to Persian input, and never
  switch to a third language.
- The CLI treats a leading backslash as a command prefix, so `\mems`, `\exit`,
  and friends work exactly like their slash forms. Unknown commands suggest
  the closest known command instead of falling through to the model.
- Assistant tool calls are now recorded in chat-completions wire format
  (`type: "function"`, `name`/`arguments` nested under `function`, arguments as
  a JSON string). Conversations previously failed with HTTP 400 on the second
  turn, when the malformed history was replayed to the model.
- Optional annotations are unwrapped when deriving JSON Schema, so
  `list | None` is described as an array rather than a string. `remember_fact`
  now tells the model that `tags` is a list, matching what the code expects.
- Failed model requests report the server's response body, whitespace-collapsed
  and truncated, instead of only `HTTP Error 400: Bad Request`. API keys and
  bearer tokens are redacted from those messages.
- Tool results are unambiguous outside the registry too: `execute()` returns
  `{"status": "ok", "result": …}` on success and
  `{"status": "error", "error": {"type", "message"}}` with a message starting
  `Tool call failed:` on failure, so a model cannot misread a failed call as
  a success and narrate «ذخیره شد» over a store that never happened.
- `remember_fact` normalises instead of rejecting. `kind` is
  lowercased/stripped, obvious synonyms map onto valid kinds
  (fact/info/preference/profile → semantic, event/episode → episodic,
  rule/instruction/howto → procedural), and anything unrecognised falls back
  to semantic; `importance` is clamped into [0, 1], numeric strings are
  accepted, and unreadable values default to 0.5. A sloppy call from a small
  local model now stores the memory under a close-enough kind instead of
  losing it entirely.

- **S13 — Desktop launch must work (hotfix + shell craft).** Fixed the
  `Cannot read properties of undefined (reading 'dot')` crash that appeared
  seconds after launching the installed `Dream_0.3.0_x64-setup.exe`. The Rust
  supervisor emits the `ConnectionState` enum directly as a bare JSON string
  (e.g. `"restarting"`), but the frontend read `payload.state` off it — which
  is `undefined` — and then read `.dot` off `undefined`. The `bridge://state`
  listener now normalises every payload (bare string *or* `{ state: string }`)
  through `normalizeBridgeState`, which fails closed to `"disconnected"` for
  any untrusted/unknown value, and `BridgeStatusIndicator` reads
  `STATE_META[state] ?? STATE_META.disconnected`. The UI union now also carries
  the first-class `restarting` state (Rust's auto-restart), rendered as
  "Reconnecting". Unit tests cover the normaliser and render the indicator with
  `restarting` and with a malformed state without throwing.
- **S13 — Windows sidecar no longer flashes consoles.** The sidecar spawn now
  sets `CREATE_NO_WINDOW` (0x08000000) on Windows and redirects stderr away
  from the console, so the `python`/`py`/`python3` discovery retries (and the
  Windows Store `python` stub) no longer pop a `cmd` window. The console is
  only hidden — the sidecar still runs with piped stdio and the same
  `-u -m dream.bridge` command; spawn diagnostics are still logged via
  `log::warn!`/`log::error!`. A pure, cfg-gated helper
  `sidecar_creation_flags()` (no real process spawned) is unit-tested to assert
  the Windows flag is set and POSIX uses none.
- **S13 — Honest, bilingual "kernel missing" state.** A calm `bridge-banner`
  appears in the app shell when the bridge is disconnected (e.g. the owner has
  no Python kernel), stating in English *and* Persian that the engine is not
  installed or did not start, with the one action Reconnect. It never pretends
  the model is local. Copy lives in the locale tree
  (`errors.bridgeKernelMissing` / `errors.bridgeKernelHelp`) across all eight
  languages via the generator, keeping identical key trees.

## [0.1.0] - 2026-07-31

### Added

- Persian-aware SQLite/FTS5 memory with normalisation, suffix stemming, hybrid
  retrieval, and journal storage.
- Schema-derived tool registry with safe, guarded, and dangerous risk tiers.
- Provider-neutral agent loop with OpenAI-compatible, Ollama, and offline Echo
  backends, memory injection, and approval enforcement.
- Interactive CLI with slash commands, offline demo, and opt-in YOLO mode.
- Offline diagnostics for installation, FTS5, memory, normalisation, registry,
  approval, and optional live model tool-calling verification.
