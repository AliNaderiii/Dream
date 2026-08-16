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

## Phase 3 — Projects, Subagents & Provenance (Prompt P-03)
- [ ] 3.1 Project dashboard; file browser
- [ ] 3.2 Subagent monitor
- [ ] 3.3 Run history / provenance viewer

## Phase 4 — Data Science Workbench (Prompt P-04)
- [ ] 4.1 Data preview grid; cleaning steps
- [ ] 4.2 Chart builder; report preview/export

## Phase 5 — Providers, MCP & Web Gateway (Prompt P-05)
- [ ] 5.1 Provider configuration + connection test
- [ ] 5.2 MCP server configuration
- [ ] 5.3 Web gateway (mobile/tablet responsive) + authentication
