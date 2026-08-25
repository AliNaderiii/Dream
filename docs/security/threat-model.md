# Dream — Threat Model (Eight-Layer Defense in Depth)

**Version:** 2.0 (P6 — agentic layer) · **Date:** 2026-08-25 · **Base commit:** `70b49cb`
(`feat(workspace): local-first workspace, projects 2.0, and agent modes (#88)`)
**Previous:** 1.0 (SEC Stage A, base `8e4dc9e`) · **Owner:** Chief Security Engineer (AEGIS)
**Status:** SEC gaps G-01…G-25 closed (Stages B–F). P6 opens and closes the agentic
register `AG-01…AG-12` over the surfaces P1/P3/P4/P5 added; residual risks in §7.

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
| A9 | Model-generated code | research/data-QA analysis programs, `/plan` steps, workspace `!shell` | Text a model wrote, aimed at an interpreter. If the host runs it, an injection becomes an execution. |
| A10 | Datasets and their cells | workspace roots, imported CSV/Parquet, tool output feeding codegen | Every cell is attacker-controllable in the general case; a cell that reaches a code-generation prompt is an instruction channel with a compiler behind it. |
| A11 | Plans | research plans, data-QA query plans, `/plan` and `/goal` step lists | A plan is what the owner approved. If it can change after approval, approval means nothing. |
| A12 | Published figures, tables, and numbers | reports, charts, answer text | The output is the product. An ungrounded number is a fabrication the owner may act on. |
| A13 | Provider-hub credentials and endpoints | gateway tokens, keychain entries, runtime endpoints (`RUNTIME_SPECS`) | Tokens are theft targets; probe paths are SSRF and exfiltration candidates. |

## 2. Attacker personas

| Persona | Capability | Primary targets |
| --- | --- | --- |
| P1 Hostile file | A document, SKILL.md, `/learn` source, or web page whose content carries hidden directives (bidi overrides, zero-width characters, EN+FA instruction-override text). | A4 → A5, A2 |
| P2 Malicious MCP server | A stdio child process Dream launches; returns crafted tool descriptions and payloads; sees its own environment. | A2 (env leakage), A4 (description injection), A5 |
| P3 Unlinked chat user | A stranger in a group channel or DM; may observe link codes in transit. | A6, A5 (via commands) |
| P4 Compromised linked user | A linked identity on a stolen phone/account. | A5, A2 — containment must come from scopes + unlink + per-user rate limits. |
| P5 LAN attacker | Anyone on the local network reaching the gateway. | A7, A2 |
| P6 Prompt-driven misuse | The model itself, steered by user or injected text, asking for destructive shell commands, including obfuscated ones. | A1, A5 — the blocklist is the floor that even approval cannot override. |
| P7 Poisoned dataset | A CSV/Parquet the owner imported in good faith whose cells carry directives (EN or FA) aimed at the code-generation step rather than the reader. | A9, A10 → A1, A2 |
| P8 Plan-swap attacker | Any channel that can edit a plan between approval and execution — injected text in a step title, a racing bridge call, a mutated session file. | A11 → A5, A9 |
| P9 Fabricating model | The model under pressure to answer, inventing a statistic no code produced. | A12 — an integrity failure, not a confidentiality one; the owner acting on it is the harm. |
| P10 Hostile or spoofed runtime endpoint | Something answering on a probed port, or an endpoint the owner was tricked into configuring. | A13, A2 — SSRF, credential capture, oversized-response denial. |

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

 P6 adds the agentic path, which runs INSIDE the arrows above:

 dataset cell / tool output ──▶ L9-B codegrounding ──▶ (framed as data, or refused)
                                        │
                                        ▼
                             code-generation step
                                        │
                                        ▼
 plan ──▶ L9-C plan gate (digest-bound approval; degraded when autonomous)
                                        │
                                        ▼
              L9-A agentcode ──▶ Docker sandbox (network off, RO mount, bounded)
                                        │        └─ no Docker ⇒ REFUSE, never the host
                                        ▼
                    result ──▶ L9-D authenticity (seal artifact, ground every number)

 provider hubs ──▶ L9-E gateway policy (per-tool token, bounded loopback probe)
```

Rule that governs every arrow: **untrusted data crosses a boundary only
validated, and untrusted text crosses into context only scanned.** Evidence
for each boundary lives in the layer tables below.

## 4. The layers — current code, threats, gaps

L1–L8 were verified against `8e4dc9e` at Stage A and closed across Stages
B–F; "Present" citations there are the files and symbols those stages
shipped. **L9 (the agentic layer) was verified against `70b49cb` at P6** and
is closed in the same document revision that opens it — it ships with its
controls, its tests, and its audit assertions together, because a layer with
an open register is a layer that does not exist yet.

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

### L9 — The agentic layer (P6)

P1 (research), P3 (data Q&A), P4 (workspace + agent modes), and P5
(provider hubs) added capability faster than they added containment. L9 is
the layer that sits under all four. It is additive: L1–L8 are unchanged and
still run first, and every L9 module **calls** the existing engine rather
than reimplementing it (`ApprovalPolicy` for tool risk, `injection.scan_text`
for prose, `docker_sandbox` for isolation, `provenance` for lineage,
`secrets.redact_*` for value scanning).

#### L9-A — Agentic code-execution sandbox policy

**Present.** `dream/security/agentcode.py`. The contract: **the host never
executes model-generated code.** `preflight_code` parses (never evaluates) a
program and refuses a deny-by-default import list — only the analysis stack
plus authority-free stdlib helpers pass; `os`, `sys`, `socket`, `subprocess`,
`shutil`, `pickle`, `ctypes` and friends are absent from `ALLOWED_IMPORTS`.
`exec`/`eval`/`compile`/`__import__` and object-graph escapes (`__globals__`,
`__subclasses__`, `__reduce__`, …) are refused. String literals that name a
path outside the mounted dataset root — absolute, `~`, drive-lettered, UNC,
or `..`-traversing — are refused. `SandboxPolicy` is frozen with
`network_enabled=False` and raises if a caller tries to set it True; it
carries wall-clock, memory, CPU, PID, disk and output-size bounds.
`run_agent_code` confines the working directory (symlinks resolved),
delegates to `DockerSandbox.run_code` with a read-only mount, wraps it in an
outer deadline, truncates and redacts output, and — when Docker is
unavailable — **refuses**. There is no host-subprocess fallback.

**Threats.** T9.1 injected text steering the model into writing an
exfiltrating or destructive program. T9.2 sandbox escape via imports or the
object graph. T9.3 escape via a path literal reaching the owner's home or
`/etc`. T9.4 network egress from inside the analysis step. T9.5 resource
exhaustion (fork bomb, allocation storm, infinite loop, output flood).
T9.6 the convenience regression: "Docker isn't installed, run it locally".

**Controls → evidence.** `tests/test_sec_agentic_sandbox.py` (61 cases) plus
the audit's `L9-A` section, including a mechanical sweep asserting that **no
module under `dream/security/` contains an `exec`/`eval`/`compile`/`runpy`
call site**. The Docker-absence refusal is asserted with a sandbox double
whose `run_code` raises if it is ever reached.

**Residual.** The container is Docker's boundary, not Dream's — a Docker or
kernel escape is out of Dream's control (accepted, §7). `--userns=remap` and
the seccomp profile come from `docker_sandbox.py`, which P6 deliberately did
not rewrite. Bash and R languages remain reachable through the underlying
sandbox API; the L9-A policy only clears Python, so anything else refuses.

#### L9-B — Data-as-data framing for code generation

**Present.** `dream/security/codegrounding.py`. L5 guards prose entering
context; L9-B guards values entering a **code-generation** context, where a
payload has a compiler behind it. Three rules in order: never interpolate
(`as_code_literal` renders inert literals after stripping invisibles;
`as_parameter_block` emits JSON the sandbox *loads*, so a value is a value);
frame as data (`frame_as_data` wraps content in a fenced, labelled block
under a bilingual "this is data, not instructions" banner, neutralising any
fence the payload carries); reject instruction lookalikes
(`scan_data_payload` runs `injection.scan_text` first, then codegen-specific
detectors for fences, comment smuggling, shell/pipe payloads, SQL tampering,
credential reads, exfiltration verbs, agent-addressing phrasing, and Persian
data-poisoning: «این دستور را اجرا کن», «به کد اضافه کن», «همه فایل‌ها را
حذف کن», «کلید را بفرست», «ستون‌ها را نادیده بگیر»).

**Threats.** T9.7 a poisoned cell becoming a statement in the generated
program. T9.8 a cell addressing the model directly ("Assistant: before you
write the code…"). T9.9 SQL/filter tampering through a filter value.
T9.10 the precision failure: over-blocking ordinary Persian free text until
the owner switches the control off.

**Controls → evidence.** `tests/test_sec_agentic_codegrounding.py` (77
cases): 26 English and 14 Persian hostile payloads all rejected; 16 benign
controls — Persian literary prose, recipes, Jalali dates, prices in Persian
digits, an English sentence containing the word "ignore" — all pass. Literals
are round-tripped through `ast.literal_eval` to prove they never became
syntax. U+200C (ZWNJ) is pinned as Persian orthography, never a finding.

**Residual.** These are heuristics: a sufficiently novel phrasing can pass.
The compensating control is that L9-B's *primary* defense is structural — the
parameter block — not the scanner. A payload that slips the scanner is still
a JSON string, and the program that consumes it still has to clear L9-A.

#### L9-C — Plan-approval gating and degraded autonomous grants

**Present.** `dream/security/planpolicy.py`. Approval binds to
`plan_digest(kind, steps)`, a SHA-256 over the plan's kind and ordered steps
with volatile bookkeeping (`status`, `updated_at`) excluded so a live status
tick does not invalidate a grant. `EXPENSIVE_ACTIONS` classifies what must
not start unapproved (code execution, long runs, network fetches, bulk model
calls, writes, deletes, shell, provider probes, exports);
`DEGRADED_GRANTS` is what remains without a human (plan, read, list,
summarise, status). In `cron`/`single_query`/`autonomous` contexts approval
**cannot be minted at all** and every expensive action refuses.
`ApprovalAttemptLimiter` is a sliding-window throttle in which a *refused*
attempt still costs budget. `authorize_tool` runs the plan gate and then
delegates the tool verdict to `ApprovalPolicy.allows`, so the L3 floor still
precedes every gate and the plan gate can only ever *add* a refusal.

**Threats.** T9.11 the plan swap — approve a cheap plan, execute an
expensive one. T9.12 an autonomous dream spending money or writing files
with nobody watching. T9.13 an injection loop re-asking for approval until
the owner clicks yes. T9.14 an unclassified new action slipping past the
gate because nobody remembered to list it.

**Controls → evidence.** `tests/test_sec_agentic_planpolicy.py` (55 cases).
T9.14 is closed by construction: an action that is in neither set refuses
with `unknown_action` rather than defaulting to allowed.

**Residual.** The gate governs actions routed through it. A future surface
that calls a sandbox or a provider directly, without classifying its action,
bypasses L9-C — which is why the classification is fail-closed and why the
audit asserts the two sets stay disjoint. Wiring the existing P1/P3/P4
call sites into the gate is owner-scheduled follow-up work: P6 owns the
primitive, and the domain modules are outside its change surface.

#### L9-D — Artifact and claim authenticity

**Present.** `dream/security/authenticity.py`, built on `dream/provenance`.
`RunFingerprint` hashes the code text, every input file's bytes, the
parameter block, the run id and the tool into one `run_hash`; an input that
cannot be read is recorded as `unreadable` rather than skipped, so an
incomplete lineage is visible instead of implied. `seal_artifact` binds an
artifact's own SHA-256 to that run hash, records it through
`ProvenanceTracker` (whose payloads are already value-scanned and
hash-chained) and links a sidecar via `ArtifactManager`. `verify_artifact`
re-hashes on disk. `verify_claims` extracts every number from prose —
Persian and Arabic-Indic digits, Persian decimal/thousands marks, ASCII
separators — skips structural references ("section 3", «جدول ۴»), and
refuses any number no computed value grounds, allowing sane rounding and
fraction/percent equivalence.

**Threats.** T9.15 a fabricated statistic in a report. T9.16 a figure
silently regenerated from different data while the old caption stands.
T9.17 an artifact edited after publication. T9.18 the honest-mistake case:
refusing a correctly rounded number and training the owner to ignore the
control.

**Controls → evidence.** `tests/test_sec_agentic_authenticity.py` (28
cases). A broken provenance store degrades the record to `record_id=None`
and never silently drops the seal.

**Residual.** `verify_claims` is numeric. A qualitative fabrication ("the
trend is clearly seasonal") is not detected by this control and is recorded
as an accepted risk. Sealing is only as good as the call sites that use it;
as with L9-C, wiring P1/P3 outputs through `seal_artifact` is follow-up work
outside P6's change surface.

#### L9-E — Provider-hub credential and gateway policy

**Present.** `dream/security/providergateway.py`, calling into
`dream/providerhubs`. Tokens are minted per **tool** (`web_search`, `image`,
`tts`, `browser`) and per **scope** (`read` | `use`) — there is no wildcard
tool and no `admin` scope, and `mint_token` refuses both plus unbounded
lifetimes. Only a SHA-256 digest is retained; the plaintext exists once, at
mint time. Verification is constant-time over every candidate
(`hmac.compare_digest`, no early exit). `rotate` replaces the secret and
keeps the grant; `revoke` is immediate. `safe_snapshot` runs the L6 value
scanner and then drops any field whose *name* implies a secret, so a field
added later cannot leak by omission; `redact_headers` blanks every
credential-bearing header. `probe_runtime` refuses unknown runtimes,
endpoints that are not the configured one for that runtime, non-HTTP
schemes, credentials in the URL, crafted paths, and non-loopback hosts;
it disables redirects, sends **no** credential header, caps the read at
64 KiB and clamps the timeout to 5 s.

**Threats.** T9.19 a global gateway token stolen from a log or a state
dump. T9.20 credential leakage through a trace, an RPC reply, or an error
string. T9.21 SSRF — a probe pointed at `169.254.169.254` or an attacker
host. T9.22 a redirect turning a health check into an unreviewed second
request. T9.23 an oversized or slow response as a denial vector.

**Controls → evidence.** `tests/test_sec_agentic_gateway.py` (72 cases),
including a live-minted token asserted absent from snapshots, header dumps,
probe results and the logging filter's output. Fixtures use broken shapes
(`sk_EXAMPLE_not_a_real_key`) so nothing in the tree resembles a credential.

**Residual.** The store is in-memory: it owns the *grant*, while durable
secrets remain the OS keychain's job (`KeychainCredentialStore`). Loopback
enforcement is address-based; an owner who deliberately widens
`allowed_endpoints` to a remote host takes that risk knowingly, and the
non-local refusal still fires unless they do.

## 5. Fail-closed posture (invariant)

Every layer added under this program obeys: on error, timeout, corruption,
or ambiguity, Dream **refuses, names the reason in both languages, and
changes nothing.** This is the invariant MP-02 proved across three SQLite
stores and the bridge error paths; SEC extends it to approvals, scanning,
and isolation. Assessor timeout → deny. Scanner failure → treat as
suspicious. Unknown grant → `unknown tool`. Corrupt quarantine → refuse to
restore, never delete silently. P6 extends the same invariant to the
agentic layer: no Docker → refuse (never the host); unclassified action →
refuse; unparsable program → refuse; unreadable artifact → not authentic;
number with no computed backing → refuse; endpoint that was never
configured → refuse. In every one of those the reason is named in English
and Persian, and nothing runs.

## 6. Layer → code → stage map

| Layer | Present today (verified files) | Gap IDs | Stage · SA |
| --- | --- | --- | --- |
| L1 authorization | `connectivity/auth.py`, `ratelimit.py`, `gateway.py`, `gateway_server.py`, **per-user scopes + approval throttle + constant-time tokens (Stage E, closed; Settings UI with the Stage F Security Center)** | ~~G-01…G-03~~ closed at E | E · SA-1 RAMPART |
| L2 approval engine v2 | `tools.py` tiers, `agent.py:ApprovalPolicy`, **`security/engine.py` + `security/assessor.py` + `security/history.py` (Stage B, closed)** | ~~G-04…G-07~~ closed at B | B · SA-2 SENTRY |
| L3 blocklist floor | **`security/blocklist.py` (Stage B, closed)** | ~~G-08~~ closed at B | B · SA-2 SENTRY |
| L4 file-write safety | `tools.py:_safe_path`, skills name validation, **`security/pathsafety.py` denylist + `security/quarantine.py` (Stage C, closed)** | ~~G-09…G-11~~ closed at C | C · SA-3 VAULT |
| L5 injection scanning | **`security/injection.py` detection layer over `security/textguard.py`, wired at all seven context-entry surfaces (Stage D, closed)** | ~~G-12, G-13~~ closed at D | D · SA-4 HORIZON |
| L6 credential hygiene | **`security/envfilter.py`, `security/textguard.py`, `security/secrets.py` (Stage C, closed — the `mcp/transport.py:69` leak is fixed)** | ~~G-14…G-17~~ closed at C | C · SA-3 VAULT |
| L7 isolation | `subagents.py` grants, `INSTANCE_BOUND_TOOL_NAMES`, **degraded cron grants, mechanical grant-chain sweep, fail-closed session pins, cron storage pins (Stage E, closed)** | ~~G-18…G-21~~ closed at E | E · SA-1 RAMPART |
| L8 transport | `bridge/server.py` limits, `bridge/methods.py` validation, gateway headers, **boundary property sweep + seeded fuzzing, pure header policy, token rotation audit, per-token rate limits, legacy window quarantined (Stage D, closed)** | ~~G-22…G-25~~ closed at D | D · SA-4 HORIZON |
| **L9 agentic (P6)** | **`security/agentcode.py` (sandbox-only exec, deny-by-default imports, path confinement, network off, bounds), `security/codegrounding.py` (data-as-data framing, EN+FA codegen corpus), `security/planpolicy.py` (digest-bound approval, degraded autonomous grants, attempt throttle), `security/authenticity.py` (run fingerprints, artifact seals, `verify_claims`), `security/providergateway.py` (per-tool least-privilege tokens, bounded non-exfiltrating probes)** | ~~AG-01…AG-12~~ closed at P6 | P6 · Agent-S |

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

**Stage E close (2026-08-24).** G-01…G-03 and G-18…G-21 are closed.
Linked identities carry a scope (`chat_only | safe_tools | guarded_tools |
admin`; existing users keep `admin`), enforced by an `ApprovalPolicy`
ceiling that sits AFTER the floor (the floor still precedes every gate)
and applied live per turn by the connectivity gateway; the bridge gains
append-only `gateway.set_user_scope` and scope-bearing `linked_users`
rows (the Settings surface ships with the Stage F Security Center).
Approval attempts are throttled per user (10/min default; floor/scope
blocks spend no budget). Gateway token verification is constant-time
(`secrets.compare_digest` per candidate). Autonomous dreams run degraded
grant sets (dangerous tools absent outright); the subagent/council grant
chain is pinned by a seeded 60-trial mechanical sweep; session-addressed
bridge methods fail closed on unknown/malformed ids with 80-bit opaque
session ids; cron storage is pinned inert against traversal and SQL
injection shapes. Residual risk documented: platforms the owner runs with
`require_auth: false` keep pre-scope behaviour for unlinked sessions
(scopes govern linked identities). Evidence: `tests/security/` grew to
464 cases; SEC-GATES.md Gate E.

## 7. Out of scope / accepted risks (recorded, not ignored)

- `run_shell` remaining a `shell=True` tool is accepted **only** behind
  L3 floor + L2 approval; the floor makes the blast radius finite.
- Bandit B310/B104 deferrals from `docs/security/audit-report.md` carry
  forward; the network boundary (`_validate_network_url`) is the control.
- Desktop shell supply chain (Tauri/npm deps) is covered by `npm audit`
  in CI, not by this program.
- **Container escape (L9-A).** The isolation boundary is Docker's, not
  Dream's. A Docker daemon or kernel escape defeats L9-A; Dream's control is
  that it *refuses* rather than dropping to the host when that boundary is
  unavailable. `docker_sandbox.py` was deliberately not rewritten in P6.
- **Heuristic recall (L9-B).** The codegen detectors are precision-first;
  a novel phrasing can pass them. The structural control — parameters, not
  interpolation — is what carries the layer, with the scanner as depth.
- **Qualitative fabrication (L9-D).** `verify_claims` grounds *numbers*.
  A fabricated qualitative statement is not detected and remains a known
  gap; the honest posture is to say so rather than imply coverage.
- **Call-site adoption (L9-C, L9-D).** P6 owns the primitives and cannot
  edit `dream/research/**`, `dream/dataqa/**`, `dream/workspace/**`,
  `dream/agentmodes/**` or the bridge method modules. Wiring the existing
  surfaces through `PlanGate` and `seal_artifact` is scheduled follow-up.
  Until then those surfaces keep their pre-P6 behaviour: the primitives are
  available and proven, not yet universally mandatory.
- **Keychain dependency (L9-E).** Durable secrets live in the OS keychain.
  On a host with no keyring backend, `KeychainCredentialStore` fails closed
  (no file fallback) — a usability cost accepted in exchange for never
  writing a credential to disk.

## 8. Change control

This document is the single source of truth for layer→code mapping.
Every stage closes by updating §4/§6 with verified file paths and gap
status; `docs/handoff/SEC-GATES.md` carries the command evidence for
Stages B–F and `docs/handoff/P6-GATES.md` for the agentic layer.

**P6 close (2026-08-25).** L9 ships closed. Five modules
(`agentcode`, `codegrounding`, `planpolicy`, `authenticity`,
`providergateway`) add the agentic controls without modifying
`dream/agent.py`, `security/engine.py`, `security/injection.py`,
`security/quarantine.py`, `security/pathsafety.py`, `docker_sandbox.py`,
`dream/providerhubs/**`, or any bridge method module — each new module
calls the existing layer rather than rewriting it. `tools/security_audit.py`
grew an L9 battery and is proven to fail: `tests/test_sec_agentic_audit.py`
breaks each control in a subprocess across **19 sabotage scenarios** (plus a
baseline L3 check that the pre-P6 alarm still fires) and asserts the audit
exits 1 naming the right layer. New coverage: 349 cases across six
`tests/test_sec_agentic*.py` files; suite 2502 → 2851 with zero
regressions. CI wiring is Path B (`docs/handoff/sec-agentic-audit.patch`).
