# Dream Desktop Shell

Tauri 2 + React 19 + TypeScript + Tailwind CSS v4 desktop application for Dream.

This is the **desktop layer only**. The Python package in `dream/` is untouched;
the IPC bridge to it arrives in P-02.

## Requirements

- Node.js 22+
- Rust stable (1.77.2+)
- Linux only: `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf libgtk-3-dev libsoup-3.0-dev libjavascriptcoregtk-4.1-dev`

## Commands

| Command | Purpose |
| --- | --- |
| `npm run dev` | Vite dev server (browser only, no native APIs) |
| `npm run tauri dev` | Full desktop app with hot reload |
| `npm run tauri build` | Produce installers for the host platform |
| `npm run typecheck` | `tsc --noEmit`, strict mode |
| `npm run lint` | ESLint (type-aware) |
| `npm test` | Vitest unit + component tests |
| `npm run icons` | Regenerate app icons from `src-tauri/icons/source-icon.png` |

The shell runs in a plain browser too: every native call in `src/lib/tauri.ts`
falls back to a safe default when `window.__TAURI_INTERNALS__` is absent, so UI
work and tests need no Rust toolchain.

## Layout

```
src-tauri/            Rust backend
  src/commands/       window, tray, notifications, dialogs
  src/state.rs        app state (agent status, approvals, workspace root)
  src/error.rs        serializable error type for all commands
  capabilities/       permission allowlist (security boundary)
src/
  routes/             one file per screen
  components/layout/  title bar, activity rail, sidebar, top bar, status bar
  components/ui/      Shadcn-style primitives
  stores/             Zustand: app, session, provider
  hooks/              theme, shortcuts, native bridge, file drop
  styles/theme.css    design tokens as Tailwind v4 @theme
```

## Design tokens

`src/styles/theme.css` mirrors `docs/design/tokens/dream.css` from the P-00
design package, re-expressed for Tailwind v4 so tokens are reachable as
utilities (`bg-canvas`, `text-fg-primary`, `shadow-e2`). Themes are driven by
`data-theme` on `<html>`; direction by `dir`. Both are owned by `useTheme()`.

## Security

- CSP is set explicitly; `default-src 'self'`, no remote script origins.
- The capability file grants only what the shell needs. There is **no**
  `shell:allow-execute`, no `fs:allow-*` scope, and no HTTP plugin.
- Every filesystem path from a dialog or drag-drop is canonicalized in Rust and
  checked against the workspace root before it reaches the frontend.

## Updater

`tauri.conf.json` carries the updater **public** key. Updater artifacts are
signed in CI with `TAURI_SIGNING_PRIVATE_KEY` and are only produced when that
secret exists (see `tauri.release.conf.json`). The Windows installers
themselves are **unsigned** unless an Authenticode certificate is configured,
so SmartScreen may warn on first run. The private key generated during
development is intentionally **not** committed.
