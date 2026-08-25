# P4 gate evidence

Date: 2026-08-25. Branch: current session branch from `origin/main` at `0a9d85f`.

## Commands and observed output

| Gate | Command | Observed result |
|---|---|---|
| P4 Python unit/security | `.venv/bin/pytest -q tests/test_workspace.py tests/test_workspace_security.py tests/test_agentmodes.py tests/test_agentmodes_security.py` | **PASS** — `33 passed in 0.27s` |
| Full Python regression | `.venv/bin/pytest -q` | **PASS** — `2471 passed, 14 skipped in 95.78s` |
| Repository Python lint | `.venv/bin/python -m ruff check .` | **PASS** — `All checks passed!` |
| P4 Python formatting | `.venv/bin/python -m ruff format --check dream/workspace dream/agentmodes dream/bridge/methods_workspace.py tools/workspace_probe.py tests/test_workspace.py tests/test_workspace_security.py tests/test_agentmodes.py tests/test_agentmodes_security.py` | **PASS** — 24 files already formatted |
| P4 Python syntax | `.venv/bin/python -m compileall -q dream/workspace dream/agentmodes dream/bridge/methods_workspace.py tools/workspace_probe.py` | **PASS** — no output |
| Bridge namespace invariant | Import `HANDLERS` and assert every key starts with `workspace.` | **PASS** — `24 handlers, all workspace.*` |
| Workspace desktop tests | `npx vitest run src/lib/bridge/workspace.test.ts src/routes/workspace.test.tsx src/routes/agents.test.tsx src/lib/route-registry.test.ts src/routes/projects.test.tsx --reporter=dot` | **PASS** — `5 passed (5)`, `15 passed (15)` |
| Desktop formatting | `npm run format:check` | **PASS** — all matched files use Prettier style |
| Desktop typecheck | `npm run typecheck` | **PASS** — `tsc --noEmit` |
| Desktop lint | `npm run lint` | **PASS** — zero errors and 13 established warnings outside P4 |
| Locale integrity | `python ../../tools/check_locales.py` | **PASS** — 8 locales × 20 namespaces, 957 leaves, identical key/type/placeholder trees, Persian fallback 0 |
| Offline probe | `.venv/bin/python tools/workspace_probe.py` | **PASS** — `copied=False`; plan=`complete`; goal=`unable`; `could not meet must fetch live market prices` |
| Patch whitespace | `git diff --check` | **PASS** — no output |
| Owned-surface review | `git status --short` plus forbidden-path diffs | **PASS** — only approved P4 add/upgrade paths; no forbidden central files modified |

Live-provider smoke is **owner-run / not run here**. Plan, goal, stop, preview, and Echo acceptance are offline-deterministic.

## Acceptance matrix

- In-place import never copies and lists real folder contents: `test_in_place_import_never_copies_and_shows_real_contents`
- CSV preview with a chart: `test_csv_preview_includes_a_chart` and workspace route test
- `../` and symlink traversal refused: `test_dotdot_traversal_is_refused`, `test_symlink_escape_is_refused`
- Preview never executes HTML/notebooks: `test_html_preview_strips_scripts`, `test_notebook_preview_does_not_execute`, `test_preview_never_executes_html`
- `/plan` then continue: `test_plan_waits_for_continue`
- `/goal` honest inability and completion: `test_goal_reports_honest_inability`, `test_goal_reports_honest_completion`
- `/stop` true cancel, no hang: `test_stop_cancels_a_running_plan`, `test_stop_does_not_hang`
- `@file` `#conversation` `/commands` `!shell`: `test_chat_references_parse_file_conversation_command_and_shell`
- Shell approval-gated, network off: `test_shell_is_approval_gated_and_network_off`, `test_dangerous_shell_is_not_executed_without_approval`
- Contribute_prompt hook: `test_contribute_prompt_hook_is_available_on_the_provider`
- Existing projects tests: `src/routes/projects.test.tsx` four cases green; Python `test_bridge_projects.py` included in full suite
- Route registry keeps `/dataqa` and `/research` and adds `/workspace` and `/agents`

## Security and resource limits exercised

Workspace roots refuse symlink directories. Relative paths refuse `..`, absolute forms, and null bytes. Symlink members that resolve outside the root are refused. Listings skip symlinks, cap at 200 names, and page with a cursor. Previews read at most 64 KiB, never execute, strip HTML script/style/handlers, and redact password/token/bearer values. `!shell` classifies risk, disables network, uses `shell=False`, and requires approval except for the safe tier.

## Provider smoke status

Live-provider smoke is **owner-run / not run here**. The shipped planner, goal reporter, probe, and browser Echo path require no provider. This is not represented as a live-provider pass.
