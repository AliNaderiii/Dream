# Dream — User Manual

## 1. Getting Started

### What Dream is

Dream is a **local-first personal assistant**. Two properties set it apart:

1. **Durable memory** — it stores what you tell it in a SQLite/FTS5 database on
   your own disk, with first-class Persian-language retrieval (spelling
   variants are normalised before storing or searching).
2. **Consent** — every tool call carries a risk tier. Safe actions run
   automatically; irreversible ones (`dangerous`) pause and ask you first.

### Installation

See [quick-start.md](quick-start.md). The CLI entry point is `dream`; the
desktop shell is a separate Tauri app under `apps/desktop`. On Windows,
double-click **`run.bat`** — that is the only first-run launcher.

### Language

Dream auto-detects your language from the system and falls back to English. You
can switch any of eight languages — English, Persian, Simplified Chinese,
Japanese, Spanish, German, French, Korean — from **Settings → Language**. Only
Persian flips the interface to right-to-left.

---

## 2. Conversations

- **Multi-pane workspace** — open several conversations side by side and resize
  the split. Each pane is an independent session.
- **Markdown & code blocks** — replies render Markdown; code blocks are
  monospaced and copyable.
- **RTL Persian** — when the UI is in Persian, text flows right-to-left and
  mixed Latin/Persian segments keep their own direction automatically.
- **Sessions** — the sidebar groups sessions into *Today / This week / This
  month / Older*. `⌘N` (or `Ctrl+N`) starts a new session.
- **Command palette** — `⌘K` (or `Ctrl+K`) opens a searchable list of every
  command.

---

## 3. Memory & Skills

**Memory.** The memory explorer (`/memory`) shows everything Dream remembers:
semantic facts, episodic events, procedural rules, and preferences, each with
an importance star rating. You can add, edit, or delete memories by hand.
Search matches Persian spelling variants — storing «می‌خواهم کتاب» and
searching «میخواهم کتاب» finds the same memory.

**Skills.** Skills are reusable procedures Dream can follow, stored as files
(`.dream-skill.txt`). The skills manager lets you import, enable/disable, edit,
and export skills (individually or as a ZIP). Skills persist across restarts.

---

## 4. Subagents & Scheduling

**Subagents** delegate a task to an isolated child agent with its own memory
and only the tools you explicitly grant it. The subagent monitor shows each
child's status, progress, and a live log; you can pause, resume, or cancel.

**Scheduling** runs one-off or recurring tasks. Natural-language schedule
expressions (including Persian) are parsed into cron expressions.

---

## 5. Platform Connections

Dream bridges into six platforms — **Telegram, Discord, Slack, WhatsApp,
Signal, and Email** — so you can talk to it from your chat app of choice.
Configure each from **Connectivity**: connect, copy the link code, and start
the gateway. The message log shows what flowed through. See
[troubleshooting.md](troubleshooting.md) if a platform won't link.

---

## 6. Data Science

The workbench (`/data`) ingests CSV, TSV, Excel, JSON, YAML, XML, SQLite and
Parquet files, then lets you:

- **Preview** — sort, filter, paginate, resize and copy cells (a 1,000,000-row
  table scrolls smoothly thanks to virtualisation).
- **Profile** — per-column statistics, IQR/z-score outliers, histograms.
- **Clean** — ten cleaning operations with schema tracking.
- **Analyse** — correlation, time-series, and more.
- **Charts** — ranked suggestions plus a gallery (PNG/SVG/PDF/HTML).
- **Report** — a PDF (≤ 5 pages) with the summary and charts, plus a Markdown
  twin.

Every operation runs in the **Docker sandbox**, never in the host process.

---

## 7. Docker, Chrome & the Web Gateway

- **Docker sandbox** (`Settings → Docker`) runs untrusted code (and all data
  work) in an isolated container with no network and no privileged access.
- **Chrome control** (`Settings → Browser`) lets Dream drive a browser for
  tasks like "open this page and read the results".
- **Web gateway** (`Settings → Gateway`) serves the same UI to your phone or
  another browser on your LAN. It is token-gated: a random setup token is
  created on first launch and shown only to you.

---

## 8. Security & Privacy

- **Approval gates** — dangerous tools (shell, irreversible changes) never run
  without an interactive "approve?" prompt.
- **Sandbox** — untrusted code runs in a Docker container with network
  disabled, capabilities dropped, and a seccomp profile.
- **Keychain** — API keys live in your OS keychain, never in a settings file.
- **Secrets never logged** — logs, exports, sessions and provenance records
  redact or omit credentials.
- **Local-first** — memory, skills and datasets stay on your machine.

See the security audit at `docs/security/audit-report.md` (0 critical, 0 high).

---

## 9. Customisation

- **Models** — add any OpenAI-compatible provider, or run Ollama locally.
- **Prompts** — the system prompt is configurable; default behaviour is
  "reply in the user's language".
- **MCP servers** — add Model Context Protocol servers to extend the tool set
  (`Settings → MCP Servers`).
- **ACP agents** — interoperate with other Agent Client Protocol agents
  (`Settings → ACP`).
- **Custom tools** — see the developer guide `docs/dev/how-to/add-a-tool.md`.

---

## 10. Reference Tables

**Keyboard shortcuts** — see [keyboard-shortcuts.md](keyboard-shortcuts.md).

**Risk tiers** — every tool is one of:

| Tier | Behaviour |
| --- | --- |
| `safe` | runs automatically (e.g. store a memory). |
| `guarded` | runs automatically but is logged (e.g. web search). |
| `dangerous` | pauses for approval (e.g. `run_shell`, delete). |

**Configuration keys** — `DREAM_TEMPERATURE` (sampling, default `0.3`),
`DREAM_MEMORY_BLOCK_CHAR_LIMIT`, `DREAM_DATASETS_DIR`, plus per-provider
environment variables such as `OPENAI_API_KEY` / `OPENAI_BASE_URL`.

---

## 11. Troubleshooting

See [troubleshooting.md](troubleshooting.md) for the symptom → cause →
solution table.

---

## 12. Where to Get Help

- Repository & issues: <https://github.com/AliNaderiii/Dream/issues>
- Diagnose locally first: `python doctor.py` then `dream --backend echo --debug`.
- Version policy: follow the changelog (`CHANGELOG.md`); `dream --version`
  prints your build.

---

## Deep research (autonomous data science)

Dream can run a whole analytical project on its own: point it at a folder of
data and a question, and it plans a study, analyses the data step by step, and
writes you a report with a PDF — every number in it produced by code that
actually ran.

### Running one

```bash
python examples/research_demo.py                    # offline demo, seeded data
python examples/research_demo.py --backend ollama   # local model, no VPN
```

From Python:

```python
from dream.research import ResearchEngine

engine = ResearchEngine()
session = engine.create(
    "Why did revenue dip in March?",
    "/path/to/my/data-folder",
    config={"language": "fa", "max_iterations": 3},
)

plan = session.plan()          # Dream proposes the study
for section in plan.sections:  # review it before anything expensive runs
    print(section.title, "—", section.thesis)
print(session.record.cost_estimate)

session.approve()              # or session.modify({...}) / session.cancel()
session.start()
print(session.record.report.markdown_path)
print(session.record.report.pdf_path)
```

### What you get

A cover, an abstract, the methodology (including exactly which cleaning steps
ran and why), one section per research question with tables and figures,
anomaly alerts (spikes, drops, outliers the data itself raised), a discussion,
conclusions, an honest limitations list, recommended actions, the full
execution trace as an appendix, references, and reproducibility notes.

### Reviewing and editing the plan

The plan is a document, not a black box. Before you approve it you can edit
the outline:

```python
session.modify({
    "sections": [
        {"title": "March revenue", "thesis": "Isolate the dip to a region."},
        {"title": "Discount effect", "thesis": "Test discount rate against revenue."},
    ]
})
```

Or ask for a fresh plan with `session.modify({"replan": True})`. Nothing runs
until you call `approve()`.

### Steering the research with a document

Put a `METHODOLOGY.md` in the folder and Dream reads it as guidance for the
plan — "focus on the March dip", "always report the discount rate alongside
revenue". It is treated as *your* guidance, not as a command channel: it still
passes through Dream's prompt-injection gate.

### Persian

Set `"language": "fa"` and the plan, prose, and headings are Persian, with
RTL-safe Markdown and Persian-digit-aware data handling.

### Safety

- Code Dream writes runs in a sandbox with no network, never on your machine
  directly, and is refused outright if it tries to import `os`, open an
  absolute path, or write a file.
- Text *inside* your data is treated as data. A CSV cell saying "ignore all
  previous instructions" is reported as content, never obeyed.
- Numbers are checked. If a sentence contains a figure that no executed step
  produced, that sentence is removed before the report is written.
- Nothing hangs. Every step has a deadline; a stuck run fails cleanly and
  tells you which section it gave up on.
- Scheduled/unattended runs use a reduced, read-only tool set — they can
  profile and analyse, but they cannot clean, write charts, or touch anything
  outside the dataset directory.

### Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `max_iterations` | 3 | research turns per section |
| `max_time_seconds` | 900 | hard wall-clock budget for the whole run |
| `step_timeout_seconds` | 120 | deadline for one model call or one code run |
| `max_retries` | 2 | self-correction attempts after a failed snippet |
| `max_sections` | 6 | report sections |
| `language` | `en` | `en` or `fa` |
| `autonomous` | `false` | skip the approval checkpoint, degraded grant set |
| `max_pages` | 20 | PDF page cap |
| `output_length` | `standard` | `brief`, `standard`, or `detailed` |

Environment: `DREAM_RESEARCH_DIR` (session storage, default `data/research`),
`DREAM_DATASETS_DIR` (dataset registry), `DREAM_DATA_LOCAL_EXEC=1` (force the
guarded subprocess when Docker is unavailable).
