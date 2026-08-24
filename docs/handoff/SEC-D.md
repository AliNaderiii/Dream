# SEC-D — Injection & transport (L5 scanning + L8 hardening)

**Stage:** D of six · **PR:** PR-S2 (with Stage C) · **Date:** 2026-08-24
**Base:** Stage C close `85c7c71` on `arena/01a03293-dream`
**Evidence:** [`SEC-GATES.md`](./SEC-GATES.md) Gate D sections (real output only).

## What shipped

| Commit | Surface |
| --- | --- |
| `a1d873e` | D-1: L5 detection layer + precision corpus (59 tests) |
| `eeec5db` | D-2: scanner wired at every context-entry surface (14 pipeline tests) |
| `9a62823` | D-3: L8 boundary audit + fuzzing + headers + tokens + legacy gate (15 tests) |
| this | docs + changelog |

## Gaps closed

- **SEC-G-12 (injection scanner).** `security/injection.py` over the
  `textguard.py` strip layer. Modes `off | warn | strip`
  (`DREAM_INJECTION_MODE`, default `strip`): hidden Unicode is stripped in
  strip mode / flagged in warn mode; instruction-override patterns in
  English AND Persian plus smuggled tool-call shapes always warn. The
  scanner never raises into a turn; invalid modes fall back to strip.
- **SEC-G-13 (warn + quarantine + provenance).** Findings enter context as
  sanitized text under a visible bilingual banner; the untouched original
  is quarantined under `DREAM_INJECTION_QUARANTINE`
  (default `data/injection-quarantine`) with metadata, and an optional
  provenance tracker receives a `security.injection_quarantined` entry.
  A broken tracker never breaks the turn.
- **Scan surfaces (all seven).** `read_note`, `read_page`/`search_web`,
  MCP `call_tool` text + `read_resource`, `skill_view` (body, description,
  steps) and slash-loaded bodies, `/learn` sources (every kind + the
  existing skill merged into), `extract_snippet`, and `MemoryStore.recall`.
  Stored rows are never mutated — only context copies are guarded (pinned).
- **SEC-G-22 (boundary audit + fuzzing).** Property sweep over every
  handler (sync + async) with 19 garbage shapes; 400 seeded bounded fuzz
  cases weighted over the MP-02 families; result serialisability pinned.
  **Three real leaks found and fixed**: `memory2.snapshot/status` accepted
  unhashable targets (now type-checked), `provenance.list` parsed
  limit/offset unguarded (now validated), three browser read handlers
  leaked `BrowserUnavailableError` (now `TOOL_ERROR`).
- **SEC-G-23 (header tests).** Policy moved into pure
  `build_security_headers()`: CSP `default-src 'self'` +
  `frame-ancestors 'none'`, X-Frame-Options DENY, nosniff, HSTS only over
  TLS, existing CSP respected case-insensitively. Pinned without FastAPI
  installed (zero-dependency discipline kept).
- **SEC-G-24 (token hygiene).** Rotation audited (old token dies, scope
  survives, unknown tokens refuse; read-scope stays read-only after
  rotation). `TokenRateLimiter` (240/min/token default) wired into both
  gateway verify dependencies with a 429 refusal — per-token budgets, so
  one abused credential cannot starve the owner's other devices.
- **SEC-G-25 (desktop.py decision).** **Quarantine behind an explicit
  flag**, implemented as the smaller, non-destructive option:
  `python desktop.py` without `DREAM_ENABLE_LEGACY_DESKTOP=1` exits 2 with
  a bilingual notice; with the flag it behaves exactly as before. The
  `.bat` launchers keep working (they print the notice). The Tauri desktop
  remains the supported surface. Pinned by subprocess + gating tests.

## Corpus (required shapes)

- Poisoned **SKILL.md** — viewed (`skill_view`) and slash-loaded
  (`/evil-slash`) through the real registry/ledger: flagged, quarantined,
  benign twin byte-identical.
- Poisoned **/learn file** — the composed turn carries the bilingual
  warning; benign Persian twin stays clean.
- **FA bidi payloads** — RTL overrides and zero-width splits stripped in
  strip mode; FA override phrases detected after normalizer folding.
- **Instruction overrides EN + FA** — 11 EN and 5 FA payload shapes
  detected; 12 benign controls pass untouched, including Persian recipe /
  literary / religious prose and ordinary docs that use "ignore" /
  "disregard" / "دستور" / "نادیده" honestly.

## Precision contract

U+200C (ZWNJ) is first-class Persian orthography (`می‌خواهم`,
`دستورالعمل‌ها`) — it is NOT flagged anywhere (textguard strip layer
included). LRM/RLM marks are honest in mixed-direction text. Only bidi
overrides/isolates, zero-width space/joiner, and invisible formatting
trip the hidden-Unicode class. This is pinned by the benign corpus in
`test_sec_injection.py`.

## Gate D criteria — status

- [x] Injection corpus (malicious SKILL.md, poisoned /learn file, FA bidi
      payloads, EN+FA overrides) stripped/flagged correctly with benign
      controls untouched.
- [x] Bridge fuzzing finds no unhandled exceptions (400 seeded cases +
      full-handler property sweep; three leaks found and fixed).
- [x] Gateway header/CSP tests green without new dependencies.

**Decision: GREEN — Stage E (L1 scopes + L7 isolation) may begin.**
