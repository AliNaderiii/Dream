# FIX — sidecar UTF-8, writable data root, tzdata

Owner-measured on the v0.4.1 installer (2026-08-26).

## Defects

1. `DREAM_SIDECAR_PYTHON` skipped the bundled env block, so Windows used
   cp1252. `conversation.send` with `سلام` returned
   `'charmap' codec can't encode characters`.
2. Relative `data/` under the Start Menu cwd (`C:\Program Files\Dream`)
   cannot be created. The sidecar exited before `DREAM-PROTOCOL`.
3. Embeddable CPython has no IANA database. `get_datetime(Asia/Tehran)`
   raised `ZoneInfoNotFoundError`.

## Fix

- `sidecar_python_env`: always `PYTHONUTF8` + `PYTHONIOENCODING`;
  `PYTHONNOUSERSITE` still bundled-only. Override of the bundled exe is
  still marked bundled.
- `sidecar_data_root` / `ensure_sidecar_data_root`: cwd =
  `%LOCALAPPDATA%\Dream` (`DREAM_HOME` wins).
- `tzdata` in `pyproject.toml`; bundle smoke imports `ZoneInfo('Asia/Tehran')`.
- `get_datetime` falls back to the host offset if the zone is missing.

## Gates

- `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib`
- `python -m pytest tests/test_get_datetime_tzdata.py tests/test_datetime_tool_locale.py`
- `python -m ruff check dream/tools.py`
