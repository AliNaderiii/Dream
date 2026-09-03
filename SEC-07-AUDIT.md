# SEC-07 — User-Agent Hardening Audit (STAB-02)

- **Repository:** Dream v0.4.6 (target release v0.4.7)
- **Base commit:** `c274772a897cb53cd8f76190edd99aa68e8767d8` (`fix(reliability): make sleep operations interruptible (SEC-06)` — the tip of `main` at task start, i.e. Dream v0.4.6 + merged SEC-01 … SEC-06)
- **Working branch:** `arena/01a06693-dream` (this session is fixed to this branch by the Arena environment; the brief's `fix/p0-security-stability` name could not be used — see Coordination Needed)
- **Scope actually touched:** `dream/agent.py` (User-Agent constants, `_reject_user_agent`, `_resolve_user_agent`, one line in `OpenAIBackend.__init__`), `dream/__init__.py` (version binding order only), `tests/test_user_agent.py` (new), `SEC-07-AUDIT.md` (this file). Nothing else.

## 1. Findings from the inspection

Inspected at the base commit before editing (`rg -n "resolve_user_agent|DEFAULT_USER_AGENT|User-Agent|user_agent|OpenAIBackend|__version__" dream tests pyproject.toml`):

| Item | Where | State at base |
|---|---|---|
| `DEFAULT_USER_AGENT` | `dream/agent.py:89` | Hardcoded `"dream-assistant/0.1.0"` while the package ships `0.4.6` — three minor releases stale. |
| `_resolve_user_agent(raw)` | `dream/agent.py:312-326` | `str.strip()`, then reject only if `"\n"` or `"\r"` remains. NUL, TAB, ESC, DEL, C1 controls and unbounded length all passed through. No log on rejection. |
| Wiring | `dream/agent.py:353` | `self.user_agent = _resolve_user_agent(os.environ.get("DREAM_USER_AGENT"))` in `OpenAIBackend.__init__`. |
| Header construction | `dream/agent.py:404-412` | `Request(..., headers={"Content-Type", "Authorization", "User-Agent": self.user_agent})` — a dict, so already a single header slot; the value was the risk, not the plumbing. |
| Canonical version | `dream/__init__.py:20` `__version__ = "0.4.6"`; `pyproject.toml:7` `version = "0.4.6"` | Two declarations, kept identical by the release checklist (`docs/dev/how-to/build-and-sign-installers.md`, "bump in all five places"). `dream/bridge/methods.py` already treats `dream.__version__` as "core version". |
| Existing tests | `tests/test_dream.py:886-981` (11 tests) | Cover default sent, single line, override honoured, `["", "   ", "\t", "\n", "\r", "spaced\r\ninjection"]` fall back, sent on conversation + extraction, body unchanged. All still pass unchanged. |

### Why bare CR/LF filtering was insufficient

`http.client` validates header values with the pattern `\n(?![ \t])|\r(?![ \t\n])`, i.e. it **accepts** a CR or LF that is followed by a space or TAB (obsolete line folding, RFC 9112 §5.2). Verified on this interpreter:

```text
'a\r\n\tfolded' -> ACCEPTED by http.client: b'User-Agent: a\r\n\tfolded'
'a\r\n folded'  -> ACCEPTED by http.client: b'User-Agent: a\r\n folded'
'a\x00b'        -> ACCEPTED by http.client: b'User-Agent: a\x00b'
'a\tb'          -> ACCEPTED by http.client: b'User-Agent: a\tb'
'a\x7fb'        -> ACCEPTED by http.client: b'User-Agent: a\x7fb'
```

The old resolver refused `'a\r\n\tfolded'` (it contains `\r`), so plain injection was already blocked at the Dream layer — but NUL/DEL/TAB/C1 were forwarded verbatim, oversize values were unbounded, and there was no observability. `tests/test_user_agent.py::test_obsolete_line_folding_is_rejected` now proves both halves: the stdlib would accept the folded value, and Dream refuses it.

## 2. Canonical version source

- **Runtime source:** `dream.__version__` in `dream/__init__.py` (a plain string literal; no second constant was introduced).
- **Packaging source:** `pyproject.toml` `[project] version`, kept identical by the documented release checklist.
- **Wiring:** `dream/agent.py` does `from dream import __version__` and builds `DEFAULT_USER_AGENT = f"{USER_AGENT_PRODUCT}/{__version__}"`.

### Circular import and how it was resolved

`dream/__init__.py` imports `dream.agent` at the top, and `dream.agent` now imports `__version__` back from `dream`. With the original layout (`__version__` assigned *after* the submodule imports) this raised `ImportError: cannot import name '__version__' from partially initialized module 'dream'` — reproduced before editing.

Fix: move the `__version__ = "0.4.6"` assignment in `dream/__init__.py` **above** the submodule imports (with a comment explaining why). Python binds it on the partially-initialised module object before `dream.agent` runs, so the import resolves. Ruff's E402 does not flag a dunder assignment before imports (verified: `ruff check` passes on `dream/__init__.py`). The alternative, `importlib.metadata.version("dream-assistant")`, was rejected because it fails for a source checkout that was never `pip install -e .`'d (the repo's `.bat` launchers and `cli.py` support that mode) and would have created a second source of truth.

Drift guard: `test_package_version_matches_pyproject` asserts `dream.__version__ == pyproject [project].version` and that `DEFAULT_USER_AGENT` ends with it, so the header can no longer lag a release silently.

## 3. Old vs new behaviour

| Input (`DREAM_USER_AGENT`) | Before (base) | After (SEC-07) |
|---|---|---|
| unset / `""` | `dream-assistant/0.1.0` | `dream-assistant/0.4.6`, no log |
| `"   "`, `"\t"` | default, silent | default, `WARNING … blank` |
| `"custom-agent/1.0"` | forwarded exactly | forwarded exactly, no log |
| `"  custom-agent/1.0  "`, `"\tcustom/1\t"` | trimmed → forwarded | trimmed → forwarded (unchanged) |
| `"custom-agent/1.0\n"` (trailing newline) | `strip()` ate it → forwarded | **rejected** (`control_character`) — see policy note |
| `"a\r\nX-Injected: 1"`, `"a\nb"`, `"a\rb"` | default, silent | default, `WARNING … control_character` |
| `"a\r\n\tX-Folded: 1"` | default (contains `\r`) | default, logged |
| `"a\x00b"`, `"a\x1bb"`, `"a\x7fb"`, `"a\x85b"` | **forwarded verbatim** | default, `WARNING … control_character` |
| `"a\tb"` (interior TAB) | **forwarded verbatim** | default, `WARNING … control_character` |
| 201+ characters | **forwarded verbatim** | default, `WARNING … too_long` |
| `"Caf\u00e9/1.0"` (printable ISO-8859-1) | forwarded | forwarded (unchanged) |
| `"سلام/1.0"` (outside ISO-8859-1) | forwarded → **every request failed later** with `UnicodeEncodeError` inside `http.client` | default, `WARNING … unencodable` at construction |

Default format: **`dream-assistant/<dream.__version__>`** (RFC 9110 `product/version` token; the `dream-assistant` product name is the repository's established one, matching `pyproject.toml` `name`, `dream/gws/http.py`, `dream/tools.py`, and the Discord adapter). Currently resolves to `dream-assistant/0.4.6`.

## 4. Accepted / rejected character policy

Implemented in `_resolve_user_agent(raw: str | None, version: str) -> str`, evaluated in this order; the first rule that matches decides.

| # | Rule | Result | Log reason |
|---|---|---|---|
| 1 | `raw is None` or `raw == ""` | versioned default | *(none — "not configured" is normal)* |
| 2 | Trim surrounding SP (`0x20`) and HTAB (`0x09`) only — RFC 9110 OWS. Nothing else is normalised; interior spaces are kept verbatim. | continue with trimmed value | |
| 3 | Trimmed value empty | default | `blank` |
| 4 | Any character in `[\x00-\x1f\x7f-\x9f]` anywhere in the trimmed value: all C0 controls (NUL, TAB, LF, CR, ESC, …), DEL, all C1 controls (NEL `0x85`, CSI `0x9b`, …) | default | `control_character` |
| 5 | Trimmed length > `USER_AGENT_MAX_LENGTH` (**200**) | default | `too_long` |
| 6 | Not encodable as ISO-8859-1 (what urllib/`http.client` uses for header values) | default | `unencodable` |
| 7 | Otherwise | **the trimmed value, byte-for-byte** | *(none)* |

Notes on specific decisions:

- **TAB:** trimmed at the edges (it is legal OWS there and a recipient discards it anyway); **rejected in the interior**. An interior TAB is exactly the folding whitespace an `http.client`-tolerated `CRLF+HTAB` split needs, and it never appears in an honest product token. `test_tab_can_never_introduce_a_second_header_line` proves no TAB combination yields a second header line.
- **Rejection is all-or-nothing.** Bad characters are never stripped with the remainder forwarded (`test_a_rejected_value_is_never_partially_forwarded`); doing so would still forward attacker-chosen content.
- **One deliberate behaviour change vs. the old `str.strip()`:** a CR/LF (or `\x0b`, `\x0c`, `\x1c-\x1f`, `\x85`, NBSP `\xa0`, etc.) at the *edges* of a value was previously silently eaten by `strip()`; it is now a rejection like anywhere else, so nothing control-shaped is ever discarded on the way to the wire. The trade-off (a `.env` reader that leaves a trailing `\n` on the value now gets the default plus a WARNING instead of a silently-cleaned custom value) is documented in the docstring and pinned by `test_surrounding_controls_are_not_silently_trimmed`. No supported Dream launcher produces such a value — the shell, `.bat` files and `os.environ` all deliver it without the line ending.
- **Non-ASCII:** printable ISO-8859-1 (e.g. `é`) is still forwarded, as before, to avoid changing valid custom values. Anything urllib cannot encode is refused up front rather than letting every subsequent request fail with an opaque codec error (that was a latent availability bug at base).
- **200-character limit:** the brief's preferred maximum; the repository had no established limit. Applied to the trimmed value, so padding never counts against it.

## 5. Injection threat model

**Asset:** the outbound request line/headers of every chat-completions call (`OpenAIBackend._attempt_chat`), including the `Authorization: Bearer …` header that travels next to `User-Agent`.

**Attacker-controlled input:** the `DREAM_USER_AGENT` environment variable. Realistic sources: a malicious or mangled `.env`, a compromised launcher script, a supervisor/container environment, or an owner pasting the wrong clipboard content.

| Threat | Mechanism | Mitigation | Test |
|---|---|---|---|
| Header injection | `CR LF Header: value` in the UA adds headers (e.g. overriding `Host`, adding `X-Forwarded-*`, or a second `Authorization`) | Rule 4 refuses CR/LF anywhere | `test_newline_injection_is_rejected`, `test_carriage_return_injection_is_rejected` |
| Request smuggling / splitting | `CR LF CR LF GET /… HTTP/1.1` terminates the header block early | Rule 4 | same, plus `assert_well_formed` on the captured wire bytes |
| Folding bypass | `CR LF SP` / `CR LF HTAB` passes `http.client`'s own check | Rule 4 refuses the CR/LF **and** the TAB | `test_obsolete_line_folding_is_rejected` (proves stdlib acceptance first) |
| NUL truncation | C proxies/loggers stop at `\x00`, hiding trailing content | Rule 4 | `test_null_byte_is_rejected_and_logged_safely` |
| Terminal/log injection | ESC sequences (`\x1b[…`) in provider logs or Dream's own stderr | Rule 4 | `test_every_other_control_character_is_rejected` (all 32 C0 + DEL + 32 C1, three positions each) |
| C1 line breaks | NEL `\x85` is a line terminator to some parsers | Rule 4 (C1 range) | same |
| Resource / 431 abuse | multi-KB header | Rule 5 (200) | `test_values_over_the_limit_are_rejected[201/500/10000]` |
| Availability | non-Latin-1 value → `UnicodeEncodeError` on every request | Rule 6 | `test_values_urllib_cannot_encode_are_rejected_up_front` |
| Duplicate header | two `User-Agent` lines | dict-keyed `Request(headers=…)`, single slot; verified on the wire bytes | `test_default_user_agent_is_sent_as_exactly_one_header`, `..._custom_...`, `..._rejected_...` |
| Log-based exfiltration | logging the rejected value leaks whatever was in the variable | see §6 | `test_newline_injection_is_logged_without_the_value`, `test_oversized_rejection_log_is_bounded`, `test_rejection_logs_never_carry_credentials_or_request_data` |

Invariant pinned by the fuzz-style test `test_resolved_value_is_always_a_single_safe_line` (every byte `0x00–0x9f` in context, plus CR/LF sequences, oversize and NUL-padded values): the resolved value is always non-empty, ≤ 200 characters, contains no `[\x00-\x1f\x7f-\x9f]`, and encodes as ISO-8859-1. `test_resolver_never_raises_on_odd_input` covers `None`, lone surrogates and a 100 000-character value.

The value reaches `urllib.request.Request(headers={...})` through a dict keyed `"User-Agent"`; there is no string concatenation into a raw header block anywhere on the path.

## 6. Logging / redaction policy

- Logger: the module's existing `log = logging.getLogger("dream.agent")`, same convention as the extraction-pass records (message + `extra={...}` structured fields).
- Level: `WARNING` for every rejection; **nothing** is logged for "not configured" (`None`/`""`) or for an accepted override.
- Record content: `"user-agent override rejected: %s (length=%d); using the default"` with `extra={"user_agent_reason": <blank|control_character|too_long|unencodable>, "user_agent_length": <len(raw)>}`.
- **The raw value is never logged — not even a prefix or a hash.** An environment variable can hold anything the owner pasted into it (a `sk-…` key, a URL with `?key=`), so a "bounded safe summary" of the value itself is still a leak; reason + length is the summary.
- The log line is bounded (< 120 characters regardless of input; pinned by `test_oversized_rejection_log_is_bounded` with a 13 KB input).
- No API key, bearer token, prompt, message content, base URL, endpoint path or request body appears in the record (`test_rejection_logs_never_carry_credentials_or_request_data` sets the override, the API key and a keyed URL to sentinel values and asserts none appear).
- The bridge's `install_redaction_filter("dream")` remains a second line of defence for any logger under `dream.*`; SEC-07 does not rely on it.

## 7. Provider compatibility

- **Single header, unchanged plumbing:** `_attempt_chat` still builds `Request(url, data=…, headers={"Content-Type", "Authorization", "User-Agent": self.user_agent}, method="POST")`. The dict is the only path; no concatenation.
- **Wire-level proof without a socket:** the new tests drive `urlopen` through a real `OpenerDirector`/`HTTPHandler` with an `HTTPConnection` whose `connect/send/getresponse` are replaced, so header casing, ordering and encoding are the stdlib's own. Captured request head for the default case:
  `POST /v1/chat/completions HTTP/1.1` · `Accept-Encoding: identity` · `Content-Length: …` · `Host: model.test` · `User-Agent: dream-assistant/0.4.6` · `Content-Type: application/json` · `Authorization: Bearer …` · `Connection: close` — exactly one `User-Agent` line, no folded continuation lines, no `X-Injected`.
- **Custom values stay custom:** `custom-agent/1.0` is sent byte-for-byte and `dream-assistant` does not appear in the head.
- **Retries:** `self.user_agent` is resolved once in `__init__` and reused by every `_attempt_chat`; `test_user_agent_is_stable_across_retries` changes the environment *after* construction, drives three 429 attempts with the sleep patched out, and sees the same value three times. Retry count, backoff formula, 60 s timeout, and response parsing are untouched (diff confirms only the one `__init__` line changed inside the class).
- **Extraction pass:** `Dream._extraction_backend()` uses `copy.copy(backend)`, so the colder extraction client carries the identical `user_agent`; the pre-existing `test_user_agent_is_sent_on_conversation_and_extraction` still passes.
- **`OllamaBackend`** inherits the behaviour unchanged. `bridge/methods.py::build_configured_backend` constructs `OpenAIBackend` the same way and needs no change.
- **Body, auth and temperature are unaffected:** `test_user_agent_does_not_change_the_request_body_or_auth` (new) and `test_user_agent_does_not_change_the_request_body` (pre-existing).
- **Failure path:** the backend's existing `_failure` printing/redaction is unchanged; the new tests only drain it with `capsys`.

## 8. Tests

New file `tests/test_user_agent.py` — 38 test functions, **297 collected cases** (parametrised over every C0/C1/DEL byte in three positions, several injection shapes, lengths and hostile values). Coverage against the brief:

| Brief item | Test(s) |
|---|---|
| None → versioned default | `test_none_uses_the_versioned_default`, `test_unconfigured_values_do_not_log` |
| empty → versioned default | `test_empty_string_uses_the_versioned_default` |
| whitespace-only → default | `test_whitespace_only_uses_the_versioned_default[4]`, `test_whitespace_only_is_logged_as_blank` |
| valid custom preserved | `test_valid_custom_values_are_preserved_exactly[6]`, `test_interior_spaces_are_kept_verbatim`, `test_exactly_the_maximum_length_is_accepted` |
| surrounding whitespace | `test_surrounding_spaces_and_tabs_are_trimmed[5]`, `test_padding_does_not_count_towards_the_length_limit`, `test_surrounding_controls_are_not_silently_trimmed[4]` |
| newline injection rejected + logged safely | `test_newline_injection_is_rejected[5]`, `test_newline_injection_is_logged_without_the_value` |
| carriage-return injection | `test_carriage_return_injection_is_rejected[3]`, `test_obsolete_line_folding_is_rejected[4]` |
| null and other controls | `test_every_other_control_character_is_rejected[61]`, `test_null_byte_is_rejected_and_logged_safely` |
| tab policy / cannot inject | `test_interior_tab_is_rejected`, `test_tab_can_never_introduce_a_second_header_line` |
| > 200 rejected | `test_the_documented_limit_is_200_characters`, `test_values_over_the_limit_are_rejected[3]`, `test_oversized_rejection_log_is_bounded` |
| version from canonical source | `test_default_user_agent_uses_the_package_version`, `test_package_version_matches_pyproject`, `test_default_user_agent_is_not_the_obsolete_pin`, `test_backend_default_follows_the_package_version` |
| rejection logs carry no raw value / secrets | `test_newline_injection_is_logged_without_the_value`, `test_null_byte_is_rejected_and_logged_safely`, `test_rejection_logs_never_carry_credentials_or_request_data` |
| one header in a mocked provider request | `test_default_user_agent_is_sent_as_exactly_one_header`, `test_custom_user_agent_is_sent_as_exactly_one_header`, `test_rejected_user_agent_sends_the_default_and_nothing_injected` |
| retries don't mutate UA | `test_user_agent_is_stable_across_retries` |
| body/auth unchanged | `test_user_agent_does_not_change_the_request_body_or_auth` |
| encoding | `test_values_urllib_cannot_encode_are_rejected_up_front` |
| invariants / no raise | `test_resolved_value_is_always_a_single_safe_line[176]`, `test_resolver_never_raises_on_odd_input`, `test_a_rejected_value_is_never_partially_forwarded`, `test_default_never_contains_line_breaks_or_controls`, `test_default_is_a_product_token_of_the_given_version` |
| existing provider tests unchanged | the 11 User-Agent tests in `tests/test_dream.py` and all other OpenAIBackend suites pass **without modification** |

No test opens a socket; `urlopen` is always replaced, and the wire-capture connection never calls `connect()`.

Mutation check (performed manually, then reverted): reverting the control regex to `[\r\n]` → 134 failures; logging the raw value → 4 failures; restoring the `0.1.0` pin → 5 failures; removing the length check → 4 failures. Each hardening rule is load-bearing in the suite.

## 9. Commands run and results

All commands run from the repository root inside a fresh `python -m venv .venv && pip install -e ".[dev]"` (Python 3.11.2, pytest 9.1.1, ruff 0.16.5).

```text
$ .venv/bin/python -m pytest -q tests/test_user_agent*.py
297 passed in 0.32s

$ .venv/bin/ruff check dream/agent.py tests/
All checks passed!

$ .venv/bin/ruff check .                      # the CI lint step
All checks passed!

$ .venv/bin/python -m pytest -q
3367 passed, 14 skipped in 128.49s (0:02:08)   # base was 3070 passed, 14 skipped: +297, all new

$ .venv/bin/python tools/check_suite_count.py
Suite count check passed: 3370 tests collected (minimum required: 652).

$ .venv/bin/python tools/check_commit.py HEAD  # run before committing, HEAD = base c274772
Commit rule violations for HEAD:
  - Invalid commit author name: 'arena-ai-coding-agent[bot]'. Expected 'Ali Naderi'.
  - Invalid commit author email: '298482267+arena-ai-coding-agent[bot]@users.noreply.github.com'. ...
(pre-existing: the base commit's *local* author metadata. The SEC-07 commit is
authored with the project-required name/email, exactly as SEC-01..06 were, and
re-checked after committing — see the final report.)

$ git diff --check
(clean)

$ .venv/bin/python -m pytest -q tests/test_dream.py -k user_agent   # pre-existing UA tests, unmodified
11 passed, 100 deselected

$ .venv/bin/python -m pytest -q tests/test_dream.py tests/test_provider_failure_replies.py \
    tests/test_reliability_sleep.py tests/test_nonblocking.py tests/test_router.py \
    tests/test_council.py tests/test_model_providers.py tests/test_extraction_observability.py
265 passed in 2.77s
```

Obsolete/unsafe search after the change (`rg -n "0\.1\.0|DEFAULT_USER_AGENT|_resolve_user_agent|User-Agent|user_agent" dream tests`): the only remaining hits in `dream/agent.py` are the new constants/functions; `0.1.0` no longer appears anywhere in `dream/agent.py`. Remaining `0.1.0` hits are all **outside SEC-07 scope** and listed in §10.

Not available in this sandbox: Python 3.10/3.12/3.13 interpreters (an attempt to fetch them was blocked by the sandbox's TLS interception), so the matrix is left to CI. The new test file avoids `tomllib` (3.11+) on purpose and passes `ruff --target-version py310`.

## 10. Coordination Needed and known limitations

**Out of scope, found during the inspection (not changed):**

| Location | Issue | Suggested owner |
|---|---|---|
| `dream/tools.py:759` | `headers={"User-Agent": "dream-assistant/0.1.0"}` — stale hardcoded UA on the fetch tool | tools owner (SEC-05 area) |
| `dream/connectivity/adapters/discord.py:63` | `"User-Agent": "dream-assistant/0.1.0"` — stale | connectivity owner |
| `dream/gws/http.py:44` | `"User-Agent": "dream-assistant/0.4.6"` — correct today but hardcoded; will drift at 0.4.7 | gws owner |
| `dream/remotegw/http.py:41` | `server_version = "DreamRemote/0.4.6"` — hardcoded | remotegw owner |
| `dream/mcp/transport.py:96,245`, `dream/acp/server.py:95` | `clientInfo`/`version: "0.1.0"` — protocol handshake versions, possibly intentional | mcp/acp owners to confirm |
| `dream/connectivity/__init__.py:29`, `dream/bridge/__init__.py:15` | `__version__ = "0.1.0"` — sub-protocol versions, intentionally separate per the release checklist | none (documented) |

Recommendation: the modules above could import `USER_AGENT_PRODUCT`/`DEFAULT_USER_AGENT` from `dream.agent` (or a future tiny `dream/version.py` if the team prefers to avoid importing `agent` from leaf modules) so every outbound identity tracks `dream.__version__`. That is a cross-module change and was deliberately left out of SEC-07.

**Version centralisation:** `pyproject.toml` and `dream/__init__.py` still each carry the literal `0.4.6`. Single-sourcing (e.g. `[tool.setuptools.dynamic] version = {attr = "dream.__version__"}`) touches `pyproject.toml` beyond the "read only" allowance and the release checklist/docs, so it is proposed for the release owner rather than done here. SEC-07 adds a test that fails the moment the two drift.

**Branch name:** this session is pinned to `arena/01a06693-dream`; the PR is opened from it against `main`, exactly as SEC-01…SEC-06 were. If the project wants the work on `fix/p0-security-stability`, a maintainer can retarget or cherry-pick the single commit.

**Known limitations / residual risk:**

- The policy allows printable ISO-8859-1 beyond ASCII (e.g. `é`, and `\xa0`/`\xad` which are not controls) to avoid changing valid custom values that were accepted before. If the team wants a stricter RFC 9110 `token`/`comment` grammar, that is a one-line regex change plus a policy note; it was not done because the brief requires preserving valid custom values.
- Rejection is observable only via the `dream.agent` logger at WARNING; there is no metrics counter for it (the existing `dream.metrics` names are extraction-specific and adding a new stable metric name felt out of scope). Easy follow-up if desired.
- `_resolve_user_agent` runs at backend construction; a value changed in the environment mid-process is (intentionally) not picked up until a new backend is built. This matches the prior behaviour and is what makes retries stable.
