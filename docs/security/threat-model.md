# Dream — Threat Model (Eight-Layer Defense in Depth)

**Version:** 1.0 (SEC Stage A) · **Date:** 2026-08-24 · **Base commit:** `8e4dc9e`
(`feat(memory): MP-02 Stage F — desktop surfaces, bridge error paths, close-out (#79)`)
**Owner:** Chief Security Engineer (AEGIS) · **Status:** gap register open — every gap
assigned to a stage (B–F) in [`SEC-A.md`](../handoff/SEC-A.md).

Dream is a local-first, bilingual (Persian/English) personal assistant: a
stdlib-only Python kernel (`dream/`), a Tauri 2 + React desktop shell
(`apps/desktop/`), a framed newline-delimited JSON-RPC bridge (protocol 1.1,
strictly append-only), six messaging-platform adapters, an optional web
gateway, an MCP client, a hardened Docker sandbox for data-science code, and
optional Chrome control over CDP. The philosophy is fixed and every control
below must respect it: **offline-first, zero telemetry, zero new runtime
dependencies, bilingual refusals, fail closed out loud.**

---

## 1. Assets

| # | Asset | Where | Why it matters |
| --- | --- | --- | --- |
| A1 | Owner's files | workspace root (`DREAM_WORKSPACE_ROOT`) | The assistant has write tools; a confused deputy can destroy data. |
| A2 | Credentials & keys | env vars, `.env`, `~/.dream/gateway_tokens.json`, platform tokens, provider API keys | Exfiltration through tools, MCP children, logs, or the wire. |
| A3 | The three MP-02 stores | `memory_stores` (bounded DB), `session_search` FTS index, skills ledger (`data/dream-skills.db`) | Integrity-critical, already fail-closed on corruption; must stay isolated per session where scoped. |
| A4 | The model's context | system prompt + history + tool results | Anything entering context is an instruction channel: prompt injection is Dream's primary remote attack surface. |
| A5 | The shell | `run_shell` (dangerous tier), MCP stdio children, Docker sandbox | Arbitrary execution; layered approval + blocklist is the only safe posture. |
| A6 | Linked identities | `AuthStore` linked-user registry | A linked chat identity can command the agent; identity compromise must be containable (scopes, unlink). |
| A7 | The gateway session | token store, TLS state, mDNS advertisement | LAN-reachable surface; token theft or downgrade must be detected and recoverable. |
| A8 | The audit trail | message log, provenance records, approval history | Without an untampered trail, no incident is reconstructable. |

## 2. Attacker personas

| Persona | Capability | Primary targets |
| --- | --- | --- |
| P1 Hostile file | A document, SKILL.md, `/learn` source, or web page whose content carries hidden directives (bidi overrides, zero-width characters, EN+FA instruction-override text). | A4 → A5, A2 |
| P2 Malicious MCP server | A stdio child process Dream launches; returns crafted tool descriptions and payloads; sees its own environment. | A2 (env leakage), A4 (description injection), A5 |
| P3 Unlinked chat user | A stranger in a group channel or DM; may observe link codes in transit. | A6, A5 (via commands) |
| P4 Compromised linked user | A linked identity on a stolen phone/account. | A5, A2 — containment must come from scopes + unlink + per-user rate limits. |
| P5 LAN attacker | Anyone on the local network reaching the gateway. | A7, A2 |
| P6 Prompt-driven misuse | The model itself, steered by user or injected text, asking for destructive shell commands, including obfuscated ones. | A1, A5 — the blocklist is the floor that even approval cannot override. |

## 3. Trust boundaries

```
 chat platforms (6) ──▶ connectivity gateway ──┐
                       (link auth, rate limit) │
 web gateway ─────────▶ token/scope check ─────┤
 desktop UI ──────────▶ bridge (NDJSON) ───────┤
                                               ▼
                                        agent turn loop
                                               │
                ┌──────────────────────────────┼─────────────────────────────┐
                ▼                              ▼                             ▼
      L5 injection scan             L3 blocklist (floor)            L7 grants (subagents,
      (before context entry)        L2 approval engine               council, scheduler)
                │                   L1 user scope                            │
                ▼                              ▼                             ▼
            model context ──────────▶ tool dispatch (risk tiers) ──▶ L4 file safety
                                                                     L6 MCP env hygiene
                                                                     sandbox / CDP / shell
```

Rule that governs every arrow: **untrusted data crosses a boundary only
validated, and untrusted text crosses into context only scanned.** Evidence
for each boundary lives in the layer tables below.

## 4. The eight layers — current code, threats, gaps

Verified against `8e4dc9e`. "Present" citations are files and symbols
checked at Stage A; every gap carries an ID that `SEC-A.md` assigns to a
stage and sub-agent.

### L1 — User authorization

**Present.** `dream/connectivity/auth.py`: single-use, 10-minute, 6-digit
link codes; `secrets.compare_digest` comparison; registry persisted `0600`
via atomic replace. `dream/connectivity/ratelimit.py`: per-`(platform,
user_id)` fixed-minute window (default 20/min, per-platform override).
`dream/connectivity/gateway.py` pipeline: log → pre-auth commands →
`is_linked` → rate → agent.

**Threats.** T1.1 code brute-force before expiry (mitigated: 10⁶ space,
10 min TTL, single-use, per-user rate limit). T1.2 a linked user has no
least-privilege ceiling — any linked identity reaches the full command
surface. T1.3 gateway tokens are global: `read`/`write` scopes exist
(`dream/gateway_server.py:TokenScope`) but no per-user scope model exists
for chat identities.

**Gaps.** `SEC-G-01` per-linked-user scopes (chat-only / safe-tools /
guarded-tools / admin) in `LinkedUser` + enforcement point + Settings UI.
`SEC-G-02` approval-attempt rate limiting per user (distinct from message
rate limiting). `SEC-G-03` constant-time token comparison on the gateway
verify path.

### L2 — Dangerous-command approval engine v2

**Present.** `dream/tools.py` three-tier registry (`safe`/`guarded`/
`dangerous`); `dream/agent.py:ApprovalPolicy.allows` resolves risk from the
*dispatch* registry, hard-denies `dangerous` with no approver
(`dangerous tool denied: no approver configured` — visible in `cli.py --demo`).
`execute()` independently refuses dangerous tools without `approved=True`,
so direct callers fail closed too.

**Threats.** T2.1 a human approver rubber-stamps a destructive command
they cannot parse (obfuscation). T2.2 autonomous contexts (cron,
single-query) have no human present at all. T2.3 approval decisions leave
no durable history (audit trail A8).

**Gaps.** `SEC-G-04` auxiliary risk assessor (secondary cheap model call,
strict JSON schema low/medium/high/catastrophic, hard timeout, default deny
on timeout/error; offline/echo → deterministic pattern rules). `SEC-G-05`
modes `smart | manual | off` with explicit opt-in, persistent red banner
and status-bar indicator for `off`. `SEC-G-06` `cron_mode` and
`single_query_mode` defaulting to deny. `SEC-G-07` durable approval
history (basis for the Security Center surface in Stage F).

### L3 — Hardline blocklist (the floor)

**Present.** Nothing. `run_shell` forwards any approved string to
`shell=True` (deliberate, `nosec B602`, compensating control = approval).

**Threats.** T3.1 user-approved or injected destructive commands
(`rm -rf /`, fork bombs, `mkfs` on mounted root, raw block-device writes,
`curl … | sh`, Windows `rd /s /q C:\`, `format`, registry-hive deletes,
PowerShell equivalents). T3.2 obfuscation: quoting, env expansion,
`$((…))`, path normalization, Unicode homoglyphs, mixed separators.

**Gaps.** `SEC-G-08` data-driven blocklist module (`dream/security/blocklist.py`)
evaluated **before** any approval layer, non-overridable by `off`, cron
approve-mode, or "always allow"; bilingual refusal naming the matched
class; exhaustive red-team corpus including Windows-first coverage and
obfuscation (reusing the Persian normalizer for homoglyph folding).
*This layer ships in PR-S1 because the safety floor must land first.*

### L4 — File-write safety

**Present.** `dream/tools.py:_safe_path` confines every note path to the
workspace, rejects absolute paths and `relative_to` escapes, rejects
Windows reserved device names (`con`, `prn`, `com1`… after Persian digit
folding) and trailing dot/space components. Skill writes are name-validated
(`dream/skills/format.py:validate_name`) and append-only versioned.

**Threats.** T4.1 symlink farms planted inside the workspace pointing
outside (`resolve()` catches reads of existing links, but link *creation*
and TOCTOU windows need a rule). T4.2 8.3 short-name aliases on Windows
bypassing string denylists. T4.3 writes/deletes of sensitive files if any
future tool escapes the workspace convention. T4.4 deletion with no undo.

**Gaps.** `SEC-G-09` explicit sensitive-path denylist (credentials, `.ssh`,
the skills ledger, provenance, Dream data dir incl. the three MP-02 stores,
system dirs, Windows known paths incl. AppData/Program Files/UNC) evaluated
for every write/patch/delete tool. `SEC-G-10` traversal corpus
(`..`, symlinks, 8.3, homoglyphs) as a permanent suite. `SEC-G-11`
size-capped quarantine for deletions (move-first; restore/purge UI later).

### L5 — Prompt-injection scanning

**Present.** Nothing scans inbound text for directives. Protections that do
exist are adjacent, not scanning: network tools are opt-in and SSRF-guarded
(`_validate_network_url`); web text is markup-stripped and capped; SKILL.md
catalogs keep bodies out of the system prompt until `skill_view`; the
MP-02 bridge families validate types at the boundary.

**Threats.** T5.1 hostile file/web/MCP text entering context with hidden
Unicode (bidi overrides U+202E et al., zero-width chars) that flips the
meaning of what the user sees. T5.2 EN+FA instruction-override patterns
("ignore previous instructions" / «دستورالعمل‌های قبلی را نادیده بگیر»).
T5.3 poisoned skill bodies (`SKILL.md`), poisoned `/learn` sources,
session-search snippets, and recalled memories as re-entry vectors.
T5.4 fake tool-invocation shapes smuggled into context.

**Gaps.** `SEC-G-12` scanner module with modes `off | warn | strip`
(default strip for hidden-Unicode, warn for heuristics); scans **before
context entry** for file contents, web extractions, MCP payloads, SKILL.md
bodies, `/learn` material, session-search snippets, memory recall.
`SEC-G-13` sanitized output enters context with a visible bilingual
warning; originals quarantined with a provenance entry.

### L6 — MCP & subprocess credential hygiene

**Present.** MCP config supports a per-server `env` map
(`dream/mcp/models.py`), and Dream redacts tokens on several existing
paths: `dream/agent.py:_redact` on error detail, `dream/bridge/errors.py`
redaction policy, platform adapters (`redact_token`), config redaction in
`dream/connectivity/config.py`. `tests/test_security_secrets.py` scans
tracked files for key shapes.

**Threats.** T6.1 MCP children inherit secrets. **Confirmed at Stage A:**
`dream/mcp/transport.py:69` does `merged_env = dict(os.environ)` then
`merged_env.update(self.config.env)` — the full parent environment
(provider API keys, gateway tokens, platform tokens) reaches every MCP
child. T6.2 MCP tool descriptions are model-visible text: an injection
channel into context. T6.3 a compromised MCP child exfiltrating over the
network (no per-server egress policy). T6.4 secrets landing in logs,
message logs, provenance, or error strings that the existing redactors do
not cover (JWT shapes, `sk-…` in arbitrary text).

**Gaps.** `SEC-G-14` allowlist-filtered environment for MCP children
(strip everything not explicitly mapped). `SEC-G-15` MCP tool description
sanitization before prompt entry (shares the L5 scanner). `SEC-G-16`
per-server egress toggle. `SEC-G-17` value-scanning redaction extended to
logs, message logs, provenance, and errors (`sk-`-style, JWT shapes,
gateway-token prefixes) — never a key on the wire or in logs.

### L7 — Cross-session & multi-agent isolation

**Present.** `dream/subagents.py` grant builder: children get a private
table; `dangerous` tools dropped unless explicitly allowed; names in
`dream/agent.py:INSTANCE_BOUND_TOOL_NAMES` (`agent_notes`, `user_profile`,
memory/reminder names) are dropped whenever the child would receive the
parent's closure verbatim; the child's `ApprovalPolicy` resolves risk from
its own table and carries **no approver**, so even a granted dangerous tool
is refused at call time (`unknown tool` for anything outside the grant).
Schedules persist in SQLite tables inside the session's `MemoryStore`
(`dream/scheduler.py:ensure_schedule_tables`) — no file path is derived
from user input today.

**Threats.** T7.1 one session reading another's stores via bridge params.
T7.2 grant-chain drift as new instance-bound tools are added (the set is a
manual list). T7.3 the council path (`dream/council.py`) composing grants
without a minimal-grant assertion. T7.4 scheduled jobs executing with a
full interactive grant set while no human is present.

**Gaps.** `SEC-G-18` cross-session store access fails closed (explicit
ownership checks + tests). `SEC-G-19` grant-chain audit assertions for
subagents **and** council (minimal grants, mechanically checked).
`SEC-G-20` scheduled jobs run with a degraded grant set (no `dangerous`,
no browser, no network). `SEC-G-21` cron/schedule storage traversal
hardening pinned by tests even though today's storage is SQLite-backed
(defense in depth for future file persistence).

### L8 — Input sanitization & transport hardening

**Present.** `dream/bridge/server.py`: NDJSON with a 10 MiB line limit
(`DEFAULT_MAX_LINE_BYTES`), malformed-JSON tolerance, oversize rejection.
`dream/bridge/methods.py` (~3,800 lines): per-method `isinstance` boundary
validation; MP-02 families covered by the Gate-F error-path suite
(29 functions / 52 cases: `memory2.*`, `skills.*`, `search.sessions.*`,
`conversation.compact`, `nudge.status`). `dream/bridge/errors.py` redacts
before wire errors. `dream/gateway_server.py`: token store with
read/write scopes, `rotate_token`, `revoke_token`; headers
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy`, HSTS under TLS, default CSP. Shell execution elsewhere
uses argument arrays (`docker_sandbox.py` builds argv lists; only the
deliberate `run_shell` uses `shell=True`).

**Threats.** T8.1 any future bridge family merged without boundary
validation. T8.2 header regressions (no automated CSP/HSTS tests today).
T8.3 token-store file permissions and rotation hygiene untested. T8.4
per-token rate limits absent (a stolen token can saturate the agent).
T8.5 the legacy Tk window `desktop.py` (1,570 lines, M22–M26) predates the
bridge-era boundary discipline; it is a dormant second front end.

**Gaps.** `SEC-G-22` boundary-validation audit over **all** MP-02 families
with a reject-before-dispatch property test + bounded, seeded bridge
fuzzing. `SEC-G-23` gateway header tests (CSP/HSTS/X-Frame-Options) in the
suite. `SEC-G-24` token rotation + read-only scope enforcement audit +
per-token rate limits. `SEC-G-25` `desktop.py` audit: quarantine (behind
an explicit flag) or remove, documented in this threat model.

## 5. Fail-closed posture (invariant)

Every layer added under this program obeys: on error, timeout, corruption,
or ambiguity, Dream **refuses, names the reason in both languages, and
changes nothing.** This is the invariant MP-02 proved across three SQLite
stores and the bridge error paths; SEC extends it to approvals, scanning,
and isolation. Assessor timeout → deny. Scanner failure → treat as
suspicious. Unknown grant → `unknown tool`. Corrupt quarantine → refuse to
restore, never delete silently.

## 6. Layer → code → stage map

| Layer | Present today (verified files) | Gap IDs | Stage · SA |
| --- | --- | --- | --- |
| L1 authorization | `connectivity/auth.py`, `ratelimit.py`, `gateway.py`, `gateway_server.py` | G-01…G-03 | E · SA-1 RAMPART |
| L2 approval engine v2 | `tools.py` tiers, `agent.py:ApprovalPolicy`, **`security/engine.py` + `security/assessor.py` + `security/history.py` (Stage B, closed)** | ~~G-04…G-07~~ closed at B | B · SA-2 SENTRY |
| L3 blocklist floor | **`security/blocklist.py` (Stage B, closed)** | ~~G-08~~ closed at B | B · SA-2 SENTRY |
| L4 file-write safety | `tools.py:_safe_path`, skills name validation, **`security/pathsafety.py` denylist + `security/quarantine.py` (Stage C, closed)** | ~~G-09…G-11~~ closed at C | C · SA-3 VAULT |
| L5 injection scanning | **`security/injection.py` detection layer over `security/textguard.py`, wired at all seven context-entry surfaces (Stage D, closed)** | ~~G-12, G-13~~ closed at D | D · SA-4 HORIZON |
| L6 credential hygiene | **`security/envfilter.py`, `security/textguard.py`, `security/secrets.py` (Stage C, closed — the `mcp/transport.py:69` leak is fixed)** | ~~G-14…G-17~~ closed at C | C · SA-3 VAULT |
| L7 isolation | `subagents.py` grants, `INSTANCE_BOUND_TOOL_NAMES` | G-18…G-21 | E · SA-1 RAMPART |
| L8 transport | `bridge/server.py` limits, `bridge/methods.py` validation, gateway headers, **boundary property sweep + seeded fuzzing, pure header policy, token rotation audit, per-token rate limits, legacy window quarantined (Stage D, closed)** | ~~G-22…G-25~~ closed at D | D · SA-4 HORIZON |

Quality and transparency across all layers: SA-5 PROOF (Stage E/F:
`tests/security/` 200+ cases, `tools/security_audit.py`) and SA-6
WATCHTOWER (Stage F: Security Center, SECURITY.md matrix).

**Stage B close (2026-08-24).** G-04…G-08 are closed. The floor lives in
`dream/security/blocklist.py` (8 data-driven rules; normalization folds
quoting, escapes, variable/tilde expansion, `..` traversal, zero-width/bidi
controls, full-width and Cyrillic homoglyphs, and reuses the shared Persian
normalizer). It runs before any approval logic at every choke point:
`ApprovalPolicy.allows`, `tools.execute`, and the bridge
(`tool.execute` / `approval.request` / `approval.resolve`). The engine
(`security/engine.py`) orders floor → context → mode; `manual` is the
default and reproduces pre-SEC behaviour exactly; `off` exists only behind
an explicit opt-in and carries persistent red banner + status-bar chip
(`apps/desktop/src/components/security/`); cron/single-query contexts
default to deny. The assessor (`security/assessor.py`) answers a strict
`{level, reason}` JSON schema under a hard timeout — timeout, error, or any
schema deviation denies. The approval trail is append-only SQLite under
`DREAM_APPROVAL_DB` (`security/history.py`), fail-closed on corruption.
Evidence: 250 tests in `tests/security/` incl. the
`blocklist_precedes_approval` property; SEC-GATES.md Gate B.

**Stage C close (2026-08-24).** G-09…G-11 and G-14…G-17 are closed
(`security/envfilter.py`, `security/pathsafety.py`, `security/quarantine.py`,
`security/secrets.py`; SEC-GATES.md Gate C).

**Stage D close (2026-08-24).** G-12/G-13 and G-22…G-25 are closed.
`security/injection.py` scans before context entry at every surface (file
reads, web extraction, MCP payloads, SKILL.md bodies via `skill_view` and
slash loads, `/learn` sources, session-search snippets, recalled memories)
with modes `off | warn | strip` (default strip): hidden Unicode is
stripped, EN+FA instruction overrides and smuggled tool-call shapes warn;
findings enter context under a bilingual warning banner, originals are
quarantined with metadata and optional provenance entries. Precision is
pinned: U+200C (ZWNJ) is first-class Persian orthography and never trips.
L8: the boundary property sweep + seeded fuzzing caught and fixed three
real leaks (memory2 target typing, provenance limit parsing, browser
state errors); gateway headers live in the pure `build_security_headers()`;
token rotation is audited and per-token rate limits (240/min) enforce at
both verify dependencies; **`desktop.py` is quarantined behind
`DREAM_ENABLE_LEGACY_DESKTOP=1`** (explicit flag chosen over removal: it
keeps the window restorable for owners who rely on it while ending silent
starts — the Tauri desktop is the supported surface). Evidence:
`tests/security/` grew to 403 cases; SEC-GATES.md Gate D.

## 7. Out of scope / accepted risks (recorded, not ignored)

- `run_shell` remaining a `shell=True` tool is accepted **only** behind
  L3 floor + L2 approval; the floor makes the blast radius finite.
- Bandit B310/B104 deferrals from `docs/security/audit-report.md` carry
  forward; the network boundary (`_validate_network_url`) is the control.
- Desktop shell supply chain (Tauri/npm deps) is covered by `npm audit`
  in CI, not by this program.

## 8. Change control

This document is the single source of truth for layer→code mapping.
Every stage closes by updating §4/§6 with verified file paths and gap
status; `docs/handoff/SEC-GATES.md` carries the command evidence.
