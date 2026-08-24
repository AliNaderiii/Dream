# P0 gate evidence

Run on 2026-08-24 after installing the repository extras in `.venv` with
`.venv/bin/pip install -e '.[dev]'` and desktop dependencies with
`cd apps/desktop && npm ci`.

| Command | Actual result |
| --- | --- |
| `.venv/bin/python -m ruff check .` | `All checks passed!` |
| `.venv/bin/python -m pytest` | `2420 passed, 11 skipped in 108.16s` |
| `cd apps/desktop && npm run typecheck` | Exit 0 (`tsc --noEmit`) |
| `cd apps/desktop && npm run lint` | Exit 0; 11 pre-existing warnings, 0 errors |
| `cd apps/desktop && npm test` | `77 passed`, `620 passed` in 162.70s |
| `cd apps/desktop && npm run accessibility:check` | `3 passed`, `13 passed` in 12.71s |
| `cd apps/desktop && npm run build && npm run performance:check` | Exit 0; all performance tests passed and JSON reports `"pass": true` |

The Python count differs from the reviewer host because this clean agent run
collected `2423` tests and skipped `11` under Python 3.11.2; it has zero
failures and includes the five P0 seam tests. The performance gate requires a
build first because it reads `dist/assets`; after that build it reported a
largest chunk of `249.94 KiB` against the `500 KiB` budget, palette open
`46.216 ms` against `100 ms`, route change `154.613 ms` against `300 ms`, and
cold dashboard render `379.386 ms` against `2000 ms`.
