# How the sidecar process lifecycle is contained

The desktop app supervises one Python sidecar (`<python> -m dream.bridge`) as a
child process over piped stdio. Because the sidecar can itself spawn children
(tools, helpers), killing only the direct child would orphan the rest of the
tree. SEC-09 made every instance run inside a **platform containment** that
owns the whole tree, so spawn, restart, hang recovery and quit all go through
one teardown path that cannot leak processes or handles.

All of this lives in `apps/desktop/src-tauri/src/bridge/process.rs`.

## Mechanisms per platform

| Platform | Containment | Established | Torn down |
| --- | --- | --- | --- |
| Windows | Private Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` | after spawn: `CreateJobObjectW` → set limits → `OpenProcess(SET_QUOTA\|TERMINATE)` → `AssignProcessToJobObject` | `TerminateJobObject`, then `CloseHandle` (kill-on-close sweeps any survivor) |
| Unix-like (Linux, macOS) | Dedicated process group, `process_group(0)` applied before `exec` | in the `Command` configuration; verified right after spawn via `getpgid(pid) == pid` | `killpg(SIGTERM)` → bounded wait → `killpg(SIGKILL)` → final sweep on close |
| Other Unix-less/Windows-less targets | none compiled in; leader-only semantics | — | `Child` kill only |

Windows has no way to pre-configure a `Command`, so the job object is attached
immediately after spawn. Any process the sidecar later starts **inherits** the
job, so the whole tree stays covered. On Unix the group is created *before*
`exec` (inside the forked child by the kernel), which survives interpreter
changes and has no parent/child race — the safe `std` equivalent of
`setpgid(0, 0)` in a `pre_exec` hook, so no `unsafe` is involved at spawn time.

## Ownership chain

Ownership is linear and single: `tokio::process::Command` configures →
`spawn()` attaches containment and returns `SpawnedSidecar { child,
containment }` → `start_instance` supervises that value → `reap_instance` →
`terminate_sidecar(child, containment)` consumes both together. There is no
other holder of the containment: `Bridge` (`mod.rs`) never touches a `Child`,
and the Unix `pgid` is stored as an `Option` that is *taken* on close, making
teardown idempotent by construction. On Windows the raw `HANDLE` lives only in
`JobHandle { raw: Option<HANDLE> }`; `Drop` closes whatever `close()` did not.
Every handle/FD opened during establishment is closed on **every** path,
including partial-failure paths (a job created but not assigned is closed
before the error is returned).

## Teardown escalation (`terminate_sidecar`)

1. **Graceful EOF wait** (1 s). Closing the writer channel sends stdin EOF,
   which the sidecar treats as "exit now" (see `docs/bridge/protocol.md`).
2. **Containment SIGTERM** (Unix only; Job Objects have no cooperative signal)
   and another 1 s wait.
3. **Forced termination** — Unix `killpg(SIGKILL)`, Windows
   `TerminateJobObject` — then a bounded reap of the leader (5 s). A reap
   timeout logs a warning only; `kill_on_drop` finishes it in the background.
4. **Containment close** — always executed, even after a clean exit: Unix does
   one final `SIGKILL` group sweep (descendants can outlive the leader);
   Windows closes the job handle, which kills any member still inside.

Worst case for one teardown is ~7 s, all of it awaited *before* the next
restart spawn, so the old group and the new one never overlap. Every failure is
a typed `BridgeError` (`io`-wrapped OS causes, no paths or command lines in the
message); the sequence continues through remaining steps instead of returning
early. `ESRCH` on Unix and `ERROR_NOT_FOUND` (1168, empty job) on Windows are
treated as success — that is the already-dead case. Nothing in this path can
panic.

Structured lifecycle log lines (safe by construction — pid + fixed text only):
`sidecar spawned (pid n)`, `containment established for pid n: <mechanism>`,
`containment setup failed for the just-spawned sidecar — terminating the
uncontained child`, `graceful termination requested for sidecar pid n`,
`forced termination performed for sidecar pid n`, `descendant cleanup
attempted for sidecar group n` (info when the final sweep hit live processes,
debug when the group was already empty), `containment cleanup failed for pid n`.

## Idempotence and safety rules

- Teardown of an already-exited child is a clean no-op (grace wait sees the
  exit, signals answer `ESRCH`/1168 → success).
- A second `terminate_sidecar` call finds `pgid` taken and the job handle
  closed: `Ok(())` without signalling anything.
- Containment **establishment failure** never yields an uncontained sidecar:
  the child is killed (`start_kill`) and dropped (`kill_on_drop` reaps), and
  discovery moves to the next interpreter candidate.
- Signals are only ever sent to groups whose pgid **equals a child pid this
  supervisor created**, and only to job handles this process created —
  unrelated-process collateral is impossible by construction. No process-name
  matching, no `taskkill /IM`, no `pkill`, anywhere.

## Known limitations (documented, accepted)

- **`PR_SET_PDEATHSIG` is deliberately not used.** It fires when the parent
  *thread* that forked exits, and tokio reaps idle worker threads — healthy
  sidecars would be killed mid-session. Parent death on Unix is instead covered
  by the pipe: the kernel closes sidecar stdin when the desktop process dies
  (even under `SIGKILL`), and the sidecar's EOF handler shuts it down. If the
  parent dies while a *descendant* holds a non-EOF-coupled state, that
  descendant is only swept on the next supervisor teardown; there is no
  daemon-side watchdog. (Windows does not have this gap: kill-on-close fires
  when the job handle's last reference drops with the parent process.)
- **Kill race at quit time:** `Bridge::kill()` drops the writer sender; if the
  supervisor task has just been aborted (app exits between reader EOF and
  `reap_instance`), containment close happens via `Drop` on process teardown
  (Windows: job handle closes → kill-on-close; Unix: `kill_on_drop` + EOF).
  Awaiting the containment close inside `Bridge::kill()` is a possible follow-up
  for `mod.rs` — out of SEC-09 scope, see the audit's coordination list.
- A truly stuck sidecar whose *stdout never closes* keeps the reader task
  waiting; the heartbeat watchdog marks it `Hung` after 15 s of silence and the
  instance is then torn down through the same escalation path (pre-existing
  SEC-01..08 behaviour, preserved).

## Testing the lifecycle

Bounded, PID-based tests live in `mod tests` of `process.rs` and spawn only
`/bin/sh` (Unix) or `powershell.exe` (Windows) helpers — never the app's
interpreter, never anything by name, and they only signal pids they created:

| Test | Platform | Asserts |
| --- | --- | --- |
| `unix_teardown_terminates_child_and_descendants` | Unix | leader leads its group; descendant inherits it; teardown reaps leader and sweeps the descendant |
| `unix_teardown_is_idempotent_and_safe_after_natural_exit` | Unix | exited child + double teardown both `Ok` |
| `unix_containment_setup_failure_does_not_leave_an_orphan` | Unix | discarded uncontained child dies promptly |
| `unix_restart_tears_down_old_group_before_new_instance` | Unix | old instance fully dead before the new one leads a fresh group |
| `windows_job_object_contains_child_and_descendants` | Windows | child **and** its grandchild are `IsProcessInJob`; teardown kills both |
| `windows_teardown_is_idempotent_and_safe_after_natural_exit` | Windows | same idempotence contract for the job path |
| `windows_containment_setup_reports_typed_error_for_dead_pid` | Windows | establishment failure is a typed error, never a panic |

```bash
cd apps/desktop/src-tauri
cargo test --lib bridge::process   # Unix: the 4 group tests run for real
cargo test --lib bridge::process -- --nocapture   # watch the lifecycle log lines
```

On Windows the lifecycle tests **compile and lint** in CI
(`clippy --all-targets`, `cargo check --all-targets`) but CI skips
`cargo test --lib` for the whole crate (pre-existing tauri-winres/ComCtl32
link issue, tracked upstream as tauri-apps/tauri#13419; see
`apps/desktop/.github/workflows/desktop-ci.yml`). Run them on a Windows dev
machine with `cargo test --lib` — the desktop CI job documents the same
workaround. Nothing in the lifecycle is Linux-only, so there is no platform
whose assertions CI silently drops.
