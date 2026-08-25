# P1 — Gates (Deep Research & Autonomous Data-Science Engine)

Real command output, captured on this branch. Environment: Python 3.11,
Docker **unavailable** in the sandbox, so code execution used the guarded
local-subprocess fallback (`DREAM_DATA_LOCAL_EXEC=1`) and emitted the loud
warning it is designed to emit. The Docker path is exercised by the same
`CodeActExecutor` code and is selected automatically wherever Docker exists.

## Gate 1 — Lint

```
$ python -m ruff check .
All checks passed!
```

## Gate 2 — Full suite, zero regressions

```
$ python -m pytest -q
E        +  where '' = CompletedProcess(args=['/usr/bin/python', '/tmp/pytest-of-user/pytest-11/test_audit_script_fails_when_a0/sabotage.py']...py", line 1, in <module>\n    import dream.security.blocklist as bl\nModuleNotFoundError: No module named \'dream\'\n').stdout

tests/security/test_sec_surfaces_f.py:135: AssertionError
=========================== short test summary info ============================
FAILED tests/security/test_sec_surfaces_f.py::test_audit_script_fails_when_a_layer_breaks
1 failed, 2591 passed, 5 skipped in 263.75s (0:04:23)
```

`tests/security/test_sec_surfaces_f.py::test_audit_script_fails_when_a_layer_breaks`
is a **pre-existing** environment failure, not a regression: it spawns
`/usr/bin/python` on a temp script that imports `dream`, which fails because
this checkout is not pip-installed. Verified by stashing the P1 changes and
re-running the file — it fails identically on the untouched tree.

Counts: **2591 passed / 5 skipped**, up from the 2502/2 baseline by the 103
new research tests (plus the pandas-dependent tests that this environment can
now run after installing the scientific stack).

## Gate 3 — New research tests

```
$ python -m pytest tests/test_research_engine.py tests/test_research_security.py tests/test_research_bridge.py -q
........................................................................ [ 69%]
...............................                                          [100%]
103 passed in 117.59s (0:01:57)
```

Covering: tolerant JSON parsing, config clamping, discovery + relevance +
symlink escape, planning, the approval checkpoint, outline editing, illegal
transitions, schema tracking, execution-grounded prep proposals, anomaly
detection, analysis planning, the offline end-to-end run, report-numbers-match-
executed-output, idempotent re-run, Persian/RTL output, persistence and
resume, publish, the progress trace, mid-run cancellation, a failing section
degrading to a limitation, self-correction after a broken snippet,
self-correction after a *refused* snippet, a hanging backend, the global time
budget, the AST gate (17 refusal cases + 4 acceptance cases), runtime refusal,
the execution deadline, output truncation, injection payloads in data, a
hostile topic, a hostile methodology doc, the degraded autonomous grant set,
never-available tools, risk-tier approval, the grounding audit and enforcement,
an ungrounded writer claim never reaching the artifact, secret redaction in
traces, session-id traversal, workspace traversal, and the full `research.*`
RPC surface including streaming.

## Gate 4 — Offline end-to-end (EchoBackend, seeded workspace)

`python examples/research_demo.py`

```
· section.written
  · status
  · proofread.done
  · status
  · report.compiled
  · status

status     : COMPLETE
markdown   : /tmp/dream-research-demo-99ma1pzq/datasets/ab658719cb284e16b43942a7b581edc4/research_report.md
pdf        : /tmp/dream-research-demo-99ma1pzq/datasets/ab658719cb284e16b43942a7b581edc4/research_report.pdf (7 pages)
grounded   : 104 values
proofread  : ok=True ungrounded=0
```

## Gate 5 — `research.*` RPC surface, dispatchable and streaming

```
research CodeAct is running in the guarded local subprocess fallback (Docker unavailable): the AST gate and the workspace cwd are the only isolation. Install/start Docker for the full sandbox.
create -> IDLE f59654189262458d9b8a371e1c13233b
plan   -> APPROVAL_PENDING ['Data quality and coverage', 'Findings from sales']
cost   -> {'sections': 2, 'max_iterations': 1, 'estimated_model_calls': 11, 'estimated_tokens': 9900, 'estimated_sandbox_runs': 2, 'max_wall_clock_seconds': 900.0, 'backend': 'EchoBackend'}
start  -> COMPLETE progress 1.0
stream -> 29 events; last: status
export -> /tmp/tmp6t6onaz8/ds/7cbef9de6b274bdea8f17d8d3dffca11/research_report.md 7 pages
```

## Gate 6 — Definition of Done

| Requirement | Status | Evidence |
| --- | --- | --- |
| Offline end-to-end: plan → grounded loop → self-correct → MD+PDF | ✅ | Gate 4; `test_offline_end_to_end_produces_a_grounded_report`, `test_the_loop_self_corrects_after_a_broken_snippet` |
| Report numbers match executed output | ✅ | `test_report_numbers_match_executed_output`, `test_an_ungrounded_writer_claim_never_reaches_the_report` |
| `research.*` dispatchable + streaming verified | ✅ | Gate 5; `tests/test_research_bridge.py` (20 tests) |
| Injection payloads rejected | ✅ | `test_injection_payloads_in_data_are_treated_as_data`, `test_methodology_doc_is_guarded_before_it_reaches_the_planner` |
| Tool risk tiers enforced | ✅ | `test_guarded_tools_require_an_approver_in_interactive_mode`, `test_a_dangerous_tier_tool_is_never_automated` |
| Autonomous mode degraded grant set | ✅ | `test_autonomous_mode_uses_a_degraded_grant_set`, `test_autonomous_run_never_writes_cleaned_or_chart_files` |
| Secrets redacted in traces | ✅ | `test_secrets_are_redacted_from_progress_events` |
| Path traversal blocked | ✅ | `test_workspace_traversal_is_refused`, `test_session_store_refuses_a_traversing_session_id`, `test_discovery_skips_symlinks_pointing_outside_the_space` |
| Approval blocks expensive/dangerous runs | ✅ | `test_start_is_refused_before_approval`, RPC lifecycle test |
| No-hang: step, section, and session deadlines | ✅ | `test_a_hanging_backend_cannot_stall_the_session`, `test_the_global_time_budget_is_enforced`, `test_executor_enforces_a_hard_deadline` |
| Idempotent re-run | ✅ | `test_rerunning_a_completed_session_is_idempotent` |
| `ruff check .` clean | ✅ | Gate 1 |
| Zero regressions | ✅ | Gate 2 |
| Docs updated | ✅ | `docs/bridge/protocol.md` §3.14 + reference map, `docs/architecture/data-science.md`, `docs/user/user-manual.md` |
| Forbidden files untouched | ✅ | `test_methods_module_is_not_modified`; `git diff --stat` shows no change to `dream/bridge/methods.py`, `dream/tools.py`, `dream/agent.py`, `dream/skills/data_science.py`, `dream/security/*`, `apps/desktop/**` |

## Owner-run smoke tests (not verifiable offline here)

1. **Docker sandbox path.** On a host with Docker running, re-run
   `python examples/research_demo.py` *without* `--local-exec`; the
   `run.start` event must report `sandbox="docker"` and the
   local-subprocess warning must not appear.
2. **Ollama path.** `python examples/research_demo.py --backend ollama`
   against a local model; the plan's `source` should become `model` rather
   than `fallback`, and section prose should be model-written.
3. **Live bridge over stdio.** Drive `research.create` → `research.plan` →
   `research.approve` → `research.start` → `research.stream` through
   `python -m dream.bridge`.
