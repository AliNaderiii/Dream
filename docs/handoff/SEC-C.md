# SEC-C — Data & files (L4 file-write safety + L6 credential hygiene)

**Stage:** C of six · **PR:** PR-S2 (with Stage D) · **Date:** 2026-08-24
**Base:** Stage B close `1fcb45b` on `arena/01a03293-dream`
**Evidence:** [`SEC-GATES.md`](./SEC-GATES.md) Gate C sections (real output only).

## What shipped

| Commit | Surface |
| --- | --- |
| `76f67fb` | C-1: MCP credential hygiene + secret value-scanning (17 tests) |
| `8c5683d` | C-2: file-write safety floor + deletion quarantine (48 tests) |
| this | docs + changelog |

## Gaps closed

- **SEC-G-14 (MCP env leak — the confirmed finding).** `dream/mcp/transport.py`
  no longer passes `dict(os.environ)` to children. `security/envfilter.py`
  builds a credential-free functional allowlist (PATH/HOME/locale/temp/shell
  basics, audited by name to contain no KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL)
  plus ONLY the variables the owner explicitly mapped in the server config.
  Proven end-to-end by a malicious fake stdio MCP server launched as a real
  child process with fake provider/gateway/VCS/cloud/chat credentials seeded
  in the parent: its exfiltration dump contains zero secrets and only the
  allowlist + its one mapped variable.
- **SEC-G-15 (description sanitization, C-layer).** Server-authored text is
  sanitized before anything else sees it — invisible/control stripping
  (zero-width, bidi overrides, C0/C1), whitespace collapsing, 1 000-char
  cap — applied at `MCPTool/Resource/Prompt.from_dict`, the single choke
  point where MCP text enters Dream. Stage D layers injection-pattern
  detection on top of the same module.
- **SEC-G-16 (egress toggle).** `MCPServerConfig.egress` defaults deny.
  Network transports (sse/ws) refuse to connect while it is off — pinned by
  a test that fails if any network call is attempted. Stdio children always
  receive the filtered environment.
- **SEC-G-17 (value-scanning redaction).** `security/secrets.py` scans for
  provider keys, VCS tokens, cloud access keys, chat tokens, JWTs, `drm_`
  gateway tokens, and private-key blocks. Wired into the message log
  (before persist), provenance payloads (before sealing), bridge error
  strings, and log records via an idempotent redacting filter installed at
  bridge startup. Redaction copies; originals stay untouched.
- **SEC-G-09 (sensitive-path denylist).** `security/pathsafety.py` — second
  layer on every write surface (`write_note`, legacy skill writes,
  `save_skill_md`, `/learn` references): POSIX system dirs, home credential
  dirs, credential file names (`.env*`, `.netrc`, `id_*`,
  `.git-credentials`, `known_hosts`…), Dream's own stores and private data,
  Windows system dirs + AppData, UNC shares. Checks run against the
  symlink-resolved absolute path; refusals are bilingual.
- **SEC-G-10 (traversal corpus).** 8.3 short names refused, UNC refused,
  symlinked escape to a secret refused (both the workspace check and the
  denylist fire), `..` normalization covered; benign workspace writes
  pinned to keep working.
- **SEC-G-11 (quarantine).** Deletions are moves: `quarantine_delete()`
  relocates files and skill folders into `data/quarantine`
  (`DREAM_QUARANTINE_DIR`) with JSON metadata; bounded at 50 MiB per item /
  500 MiB store — an oversized item or a full store is REFUSED, never
  destroyed. `restore()` returns byte-identical (refuses when the original
  path is occupied), `purge()` destroys only the quarantined copy.
  `delete_skill` routes through it; reply gains additive `quarantined` /
  `quarantine_id` fields. Restore/purge UI lands with the Stage F Security
  Center.

## Malicious-MCP gate proof (required by Gate C)

`tests/security/test_sec_mcp_hygiene.py::test_malicious_stdio_server_cannot_exfiltrate_the_environment`:
a real child process, instructed to dump its entire environment, receives
`PATH` and its one explicitly mapped variable — and none of the five seeded
fake credentials — while its hostile tool descriptions (zero-width +
bidi-override + 3 KB padding) arrive at the client sanitized and capped.
`test_network_transport_refuses_to_connect_when_egress_is_off` proves the
egress gate refuses before any wire activity.

## Self-fixes (this stage)

- The C-1 redaction fixtures are assembled from fragments so the repo's
  tracked-file secret scanner never matches source literals while the
  runtime values still exercise every redaction shape.
- C-2 wiring initially used `importlib.reload(tools)` in tests; reloading
  the registry module corrupts cross-test state. Rewritten to the
  established `monkeypatch.setattr(tools, "WORKSPACE_ROOT", …)` pattern
  (no legacy test edited; caught and fixed inside the stage).

## Gate C criteria — status

- [x] Traversal corpus blocked on Windows + POSIX (pathsafety suite).
- [x] Quarantine restore/purge works; bounds fail closed; deletions never
      destroy outright (`delete_skill` included).
- [x] Malicious-MCP test proves env filtering + description sanitization.
- [x] Automated secret-scan clean (tracked-file scanner green with the new
      test files tracked) and value-scanning wired across logs, message
      log, provenance, and errors.

**Decision: GREEN — Stage D (L5 injection scanning + L8 transport) may begin.**
