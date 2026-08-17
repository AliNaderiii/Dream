# Performance Budget

Measured end-to-end (not synthetic). Worst-case targets for the 0.2.0 release.

| Metric | Target |
| --- | --- |
| Cold start (icon click → UI ready) | < 5 s |
| Idle memory (single window, no conversation) | < 200 MB |
| Conversation memory (10 000 messages) | scroll 60 fps, load < 2 s |
| 1 GB CSV load (data workbench) | < 30 s |
| Docker sandbox cold start (image pull) | documented — installer bandwidth, not a runtime goal |
| Bridge throughput (1 000 sequential RPCs) | p50 < 5 ms, p95 < 30 ms |
| Bundle size | no regression vs. the current `apps/desktop/dist/` |

## Techniques in use

- **Code-splitting** — the data workbench, connectivity, provenance and the
  subagent dashboard load via `React.lazy()` + `Suspense`, so the shell paints
  before their chunks arrive (`apps/desktop/src/App.tsx`).
- **Virtualisation** — TanStack Table virtualisation (introduced in P-09) is
  used for the data grid; chat transcripts use windowed rendering to keep
  10 000-message conversations at 60 fps.
- **Fast cold start** — the Tauri window is created off-screen and shown on
  first paint; the sidecar is spawned once and reused.
- **Bundle audit** — `vite build --analyze` runs in the perf workflow and
  fails on size regressions.

## CI smoke

`.github/workflows/perf.yml` builds the app on every PR and, on Linux under
`xvfb`, launches the app and measures time-to-first-paint against the committed
baseline in `apps/desktop/src-tauri/perf-baseline.json`. A regression of more
than 10% fails the PR.

## How to re-baseline

After an intentional optimisation, update
`apps/desktop/src-tauri/perf-baseline.json` with the new measured median and
note it in the changelog.
