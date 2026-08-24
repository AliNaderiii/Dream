# SEC-B — Floor & engine (L3 blocklist + L2 approval engine v2)

**Stage:** B of six · **PR:** PR-S1 (with Stage A) · **Date:** 2026-08-24
**Base:** Stage A commit `b732de0` on `arena/01a03293-dream`
**Evidence:** [`SEC-GATES.md`](./SEC-GATES.md) Gate B sections (real output only).

## What shipped

| Commit | Surface |
| --- | --- |
| `87b1675` | kernel: `dream/security/` package + 222 tests |
| `cc9ad32` | wiring: floor first at every execution choke point + 28 integration tests |
| `0c42c33` | desktop: persistent off-mode banner + status-bar chip (+8 vitest) |
| this | docs + changelog |

## Gaps closed

- **SEC-G-08 (L3 floor).** `dream/security/blocklist.py` — 8 data-driven
  rules (`RULES`): POSIX root/home/system wipes (`rm`/`rmdir`/`find -delete`,
  `--no-preserve-root`), Windows drive-root and system-dir wipes
  (`rd`/`rmdir`/`del`/`erase`), disk formats (`format X:`, `mkfs*` on block
  devices), raw block-device writes (`dd of=/dev/…`, redirects), fork bombs
  (classic shell + `%0|%0` + `bash -c` wrappers), remote-pipe-to-shell
  (`curl|wget|fetch` → `sh/bash/python/…`, incl. `sudo`), PowerShell
  `Remove-Item`/`rm`/`ri` recursive wipes incl. unquoted space paths and
  `$env:` targets, registry **hive-root** deletes (`reg delete HKLM/HKCR/
  HKU/HKCC/HKCU` — subkey deletes stay legal), and PowerShell remote-payload
  execution (`iex`/`Invoke-Expression` + downloaders). Bilingual refusal
  names the matched class and rule id.
- **SEC-G-04 (assessor).** `dream/security/assessor.py` — secondary
  classification with strict JSON schema (`{"level","reason"}` exactly),
  hard timeout via joined worker thread (a hanging fake backend denies —
  pinned by test), exception isolation, and deterministic offline pattern
  rules (curated verb tables; unknown verbs fail toward the human). No
  test touches the network; model access is injected.
- **SEC-G-05 (modes).** `smart | manual | off`. `manual` is the default and
  reproduces pre-SEC behaviour byte-for-byte (demo output verified). `off`
  is constructor-guarded (`off_opt_in=True`) and env-guarded
  (`DREAM_SECURITY_MODE=off` alone is ignored; `DREAM_SECURITY_OFF_OPT_IN=1`
  required); it carries a persistent, non-dismissible red banner on every
  route plus a steady status-bar chip.
- **SEC-G-06 (autonomous contexts).** `cron_mode` / `single_query_mode`
  default `"deny"`; scheduled dreams created by the bridge get
  `context="cron"`; a single-query context denies identically. `auto` is the
  explicit override and still runs the floor first.
- **SEC-G-07 (history).** Append-only SQLite under `DREAM_APPROVAL_DB`
  (default `data/dream-approvals.db`); every floor block, assessor verdict,
  human approval/denial, off-mode allowance, and autonomous denial lands
  there. Corruption fails closed with a bilingual error and never wipes;
  a failed append never breaks the turn. Module pinned free of
  UPDATE/DELETE/DROP by test.

## The contract (evaluation order)

1. **Floor** — before any approval logic, non-overridable by `off`, cron
   auto/approve-modes, `--yolo` grants, private registries, `approved=True`
   flags, or a yes-approver. Pinned by the property test
   `blocklist_precedes_approval` (engine sweep + cross-surface sweep).
2. **Context** — autonomous contexts deny dangerous tools by default.
3. **Mode** — assessor-ordered (`smart`), human-decided (`manual`), or
   loudly-logged opt-out (`off`).

## Obfuscation coverage (red-team corpus, all pinned)

Quoting (`r''m`, `"r"m`), backslash escapes (`r\m`), case games, split and
reordered flags, `$HOME`/`${HOME}`/`~`/`%USERPROFILE%`/`%HOMEDRIVE%%HOMEPATH%`/
`%SystemRoot%`/`%WINDIR%`/`$env:*` expansion, `..` path normalization
(`/etc/../`, `/tmp/..`, `c:\windows\..\`), zero-width and bidi-override
insertion, full-width homoglyphs (NFKC), Cyrillic lookalikes (floor table),
Persian-normalizer reuse, `bash -c`/wrapper unwrapping, `&&`/`;`/`|`
segment splitting without surrounding spaces, unquoted space paths.

## RF-4 — existing-test edits

Exactly one fixture changed, with justification:
`tests/test_security_tool_risk.py::test_dangerous_tool_denied_without_approver`
used `rm -rf /` before the floor existed; that command is now (correctly)
a floor event, so the tier test uses `echo needs approval` and asserts its
original property unchanged (dangerous tier + no approver → denial naming
the missing approver). Before: 1945/11. After: 2195/11 — all other 1944
pre-existing tests pass unmodified.

## Desktop surface (G-05 indicators)

`security.json` locale namespace (3 keys × 8 locales, fa=0), echo transport
answers `security.status` with the kernel default posture, banner in its own
lazy chunk, chip in the status bar. Entry chunk 62.49 kB gzip ≤ 63.22
baseline; all desktop gates green (SEC-GATES B.6).

## Gate B criteria — status

- [x] Red-team corpus passes: no bypass including Windows + obfuscation
      (tests/security/: 250 cases).
- [x] Assessor timeout → deny proven with a hanging fake backend; error and
      schema violations deny; offline path uses pattern rules only, no network.
- [x] `off` shows persistent indicators (banner + chip, every route).
- [x] cron/single-query deny defaults tested; the floor is hit in `off` mode,
      cron approve/auto modes, always-allow/yolo grants, and yes-approvers
      (property sweep across all surfaces).
- [x] Durable approval history under the data-dir env-override pattern.

**Decision: GREEN — Stage C (L4 file safety + L6 credential hygiene) may begin.**
