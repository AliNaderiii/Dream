# Quick Start — Dream in five minutes

Dream's product UI is the Tauri desktop app in `apps/desktop/`; the Python CLI
is also available for setup, diagnostics, automation, and an offline demo.
Python 3.10+ is required. Node.js 22+ and Rust stable are required only when
building the desktop app from source.

## Windows first run — `run.bat` + Ollama

The supported first-run path today is the local CLI launcher, not an installer:

1. Install [Ollama](https://ollama.com/download) and open it once.
2. In a terminal, pull the default local model:

   ```bat
   ollama pull qwen2.5:7b
   ```

3. Double-click **`run.bat`** in the repository root.

`run.bat` creates `.venv` when needed, installs Dream, clears cloud-provider
credentials for that process, and starts `cli.py --backend ollama`. If Python
or Ollama is missing, it prints the next step and pauses so the message remains
visible. `check.bat` runs offline diagnostics. `Dream.bat` and
`Dream-Start.bat` launch the older `desktop.py` window; they are not the Tauri
product UI and are not the first-run path.

## Install the Python CLI (any OS)

```bash
python -m venv .venv
. .venv/bin/activate              # Windows: .venv\Scripts\activate
python -m pip install -e .
python doctor.py                  # offline installation checks
```

Optional repository-defined extras are `.[web]`, `.[data]`, and `.[dev]`:

```bash
python -m pip install -e ".[web]"     # FastAPI + uvicorn
python -m pip install -e ".[data]"    # nbformat
python -m pip install -e ".[dev]"     # pytest + ruff
```

## Verify and start a conversation

```bash
dream --demo                     # deterministic; no key or network
dream --backend echo             # interactive offline session
dream --backend ollama           # local Ollama session
```

At the prompt, try `سلام! اسم من مریم است.`. Use `/mems` to list memories or
`/help` for the command list.

Inspect the commercial and privacy state without starting a conversation:

```bash
dream --plan
dream --usage
dream --route
```

The same read-only commands are available during a terminal or paired Telegram
conversation as `/plan`, `/usage`, and `/route`.

## Run or build the Tauri desktop UI

From the repository root:

```bash
cd apps/desktop
npm install
npm run tauri dev
```

To produce host-platform installers:

```bash
cd apps/desktop
npm install
npm run tauri build
```

For browser-only UI development, `npm run dev` exists, but native features use
safe browser fallbacks. The Tauri app builds and communicates with the Python
kernel through the JSON-RPC sidecar. Its current surfaces include chat,
projects, the Jalali-aware scheduler, memory and skills, data science,
providers, connectivity, and settings.

In chat, model tool calls appear as status cards (`ok`, `error`, `blocked`, or
`pending`). Dangerous tools open an approval dialog: allow once, always allow
that tool for this session, or deny. Denial and missing approval fail closed.

## Pair Telegram

1. Create a Telegram bot with BotFather and set `TELEGRAM_BOT_TOKEN` in your environment.
2. Start the long-polling front end:

   ```bash
   dream-telegram --backend ollama
   ```

3. If `TELEGRAM_ALLOWED_USER` is not configured and no chat is paired, Dream
   prints a six-digit code valid for 10 minutes. In a **private chat** with the
   bot, send `/pair 123456`, replacing the digits with that code.

Pairing is persisted locally. The automated pairing and policy tests are in the
repository; the owner still performs the real bot/network smoke test because it
requires live Telegram credentials.

## For Iranian users

Ollama runs the model locally and the Windows `run.bat` path does not require a
VPN. Local-plan use is unlimited and does not need a usage ledger. Paid-plan
prices are **TBD after cost measurement**; Dream does not publish invented IRR
prices.
