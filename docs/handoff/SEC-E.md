# SEC-E — Isolation & scopes (L1 authorization + L7 isolation)

**Stage:** E of six · **PR:** PR-S3 (with Stage F) · **Date:** 2026-08-24
**Base:** merged Stages A–D tip `d610948` (PR #80, squash-merged with
owner approval) on `arena/01a03293-dream`
**Evidence:** [`SEC-GATES.md`](./SEC-GATES.md) Gate E sections (real output only).

## What shipped

| Commit | Surface |
| --- | --- |
| `841e125` | E-1: per-linked-user scopes, approval throttling, constant-time tokens (28 tests) |
| `9df8ee4` | E-2: degraded cron grants, grant-chain assertions, fail-closed sessions, cron storage pins (33 tests) |
| this | docs + changelog |

## Gaps closed

- **SEC-G-01 (per-user scopes).** `LinkedUser.scope` ∈
  `chat_only | safe_tools | guarded_tools | admin`; existing users keep
  `admin` (pre-scope behaviour changes only by explicit owner decision).
  `AuthStore` validates (`validate_scope`), persists, falls back safely on
  unknown stored values, and reports `scope_of`. `ApprovalPolicy` gains a
  ceiling gate: **after the floor** (the floor precedes every gate), tools
  above the scope's ceiling are refused naming the scope. The connectivity
  gateway applies the LIVE scope per turn — an owner's change takes effect
  without a session reset. Bridge surface (append-only): new
  `gateway.set_user_scope` (boundary-validated: types, non-empty ids, scope
  ∈ set, unknown users refused) and `gateway.linked_users` rows carry the
  scope. The Settings UI control ships with the Stage F Security Center.
- **SEC-G-02 (approval-attempt throttle).** `ApprovalAttemptLimiter`
  (fixed-minute window, 10/min default) wired into the policy for dangerous
  tools that passed floor and scope. Floor-blocked and scope-blocked
  attempts spend no budget (pinned); the next window restores it.
- **SEC-G-03 (constant-time tokens).** `TokenManager.verify_token`
  compares every stored token with `secrets.compare_digest` — timing never
  depends on how much of a guess is right; rotate/revoke/scope semantics
  pinned unchanged; near-miss prefixes refuse.
- **SEC-G-18 (cross-session fail-closed).** Every session-addressed bridge
  method (`session.get/delete/rename/configure`, `conversation.send/stop/
  compact`, `nudge.status`) refuses unknown and wrongly-typed session ids
  with a `BridgeError` before dispatch (async handlers awaited exactly as
  the server does). Session ids are `sess_` + 20 hex (80-bit, no
  enumeration); a tampered id never resolves to a store.
- **SEC-G-19 (grant-chain audit).** Seeded 60-trial sweep over
  `build_child_tools` pins all seven invariants: no dangerous without the
  flag; private-table risk resolution; approver-less child policies; no
  verbatim parent instance-bound closures; granted dangerous still refused
  at call time; unknown grants never fall back globally; the global
  registry survives byte-identical. Council stages asserted
  `allow_dangerous=False` with dangerous-free member tables.
- **SEC-G-20 (degraded cron grants).** Fresh cron/single-query dreams run
  with dangerous tools ABSENT from the dispatch table (`unknown tool`,
  refused before any approval logic); the engine context gate remains the
  second layer; interactive sessions unchanged. (Residual, documented:
  schedule runs reusing an interactive session keep that session's policy;
  the context gate + floor still apply.)
- **SEC-G-21 (cron storage pins).** Traversal-shaped prompts/session_ids
  and SQL injection attempts are stored as inert literals (parameterized
  SQL pinned against `DROP TABLE`/`DELETE` payloads); the scheduler hands
  prompts to the runner verbatim and materialises nothing on disk; empty
  name/prompt and unknown-id updates refuse.

## Decisions & residual risks

- Scopes govern LINKED identities. Platforms deliberately run with
  `require_auth: false` keep pre-scope behaviour for unlinked sessions —
  the owner's explicit choice, now documented here and in the threat model.
- The scope management UI ships with the Stage F Security Center
  (WATCHTOWER); the kernel + bridge surface are complete and tested.

## Gate E criteria — status

- [x] Cross-session access fails closed (unknown/malformed ids, opaque
      session ids, tampered ids refuse).
- [x] Subagent/council grant chain asserts minimal grants mechanically
      (60-trial seeded sweep + council stage assertions).
- [x] Per-user scopes enforced (policy ceiling + live gateway application
      + bridge management surface).
- [x] Scheduled jobs run with a degraded grant set; cron storage traversal
      pinned.

**Decision: GREEN — Stage F (Security Center UI, audit tooling,
SECURITY.md) may begin.**
