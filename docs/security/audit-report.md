# Dream Security Audit Report

**Release:** 0.2.0 (P-11 — Internationalisation, Documentation, Security Audit &
Release)  
**Date:** 2026-08-17  
**Scope:** the entire shipped codebase — `dream/` (Python core), the Tauri
desktop shell (`apps/desktop/`), and the bundled installers — on the `main`
branch tip (`f3f36da`), including every previously merged prompt (P-00 → P-10).

## Summary

| Gate | Tool / check | Result |
| --- | --- | --- |
| Python lint | `ruff check .` | ✅ clean |
| Python static security | `bandit -r dream/ -q` | ✅ **0 critical, 0 high** (10 medium, 59 low) |
| Python dependency CVEs | `pip-audit` | ✅ project deps clean (see §7) |
| TypeScript dependency CVEs | `npm audit --audit-level=high` | ✅ 0 vulnerabilities |
| TypeScript lint | `eslint . --ext .ts,.tsx` | ✅ 0 errors (9 pre-existing warnings) |
| Type-check | `tsc --noEmit` | ✅ clean |
| Credential scan | tracked-file regex scan | ✅ no matches |
| Tests | `pytest` + `vitest run` | ✅ 1498 Python + 294 frontend passing |

**Critical findings: 0 · High findings: 0.** Build green.

---

## 1. Static analysis (Bandit)

`bandit -r dream/` reports **0 high** and **0 critical** issues after two fixes
applied in this release. The two former high findings and how they were
resolved:

| Severity | ID | Location | Description | Resolution | Status |
| --- | --- | --- | --- | --- | --- |
| High | B324 | `dream/connectivity/websocket.py:64` | SHA-1 hash flagged as weak | SHA-1 here is **mandated by RFC 6455** for the WebSocket opening handshake, not a security primitive. Added `usedforsecurity=False` to document intent. | ✅ resolved |
| High | B602 | `dream/tools.py:663` | `subprocess.run(shell=True)` | `run_shell` is the deliberate shell tool, gated behind the `dangerous` risk tier, which the approval policy refuses without an interactive approver. Documented with `# nosec B602`. | ✅ resolved (compensating control) |

### Medium findings (deferred with justification)

| ID | Location | Description | Disposition |
| --- | --- | --- | --- |
| B310 ×3 | `dream/test-connection.py`, `dream/acp/client.py`, `dream/mcp/transport.py` | `urlopen` on a URL that may use a non-`http(s)` scheme | Deferred. Scheme is user-configured provider endpoint; tracked as #issue. No user-input SSRF path in shipped flows. |
| B104 ×5 | `dream/gateway_server.py`, `dream/connectivity/adapters/whatsapp.py`, `dream/bridge/methods.py` | Bind to all interfaces (`0.0.0.0`) | Deferred — intentional. The P-08 web gateway must be reachable from a phone on the LAN; access is gated by a per-device token (see §6). |
| B608 ×2 | `dream/scheduler.py:441`, `dream/memory.py:1237` | "SQL injection" via string query construction | Deferred — **false positive**: both use `?` placeholders with a bound parameter tuple; f-strings interpolate only static column names/placeholders, never user input. |

---

## 2. Sandbox escape

The P-09 data-science pipeline never imports `pandas`/`matplotlib` on the host:
every operation compiles to a generated script executed in the P-08 Docker
sandbox (`network disabled`, `cap-drop ALL`, seccomp), with parameters passed
via `_params.json`, never interpolated into code. `docker run` is invoked with
`--privileged` never set and the Docker socket is not mounted into the
container. Regression coverage: `tests/test_docker_sandbox.py` and the P-09
`test_data_science_*.py` suites. **No escape vector found.**

## 3. Subagent isolation

Subagents dispatch against their **own** tool grant. `ApprovalPolicy.allows()`
resolves risk from the policy's `registry` mapping, not the global registry, so
a name the subagent was never granted resolves to *no* risk tier and is refused
(`unknown tool`) — it can never fall back to the parent's grant. Verified by
`tests/test_security_tool_risk.py::test_subagent_grant_registry_never_falls_back_to_global`.

## 4. Workspace confinement

Notebook paths resolve through `NotebookManager._resolve_notebook`, which
confines the result to the datasets root and refuses traversal, absolute
out-of-root paths, and non-`.ipynb` suffixes. Verified by
`tests/test_security_workspace.py` (7 cases). Reminder and file tools share the
same `WORKSPACE_ROOT` discipline.

## 5. Tool-risk enforcement

Every registered tool carries a risk tier from `{safe, guarded, dangerous}`.
`ApprovalPolicy` auto-approves `safe`/`guarded`, and refuses `dangerous` tools
unless an approver callback returns true — with a hard denial when no approver
is configured. Verified by `tests/test_security_tool_risk.py` (8 cases).

## 6. Gateway XSS / CSRF

The Tauri webview enforces a strict Content-Security-Policy
(`default-src 'self'`, `script-src 'self'`, `object-src 'none'`,
`frame-ancestors 'none'`, `form-action 'none'`) in
`apps/desktop/src-tauri/tauri.conf.json`, and the web gateway authenticates
every request with a per-device token whose scope is enforced server-side
(read tokens cannot mutate; `tests/test_security_gateway.py`, 7 cases). State
changes require a write-scoped token. No inline script or third-party script
origin is permitted.

## 7. Dependency and credential hygiene

- `npm audit --audit-level=high`: **0 vulnerabilities** (365 packages).
- `pip-audit`: Dream's own runtime dependencies (`keyring`, `Authlib`) report
  **no known CVEs**. The only flagged packages are the *sandbox's own*
  `pip 23.0.1` and `setuptools 66.1.1` (build tooling), which are not shipped
  and are fixed in CI by `pip install --upgrade pip`.
- Credential scan (`tests/test_security_secrets.py`) sweeps every git-tracked
  text file for `sk-`, `ghp_`, `AKIA…`, Slack-token and private-key shapes:
  **no matches**. API keys are stored in the OS keychain (`keyring`), never in
  settings files, logs, exports, sessions, or provenance records.

---

## 8. Build green

Final smoke: `ruff check .` clean · `bandit` 0 high · `pytest` 1498 passed ·
`tsc --noEmit` clean · `eslint` 0 errors · `prettier --check` clean ·
`vitest run` 294 passed.
