# FIX-desktop-daily — sidecar discovery, single instance + tray hygiene, layout containment, activity-rail drawer

## What this phase is

The Windows NSIS app (`Dream_0.4.0_x64-setup.exe`) passed the P0–P8 UI gates but
failed daily use on a real install. This phase fixes the four owner-measured
breakages, in priority order:

1. **Bundled sidecar discovery** — stock install still needed
   `DREAM_SIDECAR_PYTHON` + a PowerShell launch to start the engine.
2. **Single instance + tray hygiene** — every open/close cycle left two Dream
   icons under Windows "Show hidden icons"; each had to be Quit by hand.
3. **Layout containment** — Settings language description ran through the
   locale chips; status/provider banners collided with their actions.
4. **Activity-rail drawer** — the icon-only rail is now an honest three-mode
   drawer (collapsed / expanded / hover+pin).

Security first, fail closed, no invented prices, every new string EN+FA, RTL
via logical CSS only, zero regressions.

## Author

Ali Naderi <alinaderi@users.noreply.github.com> — no Co-authored-by.

## Commit

Branch: `arena/01a03c96-dream` (from `origin/main` at `877e0662a8e64c6db5052f47a2d6c43870062108` / v0.4.0, #93).
No force-push. No PR opened. No version bump, no release tag.

## Delivered

### A — Windows bundled sidecar discovery (`bridge/process.rs`, `bridge/mod.rs`)

`bundled_interpreter_paths` now probes, in order, **every path that exists as a
file**:

1. `{resource_dir}/python/python.exe` — standard Tauri resource layout;
2. `{resource_dir}/python.exe` — when the resource dir *is* the python dir;
3. `{exe_dir}/resources/python/python.exe` — **the measured NSIS layout**
   (`C:\Program Files\Dream\dream-desktop.exe` + `resources\python\python.exe`);
4. `{exe_dir}/python/python.exe`;
5. the same two layouts one level above `exe_dir` (binary in a subfolder of the
   install root, e.g. `bin\dream-desktop.exe`).

Every candidate that is not an existing file is logged with `log::warn!` and
the reason it was skipped, so a stock-install miss is diagnosable from the app
log alone. Duplicates (`resource_dir == exe_dir/resources`) are collapsed.
`DREAM_SIDECAR_PYTHON` remains a hard override (never shadowed by discovery),
and bundled spawns still set `PYTHONNOUSERSITE=1` + `PYTHONUTF8=1`.

New unit tests mirror the real install tree
(`Program Files/Dream/dream-desktop.exe` + `resources/python/python.exe`) and
assert the NSIS path is **first** when `resource_dir` is missing or wrong, plus
the new ordering and the parent-of-exe_dir layouts.

`bridge::kill_bridge_on_quit` is the kill-on-quit hook used by teardown.

### B — Single instance + tray hygiene (`single_instance.rs` new, `lib.rs`, `commands/tray.rs`, `tauri.conf.json`)

- **One process, one tray icon.** `tauri-plugin-single-instance` is blocked
  (crates.io unreachable from the release environment), so a dependency-free
  fallback was implemented:
  - **Windows**: per-session named mutex `Local\DreamDesktop.SingleInstance`
    via a minimal direct FFI to `kernel32` (`CreateMutexW`/`GetLastError`/
    `CloseHandle` — no new crates). The handle is deliberately leaked for the
    process lifetime (the kernel object dies with the process).
  - **Other platforms**: PID lockfile in the app data dir with stale-lock
    recovery (`kill(pid, 0)` liveness probe; EPERM counts as alive).
  - A second launch **writes a `focus-request` marker, hides its window, and
    exits**; the primary's watcher thread (400 ms poll) shows and focuses the
    main window. Markers are cleaned on startup and on quit, so a stale marker
    never self-focuses.
- **Close with `close_to_tray == false` (the default) now really quits**:
  destroy the tray icon → `bridge_kill` the sidecar → clean single-instance
  markers → `app.exit`. No leftover icon, no surviving Python child.
- **Tray-menu Quit uses the same teardown** (`crate::teardown_and_exit`).
- **Close-to-tray (opt-in)**: hide only; exactly one icon, never re-created.
- **Root causes removed**: the config-level `trayIcon` block in
  `tauri.conf.json` (a second builder for the same `TRAY_ID`) was deleted —
  `commands::tray::init` is the only builder; and the Settings page's
  `closeToTray` UI default was `true` and pushed itself to Rust on mount,
  silently flipping quit-on-close to hide-to-tray after one visit — it now
  defaults to `false`, matching `state.rs`.
- Tests: `close_to_tray` default snapshot already asserted and extended;
  lockfile acquire → secondary → cleanup → primary cycle; stale-lock takeover;
  focus-marker write/parse; marker cleanup. Windows mutex path is
  owner/CI-run (no Windows in the sandbox).

### C — Containment / no collision (`routes/settings.tsx`, `styles/theme.css`, banners)

- **Settings `Row`**: stacks label above controls on narrow widths
  (`flex-col` → `md:flex-row`); description wraps inside its own column
  (`min-w-0` + `break-words`, capped at 45% on wide rows); the control column
  is a wrapping flex capped at 55% (`min-w-0 flex-wrap md:max-w-[55%]`) so the
  locale chips wrap inside their own area — never through the label or across
  the row boundary. All logical properties (`md:gap-6`, no physical margins).
- **Banners**: `.bridge-banner` gains a containment contract — text column
  `flex:1 1 0% / min-width:0 / overflow-wrap:anywhere`, action pinned to the
  inline-end edge (`margin-inline-start:auto`), `flex-wrap` as the last resort
  so a single unbreakable token can never overlap the action. Same treatment
  for `BridgeOfflineBanner` (`flex-wrap` + `break-words` + `ms-auto`).
- Component tests assert the DOM contract (description and chips in sibling
  flex children of the row; banner text/action in separate flex children).

### D — Activity rail drawer (`activity-rail.tsx` + tests, `use-app-store.ts`, `types.ts`, locales)

Three honest modes, persisted in the existing app store (`dream.app`, v3 —
old payloads normalised by `migrateAppState`):

| Mode | Behaviour |
| --- | --- |
| `collapsed` | icon-only at the historical width, tooltip on hover (kept) |
| `expanded` | wider rail (w-44), icon + visible `t(labelKey)` label |
| `hover` (default) | collapsed until the pointer enters the rail; expands; collapses on leave unless pinned |

- Pin control (bottom of rail, `aria-pressed`): pin open ⇄ unpin; from
  `collapsed` pinning arms hover so it takes effect immediately; in `expanded`
  it is the collapse affordance (back to hover-peek).
- Mode cycle control (chevron/Eye, `aria-label` + `title` from
  `common.rail.*`, EN + FA + all 8 locales through `generate-locales.mjs`).
- Labels come from the existing `nav.*` keys in all 8 locales — no second
  copy. Tooltips only when collapsed ("labels not tooltip-only when expanded").
- Keyboard: links and controls remain focusable; `<nav aria-expanded>`
  reflects the effective state; P0 `registeredNav` items still listed.
- RTL: rail stays on the inline-start edge (`border-e`); labels follow icons
  with a logical `gap-3`; the width transition is in-flow (`transition-[width]`
  + `duration-fast`), so `app-shell.tsx` needed no change.

## Change surface

Owned / extended:

- `apps/desktop/src-tauri/src/bridge/process.rs` — discovery order + logging + tests
- `apps/desktop/src-tauri/src/bridge/mod.rs` — `kill_bridge_on_quit`
- `apps/desktop/src-tauri/src/single_instance.rs` — new (mutex/lockfile + focus handoff)
- `apps/desktop/src-tauri/src/lib.rs` — setup single-instance wiring, close/quit teardown
- `apps/desktop/src-tauri/src/commands/tray.rs` — Quit → shared teardown
- `apps/desktop/src-tauri/src/tests.rs` — close_to_tray coverage
- `apps/desktop/src-tauri/tauri.conf.json` — removed the second tray builder
- `apps/desktop/src/components/layout/activity-rail.tsx` (+ `activity-rail.test.tsx`)
- `apps/desktop/src/routes/settings.tsx` (+ containment test), `styles/theme.css`
- `apps/desktop/src/components/bridge/bridge-disconnected-banner.tsx` (+ test),
  `apps/desktop/src/components/shared/bridge-offline-banner.tsx`
- `apps/desktop/src/stores/use-app-store.ts` (+ tests), `src/types/index.ts`
- `apps/desktop/scripts/generate-locales.mjs` + 8 locale `common.json` (new `rail.*` keys — required)
- `docs/handoff/FIX-desktop-daily.md`, `docs/handoff/FIX-desktop-daily-GATES.md`

Untouched (forbidden list honoured): `dream/**`, `client.ts`, `cli.py`,
`generate-locales.mjs` only for the required new keys, no version bump, no
release tag, no new route (`export default` + `*.route.ts` untouched), echo
still via `transportKind === 'echo'`.

## Owner-run (not faked)

- Windows NSIS smoke on a real install (`Dream_0.4.0_x64-setup.exe`):
  stock Start-Menu launch discovers `resources\python\python.exe` with **no**
  `DREAM_SIDECAR_PYTHON`; second launch focuses the running window and exits;
  X/Quit leaves zero tray icons; `Show hidden icons` stays clean after 5
  open/close cycles.
- `cargo test` / `cargo clippy --all-targets -- -D warnings` /
  `cargo fmt --check` — the sandbox has no Rust toolchain and no crates.io
  access; the Windows mutex path is exercised on Windows CI.
