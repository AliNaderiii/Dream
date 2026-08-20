# Dream — Product story after Wave 2

Dream is a local-first personal assistant for people who write Persian as well
as English. The product surface is the **Tauri 2 + React desktop app** in
`apps/desktop/`; the Python kernel and CLI provide its agent, memory, tools,
routing, metering, automation, diagnostics, and an offline demo.

The desktop now builds and talks to the Python kernel through a framed JSON-RPC
sidecar. It is not a disconnected mock shell. Browser development mode remains
available with deterministic echo fallbacks where native APIs are unavailable.

## What users can do today

- Hold multi-pane conversations and stop in-flight work. Tool calls are visible
  as cards with arguments, status, and result excerpts. Dangerous actions open
  a bilingual approval dialog with allow-once, session allowlist, and deny;
  missing or denied approval fails closed.
- Organise sessions into projects and optionally link a workspace folder in
  place. Deleting a project keeps its sessions.
- Create schedules from Persian or English prose, preview cron and next-run
  time, view Gregorian and Jalali dates, pause, run now, inspect history, and
  approve or deny gated runs.
- Use memory, skills, subagents, data-science workflows, providers, MCP,
  connectivity settings, provenance, sandbox, browser, and gateway surfaces
  delivered in the existing desktop application.
- Ask for an opt-in three-role council review — a proposer, a critic and a
  judge answer one topic in that order and the judge's answer wins — from the
  Subagents page, from a small opt-in button inside any chat pane, or from the
  CLI (`dream --council "topic"`). Members default to the offline echo
  provider, so the first run needs no credentials and nothing leaves the
  machine.
- Use the terminal CLI and a paired Telegram private chat. Telegram preserves
  the read-only `/plan`, `/usage`, and `/route` command surface; its live
  bot/network smoke remains owner-run because it needs real credentials.

## First run and local operation

Windows first-run today is **`run.bat` + Ollama**. The launcher creates a
virtual environment if needed, installs Dream, and starts the local Ollama CLI
path. It is not yet a Tauri installer launcher. Source builders can run or
package the Tauri UI with the scripts in `apps/desktop/package.json`; see
[user/quick-start.md](user/quick-start.md).

The Tauri dashboard first-run card offers the same offline echo and Ollama
paths alongside Aval AI as the recommended hosted option — the Aval line
plainly says prompts leave this machine — with BYOK still available as an
optional extra.

`dream --demo` is a deterministic offline verification path. The Python kernel
has no mandatory third-party runtime dependencies, while optional features and
the desktop have their own declared dependencies. Dream is therefore not
presented as “only a standard-library CLI.”

## Plans and usage

| Plan | Price | Quota |
| --- | --- | --- |
| `local` | 0 IRR | unlimited; no ledger required |
| `guest` | 0 IRR | 20 turns/day |
| `daily` | TBD after cost measurement | 100 turns/day |
| `individual_monthly` | TBD after cost measurement | 1,000 turns/month |
| `individual_yearly` | TBD after cost measurement | 12,000 turns/year |
| `team` | TBD after cost measurement | 5,000 turns/month |
| `company` | TBD after cost measurement | 20,000 turns/month |

Only free plans have a numeric price. Paid plans store `price: null`; there is
no payment processing or invented IRR amount yet.

Usage is stored in a local JSON ledger when `DREAM_PLAN` is not `local` or
`DREAM_LEDGER` is explicitly set. Writes are atomic and durable. Metered plans
fail closed on an unknown plan or an unreadable, invalid, malformed, or
unwritable ledger. Inspect the same state from the CLI or an interactive
conversation:

```bash
dream --plan       # or /plan
dream --usage      # or /usage
dream --route      # or /route
```

## Routing and privacy

Route selection is configuration-driven and does not probe the network:

1. hosted — messages leave the machine for the configured official cloud service;
2. Aval — messages leave for Aval AI (api.avalai.ir), the recommended hosted
   path for Iranian users (`AVALAI_API_KEY`, an Aval `OPENAI_BASE_URL`, or
   `DREAM_BACKEND=aval`);
3. Ollama — the model runs locally;
4. BYOK — messages leave for the user-configured endpoint;
5. echo — deterministic and offline.

The route command reports an English and Persian privacy sentence derived from
the selected route. There is no telemetry that reports the local usage ledger
home.

## For Iranian users

Ollama provides a local path that needs no VPN, and `run.bat` selects that path
on Windows. The local plan is unlimited. Paid plans remain **TBD after cost
measurement**; no IRR prices will be published until actual compute and support
costs are measured.

Aval AI is the recommended hosted path: one key from
`chat.avalai.ir/platform/home` reaches many model families through one
OpenAI-compatible endpoint, and the `aval` route says plainly that prompts
leave this machine for Aval.

## Honest boundaries

- Windows first-run is currently the repository launcher and CLI, not a shipped
  Tauri installer flow.
- Telegram logic is automated and tested, but the final live pairing/message
  smoke is performed by the owner with real bot credentials.
- Payment, invoices, and final paid pricing are future work.
- Local model quality and hardware requirements depend on the selected Ollama
  model and the user's machine.
