# SEC-03 — Browser Session Security Audit

## Scope, branch and base

- **Branch:** `arena/01a060d4-dream` (this session's pinned working branch)
- **Base commit:** `2690093` (`chore(desktop): add typed frontend logger (SEC-02)` — the tip of `main` at task start, i.e. Dream v0.4.6 + merged SEC-01 + merged SEC-02)
- **Target release:** v0.4.7
- **Note on branch naming:** the task specified `fix/p0-security-stability`, but this workspace is session-pinned to `arena/01a060d4-dream`; the PR is opened from that branch against `main` instead. No other branch was created or pushed.

---

## Files audited

| File | Role |
|------|------|
| `dream/browser_controller.py` | Core browser controller, `BrowserSession`, approval logic |
| `dream/bridge/methods.py` | RPC bridge — `browser.*` handlers |
| `dream/bridge/errors.py` | Error taxonomy and redaction |
| `dream/bridge/__init__.py` | Re-exports of browser types |
| `tests/test_browser_controller.py` | Existing + new SEC-03 tests |
| `tests/test_browse.py` | Browse service tests (audited, not modified) |
| `tests/test_browse_security.py` | Browse security tests (audited, not modified) |

---

## Files changed

| File | Change summary |
|------|----------------|
| `dream/browser_controller.py` | Removed `always_allow_domain` field and `always_allow` param; added approval TTL (900 s), fetch quota (20), domain blocklist, `BrowserSecurityError.reason`, injectable clock |
| `dream/bridge/methods.py` | Removed `always_allow` from `browser_approve`; updated `browser_navigate` to distinguish reason codes; added structured error data |
| `tests/test_browser_controller.py` | Rewrote existing tests for new contract; added 45 new SEC-03-specific tests |
| `data/blocked_domains.txt` | Added project-level blocklist placeholder (gitignored by `.gitignore:/data/`; force-add with `git add -f` if needed) |
| `SEC-03-AUDIT.md` | This document |

---

## Removed bypasses

### 1. `always_allow_domain` field on `BrowserSession`

**Before:** `BrowserSession` had `always_allow_domain: bool = False`. When set, the domain was added to `_approved_domains` and all future navigations to that domain were automatically allowed without re-approval.

**After:** The field is **gone**. There is no permanent domain whitelist. Approvals always expire.

### 2. `always_allow` parameter on `approve_session()`

**Before:** `approve_session(session_id, always_allow=True)` added the domain to `_approved_domains`, enabling the bypass above.

**After:** The parameter is **gone**. The signature is `approve_session(session_id: str) -> BrowserSession | None`. Any legacy caller passing `always_allow=True` receives a `TypeError` immediately, without granting any access.

### 3. `_approved_domains` set in `BrowserController`

**Before:** `BrowserController.__init__` initialised `self._approved_domains: set[str] = set()`. The `navigate()` method checked this set — domains in it bypassed the approval requirement.

**After:** The set is **gone**. There is no permanent in-memory domain whitelist.

### 4. `always_allow` in `browser_approve` RPC handler

**Before:** `dream/bridge/methods.py :: browser_approve` read `params.get("always_allow", False)` and forwarded it to `approve_session()`, propagating the bypass to any JSON-RPC caller.

**After:** The parameter is **not consumed**. The handler calls `bc.approve_session(session_id)`. Any `always_allow` key sent by an old client is silently ignored without granting access. The response no longer echoes `always_allow` back.

---

## Approval state machine and TTL policy

```
[request_approval] → status=pending
        │
        ├─ [blocklist check fails] → BrowserSecurityError(reason="blocked_domain")
        │
        │   [approve_session()]
        ├──────────────────────────────→ status=active, approved_at=clock()
        │                                       │
        │                               elapsed ≤ TTL?
        │                               ├─ YES → navigate() proceeds
        │                               └─ NO  → status=expired
        │                                        BrowserSecurityError(reason="approval_expired")
        │
        └─ [deny_session()] → status=closed, closed_at=wall-clock
```

**Key properties:**

- **Default TTL:** 900 seconds (15 minutes). Configurable via `BrowserController(approval_ttl_seconds=N)`.
- **Clock:** `time.monotonic()` by default. Injectable via `BrowserController(_clock=fn)` for deterministic testing.
- **No re-use across domains:** if `navigate()` is called for a domain that differs from the current session's domain, a new pending session is created and `approval_required` is raised.
- **Expiry on reset/navigation:** if an expired session still exists and the same domain is re-navigated, `approval_expired` is raised immediately. A new `request_approval` + `approve_session` cycle is required.
- **No session persistence:** sessions exist in memory only; they do not survive process restart.

---

## Quota policy

- **Default maximum:** 20 fetches per browser session (SEC-03 requirement).
- **Counter reset:** `_session_fetch_count` resets to `0` when `attach_existing_browser()` or `launch_isolated_browser()` is called. It does **not** reset when a new approval is granted.
- **Counting:** the counter is incremented **before** the network call, after all security checks pass. This means:
  - Quota is checked before network access.
  - Failed network requests (Playwright errors) still consume quota once the security gate passes.
  - Blocked/unapproved/expired requests do **not** consume quota (they raise before the increment).
- **Rejection:** on the (max+1)-th call, `BrowserSecurityError(reason="quota_exceeded")` is raised before any network I/O.
- **Configuration:** `BrowserController(max_fetches=N)` for tests. The production default is `DEFAULT_MAX_FETCHES = 20`.
- **Status:** `get_status()` includes `session_fetch_count` and `max_fetches`.

---

## Blocklist format and lookup rules

### File locations (checked in order)

1. `~/.dream/blocked_domains.txt` — user-level; takes effect for all Dream instances run by this user.
2. `data/blocked_domains.txt` (relative to the repository root) — project-level default. Note: `/data/` is listed in `.gitignore`; use `git add -f data/blocked_domains.txt` to track it in git if desired.

### Entry grammar

```
entry   = hostname [ ":" port ]
hostname = label *( "." label )   # simplified; Unicode IDN allowed
port    = 1*DIGIT                  # integer in [1, 65535]
```

```
# This is a comment
evil.com        # inline comment also allowed
bad.org:443     # valid port — stripped; bad.org is blocked
```

- One entry per line.
- Comments begin with `#` (line-level or inline after the entry).
- Blank lines and whitespace-only lines are **ignored without error**.
- Entries are normalised: lowercase, trailing dots stripped, port stripped after validation.
- A scheme prefix (`http://`, `https://`, `ftp://`) is stripped before parsing.
- Missing files are silently ignored (safe default).

### Fail-closed malformed-entry policy (SEC-03 hardening, v2)

**Any non-empty, non-comment entry that cannot be safely parsed raises `BlocklistParseError`.**

The `BrowserController` catches this exception on first blocklist access, sets `_blocklist_error = True`, and **refuses all navigation with `reason="blocklist_error"`** until the file is corrected and the controller is re-instantiated.

No malformed entry is silently skipped in a way that could leave a domain the operator intended to block still reachable.

#### Port validation (strict)

| Port field | Treatment |
|------------|-----------|
| Absent (no colon) | Accepted — plain hostname |
| Non-empty string of ASCII digits, value in [1, 65535] | Accepted — port stripped, hostname used |
| Empty string (`evil.com:`) | **`BlocklistParseError`** |
| Non-digit characters (`evil.com:NOTAPORT`, `evil.com:80abc`) | **`BlocklistParseError`** |
| Negative sign or plus (`evil.com:-1`, `evil.com:+80`) | **`BlocklistParseError`** — `str.isdigit()` rejects these |
| Port 0 | **`BlocklistParseError`** — out of range [1, 65535] |
| Port > 65535 (`evil.com:65536`, `evil.com:99999`) | **`BlocklistParseError`** |
| Multiple colons (`evil.com:80:extra`) | **`BlocklistParseError`** — more than one colon |

#### Other rejections (all `BlocklistParseError`)

| Entry | Reason |
|-------|--------|
| `[::1]` | IPv6 bracketed address — not a hostname-only entry |
| `<evil>` | Forbidden hostname characters |
| `evil com` | Space in hostname |
| Empty hostname part | Empty string after stripping |

#### `BlocklistParseError` attributes

| Attribute | Content |
|-----------|---------|
| `path` | Filesystem path of the blocklist file |
| `lineno` | 1-based line number of the malformed entry |
| `raw_entry` | The entry text as it appeared in the file (safe for logs) |

### Matching rules

| Situation | Result |
|-----------|--------|
| `evil.com` in blocklist, request for `evil.com` | **blocked** (exact match) |
| `evil.com` in blocklist, request for `sub.evil.com` | **blocked** (subdomain match) |
| `evil.com` in blocklist, request for `a.b.evil.com` | **blocked** (deep subdomain match) |
| `example.com` in blocklist, request for `badexample.com` | **not blocked** (substring, not subdomain) |
| `evil.com` in blocklist, request for `notevil.com` | **not blocked** |
| blocklist is empty, any domain | **not blocked** |

The subdomain check uses suffix + label boundary: `hostname.endswith("." + entry)`. This prevents substring false-positives.

### Application order

Blocklist (including fail-closed error state) → Quota → Approval → Network

The blocklist is consulted **first**, before any approval check and before any network access. An approval flag cannot override it.

### Privacy

Error messages for blocked domains do **not** reveal which blocklist entry matched, only a generic "Navigation to that domain is not permitted." message.  Error messages for `blocklist_error` do not reveal blocklist file contents.

---

## Threat model and security considerations

| Threat | Mitigation |
|--------|-----------|
| Agent navigates to an unauthorised domain without user consent | Explicit approval required; no bypass. |
| Stale approval grants indefinite access | TTL of 900 s enforced via monotonic clock. |
| Approval re-used across session resets | Counter and session reset together on new browser session. |
| Retry loops exhaust resources | Quota of 20 fetches per session; failed requests count too. |
| Operator types bad port in blocklist, intended domain silently unblocked | Fail-closed: `BlocklistParseError` → all navigation refused until fixed. |
| Malformed blocklist entry silently skipped, intended domain reachable | Fail-closed: any parse error poisons the entire blocklist. |
| Invalid port text silently stripped, wrong hostname in blocklist | Strict port validation: only integer in [1, 65535] accepted. |
| Multiple-colon entry (`evil.com:80:extra`) creates wrong hostname via `rsplit` | Detected as >1 colon → `BlocklistParseError`. |
| Operator blocklist bypassed via approval | Blocklist check precedes approval; approval cannot override it. |
| Blocklist contents leaked in errors | Error messages generic; entry that matched is not disclosed. |
| URL query params (tokens, API keys) leaked in logs | `logger.warning` logs only `reason=…`; never the URL. |
| Substring domain spoofing (`badexample.com` allowed by `example.com` block) | Label-boundary suffix check prevents this. |
| Old client sends `always_allow=True` | Silently ignored; `TypeError` if passed as keyword arg to `approve_session()`. |
| IPv6 / punycode blocklist entries | IPv6 brackets rejected as `BlocklistParseError`; lowercase normalisation handles punycode. |
| Missing blocklist file causes crash | Missing files silently ignored; safe default. |

### Residual risks / known limitations

1. **No persistent approval store.** Approvals live in memory only. Restarting the bridge loses all approvals; the next request needs fresh approval.
2. **No per-domain quota.** The 20-fetch quota is per browser session, not per domain.
3. **Blocklist is loaded at first use, not reloaded.** Changes to the blocklist file take effect only on the next `BrowserController` instantiation. The fail-closed state also persists for the controller's lifetime — restart required to recover from a parse error.
4. **`always_allow` removed from RPC contract.** Old clients must be updated to work within the TTL window.
5. **Cookie/credential exposure via `get_cookies()`.** The `browser_get_cookies` endpoint is unchanged; it returns all cookies. Frontend callers should be mindful of cookie sensitivity.

| Threat | Mitigation |
|--------|-----------|
| Agent navigates to an unauthorised domain without user consent | Explicit approval required; no bypass. |
| Stale approval grants indefinite access | TTL of 900 s enforced via monotonic clock. |
| Approval re-used across session resets | Counter and session reset together on new browser session. |
| Retry loops exhaust resources | Quota of 20 fetches per session; failed requests count too. |
| Malicious/misconfigured blocklist crashes agent | Malformed entries skipped with warning; missing files ignored. |
| Operator blocklist bypassed via approval | Blocklist check precedes approval; approval cannot override it. |
| Blocklist contents leaked in errors | Error messages generic; entry that matched is not disclosed. |
| URL query params (tokens, API keys) leaked in logs | `logger.warning` logs only `reason=…`; never the URL. |
| Substring domain spoofing (`badexample.com` allowed by `example.com` block) | Label-boundary suffix check prevents this. |
| Old client sends `always_allow=True` | Silently ignored; `TypeError` if passed as keyword arg to `approve_session()`. |
| IPv6 / punycode blocklist entries | IPv6 brackets rejected as malformed; lowercase normalisation handles punycode. |

### Residual risks / known limitations

1. **No persistent approval store.** Approvals live in memory only. Restarting the bridge loses all approvals; the next request needs fresh approval. This is conservative and correct but may be inconvenient.
2. **No per-domain quota.** The 20-fetch quota is per browser session, not per domain. A single session could exhaust its quota on one domain. This is intentional — adding per-domain limits is a future enhancement.
3. **Blocklist is loaded at first use, not reloaded.** Changes to the blocklist file take effect only on the next `BrowserController` instantiation.
4. **`always_allow` removed from RPC contract.** Old clients that relied on `always_allow=True` to avoid repeated approvals must be updated to work within the TTL window.
5. **Cookie/credential exposure via `get_cookies()`.** The `browser_get_cookies` endpoint is unchanged; it returns all cookies. This requires approval only at the browser-session level. Frontend callers should be mindful of cookie sensitivity.

---

## Compatibility notes

| Behaviour | Before | After |
|-----------|--------|-------|
| `BrowserSession.always_allow_domain` | Present, settable | **Removed** |
| `approve_session(session_id, always_allow=True)` | Adds domain to permanent whitelist | **TypeError** — param removed |
| `browser.approve` RPC with `always_allow: true` | Granted permanent access | Silently ignored; expiring approval only |
| `browser.approve` RPC response | `{"approved":true,"session_id":…,"always_allow":…}` | `{"approved":true,"session_id":…}` |
| `browser.navigate` error data on security failure | `{"approval_required":true,"url":…,"session_id":…}` | Structured by `reason`: `"approval_required"`, `"approval_expired"`, `"quota_exceeded"`, `"blocked_domain"`, `"invalid_url"` |
| `get_status()` | Included `approved_domains` | Includes `session_fetch_count`, `max_fetches`, `approval_ttl_seconds` |

**Frontend impact:** The frontend's `browse_approve` call no longer needs (or receives) an `always_allow` field. The `browser.navigate` error payload has an additional `reason` key; existing code that only checks `approval_required` continues to work.

---

## Test inventory

### Existing tests (preserved, updated)

| Test | File | Status |
|------|------|--------|
| `test_browser_controller_import` | `test_browser_controller.py` | Pass |
| `test_browser_controller_init` | `test_browser_controller.py` | Pass |
| `test_page_content_defaults` | `test_browser_controller.py` | Pass |
| `test_browser_session_defaults` | `test_browser_controller.py` | Updated — checks `approved_at`, no `always_allow_domain` |
| `test_request_approval_creates_pending_session` | `test_browser_controller.py` | Pass |
| `test_approve_session_activates_pending` | `test_browser_controller.py` | Updated — checks `approved_at` is set |
| `test_deny_session_closes_pending` | `test_browser_controller.py` | Pass |
| `test_approve_unknown_session_returns_none` | `test_browser_controller.py` | Pass |
| `test_deny_unknown_session_returns_none` | `test_browser_controller.py` | Pass |
| `test_get_status_returns_dict` | `test_browser_controller.py` | Updated — checks new fields |
| `test_attach_existing_browser_raises_without_chrome` | `test_browser_controller.py` | Pass |
| `test_launch_isolated_raises_without_chrome` | `test_browser_controller.py` | Pass |
| `test_navigate_raises_without_browser` | `test_browser_controller.py` | Pass |
| `test_get_content_raises_without_browser` | `test_browser_controller.py` | Pass |
| `test_execute_js_raises_without_browser` | `test_browser_controller.py` | Pass |
| `test_fill_form_raises_without_browser` | `test_browser_controller.py` | Pass |
| `test_click_raises_without_browser` | `test_browser_controller.py` | Pass |
| `test_screenshot_raises_without_browser` | `test_browser_controller.py` | Pass |
| `test_get_cookies_raises_without_browser` | `test_browser_controller.py` | Pass |
| `test_browser_unavailable_error_message` | `test_browser_controller.py` | Pass |
| `test_browser_security_error_message` | `test_browser_controller.py` | Updated — checks `reason` attr |
| `test_bridge_reflects_browser_imports` | `test_browser_controller.py` | Pass |

### New SEC-03 tests (added)

| Test | Coverage |
|------|----------|
| `test_always_allow_domain_field_does_not_exist` | `always_allow_domain` removed from `BrowserSession` |
| `test_approve_session_signature_has_no_always_allow_param` | `always_allow` param removed from `approve_session()` |
| `test_always_allow_true_does_not_bypass_approval` | TypeError when old caller passes `always_allow=True` |
| `test_no_approved_domains_set_after_approval` | `_approved_domains` permanent whitelist removed |
| `test_approval_required_for_unapproved_domain` | Unapproved domain → `reason="approval_required"` |
| `test_approved_session_allows_navigation_within_ttl` | Valid approval within TTL → passes gate |
| `test_approval_expires_after_ttl` | After 901s → `reason="approval_expired"` |
| `test_approval_at_exact_ttl_boundary_expires` | At exactly 900s → NOT expired (elapsed > ttl is False) |
| `test_reapproval_required_after_expiry` | Expired session → new approval cycle required |
| `test_default_approval_ttl_is_900` | `DEFAULT_APPROVAL_TTL == 900` |
| `test_default_max_fetches_is_20` | `DEFAULT_MAX_FETCHES == 20` |
| `test_fetch_quota_allows_configured_maximum` | Exactly `max_fetches` navigations allowed |
| `test_quota_exceeded_raised_before_network` | 21st fetch → `reason="quota_exceeded"` before network |
| `test_quota_resets_for_new_session` | Counter resets on new browser session |
| `test_get_status_includes_quota_info` | Status dict includes quota fields |
| `test_blocked_exact_domain_raises_before_approval` | Exact blocklist match → `reason="blocked_domain"` |
| `test_blocked_subdomain_raises` | Subdomain of blocked entry → blocked |
| `test_blocked_deep_subdomain_raises` | Deep subdomain → blocked |
| `test_lookalike_domain_not_falsely_blocked` | `badexample.com` not blocked by `example.com` |
| `test_unrelated_domain_not_blocked` | Unrelated domain not falsely blocked |
| `test_blocklist_check_before_navigate_network` | Blocklist fires before network call |
| `test_blocked_domain_error_does_not_reveal_blocklist_contents` | Error does not leak blocklist entry |
| `test_blocklist_domain_cannot_be_bypassed_by_approval` | Tampered approval does not bypass blocklist |
| `test_missing_blocklist_files_are_safe` | Missing files → empty set, no crash |
| `test_blocklist_ignores_comments_and_blank_lines` | Comments/blanks ignored |
| `test_blocklist_normalises_case` | Entries lowercased |
| `test_blocklist_normalises_trailing_dot` | Trailing dots stripped |
| `test_blocklist_handles_entry_with_port` | Valid port (e.g. `:443`) is stripped; hostname is matched |
| `test_malformed_blocklist_entry_raises_parse_error` | Invalid chars (`<evil>`) → `BlocklistParseError` with path+lineno (fail-closed, v2) |
| `test_malformed_ipv6_entry_raises_parse_error` | `[::1]` → `BlocklistParseError` (fail-closed) |
| `test_blocklist_uses_first_path_then_second` | Both files merged |
| `test_parse_blocklist_entry_valid_port` | Ports 1, 8080, 65535 accepted and stripped |
| `test_parse_blocklist_entry_no_port` | Entry without port accepted as-is |
| `test_parse_blocklist_entry_empty_port_raises` | `evil.com:` → `BlocklistParseError` |
| `test_parse_blocklist_entry_non_numeric_port_raises` | `evil.com:NOTAPORT` → `BlocklistParseError` |
| `test_parse_blocklist_entry_negative_port_raises` | `evil.com:-1` → `BlocklistParseError` |
| `test_parse_blocklist_entry_zero_port_raises` | `evil.com:0` → `BlocklistParseError` |
| `test_parse_blocklist_entry_port_too_large_raises` | `evil.com:65536`, `evil.com:99999` → `BlocklistParseError` |
| `test_parse_blocklist_entry_multiple_colons_raises` | `evil.com:80:extra` → `BlocklistParseError` |
| `test_parse_blocklist_entry_ipv6_raises` | `[::1]` → `BlocklistParseError` |
| `test_parse_blocklist_entry_invalid_chars_raises` | `<evil>` → `BlocklistParseError` |
| `test_parse_blocklist_entry_empty_raises` | Empty string → `BlocklistParseError` |
| `test_parse_blocklist_entry_strips_scheme` | `https://evil.com:8080` → `evil.com` |
| `test_parse_blocklist_entry_trailing_dot_stripped` | `evil.com.` → `evil.com` |
| `test_parse_blocklist_entry_case_normalised` | `EVIL.COM` → `evil.com` |
| `test_controller_enters_fail_closed_on_malformed_blocklist` | Malformed blocklist → `_blocklist_error=True`, all nav refused |
| `test_controller_fail_closed_persists_across_calls` | Error state persists across multiple calls |
| `test_blocklist_error_blocks_navigate_before_network` | `blocklist_error` blocks before any network call |
| `test_blocklist_error_blocks_request_approval` | `request_approval()` also refuses when blocklist is malformed |
| `test_valid_blocklist_with_port_is_not_fail_closed` | Valid port entries load normally, no fail-closed |
| `test_normalise_hostname_lowercase` | Case normalisation |
| `test_normalise_hostname_strips_trailing_dot` | Trailing dot stripped |
| `test_normalise_hostname_strips_port` | Port stripped |
| `test_normalise_hostname_strips_scheme` | Scheme stripped |
| `test_normalise_hostname_invalid_ipv6_returns_none` | IPv6 brackets → None |
| `test_normalise_hostname_empty_returns_none` | Empty/blank → None |
| `test_is_blocked_exact_match` | Exact match test |
| `test_is_blocked_subdomain` | Subdomain blocked |
| `test_is_blocked_not_substring` | Substring NOT matched |
| `test_is_blocked_unrelated` | Unrelated domain not blocked |
| `test_is_blocked_empty_blocklist` | Empty blocklist → nothing blocked |
| `test_request_approval_rejects_non_https_scheme` | Non-HTTP scheme → `invalid_url` |
| `test_navigate_rejects_non_https_scheme` | `javascript:` URL → `invalid_url` |
| `test_browser_security_error_default_reason` | `reason=""` default |
| `test_security_error_does_not_include_query_string` | Error text has no query secrets |
| `test_approval_required_error_does_not_include_url` | Error text has no URL content |

---

## Commands run and results

### Search inventory (before change)

```
rg -n "always_allow|always_allow_domain|BrowserSession|BrowserController|approved_domains" dream tests
```

Found `always_allow_domain` in `dream/browser_controller.py:51` and `tests/test_browser_controller.py:67,97-104`.
Found `always_allow` in `dream/browser_controller.py:391,397,408-410` and `dream/bridge/methods.py:2749-2753`.

### Tests (after SEC-03 v1 initial change + v2 fail-closed hardening)

```
pytest tests/test_browse.py tests/test_browse_security.py tests/test_browser_controller.py -v
```
**91 passed** (3 browse + 88 controller)

```
pytest -q
```
**3030 passed, 14 skipped** in 119.42s

### Ruff (after change)

```
ruff check dream/browser_controller.py dream/bridge/methods.py tests/test_browser_controller.py tests/test_browse.py tests/test_browse_security.py
```
**All checks passed!**

### Search for remaining bypasses (after change)

```
rg -n "always_allow|always_allow_domain" dream tests
```

All remaining occurrences are:
- Documentation comments explaining the removal
- Test code that **asserts** the bypass is gone (proving the contract)
- Zero production bypass paths

---

## Coordination needed

None required. All changes are within the strict SEC-03 scope.

### Items to communicate to other sub-agents

1. **SEC-01/SEC-02 compatibility:** No changes to Rust bridge or frontend logger; those sub-agents' work is unaffected.
2. **Frontend clients** should be updated to not send `always_allow` in `browser.approve` calls. The parameter is now silently ignored, but emitting it is confusing. The `browser.navigate` error response now contains a `reason` field that clients can use to distinguish security failure types.
3. **Browser RPC contract version bump:** Consider documenting the `browser.approve` response shape change (`always_allow` removed from response) in `docs/bridge/protocol.md` in a subsequent PR.

---

## Known limitations

1. **Blocklist not git-tracked by default.** The `/data/` directory is excluded by `.gitignore`. The project-level `data/blocked_domains.txt` file is created but must be force-added (`git add -f`) to be tracked. The user-level `~/.dream/blocked_domains.txt` is the primary recommended location.
2. **No approval UI in the bridge.** The approval flow (call `browser_request_approval`, present dialog, call `browser_approve`) is unchanged from the pre-SEC-03 design. This task only hardens the security contract; it does not add a UI.
3. **Playwright optional.** If Playwright is not installed, all `browser.*` RPC methods raise `BridgeError(-32011, …)`. This is unchanged from pre-SEC-03.
