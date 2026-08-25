# P5 gate evidence (Providers UI slice)

Date: 2026-08-25. This slice is the providers-page upgrade: local runtimes, catalog, optional tool gateway, diagnostics, echo wrappers, and eight locale files.

Live vLLM / SGLang / llama.cpp / LM Studio adapters were not installed here. The hermetic path is the echo runtime plus mock wire tests. Owner-run smoke for those stacks is still outstanding.

## Commands and observed output

| Gate | Command | Observed result |
|---|---|---|
| Provider hubs unit + a11y | `npx vitest run src/components/providerhubs src/lib/i18n/namespaces.test.ts --reporter=verbose` (in `apps/desktop`) | **PASS** — 3 files, 14 tests, 5.05s. Includes axe on the panel (`violations=[]`), echo doctor test, gateway toggle, vLLM fix hint, Persian privacy lines, and `hosted → aval → ollama → byok → echo`. |
| Desktop typecheck | `npm run typecheck` | **PASS** — `tsc --noEmit` |
| Desktop lint (owned files) | `npx eslint src/components/providerhubs src/lib/bridge/providerhubs.ts src/lib/bridge/echo-providerhubs.ts src/routes/providers.tsx` | **PASS** — zero errors |
| Desktop formatting | `npm run format:check` | **PASS** — `All matched files use Prettier code style!` |
| Locale integrity | `npm run locales:check` | **PASS** — `8 locales × 19 namespaces; 957 leaves and identical key/type/placeholder trees.` `fa=0`; fa gate=PASS |
| Patch whitespace | `git diff --check` | **PASS** — no output |
| Owned-surface review | `git status --short` plus forbidden-path diffs | **PASS** — only the P5 UI/docs paths below; no edits to `dream/bridge/methods.py`, `App.tsx`, `activity-rail.tsx`, `app-shell.tsx`, `client.ts`, `cli.py`, `common.json`, or `route-registry.test.ts` |
| Secret-shape scan (owned files) | ripgrep for `sk-` / `ghp_` / `AKIA` shaped tokens | **PASS** — no matches |
| Python / sidecar adapters | not run | **NOT RUN** — this slice is the desktop P5 UI. No local Python environment was present. Live runtime smoke is owner-run. |

Verbose vitest tail:

```
Test Files  3 passed (3)
     Tests  14 passed (14)
  Start at  09:30:51
  Duration  5.05s
```

Locale checker tail:

```
Locale integrity: PASS — 8 locales × 19 namespaces; 957 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=372, ja=372, es=372, de=372, fr=372, ko=372; fa gate=PASS
```

## Acceptance matrix (this slice)

- Echo lists Ollama, vLLM, SGLang, llama.cpp, LM Studio, and generic.
- Ollama is recommended, detected, and passes the bounded doctor test (`6 ms`, no secrets).
- Generic fallback parser is flagged `reduced_reliability`.
- vLLM diagnosis returns `--enable-auto-tool-choice --tool-call-parser qwen`.
- Tool gateway is optional, off by default, and not required for local chat.
- Route priority is fixed: hosted → aval → ollama → byok → echo.
- Catalog filter is honest; Persian privacy sentences render when locale is `fa`.
- Real-transport wrappers emit `providerhubs.*` single-segment method names.

## Files in this slice

- `apps/desktop/src/lib/bridge/providerhubs.ts`
- `apps/desktop/src/lib/bridge/echo-providerhubs.ts`
- `apps/desktop/src/components/providerhubs/**`
- `apps/desktop/src/routes/providers.tsx` (seam only: mounts `ProviderHubsPanel`)
- `apps/desktop/src/locales/<lang>/providerhubs.json` (en, fa, zh-CN, ja, es, de, fr, ko)
- `docs/dev/api/providerhubs-rpc.md`
- `docs/handoff/P5.md`
- `docs/handoff/P5-GATES.md`
