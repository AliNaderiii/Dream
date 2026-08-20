# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
