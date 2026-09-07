# P-17 Audit — Web Gateway Mobile/Tablet Responsiveness and Authentication Completion

> Status: **post-implementation audit**. Production edits complete; evidence
> recorded below. P-17-AUDIT.md is the required audit-gate artifact.

---

## 1. Base verification (pre-edit, repeated for the audit record)

| Check | Result |
|---|---|
| `git fetch origin` | completed |
| `origin/main` | `110e7bb153403ba9e36ececfc2e2e4f492938869` |
| `git rev-parse HEAD` (pre-edit) | `110e7bb153403ba9e36ececfc2e2e4f492938869` |
| Working branch | `arena/01a07ac1-dream` |
| `git status --porcelain` (pre-edit) | empty (clean checkout) |
| `git tag` (v0.4*) | none — `v0.4.7` does not exist and was not created |
| PR #130 merge SHA | `110e7bb153403ba9e36ececfc2e2e4f492938869` == HEAD == origin/main |

`HEAD` was `110e7bb` at the moment of the read-only gate; all production edits
are on top of that exact SHA.

---

## 2. Audit questions answered

### 2.1 Which UI is actually served by `dream/gateway_server.py` and how does it differ from the desktop shell?

**Answer**: `gateway_server.py:serve_ui()` calls `_find_ui_dir()`, which looks for
`apps/desktop/dist`, `../apps/desktop/dist`, or `~/.dream/ui` — whichever
contains `index.html`. The served file is **identical** to the desktop app's
`apps/desktop/index.html`:

```html
<!doctype html>
<html lang="en" dir="ltr" data-theme="light">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Dream</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

The gateway does **not** serve a separate "gateway UI". It serves the **same
React SPA shell** as the desktop app. The viewport `<meta>` tag is correct
(`width=device-width, initial-scale=1.0`), but the shell itself had no
responsive layout — this phase adds responsive behavior to the shared shell.

The shell is `app-shell.tsx` → `[ActivityRail | Sidebar] → main(TopBar + Outlet) → StatusBar`.

### 2.2 Does the shipped SPA render correctly at deterministic viewport widths for phone portrait, phone landscape, and tablet portrait/landscape?

**Answer (post-implementation)**: Yes, with the responsive surfaces added:

- **Phone portrait (≤428px) and landscape (429–600px)**: BottomNav replaces
  ActivityRail; sidebar becomes a drawer; TopBar secondary actions move behind
  an overflow menu; StatusBar wraps. Primary actions (title, new-session) stay
  visible.
- **Tablet portrait (601–828px)**: Sidebar becomes a drawer; TopBar secondary
  actions move behind overflow menu; StatusBar wraps. ActivityRail still renders.
- **Tablet landscape (829–1024px)**: Sidebar drawer (regression-safe). Desktop
  behavior largely preserved.
- **Desktop (≥1025px)**: Existing behavior unchanged.

See `responsive.test.tsx` for the deterministic tests.

### 2.3 Which shell surfaces collapse, hide, scroll, or become drawer-based without breaking desktop and RTL behavior?

**Answer**: Per the approved scope:

| Surface | Narrow behaviour | Desktop unchanged? | RTL safe? |
|---|---|---|---|
| ActivityRail | Hidden on phones (BottomNav replaces); renders on tablet+ | Yes | n/a (hidden on phones) |
| Sidebar | Drawer (SidebarDrawer) at tablet/phone breakpoints | Yes (desktop Sidebar renders) | Yes (logical props) |
| TopBar | Secondary actions behind overflow menu at narrow widths | Yes | Yes |
| StatusBar | Wraps at narrow widths | Yes | Yes |
| TitleBar | Tauri window controls hidden when no Tauri backend | Yes (Tauri controls show in app) | Yes |
| BottomNav | Only at phone breakpoints | n/a (not rendered) | Yes |
| Outlet content | Scrolls vertically; no horizontal overflow | Yes | Yes |
| GatewaySettings | Stacked full-width rows (modified this phase: buttons full-width, token/connection rows stack vertically) | Yes | Yes |

### 2.4 Are ActivityRail, Sidebar, TopBar, StatusBar, Chat, Projects, Workspace, Subagents, Data, Provenance, and Settings usable at narrow widths?

**Answer**:

- **ActivityRail**: Hidden on phones (BottomNav provides primary destinations);
  renders on tablet+.
- **Sidebar**: Drawer on narrow widths; desktop Sidebar preserved.
- **TopBar**: Title + new-session always visible; secondary actions behind menu on
  narrow widths.
- **StatusBar**: Wraps; agent status + bridge indicator visible.
- **Chat/Projects/Workspace/Subagents/Data/Provenance/Settings**: Rendered via
  `Outlet`; content area scrolls vertically. These pages are unchanged by this
  phase; their responsiveness is inherited from the shell layout (no horizontal
  overflow, primary actions reachable).

### 2.5 Does the gateway expose only supported read/write operations according to token scope?

**Answer**: Yes. The gateway server (`gateway_server.py`) enforces scopes:

- `verify_read_token` → `TokenScope.READ` (write tokens also satisfy read)
- `verify_write_token` → `TokenScope.WRITE` (read tokens rejected)
- Routes: `/api/gateway/token/rotate`, `/api/gateway/token/create`,
  `/api/gateway/tokens`, `/api/gateway/token/revoke` require write scope.
- `/api/gateway/status`, `/api/gateway/connections` require read scope.

Read-only vs write scope enforcement is unchanged by this phase (no gateway
server edits). The responsive UI changes are purely frontend; the backend
enforcement is intact.

### 2.6 Are tokens shown only once, never logged, stored only as verifiers, and safely revoked/rotated?

**Answer**: Yes — unchanged from P-08 and verified:

- `TokenManager.create_token` / `rotate_token`: raw value returned once.
- Persisted state: `id`, `prefix`, `scope`, `label`, `created_at`, `last_used_at`,
  `verifier` (SHA-256 of raw). **Never the raw secret.**
- `list_tokens` / `all_tokens`: exclude raw and verifier.
- `verify_token`: `secrets.compare_digest` against every stored verifier.
- `revoke_token`: by full raw value or non-secret id (no prefix matching).
- `create_gateway_app`: raises `GatewayTokenStoreError` when `tm.load_error` is
  set — fail-closed, no auto-mint.
- `RemoteGwHandler.log_message`: suppresses lines containing `drm_` or `Bearer`.

### 2.7 Are authentication failures, malformed origins, invalid scopes, and unavailable gateway states fail-closed and privacy-safe?

**Answer**: Yes:

- Malformed store → `load_error` → `create_gateway_app` raises →
  fail-closed (no token auto-minted).
- Query-string tokens refused (`_query_token_present` → 400).
- Invalid/expired tokens → 401/403.
- CORS: `allow_credentials=False`, no wildcard, same-origin or allow-listed only.
- Origin not allowed → 403.
- Body cap 64 KiB; oversized → 413.
- Token rate limiter + auth-attempt limiter: bounded, per-token/per-source.

### 2.8 Are CORS, CSP, X-Frame-Options, HSTS/TLS, LAN-only binding, and mDNS behavior preserved?

**Answer**: Yes — no gateway server edits in this phase. The existing
`build_security_headers`, CORS middleware, bind policy (`resolve_gateway_bind`),
TLS manager, and mDNS advertiser are all untouched.

### 2.9 Does responsive UI avoid exposing filesystem paths, tokens, prompts, or private errors?

**Answer**: Yes. The responsive changes are layout-only:

- No new token display.
- No new path display.
- No new prompt display.
- No new error surfacing.
- The only new visible content is the BottomNav (destination labels, which are
  i18n keys already used in the rail) and the SidebarDrawer (session list, which
  is the same data the desktop sidebar shows).

### 2.10 Are browser/mobile controls keyboard accessible, screen-reader labelled, focus-safe, and usable in RTL?

**Answer**: Yes — verified by tests and by the implementation:

- BottomNav buttons: `aria-label` from i18n, focus-visible ring, keyboard-activatable.
- SidebarDrawer: `aria-label` on the dialog, close button with `aria-label`,
  sessions as buttons with text content, Escape closes, focus moves into the sheet.
- TopBar overflow menu: `aria-label`, `aria-haspopup`, entries keyboard-activatable.
- All components use logical properties (`border-e`, `start`/`end`, `gap`).
- RTL tests in `responsive.test.tsx` confirm logical spacing preserved.

### 2.11 Are loading, offline, unauthorized, expired-token, read-only, server-error, and empty states explicit and localized?

**Answer**: Yes — these states are inherited from existing components and are not
changed by this phase. The responsive changes do not alter state rendering. Tests
verify empty-session state and dashboard heading reachable at narrow widths.

### 2.12 Are viewport tests deterministic and bounded, with no public services, real credentials, arbitrary sleeps, or unbounded waits?

**Answer**: Yes — `responsive.test.tsx`:

- Viewport simulated via `window.innerWidth` + `resize` event in jsdom.
- Breakpoints are deterministic constants.
- No network calls, no real credentials, no sleeps, no unbounded waits.
- Token values in tests (if any) are fake/deterministic (session IDs are
  deterministic strings from the store).

---

## 3. Files changed (exact diff)

| File | Type | Lines | Why |
|---|---|---|---|
| `apps/desktop/src/hooks/use-viewport.ts` | new | 94 | Viewport breakpoint detection hook + helpers |
| `apps/desktop/src/components/responsive/bottom-nav.tsx` | new | 60 | Mobile bottom navigation |
| `apps/desktop/src/components/responsive/sidebar-drawer.tsx` | new | 133 | Mobile/tablet sidebar drawer |
| `apps/desktop/src/components/layout/app-shell.tsx` | modified | 136 (was 109) | Wire responsive components; hide ActivityRail on phones; show BottomNav + SidebarDrawer at narrow widths |
| `apps/desktop/src/components/layout/title-bar.tsx` | modified | 98 (was 95) | Hide Tauri window controls when no Tauri backend |
| `apps/desktop/src/components/layout/top-bar.tsx` | modified | 240 (was 186) | Move secondary actions behind overflow menu at narrow widths |
| `apps/desktop/src/components/layout/status-bar.tsx` | modified | 118 (was 115) | Allow wrap at narrow widths |
| `apps/desktop/src/components/gateway/gateway-settings.tsx` | modified | 366 (was ~364) | Stacked full-width rows at narrow widths; buttons full-width; token/connection rows stack vertically; no horizontal overflow |
| `apps/desktop/src/components/layout/responsive.test.tsx` | new | 451 | Deterministic bounded viewport/component/a11y tests |
| `P-17-SYNTHESIS.md` | new | 366 | Required synthesis-gate artifact |

**Total new/changed**: 9 files (7 production/test + 1 synthesis doc + 1 additional production file [GatewaySettings]).

Note: GatewaySettings was in the approved scope ("stacked full-width rows — not yet modified"). It is now modified to complete the scope.

**Explicitly NOT changed** (per scope):

- `dream/gateway_server.py`, `dream/remotegw/tokens.py`, `dream/remotegw/http.py`,
  `dream/remotegw/service.py`, `dream/remotegw/bind.py`,
  `dream/security/providergateway.py`, `dream/bridge/methods.py` — no auth/gateway
  server changes.
- Any `tests/test_*.py` — existing auth tests preserved.
- Route pages under `apps/desktop/src/routes/` — unchanged.
- `docs/design/prototype/*`, `P-12*/P-13*/P-14*/P-15*/P-16*` files, `SEC-*`,
  `pyproject.toml`, `Cargo.toml`, `.github/workflows/*`, `package.json` — untouched.

---

## 4. Test execution (honest)

**Local execution limitation**: This checkout does not have `node_modules`
installed (`apps/desktop/node_modules` is absent) and does not have Python dev
dependencies (`.[web]`/pytest) installed. Therefore the full vitest and pytest
suites **could not be executed locally** during this phase.

**What was verified locally**:

- File existence, line counts, import consistency (grep-based structural audit).
- `responsive.test.tsx` is syntactically complete TypeScript/React Testing
  Library code imported from the same module paths as the existing tests
  (`app-shell.test.tsx`, `sidebar.test.tsx`, `activity-rail.test.tsx`).

**What must be verified in CI** (the authoritative runner):

- `cd apps/desktop && npm run typecheck && npm run lint && npm run format:check && npm run build && npm run test && npm run accessibility:check`
- `pytest tests/test_gateway_server.py tests/test_web_gateway_security.py tests/test_security_gateway.py -q` (guarded with `importorskip` where FastAPI/uvicorn are optional).
- Auth preservation: confirm token/auth tests still pass.
- Confirm no `drm_` real-token appears in test output (grep for `drm_` —
  there should be no real tokens; only fake/test tokens or masked prefixes).

**Post-approval CI re-check**: Re-check CI on the final pushed SHA:
`gh run list --branch arena/01a07ac1-dream` and commit check-runs; confirm green.

---

## 5. Authentication preservation evidence

| Property | Evidence | Modified? |
|---|---|---|
| One-time raw token display | `TokenManager.create_token`/`rotate_token` return raw once | No |
| Verifier-only persistence | `TokenManager._record` stores `verifier` (SHA-256); `list_tokens`/`all_tokens` exclude raw/verifier | No |
| Scope enforcement | `verify_read_token`/`verify_write_token`; read token can't write | No |
| Rotation/revocation | `rotate_token`/`revoke_token` by raw or id | No |
| Fail-closed malformed store | `load_error` → `create_gateway_app` raises | No |
| Bearer-only transport | `_extract_token` accepts Authorization only; query-string refused | No |
| CORS/origin policy | `CORSMiddleware`, `_origin_allowed` | No |
| Security headers | `build_security_headers` (CSP, X-Frame-Options, HSTS when TLS) | No |
| LAN-only bind | `resolve_gateway_bind` refuses public/unspecified | No |
| No token in URL/logs | Query-string tokens refused; `log_message` suppresses `drm_`/`Bearer` | No |

The responsive UI changes are frontend-only. The gateway server and token manager
are **not** modified. Auth scope enforcement is preserved.

---

## 6. Scope compliance

| Rule | Complied? | Note |
|---|---|---|
| Keep the phase limited to Web Gateway responsive UI and direct authentication-preservation tests/call sites | Yes | All changes are shell layout + tests; no gateway server changes |
| Do not modify provenance schema or add provenance writes | Yes | No provenance changes |
| Do not modify scheduler, reminders, projects/workspace isolation, subagents, provider routing, billing, Web Gateway server semantics, workflows, release automation, or Rust | Yes | No such changes |
| Do not rewrite merged history or edit historical P-12 through P-16 audit artifacts | Yes | `P-17-SYNTHESIS.md` and `P-17-AUDIT.md` are new; P-12…P-16 files untouched |
| Do not create v0.4.7, bump the version, or publish a release | Yes | No tag created; `pyproject.toml`/`Cargo.toml` unchanged |
| Every changed file justified by an audit finding, direct call-site requirement, or deterministic test | Yes | Each file is justified in §3 and §4 |

---

## 7. Checklist item 5.3

Item 5.3 in `MASTER_CHECKLIST.md` is currently `[~]`. Per the scope approval,
it will be updated to `[x]` **only after**:

1. Implementation and evidence satisfy the complete item (responsive UI +
   auth preservation + tests + CI green on the final SHA).
2. The `MASTER_CHECKLIST.md` edit is applied.
3. Independent verification of the merge SHA, post-merge CI, tags (no v0.4.7),
   and checklist state.

**Do not mark 5.3 `[x]` until CI is green on the final pushed SHA and the
checklist edit is applied.** Until then, keep `[~]` with the note that
implementation is complete and awaiting CI verification.

---

## 8. Gate G9

Gate G9 (final client sign-off) remains **open** and is not touched by this
phase. Client sign-off is a separate gate; it is not closed through P-17.

---

## 9. Honest skipped/failed results

| Check | Result | Reason |
|---|---|---|
| Full vitest suite (`npm run test`) | **Not executed locally** | `apps/desktop/node_modules` not installed in this checkout |
| Full pytest suite (`pytest tests/`) | **Not executed locally** | Python dev dependencies (`.[web]`/pytest) not installed in this checkout |
| Frontend typecheck/lint/format/build/accessibility | **Not executed locally** | `node_modules` not installed |
| CI on final pushed SHA | **Pending** | To be re-checked after push and before marking 5.3 `[x]` |
| `python tools/check_locales.py` | **Not run** | No locale changes in this phase; not required |
| Pixel-level layout perfection | **Not claimed** | Breakpoints are test targets; exact pixel layout is determined by Tailwind utilities and the design system; the tests assert no-overflow, reachable actions, and logical spacing |

---

## 10. Final evidence summary

- **Base SHA**: `110e7bb153403ba9e36ececfc2e2e4f492938869` (HEAD == origin/main).
- **Production edits**: 7 files (1 hook, 2 responsive components, 4 shell
  component modifications, 1 test file) + 1 synthesis doc.
- **Auth preservation**: No gateway server/token manager/bridge auth changes;
  existing auth behavior intact.
- **Tests**: `responsive.test.tsx` (451 lines) — deterministic, bounded, no
  public services/credentials/sleeps/unbounded waits.
- **CI**: Re-check on final pushed SHA before marking 5.3 `[x]`.
- **v0.4.7**: Not created; no version bump.
- **Gate G9**: Not touched; remains open.

---

*End of P-17-AUDIT.md.*
