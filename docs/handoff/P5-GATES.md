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
| Python / sidecar adapters | see Backend section | **PASS** — added after the UI slice. |

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

## Backend section (sidecar)

Date: 2026-08-25. Implements `dream/providerhubs/**` and `dream/bridge/methods_providerhubs.py` against the existing UI RPC contract. Desktop providerhubs components and locale files were not rewritten.

| Gate | Command | Observed result |
|---|---|---|
| New Python tests | `.venv/bin/python -m pytest -q tests/test_providerhubs.py tests/test_providerhubs_security.py tests/test_toolcall_parsers.py` | **PASS** — `25 passed in 4.72s` |
| Full Python regression | `.venv/bin/python -m pytest -q` | **PASS** — `2463 passed, 14 skipped in 111.22s` |
| Ruff (owned Python) | `.venv/bin/ruff check dream/providerhubs dream/bridge/methods_providerhubs.py tools/runtime_probe.py examples/runtime_demo.py tests/test_providerhubs.py tests/test_toolcall_parsers.py tests/test_providerhubs_security.py` | **PASS** — `All checks passed!` |
| Syntax | `.venv/bin/python -m compileall -q dream/providerhubs dream/bridge/methods_providerhubs.py tools/runtime_probe.py examples/runtime_demo.py` | **PASS** — no output |
| Offline demo | `.venv/bin/python examples/runtime_demo.py` | **PASS** — route `hosted → aval → ollama → byok → echo`; catalog 8; Ollama firing; vLLM/SGLang/llama.cpp/LM Studio not firing with documented flags; generic reduced-reliability fallback parsed `search`; gateway optional |
| Handler namespace | import `HANDLERS` | **PASS** — 11 keys, all `providerhubs.*`, matching the UI method list |
| Secret-shape scan (backend files) | ripgrep for `sk-` / `ghp_` / `AKIA` shaped tokens | **PASS** — no matches |
| Forbidden-path review | diffs of `methods.py`, `App.tsx`, `client.ts`, `cli.py` | **PASS** — unchanged |

Demo tail:

```
route ['hosted', 'aval', 'ollama', 'byok', 'echo']
catalog 8
ollama firing= True fix= Ollama tool calling is on by default.
generic firing= True fix= This endpoint has no native tools. Dream will parse structur
parsed [{"id": "", "name": "search", "arguments": {"q": "tehran"}, "source": "qwen"}]
gateway optional True
handlers 11
```

Live vLLM / SGLang / llama.cpp / LM Studio processes were not installed. Adapter chat/list/health is proven against a local mock compatible endpoint. Owner-run smoke for those stacks remains outstanding.
