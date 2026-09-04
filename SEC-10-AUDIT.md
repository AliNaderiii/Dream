# SEC-10 — IPC Bridge Hardening Audit (Python ↔ Rust/Tauri ↔ TypeScript)

- **Repository:** Dream v0.4.6 (no version change in this work; v0.4.7 is **not** created)
- **Base commit:** `ef75cdab5769cbb6711fc215231823e3d3377171` — tip of `main` after the SEC-09 merge (PR #123)
- **Working branch:** `arena/01a06b22-dream` (fixed by the Arena session)
- **Code commits (in order):**
  1. `6b7ce1d6ae7edd2c60062c92c7a70826bbb8c5f5` — Python sidecar transport + handler offload
  2. `7c25fa4dc5ec8c20f429a3f0219d745072a13c1e` — Rust supervisor / reader / dispatcher / errors
  3. `b2f5071e2d40a481125e5412892b9cca40024874` — TypeScript error typing
  4. docs commit (this file + `docs/bridge/protocol.md`) — see §10 for the final SHA
- **Status:** PR open, **not merged**. See §10 for PR number, final head SHA and CI links.

---

## 1. Scope

### 1.1 Files changed (complete list; nothing else)

| Layer | File | Change |
|---|---|---|
| Python | `dream/bridge/server.py` | rewritten transport core (bounded reader, strict JSON out, dedicated writer, bounded drain, id validation) |
| Python | `dream/bridge/methods.py` | **only** `tool_execute`, `approval_resolve`, `sandbox_status` (made `async`, blocking work offloaded) |
| Python | `dream/bridge/errors.py` | 1 line: `BridgeError` messages pass through `_redact` (see §5 P8 — a finding surfaced by the new tests) |
| Python tests | `tests/test_bridge_transport_hardening.py` (new, 42 tests) | transport, lifecycle, secret-safety, offline provider paths |
| Python tests | `tests/test_bridge_methods.py`, `tests/security/test_sec_integration.py`, `tests/test_gateway_server.py` | call-site updates only (`run(...)` / `asyncio.run(...)` around the now-async handlers); `test_sandbox_status_returns_unavailable_without_docker` now injects a probe that raises `DockerUnavailableError` — the previous version depended on the host having no Docker daemon (the old sync handler could never reach Docker, which hid this; GitHub runners have Docker, so the first CI run of the async handler returned `available: True`) |
| Rust | `apps/desktop/src-tauri/src/bridge/reader.rs` (new) | bounded frame reader (cancellation-safe discard) + 11 tests |
| Rust | `apps/desktop/src-tauri/src/bridge/process.rs` | supervisor loop, heartbeat, reader loop, writer signal, `SupervisorTiming` (heartbeat interval/timeout, backoff list — production defaults unchanged), `SupervisorControl`; 9 new tests (+2 `const _: () = assert!(..)` compile-time checks on `HEARTBEAT_ID_BASE`) |
| Rust | `apps/desktop/src-tauri/src/bridge/mod.rs` | `send_request` cleanup on write failure, reserved-id guard, `restart` wakes supervisor, `kill` never skips the writer |
| Rust | `apps/desktop/src-tauri/src/bridge/framing.rs` | header parsing/validation, `RESERVED_ID_FLOOR`, `i32` code range; 4 new tests |
| Rust | `apps/desktop/src-tauri/src/bridge/dispatcher.rs` | `cancel()`, `fail_all` returns count + transport tag; 4 new tests |
| Rust | `apps/desktop/src-tauri/src/error.rs` | **additive**: `transport()`, `protocol_version()`, `is_transport()`, `data.kind` tags; 2 new tests, 1 updated assertion |
| TS | `apps/desktop/src/lib/bridge/errors.ts` | `BridgeErrorKind`, `kind`, `isTimeout/isCancelled/isTransport`, typed factories |
| TS | `apps/desktop/src/lib/bridge/client.ts` | typed deadline/abort rejections; id counter note + wrap |
| TS tests | `apps/desktop/src/lib/bridge/bridge.test.ts` | 6 new/extended tests |
| Docs | `docs/bridge/protocol.md`, `SEC-10-AUDIT.md` | behaviour changes documented; this audit |

### 1.2 Explicitly untouched

- SEC-09 containment code in `process.rs` (`SidecarContainment`, `terminate_sidecar`, `reap_instance`, Windows Job Object / Unix process-group code, `discard_uncontained_child`, all `unix_*`/`windows_*` containment tests). Verified with `git diff ef75cdab HEAD -- process.rs | grep -i 'SidecarContainment|terminate_sidecar|JobHandle|killpg|contain_pid|process_group'` → **no hits**.
- `.github/workflows/*`, `Cargo.toml`, `Cargo.lock`, `package.json`, UI components, `SEC-09-AUDIT.md`, release/version files, interpreter discovery (`SidecarConfig::from_env`, `prepend_bundled`, `sidecar_command`, env/cwd handling).
- Method names, JSON-RPC shapes, error codes, Persian/English message pairs, stdio transport, restart/backoff constants (2/5/10 s), heartbeat constants (5 s / 15 s), Python caps (10 MiB / 16 / 128), TS defaults (30 s / 300 s), offline/BYOK/Ollama behaviour.

---

## 2. Architecture (as audited at the base SHA)

```
React/TS (renderer)                 Rust/Tauri shell                        Python sidecar
BridgeClient.call/stream  ─invoke─▶ bridge_request cmd ─▶ Bridge::send_request
  id = counter, timeoutMs,            ├ Dispatcher.register(id) → oneshot + mpsc
  AbortSignal                          ├ writer_tx (mpsc 64) → write_stdin_loop ──stdin──▶ server.py reader thread
                                       │                                                     ├ dispatch → methods.handlers
bridge://chunk  ◀─emit─ stream drain ◀─┤                                                     ├ streams.py (chunks)
bridge://state  ◀─emit─ set_state      │ supervise_reader ◀──stdout── stdout writer ◀────────┘
                                       ├ heartbeat_watchdog (health.check)
                                       └ run_supervisor: spawn → Ready → end → reject_pending → backoff/restart
```

Locks (Rust): `dispatcher: Arc<tokio::Mutex<Dispatcher>>` (held only for a map op, never across an await/IO), `writer_tx: Arc<tokio::Mutex<Option<Sender>>>` (sender cloned out before `.send().await`), `last_activity` (now a `std::sync::Mutex<Instant>` held for a copy). `SharedState` is a lock-free `AtomicU8`.

---

## 3. Threat model

| Actor / condition | Capability | Concern |
|---|---|---|
| Misbehaving or compromised sidecar (or any process that can write to its stdout pipe) | arbitrary bytes on stdout, any JSON, unbounded line length, forged `id`s, wrong protocol header, silence | shell memory exhaustion; hijacking another request's response; permanent hang; false `Ready` |
| Misbehaving shell / test harness on stdin | arbitrary bytes on stdin, unbounded lines, invalid UTF-8, odd `id` types, NaN-producing handlers | sidecar memory exhaustion; reader thread death; unparseable output line; loop starvation |
| Slow or blocking handler (tool execution, Docker probe) | blocks the event loop | heartbeat stalls → false hang → kill of a healthy sidecar; deadlock (`sandbox.status`) |
| Crash loop / transient failures | sidecar exits repeatedly | retries spent → user stuck with no reconnect |
| Renderer | many concurrent requests, cancellation, timeouts | id collision with shell traffic; leaked dispatcher entries; indistinguishable local vs remote failures |
| Secrets in error paths | exception text includes API keys | credential leakage over the wire / into logs |

Out of scope (unchanged posture): OS-level isolation of the sidecar, TLS/auth (local pipe only), provider routing/billing/quota.

---

## 4. Findings and fixes

Severity: **H**igh (hang/DoS/incorrect routing), **M**edium (resource/robustness), **L**ow (defence-in-depth).

### 4.1 Rust shell

| # | Sev | Finding (base SHA) | Fix | Test |
|---|---|---|---|---|
| R1 | H | `heartbeat_watchdog` only set an `AtomicBool`; `supervise_reader` blocked in `next_line()` until stdout closed. A wedged sidecar (stdout open, no output) was **never killed**; every request timed out forever. | Reader `select!`s on next frame / `hung.notified()` / `writer_gone.notified()`. A hang breaks the loop → `reap_instance` (SEC-09 teardown) → restart. Bounded by `heartbeat_timeout + interval`. | `unix_heartbeat_kills_hung_sidecar_…` (pid asserted dead), `heartbeat_watchdog_fires_after_silence` |
| R2 | H | `run_supervisor` **returned** after 3 failures; `Bridge::restart` only dropped the writer. With no supervisor task alive, "Reconnect" did nothing forever. | Supervisor never returns: parks in `Disconnected` on `SupervisorControl::wait_for_restart()`. `Bridge::restart` calls `request_restart()` (level flag + `Notify`, so a request during teardown/backoff is not lost). Manual restart ⇒ fresh budget, no backoff. The automatic budget/backoff (3 × 2/5/10 s) is unchanged and resets only on a manual restart — a proposed 30 s "stable uptime" reset was **rejected in scope review and removed**. | `unix_heartbeat_kills_hung_…` (Disconnected → manual restart → Ready → round-trip), `restart_request_is_remembered_until_consumed`, `wait_for_restart_returns_immediately_for_an_earlier_request` |
| R3 | M | `send_request` registered the id, then returned `not_ready` if the writer send failed — the dispatcher entry leaked; a later request reusing the id was refused as a duplicate. | `Dispatcher::cancel(id)` on write failure. | `cancel_forgets_the_request_and_closes_channels` |
| R4 | M | `BufReader::lines()` buffered the whole line before `framing::parse` checked `MAX_FRAME_BYTES` — unbounded allocation from a hostile stdout. | New `bridge/reader.rs::FrameReader`: cap enforced per chunk while reading; excess consumed and dropped; one typed `frame_too_large` per line; invalid UTF-8 rejects only that frame; stream resyncs at the next `\n`. | 10 reader tests over `tokio::io::duplex` with a 4-byte `BufReader` (forces partial reads) |
| R5 | L | Heartbeat ids started at `1_000_000`; the frontend counter is a plain increasing integer, so a long session **could** collide and a heartbeat reply could resolve a frontend request. | `RESERVED_ID_FLOOR = 2^62`; heartbeat ids start there; responses/chunks in the band bypass the dispatcher; `send_request` refuses frontend ids in the band. | `heartbeat_watchdog_sends_reserved_ids_…`, compile-time `const _: () = assert!(HEARTBEAT_ID_BASE >= RESERVED_ID_FLOOR)` in process.rs (clippy `assertions_on_constants` rejects the runtime form), `reserved_id_floor_is_far_above_frontend_counters`, TS `issues distinct increasing numeric ids below the shell reserved band` |
| R6 | L | `DREAM-PROTOCOL:` prefix set `Ready` without reading the version. | `framing::parse_header` validates `MAJOR.MINOR`; major ≠ 1 ⇒ typed `protocol_version` error, instance never `Ready`, logged EN/FA. | `parse_header_*` (2), `unix_unsupported_protocol_major_never_becomes_ready` |
| R7 | L | `error.code as i32` truncated out-of-range codes into arbitrary taxonomy entries; `Bridge::kill` silently skipped closing the writer when `try_lock` failed. | `i32::try_from(...).unwrap_or(INTERNAL_ERROR)`; `kill` falls back to a detached task that takes the lock. | `out_of_range_error_code_maps_to_internal_error` |
| R8 | L | Shell-originated failures (`not_ready`, `sidecar closed`, `sidecar restarted`) used `-32603` with no way to distinguish them from a Python `INTERNAL_ERROR`. | Additive `data.kind = "transport"` (and `"timeout"` for `BridgeError::timeout`). Codes unchanged. `fail_all` now returns the count and tags each rejection; rejection is exactly once (entry removed as it is failed; second sweep is a no-op). | `fail_all_rejects_every_pending_request_exactly_once`, `late_response_after_fail_all_is_dropped`, `duplicate_response_resolves_only_once`, error.rs tests |
| R9 | L | Heartbeat used `tx.send(...).await` on the 64-slot writer channel; a saturated channel could stall the watchdog itself. | `try_send`; liveness is measured on stdout traffic, so a dropped ping is harmless. | `heartbeat_watchdog_sends_reserved_ids_and_tolerates_a_full_channel` |
| R10 | L | `last_activity` was a `tokio::Mutex<Instant>` locked from both the reader and the watchdog around awaits. | `std::sync::Mutex<Instant>` held for a single copy; poisoned lock treated as "just now" (cannot fake a hang). | covered by R1 tests |

### 4.2 Python sidecar

| # | Sev | Finding (base SHA) | Fix | Test |
|---|---|---|---|---|
| P1 | H | `tool_execute` / `approval_resolve` ran `dream.tools.execute` **synchronously on the event loop**; `sandbox_status` called `run_coroutine_threadsafe(check_docker(), loop).result(10)` **from the loop it was scheduled on** — a guaranteed 10 s deadlock. During any of these, `health.check` could not be answered ⇒ the shell's heartbeat would declare a false hang. | All three are `async def`; tool bodies run via `asyncio.to_thread`; the Docker probe is `await asyncio.wait_for(check_docker(), 10)`. Validation, the L3 floor and the approval gate are unchanged and still fail closed. | `test_blocking_tool_does_not_block_the_loop` (a `health.check` completes while a tool blocks), `test_bridge_methods.py` (unchanged assertions, call sites wrapped) |
| P2 | M | `sys.stdin.readline()` on the text stream: unbounded allocation before the size check; a UTF-8 decode error killed the reader thread (silent wedge). | `read_bounded_lines` on the binary buffer: bounded `readline(max+1)`, over-long remainder discarded chunk by chunk, single `OversizedLine` marker; `errors="replace"` decode. | 12 reader/size tests incl. a real 12 MiB pipe write to a subprocess |
| P3 | M | `json.dumps` default allows NaN/Infinity ⇒ unparseable line; the fallback used error code `0`. | `allow_nan=False`; encode failure ⇒ `INTERNAL_ERROR` for the same id. | `test_nan_result_becomes_a_typed_error_instead_of_invalid_json` |
| P4 | M | stdout writes went through the default executor shared with tool work; `BrokenPipeError` propagated into handlers. | Dedicated 1-thread writer executor; `OSError` on write ⇒ orderly shutdown. | `test_writer_failure_shuts_the_server_down_without_raising`, `test_stdout_writer_serialises_and_flushes_lines` |
| P5 | L | EOF drain awaited in-flight tasks unbounded (doc said 5 s). | `_drain` bounded to `DEFAULT_DRAIN_SECONDS = 5.0`; stragglers cancelled. | `test_drain_is_bounded_and_cancels_stragglers` |
| P6 | L | `id` accepted any JSON type (floats/bools/objects echoed back); `METHOD_NOT_FOUND` echoed a method name of any length; `CancelledError` was swallowed by the stream driver. | `_is_valid_id` (str / int / None; bool excluded); echo truncated to 128 chars; `CancelledError` re-raised. | `test_invalid_id_shapes_are_rejected_deterministically`, `test_unknown_method_name_is_truncated_in_the_error`, `test_repeated_cancellation_is_idempotent` |
| P7 | L | Doc said protocol `1.1`, header says `1.0`. | Documented: the header is the framing major/minor; §3.x additions bump the documented minor. Header **not** changed (a change would trip the new major check on older shells for no benefit). | — (doc) |
| P8 | M | *(found by the new secret-safety test)* `serialise_error` returned `BridgeError` messages **without** `_redact`; handlers routinely interpolate wrapped exception text (`f"Failed to start gateway: {exc}"`), which is not under their control. | `_redact(str(exc))` for `BridgeError` too. One line in `errors.py`; outside the pre-approved file list, reported here explicitly. | `test_serialised_errors_never_carry_credentials`, `test_subprocess_error_payloads_do_not_leak_secrets` |

### 4.3 TypeScript client

| # | Sev | Finding (base SHA) | Fix | Test |
|---|---|---|---|---|
| T1 | M | Deadline and abort rejected with plain `Error`; callers could not tell a local timeout from a sidecar `INTERNAL_ERROR`, and `toBridgeError` turned both into `INTERNAL_ERROR` anyway. | `BridgeRpcError.kind: 'rpc' \| 'transport' \| 'timeout' \| 'cancelled'` + `isTimeout/isCancelled/isTransport`; `BridgeRpcError.timeout()/cancelled()` factories; shell tag `data.kind` classified. Messages unchanged. No production code relied on `instanceof Error`-only checks (grep verified). | 6 tests |
| T2 | L | `RpcId = number \| string` is wider than the shell's `u64`. | Documented (§2.1); client only ever issues safe integers, counter wraps before `MAX_SAFE_INTEGER`. | `issues distinct increasing numeric ids …` |
| T3 | L | Client cancel does not notify the sidecar. | Documented (§6.2): local only; use `conversation.stop` / `subagent.cancel`. Not changed — a new cancel notification would be a protocol addition beyond this scope. | — |

### 4.4 Verified as already correct (no change)

No locks held across awaits/IO in the Rust bridge; tasks aborted and the instance reaped **before** the next spawn (SEC-09 ordering preserved — the new `writer_gone` path still goes through `reap_instance`); no `unwrap`/`expect` in production bridge code (only in `#[cfg(test)]`); Python `redact_text` patterns cover OpenAI/Anthropic/GitHub/AWS/Slack/Google/Telegram/JWT/gateway shapes; echo provider and Ollama configuration work fully offline with no probe (`test_local_ollama_configuration_does_not_probe_the_network`, `test_echo_provider_round_trip_offline`).

---

## 5. Compatibility, lifecycle and lock analysis

**Wire compatibility.** No breaking change. Additive: `error.data.kind`; reserved id band (`≥ 2^62`, never used by any client); header major enforcement (sidecar has always sent `1.0`). An old shell + new sidecar, or new shell + old sidecar, interoperate: the tag is ignored by old TS code, absent from old shells (classifies as `rpc`).

**Lifecycle invariants (after change).**
1. At most one sidecar instance, one reader, one writer task and one heartbeat task exist at any time: `start_instance` aborts the writer and awaits `reap_instance` before returning; the supervisor spawns the next instance only after that.
2. Every reader exit path is bounded: EOF / IO error (peer death), `hung` (≤ timeout + interval), `writer_gone` (immediate on `restart`/`kill`/stdin failure — `NotifyOnDrop` fires even if the writer task is aborted).
3. Every in-flight request is rejected **exactly once** on instance end (`fail_all` removes as it fails; a second sweep returns 0); late responses for those ids are dropped (`resolve` returns `false`).
4. Manual restart requests are level-triggered and consumed once; a request that arrives before the supervisor waits is not lost; a stale wake-up cannot fake a request (flag checked in the loop). `attempt` is reset **only** by a manual restart; instance uptime does not affect it.
5. `killed` still wins over everything: after `kill`, the supervisor parks in `Disconnected` until an explicit `restart` clears the flag.

**Locks.** `dispatcher` mutex: held for one `HashMap` op per call, never across `.await` on IO (`fail_all` iterates ids collected first). `writer_tx` mutex: sender cloned out, then awaited outside the guard (unchanged pattern); `kill` never blocks — `try_lock` or detached task. `last_activity`: `std::sync::Mutex` for a `Copy` read/write, no await inside. No new `Arc<Mutex>` is shared between the supervisor and command handlers beyond those already present at the base.

**Timings** (production defaults unchanged, now in `SupervisorTiming::default()`, asserted by `default_timing_matches_documented_constants`): heartbeat 5 s / 15 s, backoff 2/5/10 s. No new timing policy. Tests inject millisecond timings through `SidecarConfig.timing`.

---

## 6. Test matrix

Legend: **E** executed locally in the authoring sandbox; **CI** executed only in GitHub Actions (see §10); **C** compile-only (built/linted, not run); **S** skipped with reason.

| Suite | Linux (sandbox / CI ubuntu-22.04) | Windows (CI) | macOS (CI) |
|---|---|---|---|
| `python -m pytest -q` (3422 passed, 14 skipped; includes 42 new) | **E** + CI (py3.10–3.13) | CI matrix per `ci.yml` | CI matrix per `ci.yml` |
| `tests/test_bridge_transport_hardening.py` × 3 repeated runs | **E** (47→42 after de-dup; 3/3 green, 1.8–1.9 s each) | as above | as above |
| `python -m ruff check .` | **E** pass + CI | CI | CI |
| `python -m mypy dream/bridge/server.py errors.py streams.py` (`--follow-imports=silent`) | **E** pass | — | — |
| `python -m mypy .` | **E** fails with 96 pre-existing errors in 26 other files (identical count at base SHA; 0 in bridge files) | — | — |
| `tools/check_suite_count.py` (min 652) | **E** 3425 collected | CI | CI |
| `tools/check_commit.py` on each SHA | **E** pass ×3 | CI | CI |
| `cargo fmt --all -- --check` | **E** pass (rustfmt 1.8.0 / Rust 1.88.0, obtained from the npm registry as `@rustbin/*`) + CI | CI | CI |
| `cargo check --all-targets` | **S locally** — crates.io/static.crates.io unreachable from the sandbox (TLS reset; `cargo fetch` fails) → **CI** | CI | CI |
| `cargo clippy --all-targets -- -D warnings` | **S locally** (same reason) → **CI** | CI | CI |
| `cargo test --lib` (reader 11, dispatcher 10, framing 15, error 8, process 6 cross-platform + 3 `#[cfg(unix)]` supervisor E2E) | **S locally** → **CI** | **C** — Desktop CI runs clippy + build but skips `cargo test` on Windows (pre-existing workflow decision, tauri-winres); the 3 `unix_*` SEC-10 tests are `#[cfg(unix)]` because the fake sidecar is a `/bin/sh` script | CI |
| `npm run typecheck` (`tsc --noEmit`) | **E** pass + CI | — | — |
| `eslint src/lib/bridge` / `npm run lint` | **E** pass (bridge dir) + CI (full) | — | — |
| `prettier --check` | **E** pass (bridge dir) + CI (full) | — | — |
| `vitest run` (725 tests, 108 files; bridge dir 164) | **E** pass + CI | — | — |

**Why the Rust E2E tests are deterministic.** They use a temp-dir `/bin/sh` fake sidecar (never the installed interpreter, never matched by name); every wait is a bounded poll on state or on an explicit pid from a pid file (`wait_for_state`, `wait_unix_pid_dead`), no bare sleeps for coordination; timings are ms-scale via `SupervisorTiming`; each test owns its runtime and ends with `kill()` + a dead-pid assertion so nothing survives the test. Heartbeat timeout in tests is 1.5 s to leave headroom for a loaded runner while still catching a real hang in seconds.

**Flake check.** One unrelated test (`tests/test_connectivity_adapters.py::test_telegram_adapter_polls_and_delivers_normalised_messages`) failed once while the full pytest run overlapped a full vitest run on the same machine; it passed 3/3 in isolation, at the base SHA, and in the subsequent full run (3422 passed). It polls with a 1 s deadline and is outside this scope; not modified.

---

## 7. Command results (local, final tree)

```
$ python -m pytest -q                       → 3422 passed, 14 skipped in 186.78s
$ python -m ruff check .                    → All checks passed!
$ python -m mypy dream/bridge/server.py --follow-imports=silent
                                            → Success: no issues found in 1 source file
$ python -m mypy dream/bridge/errors.py dream/bridge/streams.py --follow-imports=silent
                                            → Success: no issues found in 2 source files
$ python -m mypy .                          → 96 errors in 26 files (pre-existing, unchanged from base; none in dream/bridge)
$ python tools/check_suite_count.py         → 3425 tests collected (minimum required: 652)
$ python tools/check_commit.py HEAD         → Commit author and trailer rules passed (each of the 3 code commits)
$ cargo fmt --all -- --check                → exit 0
$ cargo check / clippy / test               → NOT RUN locally: crates.io unreachable (see §6); executed in Desktop CI
$ npm run typecheck                         → exit 0
$ npx eslint src/lib/bridge                 → exit 0
$ npx prettier --check "src/lib/bridge/*.ts"→ All matched files use Prettier code style!
$ npx vitest run                            → Test Files 108 passed, Tests 725 passed
```

---

## 8. Limitations and remaining risks

1. **Rust compile/clippy/test evidence is CI-only.** The sandbox could obtain a toolchain (rustfmt ran) but not the crate graph. Any compile or clippy failure surfaces in Desktop CI on the PR head and is addressed there before review; §10 records the final state.
2. **Windows does not execute `cargo test`** in Desktop CI (pre-existing). The cross-platform SEC-10 unit tests (reader, dispatcher, framing, error, watchdog, control) are compiled and linted on Windows but only executed on Linux/macOS. The supervisor E2E tests are Unix-only by construction (shell-script sidecar); a PowerShell equivalent was out of scope.
3. **Client cancel is local (T3).** A cancelled `call()` leaves the sidecar handler running to completion; its response is dropped. Adding a cancel notification is a protocol addition for a future prompt.
4. **Heartbeat liveness counts any stdout traffic**, including rejected frames. A sidecar emitting garbage continuously is "alive" by design; it cannot exhaust memory (bounded reader) and every request still fails by its own deadline.
5. **Automatic restart budget is still "3 attempts, ever, until a manual restart".** A sidecar that crashes three times over the life of the app session ends in `Disconnected`; the difference from the base is that the user's "Reconnect" now works. A time-based budget reset was proposed and rejected in scope review (it could turn a periodically crashing sidecar into an unlimited restart loop); it is not implemented.
6. `docs/bridge/protocol.md` still declares `1.1` while the header says `1.0`; this is now explained in the doc rather than changed on the wire (P7).

---

## 9. Rollback

Each layer is an independent commit and can be reverted alone:

- Revert `b2f5071` — TS typing only; nothing else depends on `BridgeRpcError.kind`.
- Revert `7c25fa4` — restores the previous supervisor; the Python and TS layers remain valid (the `data.kind` tag simply stops appearing; TS classifies everything as `rpc`).
- Revert `6b7ce1d` — restores the previous sidecar; note that `test_bridge_transport_hardening.py` is removed with it and the three handlers become sync again (their test call sites are in the same commit).

No data migrations, no schema, no config format changes; `Cargo.lock`/`package-lock.json` untouched, so reverting requires no dependency work.

---

## 10. Remote verification (PR, head SHA, CI)

Every claim below is tied to a recorded head SHA. The final head SHA cannot be written into a file that is part of that same commit, so the **final** SHA and its CI run URLs are recorded in the PR description and in the final report; this section records the PR and the CI history that led to it.

- **PR:** [#124](https://github.com/AliNaderiii/Dream/pull/124) — `arena/01a06b22-dream` → `main`, base `ef75cdab5769cbb6711fc215231823e3d3377171`. **Merged:** no. **v0.4.7 created:** no.
- **First head `7432eda`** (commits `6b7ce1d`, `7c25fa4`, `b2f5071`, `37c8950`, `7432eda`):
  - CI [`33879681345`](https://github.com/AliNaderiii/Dream/actions/runs/33879681345) — **failed**, all four Python jobs (3.10–3.13), step `Test`: `1 failed, 3421 passed, 14 skipped`. The single failure was `tests/test_gateway_server.py::TestSandboxBridgeIntegration::test_sandbox_status_returns_unavailable_without_docker` (`assert True is False`). Root cause: the test assumed no Docker daemon on the host. With the old **synchronous** `sandbox_status` (P1) the probe could never actually run (it blocked its own loop and fell through to `available: False`), which masked the assumption; the fixed async handler really probes Docker, and GitHub-hosted runners have a Docker daemon. Fix: the test injects a sandbox whose `check_docker` raises `DockerUnavailableError`, so it verifies the handler's failure mapping deterministically on any host. Every other test passed on all four interpreters.
  - Desktop CI [`33879681428`](https://github.com/AliNaderiii/Dream/actions/runs/33879681428) — `Frontend checks` **passed**; `Rust (ubuntu-22.04 / windows-latest / macos-latest)` **failed** at `cargo clippy --all-targets -- -D warnings` (stable clippy 1.98): `clippy::assertions_on_constants` on the two `assert!` lines of the test `heartbeat_ids_live_in_the_reserved_band` (all three OSes) and `unused_imports` for `use tauri::Manager as _;` inside the `#[cfg(unix)]` `mock_app()` test helper (Linux/macOS only). Neither is a runtime defect; both are in `#[cfg(test)]` code. Fix: the two constant assertions became `const _: () = assert!(..)` items next to `HEARTBEAT_ID_BASE` (checked at compile time on every target, test or not) and the unused import was removed. `cargo fmt --check` passed on all three OSes; the production code compiled — clippy only failed the `lib test` target.
  - (A duplicate push-triggered Desktop CI run [`33879650779`](https://github.com/AliNaderiii/Dream/actions/runs/33879650779) failed for the same reasons.)
- **Second head `9332f61`** (`fix(bridge): make the SEC-10 suite host-independent and clippy-clean` — `tests/test_gateway_server.py`, `process.rs` test code, this file):
  - CI [`33882916049`](https://github.com/AliNaderiii/Dream/actions/runs/33882916049) — **success**: all four Python jobs (3.10–3.13) green (`3422 passed, 14 skipped`), lint, commit rules and suite count passed.
  - Desktop CI [`33882916188`](https://github.com/AliNaderiii/Dream/actions/runs/33882916188) — `Frontend checks` **passed**; `Rust (windows-latest)` **passed** (fmt + clippy `-D warnings` + build; Windows does not run `cargo test`, pre-existing); `Rust (ubuntu-22.04)` and `Rust (macos-latest)` passed fmt/clippy/build and **failed only at `Cargo test`**: `91 passed; 1 failed` on both. The failing test was `bridge::process::tests::writer_end_is_signalled_even_when_the_task_is_aborted` (timeout waiting for the notify). Root cause: `#[tokio::test]` runs on a current-thread runtime, so the spawned task was aborted **before it was ever polled**; an unpolled async block never constructed its `NotifyOnDrop` guard, so there was nothing to drop. That is a defect in the test's ordering, not in `NotifyOnDrop` or the writer: the production writer task is always polled (it is `await`ed on `rx.recv()`) long before `restart`/`kill` can end it, and the three `unix_*` supervisor E2E tests — which rely on the same signal for `ReaderEnd::WriterClosed` — all passed on Linux and macOS. Fix: the test waits on a `oneshot` for the task to reach its first `await` (deterministic, no sleep) before aborting, and additionally asserts the `JoinError` is a cancellation. Every other SEC-10 Rust test (reader 11, dispatcher 10, framing 15, error 8, process cross-platform + 3 unix E2E) **executed and passed** on Linux and macOS in this run — the first time the Rust suite ran anywhere for this PR.
- **Third head (this commit):** `fix(desktop): poll the writer-guard task before aborting it in the SEC-10 test` — `process.rs` test code + this file only. Its SHA and CI / Desktop CI run URLs are recorded in the PR body and in the final report.
