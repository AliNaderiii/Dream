# SEC — Gate evidence (mirrors MEM-GATES.md: real command output only)

**Branch:** `arena/01a03293-dream` · **Base:** `8e4dc9e` (verified below:
`git log` shows `8e4dc9e feat(memory): MP-02 Stage F — desktop surfaces,
bridge error paths, close-out (#79)`) · **Date:** 2026-08-24 · Commands ran
from the repository root unless an `apps/desktop` working directory is shown.
No claim below lacks pasted output.

---

## Step 0 — baseline verification (before any code)

Base commit verified:

```text
$ git log --oneline -1
8e4dc9e feat(memory): MP-02 Stage F — desktop surfaces, bridge error paths, close-out (#79)
```

Python (disposable ignored `.venv` from `.[dev]` — no dependency or lockfile changed):

```text
$ .venv/bin/pip install -e ".[dev]"
Successfully built dream-assistant
Successfully installed Authlib-1.7.2 SecretStorage-3.5.0 … dream-assistant-0.2.0 …

$ .venv/bin/python -m pytest -q
1945 passed, 11 skipped in 81.72s (0:01:21)

$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/python tools/check_suite_count.py
Suite count check passed: 1948 tests collected (minimum required: 652).

$ .venv/bin/python tools/check_locales.py
Locale integrity: PASS — 8 locales × 15 namespaces; 760 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=372, ja=372, es=372, de=372, fr=372, ko=372; fa gate=PASS
```

Matches the required baseline (1945/11, 1948 collected, 15 namespaces /
760 leaves / fa=0) exactly.

Desktop, in `apps/desktop` after `npm ci`:

```text
$ npm run typecheck        # exit 0

$ npm run lint
✖ 11 problems (0 errors, 11 warnings)

$ npm run format:check
All matched files use Prettier code style!

$ npm test
 Test Files  73 passed (73)
      Tests  609 passed (609)

$ npm run build
dist/assets/index-CHfkUxPY.js                203.87 kB │ gzip: 62.05 kB
dist/assets/react-vendor-BSOUYUyy.js         255.94 kB │ gzip: 83.25 kB
✓ built in 6.57s
# entry 62.05 kB gzip (≤ 63.22 budget); largest chunk 249.94 KiB (< 500 KiB budget)

$ npm run performance:check
"pass": true

$ npm run accessibility:check
reduced_motion_os=PASS reduced_motion_manual=PASS
 Test Files  3 passed (3)
      Tests  13 passed (13)   # 9 surfaces, 0 axe violations

$ npm run tokens:check
Tokens Studio schema-compatible import: PASS — 12 sets, 208 tokens, 12 themes.
Contrast gate: PASS — 108 AA checks.
Light muted/canvas ≥5.0: PASS — Violet 5.47:1, Ocean 5.47:1, Forest 5.47:1, Ember 5.47:1.
```

Baseline green; **no deltas**; proceeding was authorised by the mission brief.

---

# Gate A — threat model & audits

Implementation: [`SEC-A.md`](./SEC-A.md) · Files:
`docs/security/threat-model.md` (new), `docs/handoff/SEC-A.md` (new),
this file (new). **No code changed; no existing test edited; `apps/desktop`
and `.github` untouched.**

## A.1 — Layer-to-code mapping verified by reading the cited code

Every "present" claim in the threat model was verified at `8e4dc9e` by
reading the cited module (not by trusting prior documentation):

- L1: `dream/connectivity/auth.py` (single-use 10-min link codes,
  `secrets.compare_digest`), `ratelimit.py` (per-`(platform, user_id)`
  minute window), `gateway.py` pipeline (log → pre-auth → `is_linked` →
  rate → agent), `gateway_server.py` token scopes/rotation.
- L2: `dream/tools.py` (`RISKS`, three-tier registry), `dream/agent.py`
  `ApprovalPolicy.allows` (hard deny without approver), `execute()`
  fail-closed for dangerous without `approved=True`.
- L3: absent by inspection — `run_shell` forwards to `shell=True` behind
  approval only; no pre-approval floor exists. Gap SEC-G-08.
- L4: `dream/tools.py:_safe_path` (workspace confinement, reserved device
  names after Persian folding, trailing dot/space rules).
- L5: absent by inspection — no directive scanning; only adjacent controls
  (response caps, markup stripping, catalog bodies withheld). Gaps
  SEC-G-12/13.
- L6: **leak confirmed** — `dream/mcp/transport.py:69`
  `merged_env = dict(os.environ)` reaches every MCP child. Gap SEC-G-14.
- L7: `dream/subagents.py` grant builder (dangerous dropped,
  `INSTANCE_BOUND_TOOL_NAMES` identity check, approver-less child policy);
  schedules live in SQLite tables (`dream/scheduler.py:ensure_schedule_tables`).
- L8: `dream/bridge/server.py` (`DEFAULT_MAX_LINE_BYTES` 10 MiB),
  `dream/bridge/methods.py` per-method boundary validation, gateway headers
  (`X-Content-Type-Options`, `X-Frame-Options: DENY`, HSTS, default CSP);
  legacy `desktop.py` (1,570 lines) flagged for quarantine/removal (SEC-G-25).

## A.2 — Gap register

25 gaps (`SEC-G-01`…`SEC-G-25`), every one assigned to a stage (B–F) and a
sub-agent owner in [`SEC-A.md`](./SEC-A.md). Zero unassigned.

## A.3 — Suites re-verified at the Stage-A tree state

```text
$ .venv/bin/python -m pytest -q
1945 passed, 11 skipped in 82.39s (0:01:22)

$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/python tools/check_suite_count.py
Suite count check passed: 1948 tests collected (minimum required: 652).

$ .venv/bin/python tools/check_locales.py
Locale integrity: PASS — 8 locales × 15 namespaces; 760 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=372, ja=372, es=372, de=372, fr=372, ko=372; fa gate=PASS

$ .venv/bin/python -m pytest tests/test_m16_escaping.py tests/test_m16_conditional_assertions.py \
    tests/test_security_tool_risk.py tests/test_security_workspace.py \
    tests/test_security_gateway.py tests/test_security_secrets.py -q
31 passed in 17.28s
```

Docs-only stage: test counts unchanged (1945/11 collected 1948), machine
gates green, desktop and workflows untouched.

## Gate A decision

**GREEN.** Eight-layer threat model merged with verified code mapping;
25-gap register fully assigned; baseline and re-run suites identical to the
required numbers. Stage B (L3 hardline blocklist + L2 approval engine v2)
may begin.
