# SEC-11 Audit — Web Gateway Authentication and Remote-Access Hardening

**Phase:** SEC-11
**Branch:** `arena/01a06d27-dream`
**Base `main` SHA:** `3bcded5a7a47b6976571cc9c7d334c096ee0e451` (SEC-10)
**Date:** 2026-09-04
**Status:** PR open and unmerged. **`v0.4.7` was not created.**

---

## 1. Scope and non-goals

### In scope
- `dream/gateway_server.py` — web gateway defaults, bind policy, token verifier
  store, bearer-only auth, origin/CORS policy, body caps, auth-attempt
  throttling, typed startup/store failures.
- `dream/bridge/methods.py` — validated gateway call path, masked token listing,
  id-driven rotate/revoke, typed gateway start.
- `dream/remotegw/tokens.py` — adapts the remotegw token surface to the shared
  verifier store (the standalone bind policy was already hardened and left
  unchanged).
- `apps/desktop/src/components/gateway/gateway-settings.tsx`,
  `apps/desktop/src/lib/bridge/types.ts`, `apps/desktop/src/lib/bridge/client.ts`
  — remove token-in-URL/QR, masked token list, one-time display, truthful bind
  state.
- `docs/CONFIGURATION.md`, `docs/security/threat-model.md`, `docs/STATUS.md`.
- Existing gateway/remotegw tests plus new `tests/test_web_gateway_security.py`.
- `SEC-11-AUDIT.md` (this file).

### Non-goals / explicitly out of scope
- `dream/connectivity/**` (chat adapters, outbound RFC6455 WebSocket client).
- `dream/gws/**`, `dream/providerhubs/**`.
- `apps/desktop/src-tauri/**` (Rust bridge).
- Workflows, release tooling, unrelated frontend routes.
- SEC-08 / SEC-09 / SEC-10 implementation.
- No inbound WebSocket endpoint was added; no new provider; no billing/quota
  change; no external analytics/telemetry; no cloud dependency; no network
  probes.

---

## 2. Base `main` SHA
`3bcded5a7a47b6976571cc9c7d334c096ee0e451` — remote `origin/main` at phase
start; equal to the SEC-10 merge commit and to the local working head.

---

## 3. Architecture and trust boundaries

```
 desktop UI ──▶ bridge (NDJSON, framed) ──▶ BridgeMethods
                    │
                    └─▶ gateway.*        ──▶ TokenManager (verifier store)
                    └─▶ gateway.start   ──▶ resolve_gateway_bind ──▶ run_gateway

 web gateway (FastAPI) ──▶ token/scope check ──▶ SPA/status/token mgmt only
 LAN / browser client ────▶ Authorization: Bearer ──▶ (same check)

 remotegw (dream-serve) ──▶ bearer token ──▶ JSON-RPC (status only)
```

Trust boundaries:
1. The OS user owns `~/.dream/gateway_tokens.json` (0600).
2. The gateway accepts only same-origin/allow-listed browser origins and
   bearer-only credentials.
3. The gateway does **not** call the Dream agent, tools, memory, files,
   projects, or providers. It only serves the SPA and token-management/status
   routes.
4. `remotegw` is a separate, already-loopback-default JSON-RPC surface.

---

## 4. HTTP / WebSocket route inventory

### Web Gateway (`dream/gateway_server.py`)
| Method | Path | Auth | Bounds/Notes |
| --- | --- | --- | --- |
| GET | `/api/health` | none | No privileged work |
| GET | `/api/gateway/status` | read token | Returns enabled/port/tls/lan_only/connection tracker |
| POST | `/api/gateway/token/rotate` | write token | Rotates the authenticated token; raw value returned once |
| POST | `/api/gateway/token/create` | write token | 64 KiB cap, scope in {read,write}, label <= 200 |
| GET | `/api/gateway/tokens` | write token | Masked rows with non-secret `id` |
| POST | `/api/gateway/token/revoke` | write token | Full raw value or `id` only; no short-prefix revoke |
| GET | `/api/gateway/connections` | read token | Tracker rows (IP/UA) |
| POST | `/api/gateway/connections/{id}/disconnect` | write token | Tracker removal only |
| POST | `/api/gateway/config` | write token | In-memory metadata; validated booleans; bind unchanged |
| GET | `/`, `/{path:path}` | none | SPA; API paths served last |

### WebSocket
**No inbound WebSocket route exists.** `dream/connectivity/websocket.py` is an
outbound RFC6455 client used by Discord/Slack; it cannot be reached by a
remote client and is out of scope. WebSocket acceptance items are N/A.

---

## 5. Authentication and pairing state machines

### Web Gateway token lifecycle
```
 create_token ──▶ raw (returned once) + SHA-256 verifier stored (0600, atomic)
 verify_token ──▶ compare verifier with secrets.compare_digest
 rotate_token ──▶ old verifier removed; new raw returned once
 revoke_token ──▶ raw value or token id
```
No raw token is persisted or listed. Legacy v1 plaintext stores are migrated
to v2 atomically; a `.bak` file is kept if migration/bad-store handling needs
to preserve the original (deleted on success).

### Pairing
The web gateway has no pairing code. The **connectivity gateway** has
`connectivity/auth.AuthStore` (6-digit secure code, 10-minute TTL, single-use,
constant-time compare) — unchanged and out of scope. The remotegw surface uses
bearer tokens, not pairing codes.

---

## 6. Authorization matrix

| Operation | Read token | Write token |
| --- | --- | --- |
| Health | yes (unauthenticated) | yes |
| Gateway status / connection list | yes | yes |
| Create / rotate / revoke / list tokens | no | yes |
| Disconnect tracker entry | no | yes |
| Update in-memory config | no | yes |
| Agent tools / memory / files / projects | N/A — not exposed | N/A — not exposed |

Cross-user isolation is **N/A** for the current single-owner gateway because
no agent data surface is reachable. Token scope separation is tested.

---

## 7. Threat model

- **LAN attacker:** may reach the gateway only if the owner explicitly binds a
  private LAN address. Mitigated by bearer-only auth, read/write scopes,
  per-source and per-token throttling, body caps, origin checks, and no agent
  surface.
- **Leaked raw token:** only the scope granted by that token; token-management
  routes need the write scope; raw tokens never appear in URLs/logs, and are
  shown once.
- **Local multi-user OS:** token verifier store is 0600 and stores a digest, not
  the raw secret.
- **Malformed/oversized client:** capped 64 KiB body, malformed JSON 400,
  invalid method/path 404.
- **No inbound WebSocket** means LAN/browser clients cannot open a persistent
  authenticated socket in SEC-11.

---

## 8. Findings before implementation

| ID | Severity | Finding |
| --- | --- | --- |
| F-01 | Critical | Web Gateway bound `0.0.0.0` by default; `lan_only` was only displayed. |
| F-02 | High | Settings UI built a token-in-URL link/QR. |
| F-03 | High | `gateway.get_tokens` returned raw token values; UI displayed/copied them. |
| F-04 | High | Query-string and `X-Access-Token` auth allowed tokens in URLs/logs. |
| F-05 | High | Raw tokens stored at `0644`; store not thread-safe; per-use rewrite churn. |
| F-06 | Medium-High | `allow_origins=["*"]` + `allow_credentials=True`; no Origin policy. |
| F-07 | Medium | Unbounded `request.json()` bodies; no malformed-JSON guards. |
| F-08 | Medium | Prefix-based revocation could revoke the wrong token with a short prefix. |
| F-09 | Medium | Bridge `gateway.start` spawned a thread on `0.0.0.0` before bind validation. |
| F-10 | Medium | A silent full-access "Setup Token" was auto-minted on first launch. |
| F-11 | Low | `run_gateway` printed a token prefix; connection tracker exposed IPs/UAs. |
| F-12 | Low | Docs overstated QR/CORS/token-display protections and omitted gateway env vars. |

---

## 9. Severity and exploitability

- F-01/F-02/F-03/F-04 were exploitable by anyone who could reach the listener
  or obtain a leaked URL — the highest risk for the slow-network /
  filtered-network population this mission targets, because copied/screenshot
  URLs were the likely vector.
- F-05/F-06/F-07/F-08/F-09 were not remotely exploitable without a token but
  weakened local isolation and could cause wrong revocations or startup
  confusion.

---

## 10. Changes made

1. `dream/gateway_server.py` — loopback default; validated bind policy; public
   and unspecified binds refused; `--lan`; no token prefix print.
2. `dream/gateway_server.py` — bearer-only auth; query-token and
   `X-Access-Token` removed.
3. `dream/gateway_server.py` — verifier store v2 (SHA-256, non-secret id,
   masked prefix), 0600 atomic writes, write lock, legacy v1 migration, fail
   closed on bad/malformed store, no silent setup token.
4. `dream/gateway_server.py` — per-source auth-attempt throttle before
   verification; 64 KiB body cap; malformed JSON handler; scope/label
   validation; no short-prefix revoke; CORS credentials off, explicit origins;
   same-origin/allow-list Origin validation.
5. `dream/bridge/methods.py` — validated `gateway.start`; typed bind result;
   masked `gateway.get_tokens`; id-driven rotate/revoke; min-length guard.
6. `dream/remotegw/tokens.py` — revoke by full raw value or `id`; no unsafe
   prefix matching.
7. `apps/desktop/src/components/gateway/gateway-settings.tsx` — no token in
   URL/QR; masked stored tokens; one-time display; truthful bind/exposure block.
8. `apps/desktop/src/lib/bridge/types.ts`, `client.ts` — `GatewayTokenInfo.id`,
   `GatewayBind`, `GatewayStatus.bind`, masked echo get_tokens.
9. Docs updated; `SEC-11-AUDIT.md` added.

---

## 11. Secure-default analysis

- Effective bind is loopback unless the owner passes a validated private host
  **and** an explicit `--lan` / `DREAM_GATEWAY_LAN_ONLY` opt-in.
- `0.0.0.0`/`::`/public addresses are refused, not merely warned.
- The bridge and CLI use the same resolver.
- No external listener is started by normal desktop startup through this path
  unless `gateway.start` with a `port`/`tls`/`host` param is called, and that
  path now validates the bind.

---

## 12. Token / session / revocation analysis

- Raw tokens returned exactly once from create/rotate.
- Persisted store: version, token id, masked prefix, scope, label, timestamps,
  SHA-256 verifier (no pepper — documented rationale; raw entropy ~160 bits).
- Revocation by full raw value or non-secret id; existing verified requests are
  stateless, so the next request from a revoked token fails.
- No silent restart extension of expired credentials exists because v2 tokens
  carry no embedded expiry (the legacy store had none either); the migration
  preserves existing tokens and the store fails closed if it cannot be read.
  This is a documented known limitation — no TTL was added because that is a
  behavior change needing owner approval.

---

## 13. WebSocket and reconnect analysis

N/A. No inbound WebSocket route exists. The only WebSocket module is an
outbound client for Discord/Slack. Reconnect cannot bypass gateway auth
because there is no gateway WebSocket to authenticate. If a future inbound
WebSocket is added, it must repeat the same bearer handshake check and origin
preflight before any privileged work.

---

## 14. User-isolation analysis

The web gateway has a single owner and exposes no user-scoped data
(memory/files/projects). Cross-user isolation is N/A. Token scope separation
(read cannot perform write operations) and protection of token-management
operations are tested. Dangerous tools remain approval-gated and are never
reachable through the gateway.

---

## 15. Secret / logging analysis

- No API key, bearer token, password, cookie, pairing code, Authorization
  header, or raw token is logged by the changed code.
- The gateway runner prints only the non-secret listening URL and a hint to use
  desktop settings; it no longer prints a token prefix.
- Token rows serialized by bridge/RPC contain no verifier or raw value.
- Tests assert raw values do not appear in `repr` of list/all-token snapshots;
  mocked values are fake, never live credentials.

---

## 16. Offline / local-first analysis

- All gateway auth works without the internet.
- No test contacts external services, DNS, or providers.
- `echo` and local Ollama behavior are untouched; BYOK credentials remain
  user-controlled and are never sent to the gateway.
- The only outward notification in the new code is an optional mDNS
  advertisement, now started only when the bind is non-loopback.

---

## 17. Compatibility and migration analysis

### Compatibility preserved
- CLI/desktop startup shape; local echo/Ollama; BYOK semantics; existing
  remotegw method names and JSON-RPC behavior; existing Persian/English
  user-facing behavior; approval/quota/policy gates.
- Existing `drm_*` legacy tokens are migrated to verifier storage.

### Breaking changes (approved by the PM)
- Default bind changes from `0.0.0.0` to `127.0.0.1`; explicit LAN opt-in.
- Query-string and `X-Access-Token` auth are removed.
- `gateway.get_tokens` returns masked rows instead of raw values; rotate/revoke
  use full raw value or a non-secret `id`.
- On malformed/unreadable stores the web gateway is disabled (fail closed).
- `gateway.start` returns a typed bind result and refuses unsafe hosts.

### Migration behavior
- Legacy v1 store is backed up to `.bak`, migrated atomically to v2, `0600`,
  and the `.bak` is removed on success; on migration failure the original file
  is left untouched and the web gateway refuses to start while the rest of the
  application continues.

---

## 18. Test matrix

See `tests/test_web_gateway_security.py` and the updated existing tests.

### Executed locally (Python)
- Gateway/remotegw/security suite: **71 passed, 2 skipped**.
- Security/scopes/transport/bridge suite: **132 passed**.
- Full Python suite: **3443 passed, 16 skipped** in 159.34s.

### FastAPI app-level tests
`test_fastapi_app_refuses_unsafe_bind` and
`test_fastapi_app_does_not_auto_mint_setup_token` are guarded by
`pytest.importorskip("fastapi")`; in this sandbox and in the repo's base CI
(`pip install -e ".[dev]"`, which does not include `fastapi`/`uvicorn`) they are
**skipped / not executed**. They execute only when `.[web]` is installed.

### Not executed locally (toolchain absent)
- Frontend TypeScript/lint/unit/build: node/npm not installed in this sandbox;
  run in the existing `desktop-ci.yml` frontend job.
- Rust cargo commands: cargo not installed and no Rust file was changed; run in
  the existing `desktop-ci.yml` rust job.

---

## 19. Exact command results

| Command | Environment | Result |
| --- | --- | --- |
| `python -m ruff check .` | Linux, Python 3.11, `.venv` | Pass |
| Gateway/remotegw/security pytest (see §18) | Linux, Python 3.11 | 71 passed, 2 skipped |
| Security/scopes/transport/bridge pytest | Linux, Python 3.11 | 132 passed |
| `python -m pytest -q` | Linux, Python 3.11 | 3443 passed, 16 skipped |
| `python -m mypy .` | — | Not executed — mypy is not a project dependency and is not in CI |
| `npm run typecheck/lint/test/build` | — | Not executed — node/npm unavailable in sandbox |
| `cargo fmt/check/test/clippy` | — | Not executed — cargo unavailable; no Rust changes |

---

## 20. CI run URLs

- PR: https://github.com/AliNaderiii/Dream/pull/125
- Workflow run (Python): https://github.com/AliNaderiii/Dream/actions/runs/33907013928
- Workflow run (desktop): https://github.com/AliNaderiii/Dream/actions/runs/33907013919

CI status is pinned to the final remote SHA in §21 after the last push.

---

## 21. Final remote SHA

`a3d4cb594303e114976af3b0cca67cfa526d2ec2`

Verified via the GitHub API: PR `head.sha == a3d4cb594303e114976af3b0cca67cfa526d2ec2`,
base `main == 3bcded5a7a47b6976571cc9c7d334c096ee0e451`.

---

## 22. Changed-file verification

The PR reports 12 changed files:

1. `SEC-11-AUDIT.md`
2. `apps/desktop/src/components/gateway/gateway-settings.tsx`
3. `apps/desktop/src/lib/bridge/client.ts`
4. `apps/desktop/src/lib/bridge/types.ts`
5. `docs/CONFIGURATION.md`
6. `docs/STATUS.md`
7. `docs/security/threat-model.md`
8. `dream/bridge/methods.py`
9. `dream/gateway_server.py`
10. `dream/remotegw/tokens.py`
11. `tests/test_gateway_server.py`
12. `tests/test_web_gateway_security.py`

No workflows, release tooling, Rust shell files, connectivity/gws/providerhub
files, or SEC-08/09/10 implementation files are changed.

---

## 23. Known limitations

- Web Gateway v2 tokens have **no expiration TTL**. The legacy store had none;
  adding a TTL is a behavior change that was not approved.
- The `connections` tracker is request-scoped, not a real session registry.
- Web Gateway uses **self-signed TLS** when enabled; Dream provides **no
  trusted public certificate, no managed reverse proxy, and no OS firewall
  policy**.
- `fastapi`/`uvicorn` are optional extras; app-level route tests are skipped in
  the base CI environment.
- `DREAM_GATEWAY_ALLOWED_ORIGINS` is the only cross-origin escape hatch; the
  default is same-origin/loopback only.

---

## 24. Residual risks

- If the owner enables LAN exposure on an untrusted network without OS
  firewall/reverse-proxy hardening, LAN clients can still attempt bearer-auth
  (mitigated by scopes, throttling, body caps, and no agent surface).
- The verifier is a plain SHA-256 of a ~160-bit random token; a future
  credential with lower entropy should be pepper/HMAC-protected.
- No inbound WebSocket exists; if one is added later, it must re-apply the
  same auth/origin checks.

---

## 25. Rollback instructions

- Revert the SEC-11 commits with `git revert` (no history rewrite).
- Re-run `ruff check .`, the gateway/remotegw/security suites, and the full
  Python suite.
- Keep the PR open and never merge. `v0.4.7` is never created.

---

## 26. Explicit manual follow-ups for owners

1. Confirm the desktop Settings -> Web Gateway page shows a masked token list
   and a loopback-only bind line.
2. When enabling LAN exposure, set a concrete private bind host and
   `DREAM_GATEWAY_LAN_ONLY=true`/`--lan`; do not use `0.0.0.0`.
3. If using TLS, accept that the bundled certificate is self-signed; Dream does
   not provide trusted public TLS.
4. If a legacy `~/.dream/gateway_tokens.json` exists, verify it migrated to v2
   and that raw values were not corrupted; if `load_error` appears, inspect the
   store.
5. Manually rotate/revoke any tokens that were previously visible in the old UI
   once the desktop build is updated.
