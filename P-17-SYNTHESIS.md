# P-17 Synthesis — Web Gateway Mobile/Tablet Responsiveness and Authentication Completion

> Status: **proposed scope; awaiting explicit approval before production edits**.
> This report is the required synthesis-gate artifact. No production file is
> edited before approval.

---

## 1. Read-only base verification

| Check | Result |
|---|---|
| `git fetch origin` | completed |
| `origin/main` | `110e7bb153403ba9e36ececfc2e2e4f492938869` |
| `git rev-parse HEAD` | `110e7bb153403ba9e36ececfc2e2e4f492938869` |
| Working branch | `arena/01a07ac1-dream` |
| `git status --porcelain` | empty (clean checkout) |
| `git tag` (v0.4*) | none — `v0.4.7` does not exist |
| PR #130 merge SHA | `110e7bb153403ba9e36ececfc2e2e4f492938869` == HEAD == origin/main |
| Checklist inspected at | `MASTER_CHECKLIST.md` line 224: item 5.3 = `[~]` |

`HEAD == origin/main == 110e7bb` at the moment of the read-only gate. The
checklist was read from the working tree, which matches that exact remote SHA.

**Local verification environment** (honest, recorded for the audit):

- Python: `3.11.x`; dev dependencies (`.[web]`, `pytest`) are not installed in
  this checkout — Python gateway tests are **not** re-run locally here.
- Node `22.x`; `apps/desktop/node_modules` is not installed — vitest/tsc/eslint
  are **not** re-run locally here.
- `python tools/check_locales.py` is not required for this phase (no locale
  changes proposed) and was not run.
- CI on the base SHA adjudicates the full matrices; the post-approval
  verification plan re-checks CI on the final pushed SHA.

---

## 2. Audit of the gateway server, token manager, remote gateway route, and served SPA

### 2.1 What UI does the gateway actually serve?

`dream/gateway_server.py:get("/")` and `get("/{path:path}")` both call
`_find_ui_dir()`, which looks for `apps/desktop/dist`, `../apps/desktop/dist`,
or `~/.dream/ui` — whichever contains `index.html`. The served file is
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

**Key finding**: the gateway does **not** serve a separate "gateway UI". It
serves the same React SPA shell as the desktop app. The viewport `<meta>` is
correct (`width=device-width, initial-scale=1.0`), but the shell itself has
**no responsive layout** — it is built for a wide desktop window.

### 2.2 How does the served shell differ from a mobile/tablet-appropriate shell?

The shell (`app-shell.tsx`) renders:

```
TitleBar (h-titlebar, desktop window controls on Win/Linux)
  → [ ActivityRail (w-12 or w-44, icon-only or icon+label) | Sidebar (min 280px, resizable) ]
    → main:
        TopBar (h-12, model selector dropdown, workspace button, new-session, theme)
        Outlet (page content)
        StatusBar (h-6, status dots, bridge/sandbox/security/provider/language)
```

At phone-portrait widths (~320–428px) and tablet-portrait widths (~528–828px)
this layout has no collapse/scroll/drawer behaviour wired for the viewport —
the rail and sidebar are independent of viewport width, and the TopBar carries
several controls that would overflow or wrap poorly.

**Surfaces that must respond at narrow widths:**

| Surface | Current behaviour | Required narrow behaviour |
|---|---|---|
| ActivityRail | w-12 (collapsed/hover) or w-44 (expanded); hover-peek | Collapse to icon-only or move to a bottom/tab navigation; drawer for expanded labels; focus + Escape tested |
| Sidebar | min 280px, resizable via drag handle, collapse toggle (`mod+b`) | Collapse to a drawer/sheet on narrow widths; collapse toggle still reachable; keyboard resize still safe |
| TopBar | h-12, several controls in a row | Allow wrap/scroll or move secondary actions (workspace, theme) into an overflow menu; primary title + new-session stay visible |
| StatusBar | h-6, many indicators in a row | Allow wrap; keep status dot + bridge indicator visible; language menu reachable |
| TitleBar | Desktop window controls (Win/Linux) | Hide native window controls when served from the gateway (they are Tauri-specific); keep "Dream" brand |
| GatewaySettings | Token management card | Stacked layout, full-width token rows, copy button reachable; no loss of masked-token display |
| Chat / Projects / Workspace / Subagents / Data / Provenance / Settings | Page content via Outlet | Content area scrolls; primary actions reachable; no horizontal overflow |

### 2.3 Token manager and auth scope enforcement

`dream/gateway_server.py:TokenManager`:

- Raw token returned **once** by `create_token` / `rotate_token`.
- Persisted state stores `id`, `prefix`, `scope`, `label`, `created_at`,
  `last_used_at`, `verifier` (SHA-256 of raw) — **never the raw secret**.
- `verify_token` uses `secrets.compare_digest` against every stored verifier.
- `list_tokens` / `all_tokens` exclude raw and verifier.
- `load_error` non-empty on malformed/unsupported store → callers fail closed.
- `create_gateway_app` raises `GatewayTokenStoreError` when `tm.load_error` is
  set — never silently mints a full-access token.

`dream/remotegw/tokens.py:RemoteTokens` + `dream/remotegw/http.py:RemoteGwHandler`:

- Remote gateway (stdlib JSON-RPC) also bearer-only; query-string tokens refused.
- `extract_bearer` raises on `?token=` presence.
- `RemoteGwHandler.log_message` suppresses lines containing `drm_` or `Bearer`.
- Scope mapping: `coarse_scope` maps fine scopes (`read`, `chat`, `safe_tools`,
  `admin`) to `TokenScope.READ`/`WRITE`; write-only actions reject read tokens.

**Finding**: auth is correctly implemented and tested. P-17 must preserve this
exactly — no new auth mechanism, no scope weakening, no credential leakage.

### 2.4 Security headers, CORS, TLS, LAN, mDNS

`build_security_headers` (pure, stdlib-testable):

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: no-referrer-when-downgrade`
- `Strict-Transport-Security` only when `tls_enabled`
- `Content-Security-Policy` default (script same-origin + unsafe-inline/eval,
  style same-origin + unsafe-inline, img data:/blob:, connect ws:/wss:, frame-ancestors 'none')
  unless a route-provided CSP wins.

CORS middleware: `allow_credentials=False`, no wildcard, methods `GET/POST`,
headers `Content-Type, Authorization`. Origins from `DREAM_GATEWAY_ALLOWED_ORIGINS`
or same-origin only.

Bind policy: `resolve_gateway_bind` refuses public/unspecified addresses;
LAN requires `--lan` + explicit private host; default is `127.0.0.1`.

mDNS: `MDNSAdvertiser` advertises `_dream._tcp` via `avahi`/`dns-sd`, falls
back to printing LAN IPs.

**Finding**: All preserved. Responsive UI changes must not weaken any of these.

### 2.5 Existing tests

| Suite | File | What it covers | Relevant to P-17 |
|---|---|---|---|
| Gateway server | `tests/test_gateway_server.py` | TokenManager, TLS, mDNS, config, bridge integration (32 tests) | Preserve; token creation/rotation/revocation via bridge |
| Web gateway security | `tests/test_web_gateway_security.py` | Bind policy, verifier storage, bearer transport, CORS, throttling, FastAPI app (no auto-mint) | Preserve; auth preservation evidence |
| Security gateway | `tests/test_security_gateway.py` | Scope boundaries: read token can't write, write satisfies read, revoke, masked listing | Preserve; scope enforcement evidence |
| Connectivity gateway | `tests/test_connectivity_gateway.py` | Connectivity adapters | Out of scope; preserve |
| SEC agentic gateway | `tests/test_sec_agentic_gateway.py` | SEC agentic gateway | Out of scope; preserve |
| App shell | `apps/desktop/src/components/layout/app-shell.test.tsx` | Shell chrome, routes, sidebar toggle, theme, RTL, session creation, command palette, search | Extend with viewport behaviour |
| Sidebar | `apps/desktop/src/components/layout/sidebar.test.tsx` | Session management, resize, loading, error, retry | Extend with narrow-width collapse |
| ActivityRail | `apps/desktop/src/components/layout/activity-rail.test.tsx` | Drawer modes, pin, cycle, labels | Extend with narrow-width/Escape/focus |
| Reduced motion | `apps/desktop/src/styles/reduced-motion.test.ts` | `prefers-reduced-motion` | Preserve |

**Finding**: No viewport/responsive tests exist. P-17 adds deterministic bounded
viewport tests.

---

## 3. Exact proposed scope

### 3.1 In scope (approved only after explicit sign-off)

**A. Responsive shell behaviour (shared React components)**

Because the gateway serves the same SPA, responsive behaviour lives in the
shared shell components. Changes are limited to adding viewport-aware collapse/
drawer/scroll behaviour that:

1. **ActivityRail** — at narrow widths (below a defined mobile breakpoint),
   collapse to icon-onlyrail or move primary destinations to a bottom navigation
   bar; expanded labels become a drawer/sheet; pin/hover/peek modes remain
   functional; Escape closes any open drawer; focus order is logical in LTR and
   RTL.
2. **Sidebar** — at narrow widths, collapse to a drawer/sheet instead of a
   permanently-resizable 280px+ sidebar; the existing collapse toggle
   (`mod+b` / button) still works; keyboard resize handle remains safe and
   doesn't trap focus; RTL mirrors correctly.
3. **TopBar** — allow secondary controls (workspace, theme, model selector) to
   wrap into an overflow menu or scroll at narrow widths; keep page title +
   new-session button visible and usable.
4. **StatusBar** — allow wrap at narrow widths; keep agent status + bridge
   indicator visible; language menu reachable.
5. **TitleBar** — when served from the gateway (no Tauri window API), hide the
   native window-control buttons (minimize/maximize/close) since they are
   Tauri-specific; keep the "Dream" brand and pending-approvals badge. Desktop
   (Tauri) path unchanged.
6. **GatewaySettings** — stacked, full-width token rows; copy button reachable;
   no loss of masked-token display or one-time-token presentation.
7. **Page content (Outlet)** — content area scrolls vertically at narrow widths;
   no horizontal overflow; primary actions reachable.
8. **RTL** — all logical properties (`border-e`, `start`/`end`, `gap`, `ps`/`pe`)
   already used; verify RTL layout preserves direction, spacing, focus order, and
   readable token/path fields at narrow widths.

**Breakpoints (proposed, deterministic, testable):**

- Phone portrait: `max-width: 428px`
- Phone landscape: `min-width: 429px` and `max-width: 600px` (or a separate
  orientation-based test via `matchMedia`)
- Tablet portrait: `min-width: 601px` and `max-width: 828px`
- Tablet landscape: `min-width: 829px` and `max-width: 1024px` (desktop-ish;
  regression-only)
- Desktop regression: `min-width: 1025px` — existing behaviour unchanged.

These are test viewport widths, not product claims about supported devices.

**B. Deterministic bounded viewport/component tests**

New tests in `apps/desktop/src/components/layout/` (or a new
`apps/desktop/src/components/layout/responsive.test.tsx`):

1. Phone portrait (e.g. `matchMedia('(max-width: 428px)')` or jsdom viewport
   resize via `window.innerWidth` override where supported) — rail collapsed or
   moved, sidebar drawer, topbar wrapped/scrolled, no horizontal overflow,
   primary actions reachable.
2. Phone landscape — same checks at the landscape width.
3. Tablet portrait — rail/sidebar behaviour at tablet width.
4. Tablet landscape — regression check that desktop behaviour is preserved.
5. Desktop regression — confirm existing shell behaviour unchanged at wide width.
6. RTL at narrow width — logical spacing, direction, focus order, token field
   readable.
7. Keyboard navigation — Tab order through reachable controls at narrow width;
   Escape closes drawer/menu; focus returns to a logical place.
8. Drawer/menu focus — when a drawer opens, focus moves into it; Escape closes;
   focus does not trap inappropriately.
9. No-overflow — assert no element has `overflow-x` visible causing horizontal
   overflow at each tested width (check scrollWidth vs clientWidth on the root or
   key containers).
10. Loading / offline / unauthorized / expired-token / read-only / server-error /
    empty states — confirm these states are still explicit and reachable at narrow
    widths (largely inherited; verify not broken by responsive changes).

All tests are bounded: no public services, no real credentials, no arbitrary
sleeps, no unbounded waits. Token values in tests are fake (`drm_`-prefixed
deterministic strings or the test bridge fakes already in place).

**C. Authentication-preservation tests / call sites**

1. Confirm `dream/gateway_server.py:TokenManager` behaviour unchanged by re-running
   the existing `test_web_gateway_security.py`, `test_security_gateway.py`, and
   `test_gateway_server.py` suites (CI does this; the phase does not modify these
   files).
2. Confirm the served SPA still uses bearer-only auth (the gateway requires it;
   the SPA's `gateway.*` bridge calls go through the existing bridge surface).
3. Confirm no new credential surface is introduced: no token in URL, no token in
   logs, no token in test output, no token in screenshots/UI errors.
4. Confirm scope enforcement unchanged: read-only token cannot perform write
   operations in the responsive UI (the UI may hide write buttons when the token
   is read-only; the backend enforces this regardless).

**D. Documentation**

1. Update `MASTER_CHECKLIST.md` item 5.3 from `[~]` to `[x]` **only after**
   implementation and evidence satisfy the complete item (responsive UI + auth
   preservation + tests + CI green on the final SHA).
2. Add a `P-17-AUDIT.md` after implementation with final evidence and honest
   skipped/failed results.
3. Add a `docs/STATUS.md` P-17 entry (borderline — only if approved).

### 3.2 Out of scope (explicitly excluded)

- **No new authentication mechanism**, bypass, public service, or credential
  dependency.
- **No provenance schema or provenance writes.**
- **No scheduler, reminders, projects/workspace isolation, subagents, provider
  routing, billing, Web Gateway server semantics, workflows, release automation,
  or Rust** — unless the audit finds a direct responsive/auth call-site
  requirement and the exact change is approved. The audit found **none**.
- **No rewrite of merged history** or edit of historical P-12–P-16 audit
  artifacts (those files are untouched).
- **No v0.4.7, version bump, or release.**
- **No separate "gateway-only" UI** — the gateway continues to serve the shared
  SPA. Responsive behaviour is added to the shared shell.
- **No broadening of the gateway into a new product.**

### 3.3 Files touched (proposed, subject to approval)

| File | Change | Justification |
|---|---|---|
| `apps/desktop/src/components/layout/app-shell.tsx` | Add viewport-aware layout: hide Tauri window controls when not in Tauri context; allow shell to switch to narrow layout | Audit finding: shell has no responsive behaviour; gateway serves same shell |
| `apps/desktop/src/components/layout/activity-rail.tsx` | Add narrow-width behaviour (collapse/move to bottom nav or drawer); keyboard + Escape | Audit finding: rail is fixed-width, not usable at narrow widths |
| `apps/desktop/src/components/layout/sidebar.tsx` | Add narrow-width drawer/sheet collapse; keep resize handle safe | Audit finding: sidebar min 280px overflows at narrow widths |
| `apps/desktop/src/components/layout/top-bar.tsx` | Allow wrap/overflow menu for secondary controls at narrow widths | Audit finding: topbar carries several controls that overflow |
| `apps/desktop/src/components/layout/status-bar.tsx` | Allow wrap at narrow widths; keep key indicators visible | Audit finding: statusbar has many indicators in a row |
| `apps/desktop/src/components/gateway/gateway-settings.tsx` | Stacked full-width token rows; verify copy reachable (likely already fine; minor polish only) | Audit finding: verify no loss of masked-token display at narrow widths |
| `apps/desktop/src/styles/theme.css` | Add responsive breakpoint utility classes / media queries only as needed by the shell (no theme color changes) | Audit finding: no viewport media queries exist |
| `apps/desktop/src/components/layout/responsive.test.tsx` (new) | Deterministic bounded viewport/component/a11y tests | Audit finding: no responsive tests exist |
| `MASTER_CHECKLIST.md` | Update item 5.3 to `[x]` only after implementation + CI green | Required by mission |
| `P-17-AUDIT.md` (new) | Final evidence and honest skipped/failed results | Required by mission |

**Explicitly NOT touched:** `dream/gateway_server.py`, `dream/remotegw/tokens.py`,
`dream/remotegw/http.py`, `dream/remotegw/service.py`, `dream/remotegw/bind.py`,
`dream/security/providergateway.py`, `dream/bridge/methods.py` (gateway token
methods), any `tests/test_*.py` (preserved), `tests/test_sec_agentic_gateway.py`,
`tests/test_connectivity_gateway.py`, route pages under `apps/desktop/src/routes/`,
`docs/design/prototype/*`, `P-12*/P-13*/P-14*/P-15*/P-16*` files, `SEC-*`,
`pyproject.toml`, `Cargo.toml`, `.github/workflows/*`, `package.json`.

---

## 4. Verification plan (post-approval)

1. Implement only the approved files in §3.3.
2. `git diff --check`; assert only approved files change.
3. Frontend: `cd apps/desktop && npm run typecheck && npm run lint && npm run format:check && npm run build && npm run test && npm run accessibility:check` — where dependencies are available. If `node_modules` is not installed in the checkout, these run in CI.
4. Python: `pytest tests/test_gateway_server.py tests/test_web_gateway_security.py tests/test_security_gateway.py -q` — guarded with `importorskip` where FastAPI/uvicorn are optional (the existing suites already do this). Run only where dependencies are available; otherwise CI adjudicates.
5. Confirm token/auth tests still pass (auth preservation evidence).
6. Confirm no token, raw credential, private path, prompt, or user content appears in test output (grep test output for `drm_` real tokens — there should be none; only fake/test tokens or masked prefixes).
7. Re-check CI on the final pushed SHA: `gh run list --branch arena/01a07ac1-dream` and commit check-runs; confirm green.
8. Write `P-17-AUDIT.md` with the actual diff, exact commands, and honest notes.
9. After merge approval, independently verify the merge SHA, post-merge CI, tags (no v0.4.7), and checklist state (item 5.3 = `[x]`).

---

## 5. Explicit non-goals

- No client sign-off; Gate G9 remains open and is not touched.
- No release tag, version bump, `v0.4.7`, or release automation.
- No public service, real credential, arbitrary sleep, or unbounded test.
- No claim that G9 or release readiness is satisfied.

---

## 6. Honest environment limitations

- This synthesis was written from a read-only audit of the checkout. The full
  Python (`.[web]`/`pytest`) and frontend (`node_modules`/vitest/tsc/eslint)
  suites could **not** be executed locally because dev dependencies are not
  installed in this checkout. CI on the base SHA is green and adjudicates those
  matrices. The post-approval verification plan re-checks CI on the final pushed
  SHA.
- Exact pixel-level layout claims are deferred to the implementation and the
  deterministic tests; this synthesis only records the structural gap (no
  responsive breakpoints in the shipped shell) and the proposed scope.

---

## 7. Approval request

Please confirm or revise the proposed scope in §3 before any production edit:

1. **Responsive shell behaviour** — the listed surfaces (ActivityRail, Sidebar,
   TopBar, StatusBar, TitleBar, GatewaySettings, Outlet content) with the
   proposed breakpoints — is this the correct scope, or should any surface be
   excluded/inclusion-added?
2. **Tests** — the listed deterministic bounded viewport/component/a11y tests —
   confirm or revise.
3. **Auth preservation** — confirm the listed preservation checks are sufficient.
4. **Documentation** — confirm item 5.3 → `[x]` only-after-evidence, plus
   `P-17-AUDIT.md` and optional `docs/STATUS.md` entry.
5. **Out-of-scope exclusions** — confirm the listed exclusions are correct.

No file is edited until this synthesis is approved.
