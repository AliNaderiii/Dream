# Quick Start — Dream in five minutes

This file is the only thing you need to get from "installed" to "first
conversation". It assumes Python 3.10 or later. An internet connection is
needed only to install packages and (optionally) to talk to a cloud model.

## Windows — double-click `run.bat`

That is the **only** first-run launcher. After you have Python 3.10+ on PATH:

1. Double-click **`run.bat`**.
2. If `.venv` is missing, the script creates it (or prints the one command
   `python -m venv .venv` and waits).
3. If Ollama is missing, it prints a Persian and English message with
   <https://ollama.com/download>, then waits so you can read the window.
4. If Ollama is present, it starts Dream against the local Ollama server
   with model `qwen2.5:7b` (`cli.py --backend ollama`, the same as
   `dream --backend ollama`).

Install [Ollama](https://ollama.com/download) and open it once so it is
running. Pull the default model if you have not:

```bat
ollama pull qwen2.5:7b
```

Other Windows scripts are **not** the first-run path:

| Script | Role |
| --- | --- |
| `run.bat` | **Primary.** Local Ollama CLI, no VPN. |
| `check.bat` | Offline diagnostics (`python doctor.py`). |
| `Dream.bat` | Experimental desktop window (`desktop.py`). |
| `Dream-Start.bat` | Same desktop window, also loads `.env`. |

Every `.bat` pauses on error so the black window stays readable.

## 1. Install (any OS)

```bash
python -m venv .venv
. .venv/bin/activate              # Windows: .venv\Scripts\activate
python -m pip install -e .
```

`run.bat` runs that install for you on Windows (`pip install -e .`).

Optional extras — install only what you need:

```bash
python -m pip install -e ".[web]"    # FastAPI + uvicorn web gateway
python -m pip install -e ".[data]"   # nbformat notebook tooling
python -m pip install -e ".[dev]"    # pytest + ruff for contributors
```

You can combine extras: `python -m pip install -e ".[web,data]"` or
`python -m pip install -e ".[dev,web,data]"`.

## 2. Run the offline demo (no key, no network)

```bash
dream --demo
```

This runs a complete conversation against the built-in **echo** backend — no
API key and no network required — so you can confirm the install works and see
the memory + approval flow end to end.

## 3. Configure a real model (optional)

```bash
python doctor.py                  # verify the installation (offline)
```

`doctor.py` always prints English. If the console is UTF-8 it also prints
Persian on failures. On Windows, double-click `check.bat` for the same
offline checks.

To use a model, pick one backend:

- **Ollama (local, free, no VPN):** install from
  <https://ollama.com/download>, then `dream --backend ollama`.
  Windows: double-click `run.bat` (sets `DREAM_MODEL=qwen2.5:7b`).
- **OpenAI-compatible:** set `OPENAI_API_KEY` (and optionally
  `OPENAI_BASE_URL`) in your environment, then run `dream`.

API keys go to your operating-system keychain (Keychain Access / Windows
Credential Manager / Linux Secret Service) — they are never written to a
settings file. See [CONFIGURATION.md](../CONFIGURATION.md).

## 4. First conversation

```text
> سلام! اسم من مریم است.    (or: "Hi! My name is Mary.")
```

Dream replies in the language you used. Say `/mems` to see what it has stored,
or `/help` for the command list.

## 5. Try the desktop app

The Tauri desktop shell (the full UI) is built from `apps/desktop`:

```bash
cd apps/desktop && npm install && npm run dev
```

On Windows, `Dream.bat` opens the older experimental `desktop.py` window —
that is not the first-run path.

That's it — you're up and running in under five minutes.
