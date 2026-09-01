# SEC-01 Rust / Tauri Bridge Panic Audit

- **Date:** 2026-09-01
- **Auditor:** SEC-01 (Rust Security Auditor)
- **Repository:** Dream v0.4.6 (target release v0.4.7)
- **Working branch:** `arena/01a05caf-dream` (session branch; mission named `fix/p0-security-stability`)
- **Base commit:** `c038d9dbc12733976324227aa854b2c68e20bb94` (`chore(release): cut 0.4.6 with non-streaming chat completions (#114)`)
- **Transferable patch:** `SEC-01.patch` (repository root), generated against that base commit

## Crate inspection

From `apps/desktop/src-tauri/Cargo.toml`:

| Dependency | Present | Notes |
|---|---|---|
| `thiserror` | yes (`thiserror = "2"`) | used by the existing `Error` type |
| `serde` | yes (`features = ["derive"]`) | Tauri command payloads |
| `serde_json` | yes (`"1"`) | JSON-RPC framing |
| edition | `2021` | rust-version `1.77.2` |

No new crates were added. `Cargo.toml` / `Cargo.lock` were not modified.

Crate roots: `src/lib.rs` (library `dream_desktop_lib`) and `src/main.rs` (thin desktop wrapper calling `dream_desktop_lib::run()`). `error.rs` already existed as the Tauri command error type (`Error`); this task extends it with a typed `BridgeError` enum rather than replacing the window/tray/dialog error surface.

Existing command-facing bridge error (before this change) was a `Serialize` struct `{ code, message, data? }` in `bridge/mod.rs`. The frontend (`src/lib/bridge/errors.ts` `toBridgeError`) branches on that shape. The new enum serialises to the same object so the React layer does not need to change.

## Files audited

All production and test Rust under `apps/desktop/src-tauri/src/`:

- `main.rs`, `lib.rs`, `error.rs`, `state.rs`, `single_instance.rs`, `tests.rs`
- `bridge/mod.rs`, `bridge/process.rs`, `bridge/framing.rs`, `bridge/dispatcher.rs`, `bridge/state.rs`
- `commands/mod.rs`, `commands/window.rs`, `commands/dialogs.rs`, `commands/tray.rs`, `commands/notifications.rs`

Search used (PowerShell-friendly):

```text
rg -n "\.unwrap\(\)|\.expect\(|panic!\(|unimplemented!\(" apps/desktop/src-tauri/src
```

`.unwrap_or`, `.unwrap_or_else`, `.unwrap_or_default`, and `.expect_err` in tests are not panic-prone production sites. Poisoned mutexes in `state.rs` and `commands/notifications.rs` already recover via `into_inner()` and were left unchanged.

## Production panic-prone sites

| File | Line (pre-change) / function | Original operation | Replacement | Rationale |
|---|---|---|---|---|
| `lib.rs` | 161 `run()` | `.expect("error while running Dream desktop application")` | `if let Err(error) = builder.run(...)` then `eprintln!` + `std::process::exit(1)` | Tauri context failure is not recoverable, but a process exit is not a panic and does not unwind through user windows. Logging may not be alive yet, so stderr is used. |
| `bridge/process.rs` | 349 `start_instance` | `child.stdin.take().expect("piped stdin")` | `take_piped_stdio` → `require_piped_stdio`; on `Err`, log, `start_kill`/`wait`, try the next interpreter | Piped stdio is expected after `Stdio::piped()`, but a missing handle must not abort the desktop process. |
| `bridge/process.rs` | 350 `start_instance` | `child.stdout.take().expect("piped stdout")` | same helper | Same as stdin. |
| `bridge/dispatcher.rs` | 53 `Dispatcher::register` | `panic!("duplicate bridge request id {id}")` | `Err(BridgeError::InvalidArgument(...))` | Duplicate ids are a caller error. Returning a typed error preserves the original registration and lets `bridge_send` reject the promise. |

No other production `.unwrap()`, `.expect(`, `panic!`, or `unimplemented!` remained after the replacements.

Related hardening (not originally panic sites, but in the requested modules):

- `framing::parse` now returns `Result<ParsedMessage, BridgeError>` instead of `Option`. Empty frames, protocol headers, invalid JSON, missing JSON-RPC fields, non-object JSON, non-numeric ids, oversized frames, and invalid UTF-8 (`parse_bytes`) all error with a reason that does **not** echo the raw line.
- `supervise_reader` logs the parse error and skips the line (same skip semantics as before, with context). Stdout I/O / UTF-8 failures are logged via `BridgeError::io("read sidecar stdin/stdout", …)` and end the instance so the supervisor can restart, instead of looking like a clean EOF.
- Writer, kill, wait, spawn, and data-root failures log a typed `BridgeError` and never panic on teardown.
- `ensure_sidecar_data_root` now returns `Result<PathBuf, BridgeError>`.

## Test-only occurrences retained

All remaining `.unwrap()` / `.expect(` / `panic!` matches live inside `#[cfg(test)]` modules or `src/tests.rs`. They were left in place so production code was not weakened merely to satisfy a grep.

| File | Why retained |
|---|---|
| `src/tests.rs` | Path-validation / app-state unit tests (tempdir, canonicalize, mock app). |
| `single_instance.rs` (`mod tests`) | Lockfile / focus-marker tests. |
| `bridge/state.rs` (`mod tests`) | Serde round-trip of `ConnectionState`. |
| `bridge/process.rs` (`mod tests`) | Interpreter discovery, bundled-path fixtures, `tempfile`. Includes the known sites around original lines 641, 685, 688–697, 724. |
| `bridge/framing.rs` (`mod tests`) | Valid-frame assertions. Includes the known sites around original lines 133, 142, 155, 172, 195. |
| `bridge/dispatcher.rs` (`mod tests`) | Channel delivery assertions; `register` now uses `.expect("register")` because it returns `Result`. |
| `error.rs` (`mod tests`) | New `BridgeError` tests. |

`unimplemented!()` does not occur anywhere under `src/`.

## New error variants and conversion behaviour

`BridgeError` (in `apps/desktop/src-tauri/src/error.rs`), re-exported as `crate::bridge::BridgeError`:

| Variant | Role |
|---|---|
| `Io { operation, kind }` | I/O without embedding `std::io::Error`'s `Display` (paths). |
| `Serde(serde_json::Error)` | JSON encode/decode (`From`). |
| `ProcessNotFound(String)` | Missing interpreter / `ErrorKind::NotFound`. |
| `SidecarCrashed(String)` | Missing pipes / unusable child. |
| `InvalidArgument(String)` | Duplicate request id, etc. |
| `Timeout(Duration)` | Explicit deadline (template requirement; heartbeat still restarts the sidecar). |
| `PermissionDenied(String)` | `ErrorKind::PermissionDenied`. |
| `NotReady` | Sidecar not connected / writer gone. Replaces the old `not_ready()` struct ctor. |
| `Rpc { code, message, data }` | Sidecar JSON-RPC error, forwarded unchanged. |
| `MalformedFrame(String)` | Framing reason only — never the raw frame. |
| `FrameTooLarge { size, max }` | DoS guard at 16 MiB (`framing::MAX_FRAME_BYTES`). |
| `Other(String)` | Fallback for closed oneshots / internal coordination. Justified: those failures are real and recoverable but are not I/O, JSON, or process-lifecycle errors. `internal("sidecar closed")` still serialises as message `"sidecar closed"`. |

Conversions:

- `From<std::io::Error>` → `BridgeError::io("bridge I/O", err)` which maps `NotFound` / `PermissionDenied` and otherwise stores only `ErrorKind`.
- `From<serde_json::Error>` via `#[from]`.
- Helpers `rpc` / `not_ready` / `internal` / `io` preserve the previous call sites in `bridge/mod.rs`.

Tauri-facing `Serialize` emits `{ "code": i32, "message": String, "data"?: Value }` using JSON-RPC codes aligned with `framing::code` (`PARSE_ERROR` for serde/malformed/oversize, `INVALID_PARAMS` for bad arguments, `AUTH_ERROR` for permission, `INTERNAL_ERROR` otherwise, sidecar code for `Rpc`). `data` is omitted when `None`.

## Command / API compatibility

| Surface | Change |
|---|---|
| `bridge_send` / `bridge_status` / `bridge_restart` / `bridge_kill` | Still `Result<T, BridgeError>`. Success payloads unchanged. Error JSON still `{code,message,data?}`. |
| `Dispatcher::register` | Now `Result<RequestChannels, BridgeError>` (crate-internal). |
| `framing::parse` | Now `Result<ParsedMessage, BridgeError>` (crate-internal). Valid messages classify as before. |
| `run()` | Corrupt-bundle failure exits with code 1 instead of panicking. |
| Window / tray / dialog / notification commands | Untouched; still use `error::Error`. |

Frontend coordination is **not required**. `toBridgeError` already accepts both structured objects and strings.

## Security considerations

- I/O errors retain `ErrorKind` + operation name only. Paths such as `/home/alice/.../secrets.env` are dropped (covered by unit test).
- Framing errors store a reason (`empty frame`, `not valid UTF-8`, …), never the raw line (conversation content / credentials could appear on stdout).
- Spawn/write/kill logs include the interpreter *candidate name* (needed for diagnosis) but not request bodies.
- `Rpc.data` is still passed through from the Python sidecar — that object is owned by the core protocol (e.g. `approval_id`) and was already on the wire.
- New 16 MiB frame cap rejects oversized messages instead of allocating without bound.
- Existing `unsafe` in `single_instance.rs` (Win32 mutex FFI, POSIX `kill(pid, 0)`) was documented in-place already; this task did not expand it.

## Coordination needed

None for other sub-agents. The React layer, Python sidecar, and CI workflows were not modified.

Optional follow-up (out of scope): a frontend test that a duplicate `bridge_send` id surfaces as `INVALID_PARAMS` rather than a disconnected webview.

## Tests added or updated

**Added (12):**

- `error.rs`: `display_representative_variants`, `from_io_error_preserves_kind_without_path`, `from_io_not_found_and_permission_map_to_specific_variants`, `from_serde_json_error`, `serializes_as_structured_rpc_object`, `malformed_and_oversize_frames_use_parse_error_code`
- `framing.rs`: `parse_rejects_invalid_json_with_serde_error`, `parse_rejects_oversized_frame`, `parse_bytes_rejects_invalid_utf8`, `parse_bytes_accepts_valid_response`
- `dispatcher.rs`: `register_duplicate_id_returns_error_instead_of_panicking`
- `process.rs`: `missing_piped_stdio_returns_error_instead_of_panicking`

**Updated:** existing framing parse tests now assert `Result` (`is_err()` / `unwrap_err()`); dispatcher tests call `register(...).expect(...)`. Valid-frame and dispatcher success tests still assert the same payloads.

## Verification

### Production panic audit

Command:

```text
rg -n '\.unwrap\(\)|\.expect\(' src -g '*.rs'
rg -n 'panic!\(|unimplemented!\(' src -g '*.rs'
```

(run from `apps/desktop/src-tauri` equivalently against `src`).

**Result:** every remaining match is inside `#[cfg(test)]` modules or `src/tests.rs`. Production-only classification of the same patterns: **0 matches**. `unimplemented!()` : **0 matches** anywhere.

### Rust checks

`rustfmt` 1.8.0-stable (`6b00bc3880 2025-06-23`) was run against every `.rs` file in `apps/desktop/src-tauri` (edition 2021, `max_width = 100`, matching `rustfmt.toml`). `rustfmt --check` exits 0 on that tree.

`cargo` / `rustc` / `clippy` were **not** available as a full toolchain, so compile/test/clippy were **not run** and are **not claimed as passing**:

| Command | Result |
|---|---|
| `rustfmt --check` (edition 2021, `max_width=100`) | **PASS** on all crate `.rs` files |
| `cargo fmt --all -- --check` | **NOT RUN** as `cargo` (equivalent `rustfmt --check` passed) |
| `cargo check --all-targets` | **NOT RUN** — no `cargo` |
| `cargo test --lib` | **NOT RUN** — no `cargo` |
| `cargo clippy --all-targets -- -D warnings` | **NOT RUN** — no `clippy` |

Re-run `cargo check` / `test` / `clippy` from `apps/desktop/src-tauri` once a 1.77.2+ toolchain is available.

### Regression protection (intent)

Existing framing, dispatcher, and process unit tests were preserved and extended. Successful parse/register paths still return the same `ParsedMessage` / channel payloads. Full execution is blocked on the missing toolchain (see above).

## Transferable patch

The complete source change set lives in `SEC-01.patch` at the repository root. It is a unified diff against v0.4.6 (`c038d9d`) and is meant to be applied on the user's local tree:

```text
cd C:\Users\alina\Dream
git apply --check SEC-01.patch
git apply SEC-01.patch
```

The patch does **not** include itself. After a successful apply the working tree contains the six Rust files below plus this audit document.

Verification of the patch artefact (this environment, against a clean `c038d9d` tree):

```text
git diff --check           # exit 0 (no whitespace errors)
git apply --check SEC-01.patch   # exit 0
git apply SEC-01.patch           # exit 0
```

## Scope check

Modified files (strict isolation):

- `apps/desktop/src-tauri/src/error.rs`
- `apps/desktop/src-tauri/src/lib.rs`
- `apps/desktop/src-tauri/src/bridge/mod.rs`
- `apps/desktop/src-tauri/src/bridge/process.rs`
- `apps/desktop/src-tauri/src/bridge/framing.rs`
- `apps/desktop/src-tauri/src/bridge/dispatcher.rs`
- `SEC-01-AUDIT.md` (this file)
- `SEC-01.patch` (generated artefact; not part of the apply payload)

`Cargo.toml` / `Cargo.lock` were not changed.
