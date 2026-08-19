# Troubleshooting

| Symptom | Cause | Solution |
| --- | --- | --- |
| `dream` not found | venv not active / not installed | `. .venv/bin/activate` then `pip install -e .` (Windows: double-click `run.bat`, or `.venv\Scripts\activate`) |
| Double-click confusion / many `.bat` files | more than one launcher | Use **`run.bat` only** for first run. `check.bat` is diagnostics; `Dream.bat` / `Dream-Start.bat` are the experimental desktop window. |
| Ollama-missing message (EN + FA) | Ollama is not installed or not on PATH | Download <https://ollama.com/download>, open Ollama once, then double-click `run.bat` again |
| `.venv` missing on Windows | first run, or venv create failed | `run.bat` creates it. If that fails, run the one command `python -m venv .venv` and double-click `run.bat` again |
| Need the web gateway or notebooks | optional extras not installed | Web: `pip install -e ".[web]"`. Notebooks: `pip install -e ".[data]"`. See [quick-start.md](quick-start.md) |
| "FTS5 not available" | SQLite build lacks FTS5 | Install a SQLite build with FTS5, or use the bundled `sqlite3` fallback |
| Provider returns HTTP 400 | malformed history / bad schema | update to latest; run `doctor.py`; check provider schema version |
| Persian search returns nothing | different Unicode spelling (yeh vs keheh) | Expected to work — Dream normalises; if still empty run `doctor.py` memory check |
| `run_shell` never runs | no approver in the loop | dangerous tools need an interactive approver (`--yolo` opts out at your own risk) |
| Memory writes show "store failed" | locked / unwritable DB | check disk space and file permissions of the data dir |
| Web gateway won't open on phone | wrong token / firewall | re-copy the setup token; confirm device is on the same LAN |
| Docker sandbox "unavailable" | Docker not installed/running | install Docker, ensure the daemon is up, then re-open Settings → Docker |
| Chart/report generation hangs | large dataset / first image pull | first run pulls the sandbox image (bandwidth, not a runtime bug); retry |
| App window won't start (Linux) | missing WebKitGTK | install `libwebkit2gtk-4.1` (see the release build notes) |
| UI text still English after switching | component not yet translated / stale build | restart the app; report the screen if it persists |
| `npm run dev` fails | node_modules missing | `npm install` first |
| Type errors on build | stale `tsc` cache | `npm run build` re-runs `tsc --noEmit` |

## Getting logs

Run with `--debug` for verbose logs, or `--quiet` to hide per-tool lines. Logs
redact API keys and bearer tokens automatically.
