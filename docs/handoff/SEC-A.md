# SEC-A — Threat model, audits, gap register

**Stage:** A of six (A–F) · **PR:** PR-S1 (ships with Stage B) · **Date:** 2026-08-24
**Base:** `8e4dc9e feat(memory): MP-02 Stage F — desktop surfaces, bridge error paths, close-out (#79)`
**Evidence:** [`SEC-GATES.md`](./SEC-GATES.md) Step 0 + Gate A sections (real output only).

## Deliverables

1. [`docs/security/threat-model.md`](../security/threat-model.md) — the eight-layer
   model mapped to current code at `8e4dc9e`, assets, attacker personas, trust
   boundaries, fail-closed invariant, layer→code→stage map.
2. This file — the gap register. Every gap has an owner stage and sub-agent;
   none is unassigned.
3. `SEC-GATES.md` — evidence file mirroring `MEM-GATES.md` discipline.

## Audit method

Every "present" claim in the threat model was verified by reading the cited
code at the base commit, not by trusting prior documentation. The six
sub-agent areas (SA-1…SA-6) inherit those citations. Two findings of note:

- **Confirmed leak (L6).** `dream/mcp/transport.py:69` passes the full parent
  environment to MCP children (`merged_env = dict(os.environ)`), so provider
  keys and gateway tokens reach every configured stdio server. Fixed in
  Stage C (G-14).
- **Legacy surface (L8).** `desktop.py` (1,570 lines, M22–M26) predates the
  bridge-era boundary rules and is a dormant second front end. Audited for
  quarantine-or-removal in Stage D (G-25).

## Gap register (complete; all assigned)

| ID | Layer | Gap | Stage | Owner |
| --- | --- | --- | --- | --- |
| SEC-G-01 | L1 | Per-linked-user scopes (chat-only / safe-tools / guarded-tools / admin) in `LinkedUser`, enforcement point, Settings UI | E | SA-1 RAMPART |
| SEC-G-02 | L1 | Approval-attempt rate limiting per user (not just message rate) | E | SA-1 RAMPART |
| SEC-G-03 | L1 | Constant-time comparison on gateway token verify | E | SA-1 RAMPART |
| SEC-G-04 | L2 | Auxiliary risk assessor: secondary model call, strict JSON schema (low/medium/high/catastrophic), hard timeout, default deny on timeout/error; offline/echo → deterministic pattern rules only | B | SA-2 SENTRY |
| SEC-G-05 | L2 | Modes `smart \| manual \| off`; `off` is explicit opt-in with persistent red banner + status-bar indicator | B | SA-2 SENTRY |
| SEC-G-06 | L2 | `cron_mode` and `single_query_mode` default deny | B | SA-2 SENTRY |
| SEC-G-07 | L2 | Durable approval history (feeds Stage F Security Center) | B | SA-2 SENTRY |
| SEC-G-08 | L3 | Data-driven hardline blocklist (`dream/security/blocklist.py`): evaluated before approval, non-overridable; filesystem wipes, fork bombs, `mkfs` on mounted root, raw block-device writes, pipe-URL-to-shell; full Windows corpus (`rd /s /q C:\`, `format`, registry-hive deletes, PowerShell); bilingual refusal naming the matched class; obfuscation corpus (quoting, env expansion, path normalization, homoglyphs via the Persian normalizer) | B | SA-2 SENTRY |
| SEC-G-09 | L4 | Sensitive-path denylist for every write/patch/delete tool (credentials, `.ssh`, ledger, provenance, Dream data dir incl. the three MP-02 stores, system dirs, Windows known paths incl. AppData/Program Files/UNC) | C | SA-3 VAULT |
| SEC-G-10 | L4 | Permanent traversal corpus: `..`, symlinks, 8.3 short names, homoglyphs — Windows + POSIX | C | SA-3 VAULT |
| SEC-G-11 | L4 | Size-capped quarantine for deletions (move-first; restore/purge later) | C | SA-3 VAULT |
| SEC-G-12 | L5 | Injection scanner, modes `off \| warn \| strip` (default strip for hidden Unicode, warn for heuristics); scans before context entry: files, web extractions, MCP payloads, SKILL.md bodies, `/learn` material, session-search snippets, memory recall | D | SA-4 HORIZON |
| SEC-G-13 | L5 | Sanitized output enters context with a visible bilingual warning; original quarantined with a provenance entry | D | SA-4 HORIZON |
| SEC-G-14 | L6 | Allowlist-filtered environment for MCP children (strip everything not explicitly mapped) | C | SA-3 VAULT |
| SEC-G-15 | L6 | MCP tool-description sanitization before prompt entry (shares L5 scanner) | C/D | SA-3/SA-4 |
| SEC-G-16 | L6 | Per-server egress toggle | C | SA-3 VAULT |
| SEC-G-17 | L6 | Value-scanning redaction for logs, message logs, provenance, errors (`sk-`-style, JWT shapes, gateway-token prefix); never a key on the wire or in logs | C | SA-3 VAULT |
| SEC-G-18 | L7 | Cross-session store access fails closed (explicit ownership checks + tests) | E | SA-1 RAMPART |
| SEC-G-19 | L7 | Subagent + council grant-chain audit assertions (minimal grants, mechanically checked; `INSTANCE_BOUND_TOOL_NAMES` coverage) | E | SA-1 RAMPART |
| SEC-G-20 | L7 | Scheduled jobs run with a degraded grant set (no dangerous/browser/network) | E | SA-1 RAMPART |
| SEC-G-21 | L7 | Cron/schedule storage traversal hardening pinned by tests (SQLite-backed today; pins future file persistence) | E | SA-1 RAMPART |
| SEC-G-22 | L8 | Boundary-validation audit over all MP-02 families + reject-before-dispatch property test + bounded seeded bridge fuzzing | D | SA-4 HORIZON |
| SEC-G-23 | L8 | Gateway header tests (CSP/HSTS/X-Frame-Options) in the suite | D | SA-4 HORIZON |
| SEC-G-24 | L8 | Token rotation + read-only scope enforcement audit + per-token rate limits | D | SA-4 HORIZON |
| SEC-G-25 | L8 | `desktop.py` legacy window: quarantine behind explicit flag or remove, documented | D | SA-4 HORIZON |

Quality gates owned across stages: SA-5 PROOF — `tests/security/` adversarial
suite (200+ cases) grown stage by stage; `tools/security_audit.py` failing on
findings, wired to CI via a Path-B patch (`docs/handoff/*.patch`) in Stage F.
SA-6 WATCHTOWER — Security Center in Settings (Stage F), MP-01 visual
standards, fa=0, all desktop gates green.

## Gate A criteria — status

- [x] Threat model merged mapping all eight layers to current code.
- [x] Baseline verified green before any code (SEC-GATES.md Step 0).
- [x] Every gap in the register assigned to a stage and owner.

**Decision: GREEN — Stage B (L3 blocklist floor + L2 approval engine v2) may begin.**
