# P3 gate evidence

Date: 2026-08-25. Branch: `arena/01a035e7-dream`. Base available in this checkout: `beac980` (the requested `b60591c` object is unavailable in the shallow/grafted history).

## Commands and observed output

| Gate | Command | Observed result |
|---|---|---|
| P3 Python unit/security | `.venv/bin/pytest -q tests/test_dataqa.py tests/test_dataqa_security.py` | **PASS** — `18 passed in 2.64s` |
| Full Python regression | `.venv/bin/pytest -q` | **PASS** — `2438 passed, 11 skipped in 107.91s`; this checkout's established baseline differs from the supplied 2,502/2 reference |
| Repository Python lint | `.venv/bin/python -m ruff check .` | **PASS** — `All checks passed!` |
| P3 Python formatting | `.venv/bin/python -m ruff format --check dream/dataqa dream/bridge/methods_dataqa.py tools/dataqa_probe.py examples/dataqa_demo.py tests/test_dataqa.py tests/test_dataqa_security.py` | **PASS** — 14 files already formatted |
| P3 Python syntax | `.venv/bin/python -m compileall -q ...` over the P3 Python paths above | **PASS** — no output |
| Bridge namespace invariant | Import `HANDLERS` and assert every key starts with `dataqa.` | **PASS** — eight handlers, all `dataqa.*` |
| Data Q&A desktop acceptance | `npx vitest run src/components/dataqa/dataqa-bridge.test.ts src/components/dataqa/dataqa-route.test.tsx --reporter=verbose` | **PASS** — two files and three real-wire/Echo/axe tests passed in 5.52s |
| Desktop regression excluding frozen P0 registry assertion | `npx vitest run --exclude src/lib/route-registry.test.ts --reporter=dot` | **PASS** — 78 files and 621 tests passed in 153.72s |
| Frozen route-registry seam | `npx vitest run src/lib/route-registry.test.ts` | **EXPECTED MERGE-TIME EXCEPTION** — one test passes and only the unchanged P0 assertion expecting no routes fails because `/dataqa` is correctly auto-discovered |
| Desktop formatting | `npm run format:check` | **PASS** — all matched files use Prettier style |
| Desktop typecheck | `npm run typecheck` | **PASS** — `tsc --noEmit` |
| Desktop lint | `npm run lint` | **PASS** — zero errors and 11 established warnings outside P3 |
| Production build | `npm run build` | **PASS** — TypeScript and Vite; 2,090 modules transformed |
| Design-token/contrast gate | `npm run tokens:check` | **PASS** — 12 sets, 208 tokens, 12 themes, and 108 AA contrast checks |
| Locale integrity | `npm run locales:check` | **PASS** — 8 locales × 17 namespaces, 789 leaves, identical key/type/placeholder trees, Persian fallback 0 |
| Accessibility/reduced motion | `npm run accessibility:check` | **PASS** — 3 files and 13 tests; all nine axe surfaces reported zero violations |
| Performance | `npm run performance:check` | **PASS** — 4 files and 24 tests; report `"pass": true` |
| Offline demo | `.venv/bin/python examples/dataqa_demo.py` | **PASS** — North mean 150.0, South mean 100.0, four rows considered, and a validated bar SVG |
| Offline probe | `.venv/bin/python tools/dataqa_probe.py` | **PASS** — three candidates; `insufficient_data` and explicit “I can't determine that from this data” uncertainty |
| Patch whitespace | `git diff --check` | **PASS** — no output |
| Owned-surface review | `git status --short` plus forbidden-path diffs | **PASS** — only the approved P3 add-only paths are present; no P1/forbidden file is modified |

The route-registry test file is intentionally untouched. Its P0 assertion freezes an empty discovered-route list and must be updated by the integration owner when P3 is merged; P3 must not hide that integration seam by editing the shared test.

The desktop suites emit pre-existing, non-fatal React `act(...)` warnings. Final performance evidence: palette 47.516 ms, warm route 140.334 ms, cold render 366.859 ms, largest chunk 249.941 KiB, retained 500-message delta 0.608 MiB, longest streaming task 0.153 ms, 11 mounted rows for 500 messages, event-loop yield true, and zero unhandled rejections.

## Acceptance matrix

- Discovery with ranked reasons and bounded profiles: `test_folder_discovery_ranks_relevant_file`
- Persian semantic schema ranking: `test_persian_semantic_schema_ranking`
- Grounding to exact average-by-region evidence and validated chart: `test_average_by_region_has_evidence_and_validated_chart`
- Composable follow-up and reset: `test_follow_up_state_and_reset` and `test_working_dataframe_filter_composes_until_reset`
- Honest missing-schema uncertainty with no invented rows: `test_missing_group_is_honest_uncertainty`
- Execution-error re-grounding and one bounded retry: `test_execution_error_is_regrounded_and_retried_once`
- Cancellation contract preserved after execution cancellation: `test_cancelled_execution_preserves_cancelled_contract`
- Trend, histogram, box, scatter, and correlation-heatmap validation: `test_explicit_chart_breadth_is_grounded`
- Bridge parameter mapping and final streamed-answer consistency: `test_bridge_streams_final_answer_and_maps_invalid_params`
- Real-transport nested session wire names: `dataqa-bridge.test.ts` proves the fixed `dataqa.sessions.*` methods bypass no namespace validation and reach the client unchanged
- Initial workspace confinement: `test_workspace_confinement`
- Post-session external-symlink replacement rejection: `test_dataset_replaced_by_external_symlink_is_rejected`
- State-directory symlink rejection: `test_state_storage_symlink_is_rejected`
- Independent worker path validation: `test_worker_independently_rejects_path_outside_workspace`
- Aggregate chart count and byte quotas: `test_chart_directory_asset_quota`
- Injection-row rejection and recursive secret redaction: `test_injection_row_rejected_and_secret_redacted`
- Watchdog/no-hang behavior: `test_worker_deadline_reports_cancelled`
- Generated-code non-execution and network-off behavior: `test_plans_are_data_not_evaluated`
- Deterministic browser Echo: `apps/desktop/src/lib/bridge/echo-dataqa.ts` uses a fixed 1,000-row sales fixture; `dataqa-route.test.tsx` proves discovery → selection → streamed answer and zero axe violations offline

## Security and resource limits exercised

Dataset confinement is checked during discovery/profiling, immediately before execution, and independently inside the isolated worker. The planner's generated Python is audit material and is never evaluated. The worker runs via `python -I` with a minimal environment, socket denial, POSIX limits where available, finite per-turn deadlines, and an outer watchdog. Suspicious instruction-like rows are excluded as data, and output/errors are recursively secret-redacted. The guarded-local fallback always warns that it is not a container boundary.

Input reads are capped at 250,000 rows and result output at 200 rows/about 1 MiB. SVGs are capped at 512 KiB each and the chart directory at 32 assets/4 MiB total; symbolic-link assets are rejected. Persisted sessions retain at most 20 turns, omit inline SVG copies, and have a 24 MiB serialized-state ceiling.

## Provider smoke status

Live-provider smoke is **owner-run / not run here** because no live-provider credentials were available. P3's planner, worker, probe, demo, and browser Echo acceptance are offline-deterministic and require no provider. This is not represented as a live-provider pass.
