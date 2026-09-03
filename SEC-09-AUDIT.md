# SEC-09 — Sidecar Process-Tree Containment Audit

- **Repository:** Dream v0.4.6 baseline (target release v0.4.7)
- **Base commit:** `b4d62bc6f439308c6b53bf1d42a8de4ed47ffe2d` (`fix(memory): make BoundedStore operations thread-safe (SEC-08)` — tip of `main` with SEC-01 … SEC-08 merged)
- **Working branch:** `arena/01a06749-dream` (the Arena environment fixes this branch name; the brief's `fix/p0-security-stability` could not be used — see §8 Coordination)
- **Scope actually touched:** `apps/desktop/src-tauri/src/bridge/process.rs`, `apps/desktop/src-tauri/Cargo.toml`, `apps/desktop/src-tauri/Cargo.lock` (dependency sync only), `docs/dev/how-to/sidecar-lifecycle.md` (new), `SEC-09-AUDIT.md` (this file). Nothing else — no Python, frontend, workflow, or other Rust changes; `bridge/mod.rs` needed no edit because the whole supervision loop lives in `process.rs`.

## 1. Lifecycle inventory (audited before editing)

`rg -n "Child|kill_on_drop|terminate|start_kill|Stdio" apps/desktop/src-tauri/src` at the base commit. The pre-SEC-09 state:

| Surface | Base behaviour | SEC-09 verdict |
|---|---|---|
| `process::spawn()` | `tokio::process::Command` + `kill_on_drop(true)`; `child.kill_on_drop(true)` inherited semantics only reaped the **direct** child | descendants (sidecar-spawned tools) could outlive it → **fixed** |
| `start_instance` stdio-failure path | `abandon_child(&mut child)` — `start_kill` on the direct child only | now a full `terminate_sidecar` teardown → **fixed** |
| Supervisor exit / restart path | reader EOF → drop handles → `kill_on_drop` | now `reap_instance` → `terminate_sidecar` awaited before the next spawn → **fixed** |
| Hang path | heartbeat marks `Hung` after 15 s; reader ends; same drop path | teardown is now driven at the same point the reader ends → **fixed** (see §5 limitation) |
| `Bridge::restart` / `Bridge::kill` (`mod.rs`) | flip `killed` flag, drop the `writer_tx` sender → stdin EOF | **preserved deliberately** (see §5) — EOF reaches the sidecar, containment teardown runs inside the supervisor |
| quit teardown (`lib.rs` → `kill_bridge_on_quit`) | `Bridge::kill()` + exit | unchanged; OS-level kill-on-close (Win) / EOF+`kill_on_drop` (Unix) cover abrupt exit |
| Interpreter selection (`python`/`py`/`python3`, `DREAM_SIDECAR_PYTHON` override, bundled-first prepend) | candidate loop in `spawn_first` | **unchanged**, containment attaches per successfully spawned candidate |
| Env (`PYTHONUTF8`, `PYTHONIOENCODING`, `PYTHONNOUSERSITE`, `DREAM_PYTHONPATH`→`PYTHONPATH`), cwd (`data_root`), piped stdio, `CREATE_NO_WINDOW` + stderr null on Windows | `sidecar_command` (was inline in `spawn`) | **unchanged** — extracted verbatim into `sidecar_command()` so discovery/tests can share it; containment adds `process_group(0)` only |
| Restart backoff (2/5/10 s, max 3) and heartbeat (5 s ping / 15 s timeout) | `run_supervisor` / `heartbeat_watchdog` | **unchanged**; backoff now starts after teardown completes (not concurrently) |

`apps/desktop/src-tauri/src-tauri/tests/` contains no `process_tests.rs`; per the task brief, lifecycle tests are inline in `process.rs` (`#[cfg(test)] mod tests`).

## 2. Windows implementation (Job Object)

`SidecarContainment::establish` → `windows_job::contain_pid(pid)`:

1. `CreateJobObjectW(null, null)` — unnamed private job (no object name, so no cross-process namespace and no collision with other apps);
2. `SetInformationJobObject(JobObjectExtendedLimitInformation)` with exactly one flag: `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`;
3. `OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, FALSE, pid)` — the documented access pair `AssignProcessToJobObject` requires; handle closed in all branches (no leak);
4. `AssignProcessToJobObject(job, process)` — the child **and every process it later spawns** are inside; `GetLastError` captured before `CloseHandle` can clobber it.

Teardown: `TerminateJobObject(job, 0)` (ERROR_NOT_FOUND = empty job → `Ok`), then `CloseHandle` — kill-on-close guarantees survivors die with the last handle even if termination is skipped (crash, abort). `JobHandle` is `Send` (unsafe impl justified in-code comment: one private, non-thread-affine handle, never aliased), `Drop`-closed, and `close()` takes the option so double-close is impossible. No `taskkill` anywhere. Failure at any step → the partially-built job is closed and `spawn()` discards the uncontained child (never runs uncontained).

## 3. Unix implementation (process group)

- Before `exec`: `CommandExt::process_group(0)` → the child starts as leader of `pgid == pid` (std wrapper for `setpgid(0, 0)` in the fork hook; no race, no `unsafe`).
- After spawn, `establish` verifies `getpgid(pid) == pid` (an error ⇒ nothing was contained ⇒ discard path). It stores `pgid: Option<pid_t>`.
- Teardown escalation: `killpg(pgid, SIGTERM)` → bounded waits → `killpg(pgid, SIGKILL)` → `close()` performs one last `killpg(SIGKILL)` sweep for descendants that outlived the leader, absorbing `ESRCH` (empty group) as success and treating any other errno as a typed error.
- **`PR_SET_PDEATHSIG` deliberately excluded** (documented in code and the how-to): with tokio it fires on parent *worker-thread* exit (tokio reaps idle workers → healthy sidecars would get SIGTERM mid-run; the bug is described at length by tokio maintainers — kobzol.github.io/rust/2025-02-23/tokio-plus-prctl-equals-nasty-bug.html), and it is Linux-only anyway. Parent death is covered by the stdin EOF channel plus group sweep.
- No FDs/handles exist to leak on this path (a pgid is not a kernel object); the ownership invariant is the `Option::take` on `close()`.

## 4. Error handling & cleanup behavior

- All new fallible functions return `Result<_, BridgeError>` / `io::Result`; `BridgeError::io(ctx, err)` never embeds paths or argv (SEC-01 policy). **Zero** `unwrap()`/`expect()` outside `#[cfg(test)]` (verified: `rg -n "\.unwrap\(\)|\.expect\(" src/bridge/process.rs` — matches only inside `mod tests` / `#[cfg(test)]` helpers).
- No panics: `establish` tolerates the exited-before-assign race via `child.id()` → typed `sidecar_crashed`; every signal/handle call checks its return; `terminate_sidecar` records the *first* failure, still runs all remaining cleanup steps, and returns the recorded error — a second call is a clean no-op.
- Structured lifecycle logs (spawned / containment established / graceful requested / forced / descendant sweep info-vs-debug / containment-failure) carry pid + fixed text only.
- Teardown timeout budget: 1 s + 1 s + 5 s waits; a timed-out reap logs and relies on `kill_on_drop`; the containment close **always** runs afterwards.

## 5. Ownership and sequencing guarantees

- One `SidecarContainment` exists per spawned instance, created inside `spawn()` and stored in `SpawnedSidecar { child, containment }`; `start_instance` owns it for the instance's lifetime; `reap_instance` → `terminate_sidecar` consumes child and containment together. Nothing else can observe or signal the group/job; `mod.rs` never holds a `Child` (that is why it needed no changes).
- The old containment is fully closed before the next candidate/restart spawns (teardown is awaited inside `start_instance`/before the backoff `sleep`), so restarts never overlap groups/jobs.
- No lock is held across any await in the teardown path (the writer-channel mutex is scoped).
- Limitation (accepted, documented in the how-to): if the app aborts the supervisor task in the microseconds between reader EOF and `reap_instance`, OS cleanup falls back to `kill_on_drop` + EOF + (Windows) kill-on-close; Unix descendants of a SIGKILLed parent without supervisor can survive until process exit closes the stdin pipe's reader set. Hardening this further requires `Bridge::kill` to await containment close — a `mod.rs`/`lib.rs` change deliberately left out of scope (Coordination §8).

## 6. Test matrix

All tests are bounded (explicit deadlines: 20 s helper start, 10 s death-poll), PID-based (helpers report pids through files in a `tempfile::TempDir`), never signal anything they did not spawn, and never depend on an installed Python (`/bin/sh`, `powershell.exe`, `ping.exe` only).

| Test | Platform | Real process? | What it proves |
|---|---|---|---|
| `unix_teardown_terminates_child_and_descendants` | `cfg(unix)` | yes (sh + backgrounded `sleep`) | group membership (leader + inherited descendant), teardown reaps leader **and** sweeps descendant |
| `unix_teardown_is_idempotent_and_safe_after_natural_exit` | `cfg(unix)` | yes | already-exited child → clean no-op; double teardown → `Ok` |
| `unix_containment_setup_failure_does_not_leave_an_orphan` | `cfg(unix)` | yes | `discard_uncontained_child` policy: killed + reaped promptly |
| `unix_restart_tears_down_old_group_before_new_instance` | `cfg(unix)` | yes | old group dead before new instance leads a *different* fresh group; old leader stays dead |
| `windows_job_object_contains_child_and_descendants` | `cfg(windows)` | yes (powershell + `Start-Process ping.exe`) | `IsProcessInJob` for child **and** grandchild; teardown kills the whole tree |
| `windows_teardown_is_idempotent_and_safe_after_natural_exit` | `cfg(windows)` | yes | job-path idempotence incl. exited-child case |
| `windows_containment_setup_reports_typed_error_for_dead_pid` | `cfg(windows)` | no | typed establishment error for a reserved-miss pid, no leaked job (partial `JobHandle` Drop-closed) |
| discovery tests (`spawn_first` probes, `sidecar_creation_flags`, `require_piped_stdio`, env tables) | all | no | existing tests retyped for the `SpawnedSidecar` return — semantics asserted unchanged |

Skips / platform notes: none of the assertions above are skipped where they run; the three Windows tests are `#[cfg(windows)]` (Job Objects have no POSIX analogue) and the four Unix tests `#[cfg(unix)]` (process groups have no Win32 equivalent) — each platform gets real, platform-native coverage rather than cross-platform mockups. CI executes `cargo test --lib` on Linux and macOS only; **Windows CI skips `cargo test`** (pre-existing tauri-winres/ComCtl32 link failure, tauri-apps/tauri#13419, documented in `apps/desktop/.github/workflows/desktop-ci.yml`), but it still *compiles* the Windows tests via `cargo check --all-targets` and lints them via `clippy --all-targets`; execution is expected on Windows dev machines (`cargo test --lib`). No Linux-only mechanism (e.g. PDEATHSIG) was adopted, so there is nothing else to skip.

## 7. Commands and results

Local environment for this task had **no Rust toolchain and no network** to install one, so the full verification suite runs in CI (all three OSes) and is authoritative:

```bash
# CI (apps/desktop/.github/workflows/desktop-ci.yml, per OS ubuntu/macos-14/windows-latest):
cargo fmt --all -- --check
cargo clippy --all-targets -- -D warnings   # ubuntu job
cargo check --all-targets
cargo test -p dream-desktop --lib           # skipped on windows, see §6
# root workflow: python test suite, ruff, tools/check_commit.py
```

Locally verified before pushing:

| Command | Result |
|---|---|
| `git diff --check` | clean (no whitespace errors) |
| `git status --short` | exactly the five in-scope paths |
| `rg -n "\.unwrap\(\)\|\.expect\(" src/bridge/process.rs` | matches only inside `#[cfg(test)]` code |
| structural scan (braces/parens/brackets balanced, no line >100 except 3 pre-existing macro string literals) | balanced ✓ |
| `python3 tools/check_commit.py <rev>` | pending after commit |

CI results (recorded once green): PENDING — this section is amended with check names, run URLs and the commit SHA after the PR checks complete.

## 8. Coordination / remaining risks

- **`Bridge::kill()` does not await teardown** (by design here): it drops the writer, the sidecar EOF-exits, and the supervisor runs containment close. The only window where containment close is *not* deterministic is a hard abort between reader EOF and `reap_instance`. If the PM wants quit-time determinism, the follow-up is to have `kill_bridge_on_quit` (or `Bridge::kill`) signal and await a bounded containment close — touches `bridge/mod.rs` + `lib.rs`, out of SEC-09 scope.
- **Windows CI cannot execute the new tests** (upstream tauri#13419 link skip, pre-existing). Coverage is compile+lint in CI and execution on dev machines; recorded in the how-to. If the project later vendors a workaround for the winres link issue, remove the CI `if:` skip and these tests run there automatically.
- Python side (`dream/bridge`) and `tauri-plugin-shell` were **not touched**; the sidecar's EOF-graceful exit contract it already implements is the load-bearing piece for parent-death on Unix, so any future change to sidecar stdin handling must keep EOF ⇒ exit (docs/bridge/protocol.md).
- The supervisor's pre-existing quirk that a sidecar whose stdout never closes is only reclaimed through the **heartbeat → Hung** route (not a reader timeout) was preserved unchanged.
- `Cargo.lock` was updated by hand to match `Cargo.toml` (libc 0.2 unix, windows-sys 0.52 + the three needed Win32 features — versions selected to reuse entries already present in the lock from existing deps); `cargo` will regenerate identical entries; `--locked` CI runs will confirm.
