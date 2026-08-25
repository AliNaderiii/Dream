# P4 gate evidence

Date: 2026-08-25. Branch: session branch from `origin/main` at `0a9d85f`. This patch follows `279520c`; current SHA is `git rev-parse HEAD`.

## Commands and observed output

| Gate | Command | Observed result |
|---|---|---|
| P4 Python unit/security | `.venv/bin/pytest -q tests/test_workspace.py tests/test_workspace_security.py tests/test_agentmodes.py tests/test_agentmodes_security.py` | **PASS** — `39 passed in 0.32s` |
| Full Python regression | `.venv/bin/pytest -q` | **PASS** — `2477 passed, 14 skipped in 116.37s` |
| Repository Python lint | `.venv/bin/python -m ruff check .` | **PASS** — `All checks passed!` |
| Workspace desktop tests | `npx vitest run src/lib/bridge/workspace.test.ts src/routes/workspace.test.tsx src/routes/agents.test.tsx src/lib/route-registry.test.ts src/routes/projects.test.tsx --reporter=dot` | **PASS** — `Test Files  5 passed (5)` / `Tests  17 passed (17)` |
| Desktop typecheck | `npm run typecheck` | **PASS** — `tsc --noEmit` |
| Desktop lint | `npm run lint` | **PASS** — zero errors and 13 established warnings outside P4 |
| Desktop formatting | `npm run format:check` | **PASS** — `All matched files use Prettier code style!` |
| Locale integrity | `python ../../tools/check_locales.py` | **PASS** — `8 locales × 20 namespaces; 957 leaves and identical key/type/placeholder trees.` `English fallback counts: fa=0` |
| Offline probe | `.venv/bin/python tools/workspace_probe.py` | **PASS** — `copied=False`; `plan=complete`; `goal=unable`; `could not meet local CSV is readable; must fetch live market prices` |
| Secret scan | `python -m pytest tests/test_security_secrets.py -q` | **PASS** — `1 passed in 0.37s` |
| Patch whitespace | `git diff --check` | **PASS** — no output |
| Owned-surface review | `git diff --name-only` plus forbidden-path diffs | **PASS** — only approved P4 paths; no forbidden central files modified |

Author/trailer check (`python tools/check_commit.py`): **PASS** — `Commit author and trailer rules passed for HEAD!`

Live-provider smoke is **owner-run / not run here**. Plan, goal, stop, preview, and Echo acceptance are offline-deterministic.

## Raw stdout (this run)

```
$ .venv/bin/pytest -q tests/test_workspace.py tests/test_workspace_security.py tests/test_agentmodes.py tests/test_agentmodes_security.py
.......................................                                  [100%]
39 passed in 0.32s
```

```
$ .venv/bin/pytest -q
........................................................................ [  2%]
...
................................                                         [100%]
2477 passed, 14 skipped in 116.37s (0:01:56)
```

```
$ .venv/bin/python -m ruff check .
All checks passed!
```

```
$ cd apps/desktop && npx vitest run src/lib/bridge/workspace.test.ts src/routes/workspace.test.tsx src/routes/agents.test.tsx src/lib/route-registry.test.ts src/routes/projects.test.tsx --reporter=dot

 RUN  v3.2.7 /home/user/Dream/apps/desktop

·················

 Test Files  5 passed (5)
      Tests  17 passed (17)
   Duration  10.41s
```

```
$ cd apps/desktop && npm run typecheck && npm run lint && npm run format:check

> @dream/desktop@0.3.2 typecheck
> tsc --noEmit

> @dream/desktop@0.3.2 lint
> eslint .

✖ 13 problems (0 errors, 13 warnings)

> @dream/desktop@0.3.2 format:check
> prettier --check "src/**/*.{ts,tsx,css}"

Checking formatting...
All matched files use Prettier code style!
```

```
$ cd apps/desktop && python ../../tools/check_locales.py
Locale integrity: PASS — 8 locales × 20 namespaces; 957 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=372, ja=372, es=372, de=372, fr=372, ko=372; fa gate=PASS
```

```
$ .venv/bin/python tools/workspace_probe.py
PASS: copied=False; files=['projects.json', 'README.md', 'registry.json', 'sales.csv']; plan=complete; goal=unable
could not meet local CSV is readable; must fetch live market prices
```

```
$ python -m pytest tests/test_security_secrets.py -q
.                                                                        [100%]
1 passed in 0.37s
```

## Acceptance matrix

- In-place import never copies and lists real folder contents: `test_in_place_import_never_copies_and_shows_real_contents`
- CSV preview with a chart: `test_csv_preview_includes_a_chart` and workspace route test
- `../` and symlink traversal refused: `test_dotdot_traversal_is_refused`, `test_symlink_escape_is_refused`
- Preview never slurps whole files: `test_preview_read_is_capped` (256 KiB file, `Path.read_bytes` forbidden)
- `/plan` then continue: `test_plan_waits_for_continue`
- Continue RPC ignores `step_delay`: `test_continue_rpc_ignores_step_delay`
- `/goal` honest inability and checked completion: `test_goal_reports_honest_inability`, `test_goal_reports_honest_completion` (README on disk met; "teleport the files to Mars" unmet)
- `/stop` true cancel, no hang: `test_stop_cancels_a_running_plan`, `test_stop_does_not_hang`
- `@file` `#conversation` `/commands` `!shell`: `test_chat_references_parse_file_conversation_command_and_shell`
- Dangerous `!shell` never spawns, even with approval: `test_dangerous_shell_is_never_executed_even_with_approval`
- Guarded shell cannot leave the workspace root: `test_guarded_shell_refuses_parent_escape`, `test_guarded_shell_without_workspace_cwd_is_refused`
- Safe echo still auto-runs: `test_safe_echo_does_not_need_approval`
- Nested folder click lists children: workspace route `opens a nested folder on click and lists its children`
- Route registry keeps `/dataqa` and `/research` and adds `/workspace` and `/agents`

## Security and resource limits exercised

Workspace roots refuse symlink directories. Relative paths refuse `..`, absolute forms, and null bytes. Preview opens files in binary mode and reads at most 64 KiB (`PREVIEW_BYTES + 1`); office members use `ZipFile.open` then a capped read. `!shell` classifies risk, disables network, uses `shell=False`, never falls back to `Path.cwd()`, and refuses the dangerous tier even when `approved: true`. Guarded commands require a registered workspace root and `resolve_inside` for every path argument.

## Provider smoke status

Live-provider smoke is **owner-run / not run here**. The shipped planner, goal reporter, probe, and browser Echo path require no provider. This is not represented as a live-provider pass.
