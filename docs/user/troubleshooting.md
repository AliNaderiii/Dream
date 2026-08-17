# Troubleshooting

| Symptom | Cause | Solution |
| --- | --- | --- |
| `dream` not found | venv not active / not installed | `. .venv/bin/activate` then `pip install -e ".[dev]"` (Windows: `.venv\Scripts\activate`) |
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
