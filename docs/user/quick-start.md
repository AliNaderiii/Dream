# Quick Start — Dream in five minutes

Dream's product UI is the Tauri desktop app in `apps/desktop/`; the Python CLI
is also available for setup, diagnostics, automation, and an offline demo.
Python 3.10+ is required. Node.js 22+ and Rust stable are required only when
building the desktop app from source.

## Windows — two honest paths

### 1. Use today: `run.bat` + Ollama

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

### 2. Tauri installer (from the `v0.4.2` release onward)

Download `Dream_0.4.2_x64-setup.exe` from the GitHub Release, install it, and
run Dream. On Windows the kernel is inside the installer — no separate
`pip install`, no local Python required:

1. Download **`Dream_0.4.2_x64-setup.exe`** from the
   [GitHub Release](https://github.com/AliNaderiii/Dream/releases) for `v0.4.2`.
2. Run the installer. SmartScreen may warn because the installer is
   **unsigned** — choose **More info → Run anyway**.
3. WebView2 may be downloaded during installation if it is missing.
4. Open Dream and use it.

The Windows installer embeds a CPython runtime plus the Dream kernel
(`python/python.exe` next to the app), and the shell prefers that bundled
interpreter before falling back to `python` / `py` / `python3` on PATH.
Ollama is optional for a real local model; without it the router may fall
through to echo — Dream never pretends a hosted model is running locally.

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

## Windows desktop troubleshooting (the installed app)

The installer bundles a CPython runtime plus the Dream kernel, so the sidecar
(`python -u -m dream.bridge`) starts from the bundled `python/python.exe` with
no local Python. If the bridge cannot start (for example a corrupted install),
the status bar shows **Disconnected** and a calm banner explains
(English + Persian) that the engine is not installed or did not start. This is
not a crash — the app stays usable and never pretends the model is local.

**Symptoms and fixes**

- **"Disconnected" banner: the engine (Python kernel) is not installed or did
  not start."** Re-run the installer to repair the bundled runtime, then click
  **Reconnect**. If you are running from source (`run.bat` or `npm run tauri
  dev`) instead of the installer, install Python 3.10+ and make sure `python`
  (or `py`) is on PATH, then install the Dream kernel from the repository
  root:

  ```bat
  python -m pip install -e .
  ```

  Click **Reconnect** in the banner once that succeeds.

- **A console window flashes and closes in a loop.** This was a failed sidecar
  discovery attempt (for example the Windows Store `python.exe` stub). It is
  fixed since `v0.3.1`: the sidecar spawns without a console window, and the
  installer's bundled interpreter starts first, so discovery retries no longer
  flash a `cmd` window.

- **SmartScreen / "Windows protected your PC".** The installer is unsigned, so
  SmartScreen warns. Choose **More info → Run anyway** if you trust the
  release. An Authenticode signature is planned for a later session.

- **WebView2 prompt during install.** The Tauri WebView needs the WebView2
  runtime; Windows usually fetches it automatically. If offline, install the
  WebView2 runtime from Microsoft first.

- **Persian chat fails with `charmap` / `bridge is not connected` on Start
  Menu.** Fixed in `v0.4.2`: the engine now forces
  UTF-8 and writes `data/` under `%LOCALAPPDATA%\\Dream`. On a 0.4.1 install,
  launch with
  `Start-Process "C:\\Program Files\\Dream\\dream-desktop.exe" -WorkingDirectory $env:LOCALAPPDATA\\Dream`
  and `$env:PYTHONUTF8 = "1"`.
- **Still stuck.** From a terminal in the repository root, run
  `python doctor.py` (offline checks) and `python -m dream.bridge` to confirm
  the kernel starts. If either fails, the message tells you the next step.

