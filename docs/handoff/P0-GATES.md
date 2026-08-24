# P0 gate evidence

Recorded in this clean agent checkout on 2026-08-24:

| Command | Result |
| --- | --- |
| `python -m pytest tests/test_bridge_methods.py -q` | Blocked: `/usr/bin/python: No module named pytest` |
| `python -m ruff check dream/bridge/extensions.py dream/extensions/__init__.py dream/bridge/methods.py` | Blocked: `/usr/bin/python: No module named ruff` |
| `npm --prefix apps/desktop run typecheck` | Blocked: `tsc: not found` (desktop dependencies are absent) |

No passing full-suite claim is made. Install the repository dev dependencies and
`apps/desktop` dependencies, then run the complete commands in the requested
release gate (`python -m pytest`, `python -m ruff check .`, desktop typecheck,
lint, test, accessibility, and performance checks).
