# Dream — Product Story (S00)

This document is the honest product story for Dream 0.2. It says what the
product is, what is free, what is paid, what is measured, and what is not yet
decided. Nothing here is marketing.

## What Dream is

Dream is a **local-first personal assistant for people who write Persian as
well as English**. The commercial kernel (this milestone) does not change the
agent's nature: the product is first and foremost a local assistant whose
memory, tools, and (optionally) model run on the owner's own machine.

Two surfaces exist today:

1. **The Python kernel** (`dream/`, `cli.py`) — memory, typed tools, the
   agent loop, model backends, the usage ledger, and the model router. It is
   stdlib-only and fully offline-capable (`dream --demo`).
2. **The Tauri desktop shell** (`apps/desktop/`) — a Tauri 2 + React 19
   application with eight UI languages and a data-science workbench. The
   Python↔desktop IPC bridge is a separate milestone; today the shell is
   developed and tested on its own.

The demo transcript in the README is a real transcript of `python cli.py
--demo` in this repository. It requires no API key and no network.

On Windows the first five minutes are **no-VPN**: double-click `run.bat`
(the only primary launcher). It creates `.venv` if needed, refuses to start
without Ollama (Persian + English, with the official download URL), and
otherwise talks to a local Ollama model. Details live in
[user/quick-start.md](user/quick-start.md).

## Plans

All prices are in **IRR (Iranian rial)**. The currency field exists on every
plan from day one so nothing has to be retrofitted.

| Plan | Price (IRR) | Quota | Notes |
| --- | --- | --- | --- |
| `local` | **0** | unlimited | The default. Needs no ledger file. |
| `guest` | **0** | 20 turns/day | Free daily quota; the 21st turn is refused with a Persian sentence. |
| `daily` | `null` — TBD after cost measurement | 100 turns/day | |
| `individual_monthly` | `null` — TBD after cost measurement | 1 000 turns/month | |
| `individual_yearly` | `null` — TBD after cost measurement | 12 000 turns/year | |
| `team` | `null` — TBD after cost measurement | 5 000 turns/month | |
| `company` | `null` — TBD after cost measurement | 20 000 turns/month | |

**Pricing rule (enforced by tests):** the only numeric IRR prices in the
product are `0` for the two free plans. Every paid plan stores `price: null`
and a note that the price is *TBD after cost measurement*. Until real hosting,
compute, and support costs are measured, publishing a number would be
inventing one.

The quota figures above are capacity placeholders, kept as constants in one
place (`dream/commerce.py`) so tuning them after cost measurement is a
one-line change per plan.

## Usage metering

- Usage lives in a **JSON ledger** (`DREAM_LEDGER`, default
  `data/dream-ledger.json`). Each consumed turn appends one timestamped
  entry; writes are atomic (temp file + rename), so a crash cannot tear the
  ledger.
- `Dream.run` **consumes a turn only when a ledger is attached**: when
  `DREAM_PLAN` is set to anything other than `local`, or when `DREAM_LEDGER`
  names a file. The unlimited `local` plan therefore runs with **no ledger
  file at all**.
- Quota windows follow the plan: day (`guest`, `daily`), month
  (`individual_monthly`, `team`, `company`), year (`individual_yearly`).
- Metered plans **fail closed**: if the ledger file is unreadable, invalid
  JSON, or structurally malformed, the turn is refused with a Persian
  sentence. Corruption never converts into free turns. An unknown
  `DREAM_PLAN` name is also refused rather than silently billed as another
  plan.

## Model routing and privacy

`dream/router.py` resolves the route with a fixed priority, purely from
configuration (no network probes, deterministic, offline-testable):

1. **hosted** — cloud model service; your message **leaves this machine**.
2. **ollama** — local Ollama server; your message **never leaves this
   machine**.
3. **byok** — your own endpoint (`OPENAI_BASE_URL`); your message **leaves
   this machine** for that server.
4. **echo** — deterministic offline backend; **no data leaves this
   machine**.

Every route carries an English and a Persian sentence stating exactly whether
data leaves the machine. `dream --route` (and `/route` on the phone) prints
it. The privacy answer is a product guarantee, not a footnote.

## CLI and phone surface

| Command | Meaning | Phone |
| --- | --- | --- |
| `dream --plan` / `/plan` | active plan, currency, price | read-only, allowed |
| `dream --usage` / `/usage` | ledger usage in the current window | read-only, allowed |
| `dream --route` / `/route` | model route + whether data leaves the machine | read-only, allowed |

All three are read-only, so the phone policy admits them; the terminal and
phone command sets stay single-sourced in `cli.py` (parity tests enforce
this).

## What is deliberately not here yet

- No payment processing, no invoices, no billing backend. The ledger is the
  meter; the money plumbing is future work.
- No numeric paid prices. See the pricing rule above.
- No desktop↔kernel bridge yet (separate milestone; see
  `apps/desktop/README.md`).
- No telemetry. Dream does not report usage home; the ledger is a local file.

## How to verify this document

```bash
python -m pytest tests/test_commerce.py tests/test_router.py -q
python cli.py --demo          # exits 0, offline
python cli.py --plan          # local, IRR, price 0
python cli.py --usage         # no ledger attached (plan: local)
python cli.py --route         # echo, no data leaves
```
