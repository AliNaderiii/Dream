# SEC-04 — Extraction Typing, Status & Observability Audit

- **Date:** 2026-09-02
- **Auditor:** SEC-04 (Extraction Pass Typing & Observability)
- **Repository:** Dream — target release v0.4.7
- **Base commit:** `91b143a9149e462a5c1501ec1fa22eed0e162a54` (main, `fix(security): harden browser approval and blocklist (SEC-03)`)
- **Working branch:** `arena/01a06106-dream` (this session's pinned working branch, branched from the SEC-03 commit above). This session is fixed to `arena/01a06106-dream`; it carries SEC-01, SEC-02, and SEC-03 (already on main) plus the SEC-04 changes.

## 1. Scope and files changed

Strict scope honoured. Files modified / added:

| File | Change |
|------|--------|
| `dream/agent.py` | Extraction-related observability only: metric + structured-log emission around the extraction pass, typed exception narrowing at the extraction and storage boundaries. |
| `dream/metrics.py` | **New** thread-safe, typed, dependency-free counter registry + stable metric-name constants. |
| `tests/test_extraction_observability.py` | **New** focused SEC-04 tests (metrics thread-safety, status→metric mapping, log redaction). |
| `SEC-04-AUDIT.md` | This report. |

No changes were made to `dream/extraction.py`, Rust, frontend, browser security, CLI files, workflows, or any other sub-agent's files. `cli.py`, `desktop.py`, and the Rust/tauri tree are untouched; any future CLI surface for these metrics is recorded under *Coordination items*.

## 2. Extraction call sites audited

Inventory built by reading the implementation (`rg -n "extract_facts|extraction|except Exception|Turn\\(" dream/agent.py dream tests`), not from stale line numbers.

Call sites and their role:

- `Dream._run_extraction(message)` — starts the background worker, waits up to `extraction_timeout_seconds`, and finalizes the turn's `ExtractionResult`. This is the single place where a turn's extraction *status* is recorded (metric + log) exactly once.
- `Dream._extract_in_background(message, outcome)` — worker thread body. Runs `extract_facts(...)` (in `dream/extraction.py`) and persists each returned fact through `MemoryStore.remember(...)`. This is where parser/provider failures and storage failures can surface.
- `Dream._extraction_backend()` — returns the (colder, non-retrying) backend handle used for the extraction model pass.
- `Dream.run()` — the only caller of `_run_extraction`; attaches the result to the returned `Turn.extraction` and passes `extraction_result.status` to `guard_claims(...)`.

Result type: `ExtractionResult(facts, status, raw_text)` from `dream/extraction.py`, plus the thread-safe `_ExtractionOutcome` carrier used between worker and turn.

## 3. Status model (already present, preserved)

`dream/extraction.py` already exposes a typed-enough, constant-based status model on `ExtractionResult.status` (this module was **not** in SEC-04 scope and was not modified):

| Constant | Meaning |
|----------|---------|
| `facts_found` | Pass produced and returned ≥ 1 grounded fact. |
| `no_facts` | Pass ran; the model returned an empty array / nothing durable survived the grounding guard. |
| `too_short` | Message shorter than `MIN_MESSAGE_LENGTH` or slash-command; no model call. |
| `disabled` | Extraction disabled via `DREAM_EXTRACTION`/`DREAM-EXTRACTION`. |
| `unparseable` | Backend output could not be decoded as plausible fact JSON. |
| `error` | Provider/model call failed, or an unexpected extraction error occurred. |
| `abandoned` | The pass was still running when its wall-clock budget expired; the turn proceeds anyway. |

`ok`/`parse_error`/`store_error`/`skipped` (the naming in the SEC-04 brief) map onto this existing model: `ok`→`facts_found`/`no_facts`, `parse_error`→`unparseable`, `skipped`→`disabled`/`too_short`, `abandoned`→`abandoned`. There is **no separate `store_error` status value**: the codebase deliberately keeps `facts_found` when extraction succeeds and only the durable *write* fails, surfacing the loss through `Turn.memory_errors` (and the CLI) so a `«facts found»` report stays truthful about extraction while the storage loss is never silent. That behaviour is pinned by `tests/test_extraction.py::test_store_operational_error_is_visible_not_swallowed` and is preserved. Changing status to `store_error` there would have broken that contract and is outside the current data model, so it is surfaced via a dedicated metric instead (see §6).

Backward compatibility: no serialized field, ordering, or return shape changed; `ExtractionResult` and `Turn` are byte-compatible with callers and existing tests.

## 4. Old broad exception paths and their replacements

Paths scoped to extraction in `dream/agent.py`:

| # | Old path | Replacement |
|---|----------|-------------|
| 1 | `_extract_in_background`: `except Exception as exc` around `extract_facts(...)` flattened anything, including cancellation/system exits. | `except (KeyboardInterrupt, SystemExit): raise` re-raises system/cancellation; only then a documented final `except Exception` builds a typed `STATUS_ERROR` result so the turn still returns instead of crashing. |
| 2 | Store loop: `except ValueError: continue` then `except Exception as exc: errors.append(...)` — storage errors were recorded for the CLI but had no metric or log, and a `KeyboardInterrupt`/`SystemExit` would have been recorded like any other failure. | `except ValueError: continue` (the single expected unusable-fact case, now with a DEBUG log); then `except (KeyboardInterrupt, SystemExit): raise`; then `except sqlite3.Error as exc:` (real storage failures — locked database, disk full, constraints) handled by `_record_store_failure`; then a final documented `except Exception` boundary for non-`sqlite3` store-helper exceptions, treated identically and never silent. |

The two remaining broad `except Exception` are **bounded integration boundaries**, each documented in the code and justified below (§9). Both produce observable output (typed result / `memory_errors` entry + metric + log) and both re-raise `KeyboardInterrupt`/`SystemExit`. Neither is a bare `except:` and neither is `except BaseException`.

Catching `ValueError`, `sqlite3.Error`, `json.JSONDecodeError`-derived parse failures, etc., is done by `extract_facts` inside `dream/extraction.py` (already returns typed statuses; module out of scope and unchanged). The agent's own layer never catches `BaseException`.

## 5. Exception → status / observability mapping

| Failure | Where caught | Extraction status | Metric | Log level |
|---------|--------------|-------------------|--------|-----------|
| Backend/provider call raises | `dream/extraction.py` `extract_facts` | `error` | `dream.extraction.error` | WARNING |
| Model output not parseable as plausible JSON | `extraction.py` | `unparseable` | `dream.extraction.parse_error` | WARNING |
| Unexpected exception escaping `extract_facts` | `_extract_in_background` final boundary | `error` | `dream.extraction.error` | WARNING |
| `ValueError` from `remember` (unusable fact) | store loop | unchanged (`facts_found`/…) | — | DEBUG |
| `sqlite3.Error` from `remember` | store loop | unchanged | `dream.extraction.store_error` | WARNING |
| Other unexpected store error | store loop final boundary | unchanged | `dream.extraction.store_error` | WARNING |
| Pass exceeded wall-clock budget | `_run_extraction` | `abandoned` | `dream.extraction.abandoned` | WARNING |
| Worker returned no result | `_run_extraction` | `error` | `dream.extraction.error` | WARNING |
| Disabled / too short / no model call | `extraction.py` | `disabled` / `too_short` | `dream.extraction.skipped` | DEBUG |
| Pass produced facts | `extraction.py` | `facts_found` | `dream.extraction.success` | DEBUG |
| Pass ran, no durable facts | `extraction.py` | `no_facts` | `dream.extraction.no_facts` | DEBUG |

## 6. Metrics added (`dream/metrics.py`)

Thread-safe `Metrics` registry (one `threading.Lock` guards increments, reads, and snapshots; `snapshot()` returns a `dict` copy, never internal mutable state). Public methods are typed: `incr(name, value)`, `get(name)`, `snapshot()`, `clear()`. No network calls, no unbounded user-content labels, no exceptions expected from `incr` in normal operation. A process-wide `metrics` instance is exported.

Stable names and meanings:

| Metric | Meaning |
|--------|---------|
| `dream.extraction.success` | Extraction passes that returned ≥ 1 grounded fact. |
| `dream.extraction.no_facts` | Passes that ran and returned no durable facts. |
| `dream.extraction.skipped` | Passes skipped: extraction disabled or message too short/slash-command. |
| `dream.extraction.parse_error` | Passes whose model output was unparseable. |
| `dream.extraction.error` | Passes that hit a provider/backend error or unexpected failure. |
| `dream.extraction.abandoned` | Passes abandoned because they exceeded the wall-clock budget. |
| `dream.extraction.store_error` | Fact persistence failures (≥ 1 in a pass); counted per failed write. |

Every turn increments **exactly one** of `success`/`no_facts`/`skipped`/`parse_error`/`error`/`abandoned` from the single finalization site in `_run_extraction`, so a pass is never double-counted across the worker and the turn. `store_error` is counted at the store boundary inside the worker, separately.

## 7. Structured logging & redaction policy

New logger: `log = logging.getLogger("dream.agent")` (no duplicate metrics/log system was already present for the agent).

Policy:
- Only safe metadata is logged: `extraction_status`, `exception_type`, and a whitespace-collapsed, length-capped (`_LOG_MESSAGE_LIMIT = 200`) error message via `_safe_log_message`.
- Benign outcomes (`facts_found`, `no_facts`, `disabled`, `too_short`, unusable-fact skip) log at DEBUG.
- Failures (`unparseable`, `error`, `abandoned`, `store_error`) log at WARNING.
- **Never** logged: the extraction prompt, raw model output (`ExtractionResult.raw_text` is deliberately not written to the log), full user content, fact content, API keys/credentials, or filesystem/database paths.
- A `turn_id` is not logged because the current `Turn`/`Dream` model has no turn identifier to reference; status + exception class are the stable correlation keys. (Noted under coordination items only if a caller later wants a turn id.)

## 8. Tests

New file `tests/test_extraction_observability.py` (11 tests). It isolates the process-wide registry with an autouse fixture (`metrics.clear()` before/after) so test order never leaks counts, and uses no `sleep` for synchronization (the abandonment case is driven by a `threading.Event` + a 0.1 s configured timeout).

Coverage:
- `Metrics` increments/`get` semantics; `get` of unknown returns 0.
- `snapshot()` is a defensive copy — mutating the returned dict does not affect the registry.
- Thread safety: 8 threads × 2000 concurrent increments land exactly.
- Successful extraction → status `facts_found` and `success` metric incremented.
- Parse failure → status `unparseable` and `parse_error` metric incremented.
- Backend exception → status `error` and `error` metric.
- Disabled extraction → status `disabled` and `skipped` metric.
- SQLite/`sqlite3.OperationalError` storage failure → status stays `facts_found`, `memory_errors` set, `store_error` metric incremented, not silent.
- Abandonment (blocked worker past the budget) → status `abandoned` and `abandoned` metric.
- Log records for store failures carry safe metadata (`store_error`, exception class) and contain no user content, secret tokens, or `.db` paths.
- Failure logs never contain user content or secret tokens embedded in messages/fact content.

Existing extraction tests and behaviour are preserved and unmodified; coverage did not decrease.

## 9. Remaining broad catches and justification

Non-extraction (pre-existing, outside this pass): `except Exception` in `__init__` (ledger wiring) and the slash-invocation ledger log (`except Exception: pass`). These are unrelated to the extraction flow and were left untouched.

Extraction-scoped (in `_extract_in_background`) — the two remaining `except Exception` are retained as documented, non-swallowing final boundaries and both **re-raise `KeyboardInterrupt`/`SystemExit` first**:

1. Around `extract_facts(...)`: a narrow defensive boundary required because the agent must always hand its caller a typed `Turn` rather than crash the whole session on an unexpected extraction error. `extract_facts` itself already returns typed results for the failure classes it knows (provider error, parse error); this guard only handles the truly unexpected.
2. In the persistence loop: an integration boundary over third-party/`sqlite3`-adjacent store helpers (`sqlite3.Error` is caught specifically above it); non-`sqlite3` store-helper exceptions are still recorded, counted (`store_error`), and logged — never swallowed silently.

Neither boundary is `except BaseException`, neither is a bare `except:`, and neither swallows cancellation or system exceptions.

## 10. Verification — exact commands and results

All run from the repository root in the session's venv (`.venv`):

```
$ ruff check dream/agent.py dream/metrics.py
All checks passed!

$ ruff check dream/agent.py dream/metrics.py tests/
All checks passed!

$ python -m pytest tests/test_extraction.py tests/test_extraction_prompt.py tests/test_extraction_observability.py tests/test_agent_reminders.py -q
66 passed

$ python -m pytest tests/test_extraction_observability.py -q
11 passed

$ python -m pytest -q
3041 passed, 14 skipped in 115.42s

$ git diff --check          # clean
$ rg -n "extract_facts|except Exception|except:" dream/agent.py   # reviewed, see §9
```

Coverage/behaviour of existing extraction tests: `tests/test_extraction.py` + `tests/test_extraction_prompt.py` remain green (44 passed) with the production changes in place.

## 11. Coordination items

- **CLI / UI exposure of extraction metrics**: `cli.py` and `desktop.py` were outside SEC-04 scope and are unchanged. Exposing `dream.extraction.*` counts on the CLI or desktop activity view, if desired, is for another sub-agent / follow-up. The registry API (`metrics.snapshot()`) is ready for that consumer.
- **Turn identifier**: the `Turn`/`Dream` model currently has no turn id; extraction logs correlate by status/exception class. If a durable turn id is introduced later, the log extras can be extended to include it without other changes.
- **`store_error` semantics**: no `store_error` status value exists by design (see §3); storage losses are exposed via `Turn.memory_errors` + the `dream.extraction.store_error` metric. Confirm with the product owner if a distinct status value is wanted instead; that would require a change to the `extraction.py` status model (currently owned by a prior pass) and its pinned tests.
