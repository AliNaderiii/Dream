# Dream

**Dream is a local-first personal assistant for people who write Persian as
well as English — a real desktop product, not a toy demo.** It ships a Python
agent kernel (memory, tools, model routing, metering) with a Tauri 2 + React
desktop shell (`apps/desktop/`), an offline demo that runs with zero network,
and an honest commercial kernel: free unlimited local use, a free guest
quota, and paid plans whose prices are *not invented* — they stay
`TBD after cost measurement` until real costs are measured.

Its memory search treats Persian spelling variants as the same word before
storing or querying them, so a fact saved from one keyboard is still found
from another. The Tauri app is the product UI; the Python kernel and CLI power
it and provide an offline demo that needs no API key.

## Persian retrieval that does not silently miss

These look the same in many fonts, but are different Unicode bytes:

```text
مي‌خواهم كتاب  # Arabic yeh (U+064A) and kaf (U+0643)
می‌خواهم کتاب  # Farsi yeh (U+06CC) and keheh (U+06A9)
```

Without normalisation, storing the second spelling and searching the first can
return nothing because a database compares different code points. Dream applies
NFKC, folds Arabic letter forms and digits, removes diacritics and tatweel, and
normalises whitespace on both write and read. Both examples become
`می خواهم کتاب`, so retrieval reaches the same memory. Run the demo below to
see the value printed by the program.

## Install and run

Python 3.10 or later is required.

```bash
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
dream --demo                         # no API key or network required
python doctor.py                     # verify the local installation
```

For an interactive offline session, use `dream --backend echo`. Configure a
provider only when needed; see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

During a session, every tool call the model makes is shown on stderr as a
compact `[tool] name(args) -> ok | error | blocked` line, and confirmed
memory writes appear as `[memory] stored N facts`, so you can see what
actually happened rather than what the model claims. Pass `--quiet` to hide
these lines. If memory behaviour needs diagnosing, run
`python tools/memory_probe.py --backend ollama`: it stores nothing unless the
model really calls the tool, and prints a one-line verdict naming the failure
mode.

The desktop app (`apps/desktop/`) is a Tauri 2 + React application localised
into eight languages. It builds successfully and communicates with the Python
kernel through a framed JSON-RPC sidecar. Its product surfaces include
conversation panes, projects, a Jalali-aware scheduler, memory and skills,
data science, providers, connectivity, provenance, and settings. The shell
ships Light, Warm, and Dark themes, four accents, comfortable/dense modes,
persistent 80–150% zoom, Persian RTL, and reduced motion. Routes and locales
load on demand; transcripts and other long operational lists stay bounded from
100 rows onward.

### Windows

Two ways to run Dream on Windows — both are honest about what they are:

1. **Use today — `run.bat` (the first-run path).** Clone the repository,
   install [Ollama](https://ollama.com/download), and double-click
   **`run.bat`**. It creates `.venv` if needed (or prints the one command
   `python -m venv .venv` and waits), installs Dream, and starts the local
   Ollama backend with model `qwen2.5:7b`. If Ollama is missing it prints a
   Persian and English message with <https://ollama.com/download> and waits so
   the window stays readable.
2. **Tauri installer (from the `v0.4.5` release).** Download
   **`Dream_0.4.5_x64-setup.exe`** from the GitHub Release, install it, and run
   Dream. The kernel is inside the Windows installer — a bundled CPython plus the
   Dream package — so no separate `pip install` and no local Python are needed on
   Windows. The installer is **unsigned**, so SmartScreen warns; choose
   **More info → Run anyway**. WebView2 may be downloaded during installation.
   Ollama is optional for a real local model; without it the router may fall
   through to echo.

See [docs/user/quick-start.md](docs/user/quick-start.md) for extras
(`.[web]`, `.[data]`) and the first conversation.

Other scripts are labelled and kept, but they are not the first-run path:
`check.bat` runs offline `doctor.py`; `Dream.bat` and `Dream-Start.bat` open
the older `desktop.py` window, not the Tauri product UI.

## Desktop conversations and work

The Tauri chat transcript shows tool calls as cards with arguments, status, and
result excerpts. Dangerous actions open a bilingual approval dialog: allow
once, always allow that tool for this session, or deny. A denial or absent
approver fails closed. Projects group sessions and can link workspace folders
in place. The scheduler accepts Persian or English prose and displays both
document-locale and Jalali next-run dates, history, pause/run controls, and an
approval queue for gated jobs. An opt-in three-role council (proposer, critic,
judge) reviews one topic on the Subagents page or via `dream --council "…"`,
offline by default. The dashboard first-run card offers Aval AI as the
recommended hosted path, and the chat composer has a small opt-in Council
review button that never starts a council from plain Send.

MEM Stage F adds four durable-memory surfaces. The memory explorer's
bounded-stores tab shows the two fixed-size stores that ride with every
system prompt — a live `[67% — 1,474/2,200 chars]` capacity meter, an
approval on every edit, and a notice that the prompt was frozen at session
start. The skills learning workspace sits beside the classic manager: run
and failure counts, a version diff, `references/` notes, an approval inbox,
and a `/learn` panel that classifies a file, folder, conversation or pasted
notes — refusing a web source up front while network tools are off. Press
Ctrl/⌘+P to search every past conversation: Persian matching is
spelling-insensitive (an Arabic-spelled query finds a Farsi-spelled
transcript) and the hit is highlighted in the spelling you used; a damaged
index says so and offers a rebuild. And every compaction leaves a visible
transcript row — before/after cost, share reclaimed, messages preserved
verbatim, and what the summary kept.

Build or run the full native UI using the scripts that exist in
`apps/desktop/package.json`:

```bash
cd apps/desktop
npm install
npm run tauri dev          # native development app
npm run tauri build        # host-platform installer artifacts
npm run accessibility:check
npm run build && npm run performance:check  # emits JSON; see docs/handoff/ci-perf-check.patch
```

## Telegram pairing

Set `TELEGRAM_BOT_TOKEN`, run `dream-telegram --backend ollama`, and send
`/pair <six-digit-code>` in a private chat when the process prints its
10-minute pairing code. Pairing is saved locally. `/plan`, `/usage`, and
`/route` are available on the paired phone surface. Automated tests cover the
pairing and policy paths; the final live Telegram bot/network smoke remains an
owner-run check requiring real credentials.

## For Iranian users

Ollama provides local model inference without a VPN, and `run.bat` deliberately
uses that local path on Windows. The local plan is unlimited and requires no
ledger. Paid plans are **TBD after cost measurement**; no made-up IRR prices
are published.

For hosted cloud models, **Aval AI is the recommended path**: one key from
`chat.avalai.ir/platform/home` reaches many model families through an
OpenAI-compatible endpoint (`api.avalai.ir`), and `dream --route` names that
route `aval` with an honest leave-the-machine sentence.

## Plans and metering (honest by construction)

Dream 0.2 introduces a commercial kernel (`dream/commerce.py`) with seven
plans. All prices are in **IRR (Iranian rial)**. Only the two free plans
carry a numeric price (0); every paid plan carries a **null** price with the
note `TBD after cost measurement` — we will not invent numbers before real
costs are measured.

| Plan | Price (IRR) | Quota |
| --- | --- | --- |
| `local` | 0 | unlimited, no ledger file required |
| `guest` | 0 | 20 turns/day |
| `daily` | TBD after cost measurement | 100 turns/day |
| `individual_monthly` | TBD after cost measurement | 1 000 turns/month |
| `individual_yearly` | TBD after cost measurement | 12 000 turns/year |
| `team` | TBD after cost measurement | 5 000 turns/month |
| `company` | TBD after cost measurement | 20 000 turns/month |

Usage is a JSON ledger (`DREAM_LEDGER`, default `data/dream-ledger.json`).
`Dream.run` consumes one turn per message **only when a ledger is attached**:
`DREAM_PLAN` is set to anything other than `local`, or `DREAM_LEDGER` names a
file. The local plan runs with no ledger at all.

Metered plans **fail closed**: a ledger file that is unreadable, invalid JSON,
or malformed refuses turns with a Persian sentence instead of silently
granting unlimited usage. Writes are atomic, so a crash never tears the
ledger.

```bash
dream --plan        # active plan, currency, price
dream --usage       # turns used/remaining in the current window
# in-session: /plan /usage
```

## Model routing and privacy

`dream/router.py` resolves the model route with a fixed priority —
**hosted → Aval → Ollama → BYOK → echo** — purely from configuration, never
from network probes:

1. **hosted** — official cloud model service (`OPENAI_API_KEY` or `DREAM_BACKEND=openai`): your message **leaves this machine**.
2. **aval** — Aval AI, the recommended hosted path for Iranian users (`AVALAI_API_KEY`, `OPENAI_BASE_URL` on api.avalai.ir / api.avalapis.ir, or `DREAM_BACKEND=aval`): your message **leaves this machine** for Aval (api.avalai.ir).
3. **ollama** — local Ollama server (`OLLAMA_HOST` or `DREAM_BACKEND=ollama`): your message **never leaves this machine**.
4. **byok** — bring-your-own-key endpoint (`OPENAI_BASE_URL` points at your own server): your message **leaves this machine** for that server.
5. **echo** — deterministic offline backend: **no data leaves this machine**.

Every route carries an English and a Persian sentence stating exactly whether
data leaves the machine, and `dream --route` (or `/route`) prints it — the
privacy answer is never hand-waved.

```bash
dream --route
```

## Demo transcript

The following is a transcript captured by running `python cli.py --demo` in
this repository. Scores and the clock naturally vary between runs.

```text
1. Seeding memories across semantic, episodic, and procedural kinds
2. Hybrid retrieval for 'coffee':
   relevance=0.894  Visited Tehran coffee shop today
   relevance=0.888  I prefer dark coffee
3. Normalisation:
   Arabic forms  → می خواهم کتاب
   Persian forms → می خواهم کتاب
   This matters because equivalent spellings retrieve the same stored memory.
4. Agent tool loop:
   What time is it? Result: {"result": "2026-07-31T10:49:02.095406+03:30"}
   What is 12 × 3? Result: {"result": 36}
5. Approval gate:
   {"blocked": true, "reason": "dangerous tool denied: no approver configured"}
```

## Architecture at a glance

Dream stores three kinds of memory:

| Kind | Purpose |
| --- | --- |
| `semantic` | durable facts and preferences |
| `episodic` | timestamped events |
| `procedural` | instructions and learned rules |

Retrieval combines lexical relevance with time and user intent rather than
using similarity alone:

```text
score = 0.55 * relevance + 0.20 * recency + 0.15 * importance + 0.10 * usage
```

Tools are registered from Python signatures and docstrings, then assigned a
risk tier: `safe` tools run automatically; `guarded` local reversible writes
run and are logged; `dangerous` external or irreversible actions require an
approval callback. The agent loop consults that policy before every requested
tool execution.

Model backends share one `chat(messages, tools)` interface. `EchoBackend` is
the deterministic offline backend; `OpenAIBackend` speaks the OpenAI-compatible
HTTP API; `OllamaBackend` points that protocol at a local Ollama instance.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full data flow and
[docs/PRODUCT.md](docs/PRODUCT.md) for the product story, plans, and the
metering/privacy behaviour.

## Add a tool

The decorator derives the provider schema from the signature and `:param` lines;
do not maintain a second hand-written schema.

```python
from dream import tool


@tool(risk="safe")
def word_count(text: str, include_spaces: bool = False) -> int:
    """Count characters in text.

    :param text: Text to count.
    :param include_spaces: Whether whitespace counts.
    """
    return len(text) if include_spaces else len(text.replace(" ", ""))
```

Its generated JSON Schema has a required string `text`, an optional boolean
`include_spaces`, and the two descriptions above. The `safe` tier means the
agent may execute it automatically; choose `guarded` or `dangerous` when the
effect warrants it.

## Development

```bash
python -m pytest
python -m ruff check .
python -m build
```

The core `dream/` package depends only on `keyring` and `Authlib`. Development
tools are available through the `dev` extra; `web` (fastapi, uvicorn) and `data`
(nbformat) extras cover the optional web gateway and notebook tooling. Sample
data lives in [`examples/`](examples/), including an Iranian sales CSV with
Persian headers. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[CHANGELOG.md](CHANGELOG.md) for project process and release history.

## License

[MIT](LICENSE)
