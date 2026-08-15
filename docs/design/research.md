# Dream — Design Research & Discovery (Gate G1)

Phase 0 · Prompt P-00 · Task 1
Roles: DPM (coordination), UXR (personas & workflows)
Status: **Complete** — reviewed 2026-08-15

---

## 1. Current-state audit: what Dream already is

Source: this repository (`cli.py`, `desktop.py`, `dream/*.py`, `docs/ARCHITECTURE.md`).

### 1.1 Capabilities inventory

| Capability | Where it lives today | Design implication |
| --- | --- | --- |
| Three-kind memory (semantic / episodic / procedural), FTS5 + Persian normalization, scored retrieval (`0.55 relevance + 0.20 recency + 0.15 importance + 0.10 usage`) | `dream/memory.py`, `dream/normalization.py` | Memory explorer must expose **kind**, **importance**, **usage**, **age**, and the composite score — not just text. Search must be visibly normalization-aware (show "matched via normalized form"). |
| Tool registry with risk tiers `safe / guarded / dangerous`; dangerous fails closed without an approver | `dream/tools.py`, `ApprovalPolicy` in `dream/agent.py` | The **approval dialog is a first-class design object**, keyed to risk tier — never a generic confirm(). Tool-call transcript lines (`[tool] name(args) -> ok/error/blocked`) become structured **tool-call cards**. |
| Agent turn loop: journal → retrieve memories → render reminders (Jalali dates) → call backend → approve/execute tools → repeat | `dream/agent.py` | Conversation view needs a **turn anatomy**: retrieved-memory context (collapsible), reminder context, streaming text, tool-call cards, final reply. Provenance viewer maps 1:1 onto `Turn` objects. |
| Reminders with Jalali calendar, repeat rules (days/months) | `dream/reminders.py`, `dream/jalali.py` | Date pickers must support **dual-calendar display** (Jalali + Gregorian). |
| Skills: named, described, stepped; scored against queries; save-claim guard | `dream/skills.py`, `skills/*.txt` (note: Persian filenames exist today) | Skills manager shows name/description/steps, match scoring, and the guard state ("model claimed a save that did not happen"). Filenames may be Persian — RTL in list rows is normal, not an edge case. |
| Providers: OpenAI-compatible, Anthropic, Ollama, echo backend for offline | `dream/providers.py`, `.env.example` | Provider config screen with **test connection** and an explicit **offline/echo mode** so first-run works with zero keys — key to the local-first story. |
| Slash commands: `/mem /mems /stats /forget /dedupe /pin /remind /reminders /unremind /skill /skills /tools /reset /help /exit` | `cli.py` | Command palette (⌘K) should absorb every slash command; typing `/` in the chat input opens inline autocomplete (parity with CLI muscle memory). |
| Telegram gateway with restricted phone command set | `dream/telegram.py`, `PHONE_COMMANDS` | Mobile web gateway mirrors this reduced command surface: check status, read replies, approve/deny — not full desktop parity. |
| Tkinter desktop: chat + three panels (reminders/memories/skills), single worker thread, RLM-wrapped RTL lines, dangerous tools always refused | `desktop.py` | The new desktop replaces this. Lessons it teaches: (a) UI thread must never block on a turn (worker + queue → in the new stack, async IPC + optimistic UI); (b) RTL was bolted on with U+200F marks — the new design makes **direction a layout property**, not a text hack; (c) always-refusing dangerous tools frustrated the owner — the approval dialog fixes this properly. |
| Duplicate cleanup with mandatory dry-run + owner acceptance | `desktop.py`, `memory.cleanup_duplicates` | "Dry-run first, show the report, owner accepts" is a **house interaction pattern** — reuse it for any destructive bulk action (dedupe, forget-all, skill delete). |

### 1.2 Pain points of the current UI (heuristic evaluation of `desktop.py`)

1. **Visibility of system status** — busy state is a single flag; no streaming, no per-tool progress. → Streaming transcript + tool-call cards with live status.
2. **User control** — dangerous tools are flat-refused; no way to grant one-time or standing approval. → Allow / Deny / Always-allow dialog with risk explanation.
3. **Flexibility** — fixed 1+3 panel layout; lists don't wrap; horizontal scrollbars used as a workaround. → Multi-pane manager with wrapping, virtualized lists.
4. **RTL** — alignment simulated with Unicode marks inside an LTR widget. → True `dir="rtl"` layout mirroring at container level.
5. **Recognition vs. recall** — slash commands must be memorized. → Command palette + inline `/` autocomplete + discoverable menus.

---

## 2. Reference-application study

### 2.1 Hermes Agent (Nous Research)

Multi-platform agent gateway: one agent reachable from terminal TUI, Telegram, Discord, Slack, WhatsApp, Signal; agent-curated memory with periodic nudges; autonomous skill creation; FTS5 session search with LLM summarization.

**Adopt:**
- *One brain, many surfaces* framing — desktop is primary, web gateway/phone is a thin remote with continuity ("continue this conversation on desktop").
- Slash-command autocomplete with inline help strings (Dream's CLI already has the help fragments — surface them).
- Interrupt-and-redirect during a streaming turn (stop button that keeps partial output and lets you re-steer).
- Session search across history with summaries in results.

**Avoid:** terminal-density everywhere; Dream targets non-terminal users too, so density is a *setting* (comfortable / compact), not the default.

### 2.2 Open Science Desktop

Tauri desktop app; provenance viewer; split-pane layout.

**Adopt:**
- Split-pane workbench where the transcript and its artifacts (charts, tables, files) live side by side rather than inline-only.
- Provenance as a **navigable tree**: run → turns → tool calls → artifacts, with every artifact linking back to the exact tool call that produced it.
- Native-feeling Tauri chrome: custom title bar with traffic lights/window controls per OS, real menus, OS file dialogs.

**Avoid:** provenance as a separate "expert mode" ghetto — in Dream, any message/artifact has a right-click "Show provenance" that deep-links into the viewer.

### 2.3 DeepAnalyze (RUC)

Agentic data-science: upload data → autonomous multi-step analysis → analyst-grade report; WebUI + JupyterUI; sandboxed execution.

**Adopt:**
- *Plan visibility*: show the agent's analysis plan as checkable steps before/while it runs.
- Data preview grid as the anchor of the data-science view; transformations shown as an ordered, revertible step list (each step = a provenance node).
- Report preview that assembles charts + narrative, exportable (HTML/PDF/Markdown).

**Avoid:** hiding executed code. Every chart gets a "view code / view data slice" affordance — this is the provenance story again.

### 2.4 Competitor patterns

| Product | Pattern to borrow | Pattern to reject |
| --- | --- | --- |
| **ChatGPT desktop** | Clean transcript rhythm; date-grouped session sidebar; ⌘K search; model picker in composer | Single-pane rigidity; weak keyboard model |
| **Claude desktop** | Artifacts panel beside chat; calm tone for tool-use disclosure; projects with instructions + files | Approval UX buried in settings |
| **Cursor** | Composer with @-mentions of files/context; inline diff-style result review; background-agent status | Overwhelming first-run; settings sprawl |
| **VS Code** | Pane/editor-group management, drag-to-split, keyboard-first layout commands; activity bar + status bar model | Chrome density unsuitable for a personal assistant's default look |
| **Linear** | Token discipline; ⌘K everything; 150–250 ms motion language; empty states that teach | — |
| **Notion** | Document/report editing surface; slash-menu insertion | Slow perceived performance on large docs — we virtualize |

---

## 3. Personas (UXR)

### P1 — Leila, the privacy-conscious researcher
- 34, sociology postdoc. Runs local models via Ollama; refuses cloud APIs for interview data.
- **Needs:** absolute clarity on what leaves the machine; network-touching tools clearly marked; offline mode that is genuinely first-class; provenance for citing analysis steps in papers.
- **Design consequences:** a persistent **local/online indicator** in the status bar; `guarded`/`dangerous` tool badges; network-off toggle; export of provenance trees.
- **Frustration to avoid:** "test connection" that silently pings a cloud endpoint.

### P2 — Daniel, the data analyst
- 41, operations analyst. CSVs and dirty Excel exports all day; SQL-capable, not a programmer.
- **Needs:** load → clean → analyze → chart → report without writing code, but with every step inspectable; re-run yesterday's pipeline on today's file.
- **Design consequences:** data preview with type inference and issue highlighting; step list with revert; chart builder with sane defaults; one-click report export; "re-run with new file" from provenance.
- **Frustration to avoid:** black-box transformations he can't defend to his boss.

### P3 — Priya, the power user
- 28, staff engineer. Lives in keyboard shortcuts; runs 3 subagents in parallel; extends via MCP servers.
- **Needs:** 4-pane layouts, every action keyboard-reachable, subagent dashboard with logs and cancel, MCP tool inspection, per-tool standing approvals.
- **Design consequences:** complete shortcut map + palette; pane commands (split/focus/rotate); subagent monitor with per-agent token/cost/log; approval memory with an audit list.
- **Frustration to avoid:** modal dialogs stealing focus mid-flow.

### P4 — Maryam, the Persian-speaking user
- 52, small-business owner in Tehran. Persian-first, some English. Manages reminders (insurance renewals — a real skill file in this repo), notes, and family logistics. Uses the phone gateway heavily.
- **Needs:** full Persian UI, RTL that actually mirrors (not right-aligned LTR); Jalali dates everywhere with Gregorian secondary; mixed Persian/English text that never scrambles; a phone view for checking reminders and replies.
- **Design consequences:** locale switch flips `dir`, calendar, and font stack (Vazirmatn); numerals setting (Persian digits vs. Latin); bidi-safe chip/list components; mobile gateway with reduced command set.
- **Frustration to avoid:** punctuation on the wrong side of a sentence (the exact M23 defect this repo documents).

---

## 4. User workflow inventory (UXR)

Complete task list users must be able to perform. ★ = daily-path, must be ≤ 2 interactions from home.

**Conversation** ★ start new chat · ★ send message, watch streaming reply · ★ see/expand tool calls · interrupt & redirect a turn · approve/deny a dangerous tool · re-ask with edited message · copy/quote a message · view a turn's provenance · switch model per-conversation.

**Sessions & projects** ★ resume a recent session (date groups) · search sessions (full-text, summaries) · rename/archive/delete session · create project · attach files & instructions to project · view project memory.

**Memory** ★ search memories (normalization-aware) · add/edit/delete a memory · pin (importance) · view timeline of episodic memories · dedupe with dry-run report · see why a memory was retrieved for a turn.

**Reminders** ★ create reminder (Jalali/Gregorian, repeats) · list due/upcoming · snooze/complete/delete.

**Skills** list & search skills · view steps · create/edit skill · enable/disable · import/export `.txt` · see when a skill was auto-invoked.

**Subagents** spawn subagent from chat · ★ monitor running subagents (status, elapsed, tokens) · read a subagent's log · cancel a subagent · review/accept a subagent's output.

**Data science** load CSV/Excel · preview with type inference & issue flags · apply cleaning steps (revertible) · run analysis (plan visible) · build chart · assemble & export report · re-run pipeline on new file.

**Provenance** browse run history · inspect run → turn → tool call → artifact tree · open any artifact · export a provenance bundle.

**Configuration** first-run onboarding (locale → provider → privacy) · add/edit/test provider · set default & per-purpose models · add MCP server, inspect its tools, set risk overrides · integrations (Telegram) · appearance (theme, density, font size, numerals) · shortcuts · manage standing approvals · network on/off.

**Remote (web gateway)** open on phone · authenticate (pairing code) · check run/subagent status · read & reply to conversation · approve/deny pending approvals · hand off to desktop.

---

## 5. Constraints carried into design

1. **Implementable in Tauri 2 + React + Tailwind + Shadcn/ui** — every component in the system maps to a Shadcn primitive or a documented composite (see `design-system.md` §9).
2. **WCAG 2.1 AA** — contrast ≥ 4.5:1 body text, ≥ 3:1 large text/UI; full keyboard operation; visible focus; risk tiers never color-only (icon + label always).
3. **Color-vision safety** — success/error pairs distinguished by icon+shape+label; palette checked for protanopia/deuteranopia (see `accessibility-audit.md`).
4. **RTL is structural** — logical CSS properties only (`margin-inline-start`, not `margin-left`); direction set at the root; icons with inherent direction (arrows, chevrons) mirror; media-progress and code blocks do not.
5. **Performance** — transform/opacity-only animation, 60 fps; virtualized lists for memories/sessions/data grids; skeletons over spinners for >300 ms loads.
6. **Local-first honesty** — the UI never implies cloud when local, or vice versa; network activity is always visible.

---

## Gate G1 checklist

- [x] Existing CLI/Tkinter capabilities audited
- [x] Three reference apps studied, adopt/avoid documented
- [x] Competitor patterns documented (ChatGPT, Claude, Cursor, VS Code, Linear, Notion)
- [x] 4 personas defined with design consequences
- [x] Full workflow inventory with daily-path markers

**G1: PASSED** — proceed to user flows (`user-flows/`).
