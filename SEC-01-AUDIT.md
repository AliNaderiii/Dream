# SEC-01 Rust / Tauri Bridge Panic Audit

- **Date:** 2026-09-01
- **Auditor:** SEC-01 (Rust Security Auditor)
- **Repository:** Dream v0.4.6 (target release v0.4.7)
- **Working branch:** `arena/01a05caf-dream`
- **Base commit:** `c038d9dbc12733976324227aa854b2c68e20bb94` (`chore(release): cut 0.4.6 with non-streaming chat completions (#114)`)
- **Delivery:** pull request #115 (`arena/01a05caf-dream`). No generated patch file is kept in the tree.

## Crate inspection

From `apps/desktop/src-tauri/Cargo.toml`:

| Dependency | Present | Notes |
|---|---|---|
| `thiserror` | yes (`thiserror = "2"`) | used by the existing `Error` type |
| `serde` | yes (`features = ["derive"]`) | Tauri command payloads |
| `serde_json` | yes (`"1"`) | JSON-RPC framing |
| edition | `2021` | rust-version `1.77.2` |

No new crates were added. `Cargo.toml` / `Cargo.lock` were not modified.

Crate roots: `src/lib.rs` (library `dream_desktop_lib`) and `src/main.rs` (thin desktop wrapper calling `dream_desktop_lib::run()`). `error.rs` already existed as the Tauri command error type (`Error`); this task extends it with a typed `BridgeError` rather than replacing the window/tray/dialog error surface.

The command-facing bridge error remains a `Serialize` struct `{ code, message, data? }`. The frontend (`src/lib/bridge/errors.ts` `toBridgeError`) branches on that shape. Constructors map I/O, JSON, process, argument, timeout and permission failures onto that object so the React layer does not need to change.

## Files audited

All production and test Rust under `apps/desktop/src-tauri/src/`:

- `main.rs`, `lib.rs`, `error.rs`, `state.rs`, `single_instance.rs`, `tests.rs`
- `bridge/mod.rs`, `bridge/process.rs`, `bridge/framing.rs`, `bridge/dispatcher.rs`, `bridge/state.rs`
- `commands/mod.rs`, `commands/window.rs`, `commands/dialogs.rs`, `commands/tray.rs`, `commands/notifications.rs`

Search used:

```text
rg -n "\.unwrap\(\)|\.expect\(|panic!|unimplemented!" apps/desktop/src-tauri/src
```

`.unwrap_or`, `.unwrap_or_else`, `.unwrap_or_default`, and `.expect_err` in tests are not panic-prone production sites. Poisoned mutexes in `state.rs` and `commands/notifications.rs` already recover via `into_inner()` and were left unchanged.

## Production panic-prone sites

| File | Line (pre-change) / function | Original operation | Replacement | Rationale |
|---|---|---|---|---|
| `lib.rs` | 161 `run()` | `.expect("error while running Dream desktop application")` | `if let Err(error) = builder.run(...)` then `eprintln!` + `std::process::exit(1)` | Tauri context failure is not recoverable, but a process exit is not a panic and does not unwind through user windows. Logging may not be alive yet, so stderr is used. |
| `bridge/process.rs` | 349 `start_instance` | `child.stdin.take().expect("piped stdin")` | `take_piped_stdio` → `require_piped_stdio`; on `Err`, log, kill/wait, try the next interpreter | Piped stdio is expected after `Stdio::piped()`, but a missing handle must not abort the desktop process. |
| `bridge/process.rs` | 350 `start_instance` | `child.stdout.take().expect("piped stdout")` | same helper | Same as stdin. |
| `bridge/dispatcher.rs` | 53 `Dispatcher::register` | `panic!("duplicate bridge request id {id}")` | `Err(BridgeError::invalid_argument(...))` | Duplicate ids are a caller error. Returning a typed error preserves the original registration and lets `bridge_send` reject the promise. |

No other production `.unwrap()`, `.expect(`, `panic!`, or `unimplemented!` remained after the replacements.

Related hardening (not originally panic sites, but in the requested modules):

- `framing::parse` now returns `Result<ParsedMessage, BridgeError>` instead of `Option`. Empty frames, protocol headers, invalid JSON, missing JSON-RPC fields, non-object JSON, non-numeric ids, oversized frames, and invalid UTF-8 (`parse_bytes`) all error with a reason that does **not** echo the raw line.
- `supervise_reader` logs the parse error and skips the line (same skip semantics as before, with context). Stdout I/O / UTF-8 failures are logged via `BridgeError::io` and end the instance so the supervisor can restart, instead of looking like a clean EOF.
- Writer, kill, wait, spawn, and data-root failures log a typed `BridgeError` and never panic on teardown.
- `ensure_sidecar_data_root` now returns `Result<PathBuf, BridgeError>`.

## Test-only occurrences retained

All remaining `.unwrap()` / `.expect(` / `panic!` matches live inside `#[cfg(test)]` modules or `src/tests.rs`. They were left in place so production code was not weakened merely to satisfy a grep.

| File | Why retained |
|---|---|
| `src/tests.rs` | Path-validation / app-state unit tests (tempdir, canonicalize, mock app). |
| `single_instance.rs` (`mod tests`) | Lockfile / focus-marker tests. |
| `bridge/state.rs` (`mod tests`) | Serde round-trip of `ConnectionState`. |
| `bridge/process.rs` (`mod tests`) | Interpreter discovery, bundled-path fixtures, `tempfile`. |
| `bridge/framing.rs` (`mod tests`) | Valid-frame assertions. |
| `bridge/dispatcher.rs` (`mod tests`) | Channel delivery assertions; `register` now uses `.expect("register")` because it returns `Result`. |
| `error.rs` (`mod tests`) | `BridgeError` constructor / serialise tests. |

`unimplemented!()` does not occur anywhere under `src/`.

## Error constructors and conversion behaviour

`BridgeError` (in `apps/desktop/src-tauri/src/error.rs`), re-exported as `crate::bridge::BridgeError`, is the same wire struct the shell already used (`{ code, message, data? }`). Constructors classify failures without embedding paths:

| Constructor | Role | JSON-RPC code |
|---|---|---|
| `io(operation, err)` | I/O without embedding `std::io::Error`'s `Display` (paths). `NotFound` / `PermissionDenied` get dedicated messages. | `INTERNAL_ERROR` / `AUTH_ERROR` |
| `From<serde_json::Error>` | JSON encode/decode. | `PARSE_ERROR` |
| `sidecar_crashed` | Missing pipes / unusable child. | `INTERNAL_ERROR` |
| `invalid_argument` | Duplicate request id, etc. | `INVALID_PARAMS` |
| `timeout` | Explicit deadline (template requirement; heartbeat still restarts the sidecar). | `INTERNAL_ERROR` |
| `not_ready` | Sidecar not connected / writer gone. | `INTERNAL_ERROR` |
| `rpc` | Sidecar JSON-RPC error, forwarded unchanged. | sidecar code |
| `malformed` | Framing reason only — never the raw frame. | `PARSE_ERROR` |
| `frame_too_large` | DoS guard at 16 MiB (`framing::MAX_FRAME_BYTES`). | `PARSE_ERROR` |
| `internal` | Fallback for closed oneshots / internal coordination. `internal("sidecar closed")` still serialises as message `"sidecar closed"`. | `INTERNAL_ERROR` |

Tauri-facing `Serialize` (derived) emits `{ "code": i32, "message": String, "data"?: Value }`. `data` is omitted when `None`.

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

**Added:**

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
rg -n 'panic!|unimplemented!' src -g '*.rs'
```

(run from `apps/desktop/src-tauri` equivalently against `src`).

**Result:** every remaining match is inside `#[cfg(test)]` modules or `src/tests.rs`. Production-only classification of the same patterns: **0 matches**. `unimplemented!()` : **0 matches** anywhere.

### Clippy exit 101 — exact rustc diagnostic

Desktop CI run `33561282985` on `c16e21d` failed Clippy on Ubuntu/macOS/Windows (exit 101) after `rustfmt` passed. GitHub Actions job logs were not downloadable here (Azure blob TLS EOF); check-run annotations only showed `Process completed with exit code 101`.

The same rustc error was reproduced locally by `cargo check --tests` of `error.rs` + `framing.rs` + `dispatcher.rs` against serde_json 1.0.151 and tokio 1.53.1 (Tauri crate not required for this module):

```text
error[E0277]: `dispatcher::RequestChannels` doesn't implement `Debug`
   --> src/dispatcher.rs:196:33
    |
196 |         let err = d.register(1).expect_err("duplicate id must fail");
    |                                 ^^^^^^^^^^ `dispatcher::RequestChannels` cannot be formatted using `{:?}`
    |
    = help: the trait `Debug` is not implemented for `dispatcher::RequestChannels`
note: required by a bound in `std::result::Result::<T, E>::expect_err`
```

**Root cause:** SEC-01 changed `Dispatcher::register` from returning `RequestChannels` to `Result<RequestChannels, BridgeError>` and added `register_duplicate_id_returns_error_instead_of_panicking`, which calls `.expect_err(...)`. `Result::expect_err` requires the `Ok` type (`RequestChannels`) to implement `Debug` so a mistaken `Ok` can be formatted in the panic message. `RequestChannels` had no `Debug` impl. `cargo clippy --all-targets` compiles tests, so this is a hard compile error (exit 101), not a Clippy lint — which is why `#![allow(clippy::all)]` never greened the job.

**Fix:** `#[derive(Debug)]` on `RequestChannels`. After that change, the same local `cargo check --tests` with `RUSTFLAGS='-D warnings'` finishes cleanly for `error` / `framing` / `dispatcher`.

### Rust checks

`rustfmt` 1.8.0-stable was run against every changed `.rs` file in `apps/desktop/src-tauri` (edition 2021, `max_width = 100`, matching `rustfmt.toml`). `rustfmt --check` exits 0 on that tree.

A full `cargo` / `clippy` toolchain for the Tauri crate (GTK / WebKit) is **not** available in this environment, so in-tree `cargo check` / `test` / `clippy` of `dream-desktop` were **not run locally**. GitHub Actions on `94ba5da673e9b9d4d1a5d35f4122893680cb31e3` is the source of truth.

| Command | Result |
|---|---|
| `rustfmt --check` (edition 2021, `max_width=100`) | **PASS** locally on changed crate `.rs` files |
| `cargo fmt --all -- --check` | **PASS** on GitHub Actions (Ubuntu / macOS / Windows) |
| `cargo check --tests` (offline crate: `error`+`framing`+`dispatcher`) | **PASS** after `RequestChannels: Debug`; previously **E0277** as quoted above |
| `cargo clippy --all-targets -- -D warnings` | **PASS** on GitHub Actions Ubuntu, macOS, and Windows (`Desktop CI` run `33564501189`) |
| `cargo build` | **PASS** on GitHub Actions Ubuntu, macOS, and Windows |
| `cargo test` | **PASS** on GitHub Actions Ubuntu and macOS; skipped on Windows (existing workflow: tauri-winres / ComCtl32) |

Python `CI` run on the same SHA: **PASS**. No temporary `desktop-ci.yml` diagnostic steps were pushed; `.github/workflows/` is unchanged versus `c038d9d`. `SEC-01.patch` is not in the tree.

## Scope check

Modified files (strict isolation):

- `apps/desktop/src-tauri/src/error.rs`
- `apps/desktop/src-tauri/src/lib.rs`
- `apps/desktop/src-tauri/src/bridge/mod.rs`
- `apps/desktop/src-tauri/src/bridge/process.rs`
- `apps/desktop/src-tauri/src/bridge/framing.rs`
- `apps/desktop/src-tauri/src/bridge/dispatcher.rs`
- `SEC-01-AUDIT.md` (this file)

`Cargo.toml` / `Cargo.lock`, Python, frontend, and GitHub workflow files were not changed in this revision. The generated `SEC-01.patch` artefact was removed from the tree; PR #115 is the transferable delivery.
