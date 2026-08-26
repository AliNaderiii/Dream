# FIX-desktop-daily GATES — commands run (honest)

Branch: `arena/01a03c96-dream` (from origin/main at `877e0662a8e64c6db5052f47a2d6c43870062108` / v0.4.0, #93).
Author: Ali Naderi <alinaderi@users.noreply.github.com>.
No force-push. No PR. No version bump. Owner Windows smoke is owner-run, not faked.

Environment note: this sandbox has **no Rust toolchain** and no network access
to `crates.io` / `static.rust-lang.org` (verified: `000` on both), so the cargo
gates are listed below as CI/owner-run with real commands, not faked output.
Everything that can run in the sandbox was run, with real stdout.

## Frontend (apps/desktop)

```bash
npm ci
npm run typecheck
npm run lint
npm run format:check
npm run locales:check
npm test
npm run build
npm run performance:check
npm run accessibility:check
```

Real results:

- `npm run typecheck` (`tsc --noEmit`): **PASS** — exit 0, no errors.
- `npm run lint` (`eslint .`): **PASS** — `✖ 13 problems (0 errors, 13 warnings)`.
  All 13 warnings are pre-existing react-refresh warnings in untouched files
  (`data-table.tsx`, `report-preview.tsx`, `kind-badge.tsx`, `memory-toolbar.tsx`,
  `live-trace.tsx`, `research-composer.tsx`, `virtual-list.tsx`, `skill-code.tsx`,
  `badge.tsx`, `button.tsx`, `icons.tsx`); none from owned/edited files.
- `npm run format:check`: **PASS** — `All matched files use Prettier code style!`
  (owned files written with `prettier --write`).
- `npm run locales:check`: **PASS** —
  `Locale integrity: PASS — 8 locales × 21 namespaces; 1026 leaves and identical key/type/placeholder trees.`
  `English fallback counts: fa=0, zh-CN=372, ja=372, es=372, de=372, fr=372, ko=372; fa gate=PASS`
- `npm test` (`vitest run`): **PASS** — `Test Files 91 passed (91)` / `Tests 685 passed (685)`.
  Includes new suites:
  - `activity-rail.test.tsx` (7) — P0 items listed; collapsed default; hover peek +
    collapse on leave; expanded labels; pin holds open / unpin restores peek;
    mode cycle; pin-from-collapsed arms hover.
  - `use-app-store.test.ts` — rail defaults + migration (incl. corrupt values).
  - `settings.test.tsx` — language-row containment contract (description and
    locale chips in sibling flex children; chips wrap inside their own column).
  - `bridge-disconnected-banner.test.tsx` — text column and end-edge action are
    separate flex children.
- `npm run build` (`tsc --noEmit && vite build`): **PASS** — `✓ built in 5.35s`.
- `npm run performance:check`: **PASS** — `"pass": true` (budget gate incl.
  largest chunk, unhandled rejections 0, event loop yielded).
- `npm run accessibility:check`: **PASS** — `Test Files 3 passed (3) / Tests 13 passed (13)`.

## Python (repo root)

Sandbox installed the project exactly like CI (`pip install -e ".[dev]"`) into a
fresh venv (the dataqa/security worker subprocesses run with `-I` isolated
mode, so user-site packages are invisible — a venv matches CI).

```bash
python -m pytest -q
ruff check .
python tools/check_suite_count.py
```

Real results:

- `pytest`: **PASS** — `2908 passed, 14 skipped in 116.96s` (exit 0).
- `ruff check .`: **PASS** — `All checks passed!` (ruff 0.16.4, exit 0).
- `tools/check_suite_count.py`: **PASS** —
  `Suite count check passed: 3051 tests collected (minimum required: 652).`

## Rust (apps/desktop/src-tauri) — CI/owner-run

Commands (as CI runs them) — **not runnable in this sandbox** (no rustc/cargo;
`crates.io` and `static.rust-lang.org` unreachable; apt/debian repos also
unreachable):

```bash
cargo fmt --all -- --check
cargo clippy --all-targets -- -D warnings
cargo build --verbose
cargo test --verbose
```

Code was reviewed by hand against both gates: rustfmt-style formatting
(chain breaking, 100-col, macro layout), clippy-default-clean constructs,
`unsafe` blocks carry SAFETY comments, no new dependencies (the Windows named
mutex uses direct `kernel32` FFI — `#[link(name = "kernel32")]`; the POSIX
liveness probe uses `kill(pid, 0)` via `#[link(name = "c")]`). The Windows
mutex path and the NSIS discovery are additionally covered by the unit tests
in `src-tauri/src/single_instance.rs` (lockfile cycle, stale takeover,
focus marker) and `bridge/process.rs` (NSIS mirror layout, wrong/missing
resource dir, ordering, parent-of-exe_dir), which CI will execute.

## Owner Windows smoke (owner-run, not faked)

1. Fresh `Dream_0.4.0_x64-setup.exe` install → Start Menu launch:
   UI reaches `Ready` with **no** `DREAM_SIDECAR_PYTHON` set (discovery finds
   `C:\Program Files\Dream\resources\python\python.exe`; app log shows the
   found candidate and any skipped candidates with reasons).
2. Launch again while running → existing window comes to front, second
   process exits (`single-instance: secondary` in log).
3. X with close-to-tray off (default) → process exits; zero icons under
   `Show hidden icons`; no `python.exe` child remains.
4. Tray → Quit Dream → same teardown, zero icons.
5. Settings → Window → Close to tray ON → X hides; tray shows exactly one
   icon; re-show from tray keeps exactly one.
6. Five open/close cycles → exactly one icon total.
7. Settings Language row at 100% and 150% zoom: description never runs
   through the locale chips; chips wrap inside their own rows.
8. Activity rail: default collapsed; hover peeks; pin holds open; chevron
   cycles collapsed → hover → expanded; RTL (Persian) mirrors.
