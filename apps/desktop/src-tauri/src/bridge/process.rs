//! Sidecar process supervision.
//!
//! Spawns the Python sidecar (`<python> -m dream.bridge`), wires its stdin/stdout
//! to the dispatcher, monitors it with a heartbeat, and restarts it on crash
//! with backoff (per the failure-recovery table in the master prompt):
//!
//! - max 3 automatic restarts in a row, 2 s / 5 s / 10 s backoff; the
//!   counter resets once an instance has stayed healthy for a while, and a
//!   manual `bridge_restart` always gets a fresh attempt without backoff;
//! - heartbeat ping every 5 s; no traffic for 15 s ⇒ hang ⇒ kill ⇒ restart;
//! - on restart, every in-flight request is rejected with `INTERNAL_ERROR`
//!   (tagged `data.kind = "transport"`), exactly once;
//! - the supervisor task lives for the whole app: after the retries are spent
//!   (`Disconnected`) it waits for the next manual restart instead of exiting.
//!
//! State transitions are written to the shared [`SharedState`] and emitted as
//! `bridge://state` events so the frontend status indicator stays in sync.
//!
//! ## Containment (SEC-09)
//!
//! The sidecar can spawn descendants (tools, subprocesses), so a plain
//! `Child::kill()` would orphan them. Every instance therefore runs inside a
//! platform containment owned by [`SidecarContainment`]:
//!
//! - **Windows**: a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. The
//!   kernel keeps the whole tree alive-or-dead with the job handle: closing it
//!   — normal teardown *or* an abrupt parent exit — terminates every member.
//! - **Unix-like**: a dedicated process group (`process_group(0)`, applied in
//!   the child before `exec` — the safe std equivalent of `setpgid(0, 0)`),
//!   so teardown can signal the leader *and its descendants* via `killpg`.
//!   Parent death is covered by the pipe itself: the kernel closes the sidecar's
//!   stdin when the desktop process dies (even under `SIGKILL`), and the
//!   sidecar's EOF shutdown terminates the leader. `PR_SET_PDEATHSIG` is
//!   deliberately **not** used — it fires on parent *thread* exit, which
//!   conflicts with tokio's idle-worker reaping (see the lifecycle doc).
//!
//! See `docs/dev/how-to/sidecar-lifecycle.md` for the full lifecycle contract.

use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde_json::json;
use tauri::{Emitter, Runtime};
use tokio::io::{AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdout};
use tokio::sync::{mpsc, Mutex, Notify};

use crate::bridge::dispatcher::Dispatcher;
use crate::bridge::framing::{self, code, ParsedMessage, RESERVED_ID_FLOOR};
use crate::bridge::reader::{Frame, FrameReader};
use crate::bridge::state::{ConnectionState, SharedState};
use crate::error::BridgeError;

/// How the sidecar binary is launched.
#[derive(Clone, Debug)]
pub struct SidecarConfig {
    /// Interpreter candidates, tried in order until one starts.
    /// `DREAM_SIDECAR_PYTHON` is a hard override: when set, it is the only
    /// candidate. Otherwise the order is the bundled interpreter (if any),
    /// then `python`, `py` (the Windows launcher), `python3`.
    pub python: Vec<String>,
    /// Module to run (default `dream.bridge`, override via `DREAM_SIDECAR_MODULE`).
    pub module: String,
    /// Subset of `python` that point at the bundled CPython runtime shipped
    /// next to the app (Windows only). Spawning one of these isolates the
    /// interpreter from user site-packages (see [`SidecarConfig::is_bundled`]).
    bundled: Vec<String>,
    /// Writable directory used as the sidecar cwd so relative `data/` files
    /// never land under Program Files. `None` leaves the inherited cwd
    /// (tests that never spawn).
    data_root: Option<PathBuf>,
    /// Supervisor timings. Production uses [`SupervisorTiming::default`];
    /// tests shrink them so lifecycle paths run in milliseconds.
    pub timing: SupervisorTiming,
}

/// Heartbeat, backoff and stability windows used by the supervisor.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SupervisorTiming {
    /// Interval between `health.check` pings.
    pub heartbeat_interval: Duration,
    /// Silence on stdout longer than this marks the instance hung.
    pub heartbeat_timeout: Duration,
    /// Backoff before each automatic restart; its length is the retry budget.
    pub restart_backoff: Vec<Duration>,
    /// An instance that stays up this long after the handshake resets the
    /// retry budget, so a crash a day apart never exhausts it.
    pub stable_after: Duration,
}

impl Default for SupervisorTiming {
    fn default() -> Self {
        Self {
            heartbeat_interval: HEARTBEAT_INTERVAL,
            heartbeat_timeout: HEARTBEAT_TIMEOUT,
            restart_backoff: RESTART_BACKOFF_SECS
                .iter()
                .map(|secs| Duration::from_secs(*secs))
                .collect(),
            stable_after: STABLE_AFTER,
        }
    }
}

/// Interpreter candidates when `DREAM_SIDECAR_PYTHON` is unset. On Windows the
/// interpreter is usually `python` or the `py` launcher; `python3` covers POSIX
/// systems where `python` is not installed.
const DEFAULT_PYTHON_CANDIDATES: [&str; 3] = ["python", "py", "python3"];

impl SidecarConfig {
    /// Build the config from an environment reader. Tests inject a fake reader
    /// so no test mutates the process environment.
    fn from_env(getenv: &dyn Fn(&str) -> Option<String>) -> Self {
        let python = match getenv("DREAM_SIDECAR_PYTHON") {
            Some(explicit) if !explicit.trim().is_empty() => vec![explicit],
            _ => DEFAULT_PYTHON_CANDIDATES
                .map(|candidate| candidate.to_string())
                .to_vec(),
        };
        let module = getenv("DREAM_SIDECAR_MODULE")
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| "dream.bridge".to_string());
        Self {
            python,
            module,
            bundled: Vec::new(),
            data_root: None,
            timing: SupervisorTiming::default(),
        }
    }

    /// Record the writable data root used as the sidecar working directory.
    pub fn set_data_root(&mut self, root: PathBuf) {
        self.data_root = Some(root);
    }

    /// Interpreter candidates to try, in order.
    pub fn candidates(&self) -> &[String] {
        &self.python
    }

    /// Prepend a bundled CPython interpreter ahead of the PATH candidates.
    ///
    /// `is_override` is true when `DREAM_SIDECAR_PYTHON` was set: in that case
    /// the explicit interpreter stays the only candidate and nothing is
    /// prepended. Bundled paths that exist on disk are also recorded so
    /// [`spawn`] can isolate them from user site-packages.
    pub fn prepend_bundled(
        &mut self,
        exe_dir: &Path,
        resource_dir: Option<&Path>,
        is_override: bool,
    ) {
        let bundled: Vec<String> = bundled_interpreter_paths(exe_dir, resource_dir)
            .into_iter()
            .map(|path| path.to_string_lossy().into_owned())
            .collect();
        // Always remember which paths are the installer runtime, even when
        // `DREAM_SIDECAR_PYTHON` is a hard override. An override that *is*
        // the bundled exe must still get PYTHONNOUSERSITE isolation.
        self.bundled = bundled.clone();
        if is_override || bundled.is_empty() {
            return;
        }
        let mut merged = bundled.clone();
        merged.extend(self.python.iter().cloned());
        self.python = merged;
    }

    /// Whether `exe` is a bundled (embedded) interpreter, so the spawner can
    /// isolate it from a host-level user install.
    fn is_bundled(&self, exe: &str) -> bool {
        self.bundled.iter().any(|bundled| bundled.as_str() == exe)
    }
}

impl Default for SidecarConfig {
    fn default() -> Self {
        Self::from_env(&|key| std::env::var(key).ok())
    }
}

/// Absolute paths of a bundled CPython interpreter, in priority order.
///
/// The Windows installer embeds a CPython runtime next to the app; the
/// supervisor prefers it over the PATH fallback so a stock install never needs
/// `DREAM_SIDECAR_PYTHON`. Candidates are probed in this order (every path
/// that exists as a file wins, first match first):
///
/// 1. `{resource_dir}/python/python.exe` — the standard Tauri resource layout;
/// 2. `{resource_dir}/python.exe` — when the resource dir *is* the python dir;
/// 3. `{exe_dir}/resources/python/python.exe` — the measured NSIS layout
///    (`C:\Program Files\Dream\dream-desktop.exe` plus
///    `resources\python\python.exe`);
/// 4. `{exe_dir}/python/python.exe` — python next to the exe itself;
/// 5. the same two layouts relative to the parent of `exe_dir`, for installs
///    where the binary lives in a subfolder of the install root.
///
/// Every candidate that does not resolve to an existing file is logged with
/// the reason it was skipped, so a stock-install miss is diagnosable from the
/// app log alone. Only paths that exist on disk are returned (duplicates such
/// as `resource_dir == exe_dir/resources` are collapsed). On POSIX there is no
/// bundled interpreter (Linux/macOS still use the system Python), so no
/// `python.exe` file exists next to the binary and this naturally returns an
/// empty list.
pub(crate) fn bundled_interpreter_paths(
    exe_dir: &Path,
    resource_dir: Option<&Path>,
) -> Vec<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Some(dir) = resource_dir {
        // When the resource dir already *is* the python folder, the
        // interpreter sits directly inside it; otherwise it lives in a
        // `python` subfolder. A plain if-else binding (no nested if) keeps
        // clippy -D warnings clean.
        let python_dir = if dir
            .file_name()
            .is_some_and(|name| name.to_string_lossy().eq_ignore_ascii_case("python"))
        {
            dir.to_path_buf()
        } else {
            dir.join("python")
        };
        candidates.push(python_dir.join("python.exe"));
    }
    candidates.push(exe_dir.join("resources").join("python").join("python.exe"));
    candidates.push(exe_dir.join("python").join("python.exe"));
    // The executable may live in a subfolder of the install root (e.g.
    // `C:\Program Files\Dream\bin\dream-desktop.exe`); probe the install-root
    // layouts one level up as well.
    if let Some(parent) = exe_dir.parent() {
        candidates.push(parent.join("resources").join("python").join("python.exe"));
        candidates.push(parent.join("python").join("python.exe"));
    }

    let mut seen = std::collections::HashSet::new();
    let mut existing: Vec<PathBuf> = Vec::new();
    for candidate in candidates {
        if !candidate.is_file() {
            log::warn!(
                "bridge: bundled interpreter candidate {} skipped — not a file on disk",
                candidate.display()
            );
            continue;
        }
        // `seen.insert` reports whether the path is a new candidate; a
        // duplicate (e.g. resource_dir == exe_dir/resources) is dropped
        // silently, exactly like the original nested-if version.
        if seen.insert(candidate.clone()) {
            log::info!(
                "bridge: bundled interpreter candidate: {}",
                candidate.display()
            );
            existing.push(candidate);
        }
    }
    existing
}

/// Writable root for sidecar relative paths (`data/dream.db`, providers).
///
/// Owner-measured: a stock Start Menu launch inherits
/// `C:\Program Files\Dream` as cwd, so `data/` cannot be created and the
/// sidecar exits before `DREAM-PROTOCOL`. Prefer, in order:
/// `DREAM_HOME`, `%LOCALAPPDATA%\Dream`, `$XDG_DATA_HOME/Dream`,
/// `$HOME/.local/share/Dream`, then the process temp dir.
pub(crate) fn sidecar_data_root() -> PathBuf {
    if let Ok(raw) = std::env::var("DREAM_HOME") {
        let trimmed = raw.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        let trimmed = local.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed).join("Dream");
        }
    }
    if let Ok(xdg) = std::env::var("XDG_DATA_HOME") {
        let trimmed = xdg.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed).join("Dream");
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let trimmed = home.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed)
                .join(".local")
                .join("share")
                .join("Dream");
        }
    }
    std::env::temp_dir().join("Dream")
}

/// Create `{root}` and `{root}/data`, then return `root`.
pub(crate) fn ensure_sidecar_data_root(root: &Path) -> std::result::Result<PathBuf, BridgeError> {
    std::fs::create_dir_all(root.join("data"))
        .map_err(|err| BridgeError::io("create sidecar data root", err))?;
    log::info!("bridge: sidecar data root {}", root.display());
    Ok(root.to_path_buf())
}

/// Environment applied to every sidecar spawn.
///
/// `PYTHONUTF8` / `PYTHONIOENCODING` are **always** set: Persian chat
/// (`سلام`) raised `charmap` on Windows when `DREAM_SIDECAR_PYTHON`
/// skipped the bundled env block. `PYTHONNOUSERSITE` stays bundled-only.
pub(crate) fn sidecar_python_env(is_bundled: bool) -> Vec<(&'static str, &'static str)> {
    let mut env = vec![("PYTHONUTF8", "1"), ("PYTHONIOENCODING", "utf-8")];
    if is_bundled {
        env.push(("PYTHONNOUSERSITE", "1"));
    }
    env
}

/// Backoff schedule (seconds) between restart attempts. Three attempts max.
const RESTART_BACKOFF_SECS: [u64; 3] = [2, 5, 10];
const HEARTBEAT_INTERVAL: Duration = Duration::from_secs(5);
const HEARTBEAT_TIMEOUT: Duration = Duration::from_secs(15);
/// An instance alive this long after its handshake counts as healthy and
/// resets the automatic-restart budget (SEC-10).
const STABLE_AFTER: Duration = Duration::from_secs(30);
/// First heartbeat id. Lives in the reserved band (`>= RESERVED_ID_FLOOR`)
/// so it can never collide with a frontend id (SEC-10 request ownership).
const HEARTBEAT_ID_BASE: u64 = RESERVED_ID_FLOOR;
const STATE_EVENT: &str = "bridge://state";

/// How long the sidecar gets to exit from the stdin-EOF graceful shutdown it
/// is designed for before the containment is asked to terminate (SEC-09).
/// A healthy sidecar exits from EOF within milliseconds; the window only ever
/// delays a wedged instance, never a normal restart (the exit itself resolves
/// the wait early).
const SIDECAR_GRACEFUL_EXIT: Duration = Duration::from_secs(1);
/// Grace period after the containment-wide graceful termination request
/// (SIGTERM to the whole Unix process group; the job-close/terminate sweep on
/// Windows has no cooperative signal, so the grace windows are identical).
const SIDECAR_TERM_GRACE: Duration = Duration::from_secs(1);
/// Bounded final reap for a forcibly terminated leader. If this expires the
/// containment is still closed (which sweeps everything) and the child's
/// `kill_on_drop` safety net finishes the reap in the background — teardown
/// never blocks forever and never leaks.
const SIDECAR_REAP_TIMEOUT: Duration = Duration::from_secs(5);

/// Control channel from [`Bridge`](crate::bridge::Bridge) to the supervisor.
///
/// A manual restart is a level (`requested`) plus a wake-up (`wake`): the flag
/// is remembered until the supervisor consumes it, so a request that arrives
/// while an instance is still being torn down, or while the supervisor is
/// sleeping in backoff or parked in `Disconnected`, is never lost — and a
/// stale wake-up can never be mistaken for a request.
#[derive(Default)]
pub struct SupervisorControl {
    requested: std::sync::atomic::AtomicBool,
    wake: Notify,
}

impl SupervisorControl {
    /// Ask the supervisor for a fresh instance (`bridge_restart`, UI reconnect).
    pub fn request_restart(&self) {
        self.requested
            .store(true, std::sync::atomic::Ordering::Release);
        self.wake.notify_one();
    }

    /// Consume a pending request, if any.
    fn take_restart_request(&self) -> bool {
        self.requested
            .swap(false, std::sync::atomic::Ordering::AcqRel)
    }

    /// Park until a restart is requested (and consume it).
    async fn wait_for_restart(&self) {
        loop {
            if self.take_restart_request() {
                return;
            }
            self.wake.notified().await;
        }
    }
}

/// Run the supervisor loop for the lifetime of the app.
///
/// One supervisor task exists per [`Bridge`](crate::bridge::Bridge). It never
/// returns on its own: when the automatic retry budget is spent (or the
/// bridge was killed) it parks in `Disconnected` and waits for the next manual
/// restart, which resets the budget and skips the backoff. This guarantees
/// there is never more than one reader/writer/heartbeat set alive and that a
/// manual reconnect always works, no matter how many crashes came before.
pub async fn run_supervisor<R: Runtime>(
    app: tauri::AppHandle<R>,
    state: Arc<SharedState>,
    dispatcher: Arc<Mutex<Dispatcher>>,
    writer_tx: Arc<Mutex<Option<mpsc::Sender<String>>>>,
    config: SidecarConfig,
    killed: Arc<std::sync::atomic::AtomicBool>,
    control: Arc<SupervisorControl>,
) {
    let mut attempt = 0usize;
    loop {
        if killed.load(std::sync::atomic::Ordering::Acquire) {
            set_state(&app, &state, ConnectionState::Disconnected);
            control.wait_for_restart().await;
            attempt = 0;
            continue;
        }
        set_state(&app, &state, ConnectionState::Connecting);

        let started = Instant::now();
        let ended = start_instance(&app, &state, &dispatcher, &writer_tx, &config).await;
        // Reject everything that was in flight when the instance died —
        // exactly once (the dispatcher drops each entry as it fails it).
        let rejected = reject_pending(&dispatcher).await;
        if rejected > 0 {
            log::info!("bridge: rejected {rejected} in-flight request(s) after instance end");
        }
        let (InstanceEnd::Exited { reached_ready } | InstanceEnd::Hung { reached_ready }) = ended;
        // A handshaken instance that stayed up long enough proves the
        // interpreter works: start the budget afresh so sporadic crashes hours
        // apart never add up to a permanent disconnect.
        if reached_ready && started.elapsed() >= config.timing.stable_after {
            attempt = 0;
        }

        if killed.load(std::sync::atomic::Ordering::Acquire) {
            continue; // parks above until the next manual restart
        }
        if control.take_restart_request() {
            // The user asked for it: respawn now, no backoff, fresh budget.
            attempt = 0;
            continue;
        }
        let Some(backoff) = config.timing.restart_backoff.get(attempt).copied() else {
            // Budget spent: park until a manual restart, then start over.
            set_state(&app, &state, ConnectionState::Disconnected);
            control.wait_for_restart().await;
            attempt = 0;
            continue;
        };
        set_state(&app, &state, ConnectionState::Restarting);
        attempt += 1;
        tokio::select! {
            () = tokio::time::sleep(backoff) => {}
            () = control.wait_for_restart() => {
                // A manual restart during backoff: respawn now, fresh budget.
                attempt = 0;
            }
        }
    }
}

/// How one sidecar instance's lifetime ended. `reached_ready` records whether
/// the protocol handshake had completed.
#[derive(Debug, Clone, Copy)]
enum InstanceEnd {
    /// The process exited, its stdout closed, or its stdin was closed by a
    /// manual restart/kill (the supervisor checks the control flag).
    Exited { reached_ready: bool },
    /// The heartbeat timed out and the process was killed.
    Hung { reached_ready: bool },
}

/// Log an I/O failure without embedding OS paths (see [`BridgeError::io`]).
fn warn_bridge_io(context: &str, operation: &'static str, err: std::io::Error) {
    log::warn!("bridge: {context}: {}", BridgeError::io(operation, err));
}

/// Kill a child we cannot use as a sidecar *and* could not contain.
///
/// The process must not keep running uncontained (it could spawn descendants
/// nothing would be able to sweep). `start_kill` is synchronous; the child's
/// `kill_on_drop(true)` setup reaps it in the background once the value drops,
/// so this helper never blocks and never leaves an orphan behind.
fn discard_uncontained_child(child: &mut Child) {
    if let Err(err) = child.start_kill() {
        // `start_kill` on an already-exited child succeeds, so an error here
        // is a real (rare) platform failure — logged, never a panic.
        warn_bridge_io(
            "killing an uncontained sidecar child failed",
            "kill sidecar",
            err,
        );
    }
}

/// Drain request lines onto sidecar stdin until the channel closes, then
/// close stdin (EOF ⇒ graceful sidecar shutdown) and signal `done`.
async fn write_stdin_loop(
    mut stdin: tokio::process::ChildStdin,
    mut rx: mpsc::Receiver<String>,
    done: Arc<Notify>,
) {
    let _signal_on_exit = NotifyOnDrop(done);
    while let Some(line) = rx.recv().await {
        if let Err(err) = stdin.write_all(line.as_bytes()).await {
            warn_bridge_io(
                "writing to sidecar stdin failed",
                "write sidecar stdin",
                err,
            );
            break;
        }
        if let Err(err) = stdin.write_all(b"\n").await {
            warn_bridge_io(
                "writing newline to sidecar stdin failed",
                "write sidecar stdin newline",
                err,
            );
            break;
        }
        if let Err(err) = stdin.flush().await {
            warn_bridge_io("flushing sidecar stdin failed", "flush sidecar stdin", err);
            break;
        }
    }
    // Closing stdin signals EOF to the sidecar → graceful shutdown.
    if let Err(err) = stdin.shutdown().await {
        warn_bridge_io(
            "shutting down sidecar stdin failed",
            "shutdown sidecar stdin",
            err,
        );
    }
}

/// Fires its `Notify` when dropped — also when the owning task is aborted —
/// so a waiter can never miss the writer's end.
struct NotifyOnDrop(Arc<Notify>);

impl Drop for NotifyOnDrop {
    fn drop(&mut self) {
        self.0.notify_one();
    }
}

/// Wait for `child` to exit, bounded by `limit`. `Ok(true)` means "reaped",
/// `Ok(false)` means "still running when the window closed".
async fn wait_within(child: &mut Child, limit: Duration) -> std::result::Result<bool, BridgeError> {
    match tokio::time::timeout(limit, child.wait()).await {
        Ok(Ok(_status)) => Ok(true),
        // `wait` failing means the handle is gone (already reaped elsewhere or
        // a platform fault) — surface it typed, never panic.
        Ok(Err(err)) => Err(BridgeError::io("wait for sidecar", err)),
        Err(_elapsed) => Ok(false),
    }
}

/// Terminate one sidecar instance and everything inside its containment.
///
/// Escalation sequence (SEC-09 lifecycle contract):
///
/// 1. grace window for the stdin-EOF graceful shutdown the sidecar implements;
/// 2. graceful request to the containment (Unix: `SIGTERM` to the whole
///    process group; Windows: nothing to signal — the EOF path already asked)
///    plus a second bounded wait;
/// 3. forced termination of the containment (Unix: `SIGKILL` to the group;
///    Windows: `TerminateJobObject`), then a final bounded reap of the leader;
/// 4. containment teardown (Unix: one last `SIGKILL` group sweep for
///    descendants that outlived the leader; Windows: closing the job handle,
///    which the kernel also performs when the process dies).
///
/// Idempotent: safe to call more than once and safe when the child already
/// exited — both cases complete without spurious errors. No locks are held
/// across the waits (the caller clears the writer channel first).
pub(crate) async fn terminate_sidecar(
    child: &mut Child,
    containment: &mut SidecarContainment,
) -> std::result::Result<(), BridgeError> {
    let mut failure: Option<BridgeError> = None;
    let leader = containment.leader_pid;

    match wait_within(child, SIDECAR_GRACEFUL_EXIT).await {
        Ok(true) => {
            log::debug!("bridge: sidecar pid {leader} exited gracefully on stdin EOF");
        }
        Ok(false) => {
            if let Err(err) = containment.request_graceful_termination() {
                failure.get_or_insert(err);
            }
            log::info!("bridge: graceful termination requested for sidecar pid {leader}");
            match wait_within(child, SIDECAR_TERM_GRACE).await {
                Ok(true) => {
                    log::debug!("bridge: sidecar pid {leader} exited after containment SIGTERM");
                }
                Ok(false) => {
                    log::warn!("bridge: forced termination performed for sidecar pid {leader}");
                    if let Err(err) = containment.terminate_forced() {
                        failure.get_or_insert(err);
                    }
                    match wait_within(child, SIDECAR_REAP_TIMEOUT).await {
                        Ok(true) => {}
                        Ok(false) => log::warn!(
                            "bridge: sidecar pid {leader} reap timed out — the containment \
                             teardown below and the child's drop-time kill finish the job"
                        ),
                        Err(err) => {
                            failure.get_or_insert(err);
                        }
                    }
                }
                Err(err) => {
                    failure.get_or_insert(err);
                }
            }
        }
        Err(err) => {
            failure.get_or_insert(err);
        }
    }

    // Containment teardown runs on every path, including the ones above that
    // already saw a clean exit: descendants can outlive the leader.
    if let Err(err) = containment.close() {
        log::warn!("bridge: containment cleanup failed for pid {leader}: {err}");
    }

    match failure {
        Some(err) => Err(err),
        None => Ok(()),
    }
}

/// Drop the stdin writer and terminate the instance (process tree) after the
/// reader loop ends. Containment teardown makes this also sweep any
/// descendants the sidecar spawned.
async fn reap_instance(
    instance: &mut SpawnedSidecar,
    writer_tx: &Arc<Mutex<Option<mpsc::Sender<String>>>>,
) {
    {
        let mut guard = writer_tx.lock().await;
        *guard = None;
    }
    if let Err(err) = terminate_sidecar(&mut instance.child, &mut instance.containment).await {
        // `terminate_sidecar` already swept the containment; the supervisor
        // restarts regardless, so this is a diagnostic, never a panic.
        log::warn!("bridge: sidecar teardown did not complete cleanly: {err}");
    }
}

/// Spawn one sidecar instance and supervise it until it ends or hangs.
///
/// Discovery: every interpreter candidate is tried in order. A candidate that
/// cannot spawn at all, or that exits before completing the protocol handshake
/// (e.g. a Windows Store `python.exe` stub, a Python 2 interpreter, or a Python
/// without `dream` installed), is skipped in favour of the next one. Only an
/// instance that completed the handshake counts as a real sidecar, so its
/// death goes through the restart/backoff path.
async fn start_instance<R: Runtime>(
    app: &tauri::AppHandle<R>,
    state: &Arc<SharedState>,
    dispatcher: &Arc<Mutex<Dispatcher>>,
    writer_tx: &Arc<Mutex<Option<mpsc::Sender<String>>>>,
    config: &SidecarConfig,
) -> InstanceEnd {
    let mut remaining: &[String] = config.candidates();
    loop {
        let Some((index, exe, mut instance)) = spawn_first(remaining, |exe| spawn(config, exe))
        else {
            // No candidate could even be launched. Leave the state to the
            // supervisor (it goes Disconnected after the retries) and say why
            // in both languages.
            log_python_required(config.candidates());
            return InstanceEnd::Exited {
                reached_ready: false,
            };
        };
        // Drop the used candidates so the next discovery round resumes where
        // this one stopped.
        remaining = &remaining[index + 1..];

        let (stdin, stdout) = match take_piped_stdio(&mut instance.child) {
            Ok(pair) => pair,
            Err(err) => {
                log::error!("bridge: `{exe}` cannot be used as a sidecar: {err}");
                // The child is contained even though it is unusable as a
                // sidecar: tear the containment down (kills the child and any
                // descendants), never just drop it.
                if let Err(err) =
                    terminate_sidecar(&mut instance.child, &mut instance.containment).await
                {
                    log::warn!("bridge: teardown of unusable sidecar instance failed: {err}");
                }
                continue;
            }
        };

        // Writer task: drains the request channel and writes newline-framed
        // lines. `writer_gone` fires when the writer loop ends for any reason
        // (channel closed by `Bridge::restart`/`kill`, or a write failure), so
        // the reader can stop waiting on a peer that will never answer.
        let (tx, rx) = mpsc::channel::<String>(64);
        {
            let mut guard = writer_tx.lock().await;
            *guard = Some(tx);
        }
        let writer_gone = Arc::new(Notify::new());
        let writer =
            tauri::async_runtime::spawn(write_stdin_loop(stdin, rx, Arc::clone(&writer_gone)));

        let ended = supervise_reader(
            app,
            state,
            dispatcher,
            writer_tx,
            stdout,
            &config.timing,
            &writer_gone,
        )
        .await;

        writer.abort();
        // Runs the full containment teardown (see [`terminate_sidecar`]) and
        // completes *before* the supervisor's next spawn, so a restart never
        // overlaps the old process group / job object with the new one — and
        // no reader/writer/heartbeat task of the old instance is alive when
        // the new one starts.
        reap_instance(&mut instance, writer_tx).await;

        match ended {
            ReaderEnd::WriterClosed { reached_ready } => {
                // Manual restart/kill closed stdin, or stdin broke: either way
                // this instance is over; the supervisor decides what follows.
                log::info!("bridge: instance running under `{exe}` ended (stdin closed)");
                return InstanceEnd::Exited { reached_ready };
            }
            ReaderEnd::Hung { reached_ready } => {
                log::warn!("bridge: instance running under `{exe}` ended (heartbeat timeout)");
                return InstanceEnd::Hung { reached_ready };
            }
            ReaderEnd::Exited {
                reached_ready: true,
            } => {
                log::info!("bridge: instance running under `{exe}` ended (exit)");
                return InstanceEnd::Exited {
                    reached_ready: true,
                };
            }
            ReaderEnd::Exited {
                reached_ready: false,
            } => {}
        }
        log::warn!(
            "bridge: `{exe}` exited before the protocol handshake — trying the next interpreter"
        );
    }
}

/// Spawn the first interpreter candidate for which `probe` succeeds, returning
/// its index in `candidates`, its name, and the probed value. `probe` is a seam
/// so tests can fake the command order without spawning real processes.
fn spawn_first<'a, T, F>(candidates: &'a [String], mut probe: F) -> Option<(usize, &'a str, T)>
where
    F: FnMut(&'a str) -> std::result::Result<T, BridgeError>,
{
    for (index, candidate) in candidates.iter().enumerate() {
        match probe(candidate) {
            Ok(item) => return Some((index, candidate.as_str(), item)),
            Err(err) => log::warn!("bridge: failed to spawn `{candidate}`: {err}"),
        }
    }
    None
}

/// Take the piped stdin/stdout handles from a just-spawned child.
///
/// `Command` is constructed with `Stdio::piped()`, so both handles should be
/// present. If they are missing the child is unusable as a sidecar; return a
/// typed error instead of panicking so the supervisor can try the next
/// interpreter.
pub(crate) fn take_piped_stdio(
    child: &mut Child,
) -> std::result::Result<(tokio::process::ChildStdin, ChildStdout), BridgeError> {
    require_piped_stdio(child.stdin.take(), child.stdout.take())
}

/// Map optional stdio handles to a typed error. Extracted so the missing-pipe
/// path can be unit-tested without spawning a process.
pub(crate) fn require_piped_stdio<I, O>(
    stdin: Option<I>,
    stdout: Option<O>,
) -> std::result::Result<(I, O), BridgeError> {
    let stdin =
        stdin.ok_or_else(|| BridgeError::sidecar_crashed("sidecar spawned without piped stdin"))?;
    let stdout = stdout
        .ok_or_else(|| BridgeError::sidecar_crashed("sidecar spawned without piped stdout"))?;
    Ok((stdin, stdout))
}

/// Heartbeat watchdog: ping every `heartbeat_interval`; if stdout has been
/// silent for longer than `heartbeat_timeout`, fire `hung` and return.
///
/// The ping id lives in the reserved band ([`HEARTBEAT_ID_BASE`]) and is not
/// registered with the dispatcher: its response is dropped by design, but
/// reading it refreshes `last_activity`, proving the sidecar is responsive.
async fn heartbeat_watchdog(
    writer_tx: Arc<Mutex<Option<mpsc::Sender<String>>>>,
    last_activity: Arc<std::sync::Mutex<Instant>>,
    timing: SupervisorTiming,
    hung: Arc<Notify>,
) {
    let mut seq: u64 = HEARTBEAT_ID_BASE;
    loop {
        tokio::time::sleep(timing.heartbeat_interval).await;
        // Clone the sender out of the guard before awaiting the send.
        let tx = writer_tx.lock().await.as_ref().cloned();
        if let Some(tx) = tx {
            let line = framing::request_line(seq, "health.check", &json!({}));
            // A full channel means the writer is already backed up; the
            // liveness check still works because *any* stdout traffic counts.
            let _ = tx.try_send(line);
            seq = seq.wrapping_add(1).max(HEARTBEAT_ID_BASE);
        }
        if last_activity_elapsed(&last_activity) > timing.heartbeat_timeout {
            hung.notify_one();
            return;
        }
    }
}

/// Elapsed time since the last stdout activity. The lock is a plain
/// `std::sync::Mutex` held for a single `Instant` copy — never across an
/// await — so it cannot deadlock the reader or the watchdog.
fn last_activity_elapsed(last_activity: &std::sync::Mutex<Instant>) -> Duration {
    match last_activity.lock() {
        Ok(guard) => guard.elapsed(),
        // A poisoned lock only means a panic elsewhere; the Instant is still
        // valid. Treat as "just now" so a poisoned lock cannot fake a hang.
        Err(_) => Duration::ZERO,
    }
}

fn touch_last_activity(last_activity: &std::sync::Mutex<Instant>) {
    if let Ok(mut guard) = last_activity.lock() {
        *guard = Instant::now();
    }
}

/// Outcome of routing one stdout line.
enum LineOutcome {
    /// Keep reading.
    Continue,
    /// The sidecar announced a protocol this shell cannot speak: treat the
    /// instance as unusable (never `Ready`).
    UnsupportedProtocol,
}

/// Route one stdout line: handshake, JSON-RPC response, or stream chunk.
async fn handle_stdout_line<R: Runtime>(
    app: &tauri::AppHandle<R>,
    state: &Arc<SharedState>,
    dispatcher: &Arc<Mutex<Dispatcher>>,
    line: &str,
    reached_ready: &mut bool,
) -> LineOutcome {
    if framing::is_protocol_header(line) {
        return match framing::parse_header(line) {
            Ok(version) => {
                log::info!(
                    "bridge: sidecar speaks protocol {}.{}",
                    version.major,
                    version.minor
                );
                set_state(app, state, ConnectionState::Ready);
                *reached_ready = true;
                LineOutcome::Continue
            }
            Err(err) => {
                log::error!("bridge: refusing sidecar handshake: {err}");
                log::error!(
                    "bridge: نسخهٔ پروتکل موتور Dream با این نسخهٔ برنامه سازگار نیست — \
                     برنامه و بستهٔ dream را هم‌زمان به‌روزرسانی کنید."
                );
                LineOutcome::UnsupportedProtocol
            }
        };
    }

    match framing::parse(line) {
        Ok(ParsedMessage::Response { id, outcome }) => {
            if id >= RESERVED_ID_FLOOR {
                // Heartbeat reply: liveness was already recorded by the reader.
                return LineOutcome::Continue;
            }
            if !dispatcher.lock().await.resolve(id, outcome) {
                // Unknown or late id (already resolved, cancelled, or from a
                // request that was rejected on restart). Dropped by design —
                // it can never reach another request's channels.
                log::debug!("bridge: dropping response for unknown request id");
            }
        }
        Ok(ParsedMessage::Notification { method, params }) => {
            if method == "stream.chunk" {
                if let Some(id) = params.get("id").and_then(|v| v.as_u64()) {
                    if id < RESERVED_ID_FLOOR {
                        dispatcher.lock().await.route_stream(id, params);
                    }
                }
            }
        }
        Err(err) => {
            log::debug!("bridge: skipping unparseable line: {err}");
        }
    }
    LineOutcome::Continue
}

/// How the reader loop ended.
#[derive(Debug)]
enum ReaderEnd {
    Exited { reached_ready: bool },
    Hung { reached_ready: bool },
    WriterClosed { reached_ready: bool },
}

/// Read stdout until EOF, a heartbeat timeout, or the writer's end, routing
/// messages to the dispatcher.
///
/// The heartbeat used to only *record* a hang and rely on stdout closing —
/// which a wedged sidecar never does. The loop now `select!`s on the next
/// frame, the watchdog and the writer's end, so every exit path is bounded:
/// a hung instance is torn down by the caller within `heartbeat_timeout`
/// (+ one interval), and a manual restart takes effect immediately.
async fn supervise_reader<R: Runtime>(
    app: &tauri::AppHandle<R>,
    state: &Arc<SharedState>,
    dispatcher: &Arc<Mutex<Dispatcher>>,
    writer_tx: &Arc<Mutex<Option<mpsc::Sender<String>>>>,
    stdout: ChildStdout,
    timing: &SupervisorTiming,
    writer_gone: &Arc<Notify>,
) -> ReaderEnd {
    let mut reader = FrameReader::new(BufReader::new(stdout));
    let last_activity = Arc::new(std::sync::Mutex::new(Instant::now()));
    let hung = Arc::new(Notify::new());
    let mut reached_ready = false;

    let heartbeat = tauri::async_runtime::spawn(heartbeat_watchdog(
        Arc::clone(writer_tx),
        Arc::clone(&last_activity),
        timing.clone(),
        Arc::clone(&hung),
    ));

    // Reader loop. I/O failures end the instance (the supervisor restarts);
    // oversized, non-UTF-8 and malformed frames are skipped with context so a
    // single bad line cannot take the sidecar down.
    let end = loop {
        tokio::select! {
            frame = reader.next_frame() => match frame {
                Ok(Frame::Line(line)) => {
                    touch_last_activity(&last_activity);
                    match handle_stdout_line(app, state, dispatcher, &line, &mut reached_ready)
                        .await
                    {
                        LineOutcome::Continue => {}
                        LineOutcome::UnsupportedProtocol => {
                            break ReaderEnd::Exited { reached_ready: false };
                        }
                    }
                }
                Ok(Frame::Rejected(err)) => {
                    // Still traffic: the sidecar is alive, just misbehaving.
                    touch_last_activity(&last_activity);
                    log::warn!("bridge: dropped a sidecar frame: {err}");
                }
                Ok(Frame::Eof) => break ReaderEnd::Exited { reached_ready },
                Err(err) => {
                    warn_bridge_io("failed reading sidecar stdout", "read sidecar stdout", err);
                    break ReaderEnd::Exited { reached_ready };
                }
            },
            () = hung.notified() => {
                log::warn!("bridge: sidecar heartbeat timed out — restarting");
                break ReaderEnd::Hung { reached_ready };
            }
            () = writer_gone.notified() => {
                // The request channel was dropped (`Bridge::restart`/`kill`)
                // or stdin broke. Either way this instance is finished; do
                // not wait for the peer to notice EOF.
                break ReaderEnd::WriterClosed { reached_ready };
            }
        }
    };

    heartbeat.abort();
    end
}

/// Windows `CREATE_NO_WINDOW` (0x08000000): spawn the sidecar without a
/// visible console window, so discovery retries (and the Windows Store
/// `python` stub) do not flash a cmd window at the user.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

/// Windows `CREATE_SUSPENDED` (0x00000004): the new process is created with its
/// primary thread suspended and therefore executes *no* instruction — not even
/// loader code — until [`SidecarContainment::release_startup_suspension`]
/// resumes it.
///
/// This is what makes Job Object containment race-free (SEC-09): assignment to
/// the job happens while the child is frozen, so the child cannot have created
/// a single descendant before it is contained, and every instruction it ever
/// runs is executed as a job member.
#[cfg(windows)]
const CREATE_SUSPENDED: u32 = 0x0000_0004;

/// Creation flags for the sidecar process on the host platform.
///
/// On Windows we hide the console window (CREATE_NO_WINDOW) and start the child
/// suspended (CREATE_SUSPENDED) so containment can be attached before it runs;
/// on POSIX there is no such flag and the function returns 0 (the process group
/// is applied by the kernel inside the forked child, which is already
/// race-free). The POSIX variant is only compiled in test builds to avoid a
/// `dead_code` lint on the lib target.
///
/// The function is pure and cfg-gated so it can be unit-tested without spawning
/// a real process.
#[cfg(windows)]
pub(crate) fn sidecar_creation_flags() -> u32 {
    CREATE_NO_WINDOW | CREATE_SUSPENDED
}

/// POSIX stub — only compiled in test builds so `cargo clippy --lib` does not
/// report it as dead code.
#[cfg(all(not(windows), test))]
pub(crate) fn sidecar_creation_flags() -> u32 {
    0
}

/// One sidecar process together with the platform containment that owns its
/// whole process tree. The containment value moves with the child and must be
/// closed through [`SidecarContainment::close`] (or dropped, which does the same
/// on Windows) at teardown.
pub(crate) struct SpawnedSidecar {
    pub(crate) child: Child,
    pub(crate) containment: SidecarContainment,
}

/// Apply the pre-`exec` containment configuration to a command that is about
/// to become a containment leader.
///
/// On Unix this puts the child into its own process group (`pgid == child
/// pid`) before `exec`, so the group survives interpreter changes and covers
/// every descendant the sidecar later spawns. `process_group(0)` is the safe
/// std/tokio equivalent of calling `setpgid(0, 0)` in a `pre_exec` hook — no
/// `unsafe` needed and no parent/child race (the kernel applies it inside the
/// forked child, before `exec`).
///
/// On Windows a `Command` cannot pre-configure containment: the Job Object is
/// attached right after spawn by [`SidecarContainment::establish`].
pub(crate) fn configure_containment(cmd: &mut tokio::process::Command) {
    #[cfg(unix)]
    cmd.process_group(0);
    #[cfg(not(unix))]
    let _ = cmd;
}

/// Build the sidecar `Command` without spawning it.
///
/// Preserves the exact interpreter-selection, stdio, environment and working
/// directory semantics documented for [`spawn`]; the containment wiring is the
/// only addition (see [`configure_containment`]).
fn sidecar_command(config: &SidecarConfig, exe: &str) -> tokio::process::Command {
    // kill_on_drop prevents the sidecar from outliving the app on POSIX.
    let mut cmd = tokio::process::Command::new(exe);
    cmd.args(["-u", "-m", &config.module])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .kill_on_drop(true);
    // On Windows, discovery tries several interpreters (`python`, `py`,
    // `python3`) and each failed spawn can otherwise flash a console window.
    // Hide the console (CREATE_NO_WINDOW) and redirect stderr away from it; the
    // caller still logs spawn diagnostics via `log::warn!`/`log::error!`. POSIX
    // keeps the inherited stderr so local debugging keeps working.
    #[cfg(windows)]
    cmd.creation_flags(sidecar_creation_flags());
    #[cfg(windows)]
    cmd.stderr(Stdio::null());
    #[cfg(not(windows))]
    cmd.stderr(Stdio::inherit());
    // Containment: Unix leads a fresh process group from `exec` onwards.
    // (Note: `PR_SET_PDEATHSIG` is deliberately *not* used — it fires when the
    // parent *thread* exits, and tokio reaps idle worker threads, which would
    // kill healthy sidecars mid-run. Parent death is covered by stdin EOF —
    // the kernel closes the pipe when the process dies — plus the group sweep
    // in `terminate_sidecar`; see the lifecycle doc.)
    configure_containment(&mut cmd);
    if let Ok(path) = std::env::var("DREAM_PYTHONPATH") {
        cmd.env("PYTHONPATH", path);
    }
    for (key, value) in sidecar_python_env(config.is_bundled(exe)) {
        cmd.env(key, value);
    }
    if let Some(root) = &config.data_root {
        if let Err(err) = std::fs::create_dir_all(root.join("data")) {
            log::warn!(
                "bridge: could not create sidecar data directory: {}",
                BridgeError::io("create sidecar data root", err)
            );
        }
        cmd.current_dir(root);
    }
    cmd
}

/// Spawn the Python sidecar with piped stdio under interpreter `exe`, wrapped
/// in the platform containment (Windows: Job Object with kill-on-close;
/// Unix-like: dedicated process group).
///
/// If containment cannot be established, the child is killed and dropped
/// instead of being handed back uncontained — the supervisor must never run a
/// sidecar whose descendants nobody can sweep. Reaping of a discarded child is
/// completed by its `kill_on_drop` configuration, so this stays non-blocking.
///
/// Windows ordering is what makes containment race-free (SEC-09): the child is
/// created *suspended*, so it has executed no instruction and cannot have
/// created any descendant while the Job Object is created, configured and
/// assigned. Only after successful assignment is the primary thread resumed,
/// which means every instruction the sidecar ever executes runs inside the job.
/// If any step before the resume fails, the only process in existence is the
/// still-suspended leader, and terminating it is provably complete.
fn spawn(config: &SidecarConfig, exe: &str) -> std::result::Result<SpawnedSidecar, BridgeError> {
    let mut cmd = sidecar_command(config, exe);
    let mut child = match cmd.spawn() {
        Ok(child) => child,
        Err(err) => return Err(BridgeError::io("spawn sidecar", err)),
    };
    if let Some(pid) = child.id() {
        log::info!("bridge: sidecar spawned (pid {pid})");
    }
    let mut containment = match SidecarContainment::establish(&child) {
        Ok(containment) => containment,
        Err(err) => {
            log::error!(
                "bridge: containment setup failed for the just-spawned sidecar — terminating \
                 the uncontained child ({err})"
            );
            discard_uncontained_child(&mut child);
            return Err(err);
        }
    };
    // Windows: the child is only allowed to start running now that it is a job
    // member. On failure the containment is closed first (kill-on-close kills
    // the assigned, still-suspended leader) and the child handle is discarded
    // as a second safety net.
    if let Err(err) = containment.release_startup_suspension() {
        log::error!(
            "bridge: could not start the contained sidecar — tearing down the contained \
             child ({err})"
        );
        let _ = containment.close();
        discard_uncontained_child(&mut child);
        return Err(err);
    }
    log::info!(
        "bridge: containment established for pid {}: {}",
        containment.leader_pid,
        containment.summary()
    );
    Ok(SpawnedSidecar { child, containment })
}

/// The platform containment owning one sidecar process tree.
///
/// Ownership: exactly one [`SidecarContainment`] exists per spawned instance;
/// it is created immediately after spawn inside [`spawn`], lives inside the
/// [`SpawnedSidecar`] while the instance is supervised, and is consumed by
/// [`terminate_sidecar`] (which closes it). A containment that is only dropped
/// (e.g. a panicking supervisor) still releases its OS object — the Windows job
/// handle is closed by `Drop` (killing all members via kill-on-close); a Unix
/// group holds no kernel object, so its drop-time safety net is the child's
/// `kill_on_drop` plus the leader's stdin-EOF self-exit.
pub(crate) struct SidecarContainment {
    /// Pid of the contained leader (== process-group id on Unix).
    pub(crate) leader_pid: u32,
    #[cfg(windows)]
    job: windows_job::JobHandle,
    #[cfg(unix)]
    pgid: Option<libc::pid_t>,
}

impl SidecarContainment {
    /// Attach containment to a just-spawned child.
    ///
    /// Races where the child exits before assignment are *not* failures that
    /// can leave an orphan: there is then nothing left to contain, the child
    /// cannot be signalled again (kill returns `ESRCH`, which every helper here
    /// treats as success), and the supervisor simply moves to the next
    /// interpreter candidate.
    fn establish(child: &Child) -> std::result::Result<Self, BridgeError> {
        let pid = child.id().ok_or_else(|| {
            BridgeError::sidecar_crashed("sidecar exited before containment was established")
        })?;
        #[cfg(windows)]
        {
            let job = windows_job::contain_pid(pid)
                .map_err(|err| BridgeError::io("contain sidecar in job object", err))?;
            Ok(Self {
                leader_pid: pid,
                job,
            })
        }
        #[cfg(unix)]
        {
            let leader = libc::pid_t::try_from(pid)
                .map_err(|_| BridgeError::sidecar_crashed("sidecar pid out of range"))?;
            // Verify the pre-`exec` group actually took effect: the child must
            // lead the group that the teardown will signal. A freshly forked
            // but not-yet-reaped child always answers `getpgid`, so an error
            // here means the child vanished (or the platform refused the
            // group) — in both cases there is nothing to leak.
            let pgid =
                group_of(pid).map_err(|err| BridgeError::io("read sidecar process group", err))?;
            if pgid != leader {
                return Err(BridgeError::sidecar_crashed(
                    "sidecar does not lead its containment process group",
                ));
            }
            Ok(Self {
                leader_pid: pid,
                pgid: Some(leader),
            })
        }
        #[cfg(not(any(unix, windows)))]
        {
            // No containment primitive on this target (nothing in the
            // supported matrix hits this path); leader-only semantics apply.
            Ok(Self { leader_pid: pid })
        }
    }

    /// Let a contained child start executing.
    ///
    /// Windows: the sidecar is created with `CREATE_SUSPENDED` (see
    /// [`sidecar_creation_flags`]) precisely so that the window between process
    /// creation and Job Object assignment contains *no* executed child
    /// instruction — and therefore no descendant that could escape the job.
    /// This resumes the primary thread once assignment has succeeded, so the
    /// first instruction the child runs is already a job member's.
    ///
    /// Unix: the process group is applied by the kernel inside the forked child
    /// before `exec`, which is already race-free, so there is nothing to
    /// release and this is a no-op.
    ///
    /// Idempotency: resuming an already-running thread is a documented no-op
    /// (`ResumeThread` just decrements a zero suspend count and reports it), so
    /// a repeated call cannot corrupt the child.
    fn release_startup_suspension(&mut self) -> std::result::Result<(), BridgeError> {
        #[cfg(windows)]
        {
            windows_job::resume_process(self.leader_pid)
                .map_err(|err| BridgeError::io("resume contained sidecar", err))?;
        }
        Ok(())
    }

    /// Human-readable mechanism for lifecycle logs (never contains paths or
    /// command arguments).
    fn summary(&self) -> &'static str {
        #[cfg(windows)]
        {
            "job object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE"
        }
        #[cfg(unix)]
        {
            "dedicated process group (SIGTERM/SIGKILL to the group on teardown)"
        }
        #[cfg(not(any(unix, windows)))]
        {
            "none (leader-only kill semantics on this platform)"
        }
    }

    /// Ask the containment to exit cooperatively. Unix: `SIGTERM` to the whole
    /// group. Windows: Job Objects have no cooperative signal — stdin EOF is
    /// the graceful channel, so this is a no-op kept for a symmetric flow.
    fn request_graceful_termination(&self) -> std::result::Result<(), BridgeError> {
        #[cfg(unix)]
        if let Some(pgid) = self.pgid {
            signal_group(pgid, libc::SIGTERM)
                .map_err(|err| BridgeError::io("signal sidecar process group", err))?;
        }
        Ok(())
    }

    /// Force-terminate everything still contained.
    fn terminate_forced(&self) -> std::result::Result<(), BridgeError> {
        #[cfg(windows)]
        {
            self.job
                .terminate_all()
                .map_err(|err| BridgeError::io("terminate sidecar job object", err))?;
        }
        #[cfg(unix)]
        if let Some(pgid) = self.pgid {
            signal_group(pgid, libc::SIGKILL)
                .map_err(|err| BridgeError::io("kill sidecar process group", err))?;
        }
        Ok(())
    }

    /// Final release of the containment object; idempotent.
    ///
    /// Unix: one last `SIGKILL` sweep of the group — descendants can outlive a
    /// gracefully-exiting leader, and `ESRCH` (empty group, or already swept)
    /// is treated as success. Windows: closing the job handle; the kernel then
    /// terminates any member still inside it (`KILL_ON_JOB_CLOSE`).
    fn close(&mut self) -> std::result::Result<(), BridgeError> {
        #[cfg(unix)]
        if let Some(pgid) = self.pgid.take() {
            match signal_group(pgid, libc::SIGKILL) {
                Ok(true) => {
                    log::info!(
                        "bridge: descendant cleanup attempted — signaled process group {pgid}"
                    );
                }
                // Nothing left inside the group: normal case after a clean exit.
                Ok(false) => log::debug!("bridge: sidecar process group {pgid} already empty"),
                Err(err) => {
                    return Err(BridgeError::io("sweep sidecar process group", err));
                }
            }
        }
        #[cfg(windows)]
        {
            self.job
                .close()
                .map_err(|err| BridgeError::io("close sidecar job object", err))?;
        }
        Ok(())
    }
}

/// `getpgid` wrapper (never a panic: errors are surfaced as `io::Error`).
#[cfg(unix)]
fn group_of(pid: u32) -> std::io::Result<libc::pid_t> {
    // SAFETY: `getpgid` takes one integer and writes nothing; a pid of `u32`
    // max never enters the valid pid space (kernel reserves it), so the
    // truncating cast below cannot alias a live process.
    let pgid = unsafe { libc::getpgid(pid as libc::pid_t) };
    if pgid == -1 {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(pgid)
    }
}

/// Send `signal` to the whole process group `pgid` (`killpg`).
///
/// Returns `Ok(true)` when the signal was delivered to at least one member and
/// `Ok(false)` when the group is already empty (`ESRCH` — the idempotent
/// success case). Any other errno is an error, so a permission problem is
/// never mistaken for cleanup. Only groups we created and led are targeted —
/// `pgid` always equals a sidecar/helper child pid owned by this supervisor,
/// which makes unrelated-process collateral impossible by construction.
#[cfg(unix)]
fn signal_group(pgid: libc::pid_t, signal: libc::c_int) -> std::io::Result<bool> {
    // SAFETY: `killpg` is async-signal-safe and only takes plain integers.
    let rc = unsafe { libc::killpg(pgid, signal) };
    if rc == 0 {
        Ok(true)
    } else {
        let err = std::io::Error::last_os_error();
        if err.raw_os_error() == Some(libc::ESRCH) {
            Ok(false)
        } else {
            Err(err)
        }
    }
}

/// Windows Job Object containment.
///
/// Isolated in its own module because assigning a process to a Job Object is
/// the one part of the lifecycle that has no safe-Rust abstraction on the
/// `Command`/`Child` types. The FFI surface below is deliberately tiny: a
/// handful of `kernel32` calls via `windows-sys`, every one documented at its
/// `unsafe` block, with the raw handle wrapped in [`JobHandle`] for ownership
/// and `Drop` semantics (no handle can leak, closing is idempotent).
#[cfg(windows)]
pub(crate) mod windows_job {
    use std::io;

    // `windows-sys` 0.52 shapes (verified against the Windows CI compiler):
    // `IsProcessInJob`, `AssignProcessToJobObject` and the limit structs live
    // under `JobObjects`, `OpenProcess` under `Threading`, and `HANDLE`/`BOOL`
    // are plain `isize`/`i32` aliases whose null/failure sentinel is `0`.
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Thread32First, Thread32Next, TH32CS_SNAPTHREAD, THREADENTRY32,
    };
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, JobObjectExtendedLimitInformation, SetInformationJobObject,
        TerminateJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows_sys::Win32::System::Threading::{
        OpenProcess, OpenThread, ResumeThread, PROCESS_SET_QUOTA, PROCESS_TERMINATE,
        THREAD_SUSPEND_RESUME,
    };

    // `windows-sys` 0.52 exposes every Job Object operation *except* job
    // creation itself (`CreateJobObjectW` was only added in a later release —
    // verified against the Windows CI compiler on both candidate modules), so
    // the kernel32 import is declared directly here. The signature matches
    // the SDK header (`CreateJobObjectW(SECURITY_ATTRIBUTES*, PCWSTR)`): both
    // parameters are bare pointers (`*const c_void` is ABI-identical to the
    // `*const SECURITY_ATTRIBUTES` the API takes, and `*const u16` to the
    // `PCWSTR` newtype), and callers in this module only ever pass nulls.
    #[link(name = "kernel32")]
    extern "system" {
        fn CreateJobObjectW(
            lpjobattributes: *const core::ffi::c_void,
            lpname: *const u16,
        ) -> HANDLE;
    }

    /// `ERROR_NOT_FOUND` (`winerror.h`): `TerminateJobObject` reports this when
    /// the job contains no processes — success for teardown purposes.
    const WIN32_ERROR_NOT_FOUND: i32 = 1168;

    /// An owned, unnamed Job Object configured with `KILL_ON_JOB_CLOSE`.
    ///
    /// Ownership contract: the handle inside is created exactly once and
    /// closed exactly once — explicit [`JobHandle::close`] takes it, and
    /// `Drop` closes whatever is left. With `KILL_ON_JOB_CLOSE`, closing the
    /// *last* handle terminates every process still in the job, so even a
    /// dropped-without-teardown value (or a crashed parent process) cannot
    /// leave the sidecar tree running.
    #[derive(Debug)]
    pub(crate) struct JobHandle {
        raw: Option<HANDLE>,
    }

    // SAFETY: `JobHandle` exclusively owns a private kernel handle created by
    // `CreateJobObjectW` for this process. Job handles are not thread-affine:
    // `AssignProcessToJobObject`, `TerminateJobObject` and `CloseHandle` may
    // each be called from any thread, and the struct never duplicates or
    // aliases the handle, so transfer of ownership between threads is sound.
    unsafe impl Send for JobHandle {}

    impl JobHandle {
        /// `TerminateJobObject`: kill every process still inside the job.
        pub(crate) fn terminate_all(&self) -> io::Result<()> {
            if let Some(job) = self.raw {
                // SAFETY: `job` is the (still open) handle this struct owns;
                // exit code 0 is an arbitrary teardown status accepted by
                // the API.
                let ok = unsafe { TerminateJobObject(job, 0) };
                // Capture the error before any other call can clobber
                // `GetLastError`.
                let err = if ok == 0 {
                    Some(io::Error::last_os_error())
                } else {
                    None
                };
                if let Some(err) = err {
                    if err.raw_os_error() == Some(WIN32_ERROR_NOT_FOUND) {
                        return Ok(());
                    }
                    return Err(err);
                }
            }
            Ok(())
        }

        /// Release the job handle, killing any surviving member. Idempotent:
        /// the handle is taken, so a second call (or the `Drop`) is a no-op.
        pub(crate) fn close(&mut self) -> io::Result<()> {
            if let Some(job) = self.raw.take() {
                // SAFETY: closing the only owned reference to this job,
                // exactly once. Kill-on-close sweeps any remaining members.
                let ok = unsafe { CloseHandle(job) };
                if ok == 0 {
                    return Err(io::Error::last_os_error());
                }
            }
            Ok(())
        }

        #[cfg(test)]
        pub(crate) fn as_raw(&self) -> Option<HANDLE> {
            self.raw
        }
    }

    impl Drop for JobHandle {
        fn drop(&mut self) {
            // Best effort and never panicking: a failed `CloseHandle` on the
            // way out has no useful recovery beyond process exit, which also
            // closes the handle and triggers kill-on-close.
            let _ = self.close();
        }
    }

    /// Create a private Job Object (kill-on-close) and assign the process with
    /// `pid` to it. Errors carry the platform cause; on error the job (if it
    /// was created) has already been closed and the child was *not* contained,
    /// so the caller must discard the child (see `spawn`).
    pub(crate) fn contain_pid(pid: u32) -> io::Result<JobHandle> {
        // SAFETY: both arguments are null — default security attributes and a
        // null name (an unnamed, private job), which Win32 explicitly allows.
        let job = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if job == 0 {
            return Err(io::Error::last_os_error());
        }
        let mut job_handle = JobHandle { raw: Some(job) };

        // `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` is the whole point of the job:
        // closing the last handle must tear down every member (the sidecar and
        // all descendants it inherited into the job).
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { core::mem::zeroed() };
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        // SAFETY: `job` is valid (owned above) and `limits` is a plain-data
        // struct passed with its exact size; the API only reads it.
        let configured = unsafe {
            SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION as *const _,
                core::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        };
        if configured == 0 {
            let err = io::Error::last_os_error();
            let _ = job_handle.close();
            return Err(err);
        }

        if let Err(err) = assign_process(&mut job_handle, pid) {
            // Nothing got assigned (or the child exited mid-handshake);
            // closing the job is cheap and leaves no kernel object behind.
            let _ = job_handle.close();
            return Err(err);
        }
        Ok(job_handle)
    }

    /// `ResumeThread` failure sentinel (`(DWORD) -1`, per the Win32 docs).
    const RESUME_THREAD_FAILED: u32 = u32::MAX;

    /// Resume the primary thread of the suspended process `pid`.
    ///
    /// Called only after the process has been assigned to its Job Object, so
    /// the child begins executing as a job member and no descendant can ever be
    /// created outside containment (SEC-09).
    ///
    /// A `CREATE_SUSPENDED` process has exactly one thread — it has executed no
    /// instruction, so it cannot have created another — which is why resuming
    /// every thread owned by `pid` is precise, not a heuristic. Threads are
    /// selected by owner pid from a snapshot; no process/thread name is ever
    /// matched and nothing outside this pid is touched.
    pub(crate) fn resume_process(pid: u32) -> io::Result<()> {
        // SAFETY: a thread-only snapshot of the whole system; the `0` pid
        // argument is ignored for `TH32CS_SNAPTHREAD` (Win32 documented).
        let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) };
        if snapshot == INVALID_HANDLE_VALUE {
            return Err(io::Error::last_os_error());
        }
        let result = resume_threads_of(snapshot, pid);
        // SAFETY: closing the snapshot handle opened above, on every path.
        unsafe { CloseHandle(snapshot) };
        result
    }

    /// Walk `snapshot` and resume every thread whose owner is `pid`.
    ///
    /// Split out so the snapshot handle above is closed on all paths, including
    /// early returns from here.
    fn resume_threads_of(snapshot: HANDLE, pid: u32) -> io::Result<()> {
        // SAFETY: `THREADENTRY32` is plain data; the API requires `dwSize` to
        // be pre-filled with the struct size.
        let mut entry: THREADENTRY32 = unsafe { core::mem::zeroed() };
        entry.dwSize = core::mem::size_of::<THREADENTRY32>() as u32;
        // SAFETY: `snapshot` is a valid thread snapshot; `entry` is a live
        // out-param sized above.
        let mut more = unsafe { Thread32First(snapshot, &mut entry) };
        let mut resumed = 0usize;
        while more != 0 {
            if entry.th32OwnerProcessID == pid {
                resume_thread(entry.th32ThreadID)?;
                resumed += 1;
            }
            // SAFETY: same contract as `Thread32First`.
            more = unsafe { Thread32Next(snapshot, &mut entry) };
        }
        if resumed == 0 {
            // The child vanished between assignment and resume (it was
            // suspended, so this means an external kill). Nothing is running
            // and nothing can be orphaned; report it so the caller discards the
            // instance instead of supervising a dead sidecar.
            return Err(io::Error::other(
                "the suspended sidecar had no thread left to resume",
            ));
        }
        Ok(())
    }

    /// `OpenThread` + `ResumeThread` for one thread id, closing the handle on
    /// every path.
    fn resume_thread(tid: u32) -> io::Result<()> {
        // SAFETY: plain integer arguments; `0` is the non-inheritable flag.
        let thread = unsafe { OpenThread(THREAD_SUSPEND_RESUME, 0, tid) };
        if thread == 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: `thread` is the handle opened directly above.
        let previous = unsafe { ResumeThread(thread) };
        // Capture the error before `CloseHandle` can clobber `GetLastError`.
        let err = if previous == RESUME_THREAD_FAILED {
            Some(io::Error::last_os_error())
        } else {
            None
        };
        // SAFETY: closing the handle this function opened, in every branch.
        unsafe { CloseHandle(thread) };
        match err {
            None => Ok(()),
            Some(err) => Err(err),
        }
    }

    fn assign_process(job: &mut JobHandle, pid: u32) -> io::Result<()> {
        let Some(handle) = job.raw else {
            return Err(io::Error::other("job handle already closed"));
        };
        // `AssignProcessToJobObject` requires both access rights on the
        // process handle (see the Win32 docs for this API).
        const DESIRED: u32 = PROCESS_SET_QUOTA | PROCESS_TERMINATE;
        // SAFETY: plain integer arguments; the `0` inherit flag is `false`.
        // A child that already exited fails here with `ERROR_INVALID_PARAMETER`
        // — the documented "child exited before assignment" race, surfaced to
        // the caller as an establishment failure that discards the (already
        // dead) child.
        let process = unsafe { OpenProcess(DESIRED, 0, pid) };
        if process == 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: both handles are valid and owned appropriately (the process
        // handle is closed below in all paths; the job handle is borrowed from
        // `job`).
        let assigned = unsafe { AssignProcessToJobObject(handle, process) };
        // Capture the assignment error *before* `CloseHandle` can overwrite
        // `GetLastError`.
        let assign_err = if assigned == 0 {
            Some(io::Error::last_os_error())
        } else {
            None
        };
        // SAFETY: `process` was opened by this function and is no longer
        // needed either way — no handle leaks.
        unsafe { CloseHandle(process) };
        // Ignore `CloseHandle`'s result on our own just-opened handle: even a
        // failure there only risks a handle that process exit would reclaim;
        // the assignment outcome is what the caller acts on.
        match assign_err {
            None => Ok(()),
            Some(err) => Err(err),
        }
    }
}

/// Log the reason the sidecar stays disconnected: none of the interpreter
/// candidates could be launched. Spoken in English and Persian, so both
/// audiences see that Python 3.10+ with the `dream` package installed is
/// required.
fn log_python_required(candidates: &[String]) {
    let tried = candidates.join("`, `");
    log::error!(
        "bridge: the Dream sidecar could not start — none of `{tried}` could be launched. \
         Dream needs Python 3.10+ with the `dream` package installed (run `pip install -e .` from the repository root) on PATH."
    );
    log::error!(
        "bridge: راه‌اندازی موتور Dream ممکن نشد — هیچ‌یک از `{tried}` اجرا نشد. \
         برای اجرای Dream پایتون نسخه ۳.۱۰ یا بالاتر به‌همراه بسته‌ی dream نصب‌شده لازم است (از ریشه‌ی مخزن `pip install -e .` را اجرا کنید)."
    );
}

/// Reject every in-flight request after a crash/restart. Returns the count.
async fn reject_pending(dispatcher: &Arc<Mutex<Dispatcher>>) -> usize {
    dispatcher
        .lock()
        .await
        .fail_all(code::INTERNAL_ERROR, "sidecar restarted")
}

/// Write a state transition and emit it to the frontend.
fn set_state<R: Runtime>(
    app: &tauri::AppHandle<R>,
    state: &Arc<SharedState>,
    next: ConnectionState,
) {
    let prev = state.set(next);
    if prev != next {
        log::info!("bridge state: {prev:?} → {next:?}");
        let _ = app.emit(STATE_EVENT, next);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
    use crate::bridge::framing::Outcome;
    use std::collections::HashMap;
    use std::io;

    /// Fake environment reader built from a map, so no test touches the real
    /// process environment (and tests stay safe to run in parallel).
    fn env_from<'a>(map: &'a HashMap<&str, &str>) -> impl Fn(&str) -> Option<String> + 'a {
        move |key: &str| map.get(key).map(|value| (*value).to_string())
    }

    #[test]
    fn default_candidates_are_python_py_python3() {
        let config = SidecarConfig::from_env(&env_from(&HashMap::new()));
        assert_eq!(
            config.python,
            ["python", "py", "python3"].map(String::from).to_vec()
        );
        assert_eq!(config.module, "dream.bridge");
    }

    #[test]
    fn dream_sidecar_python_is_a_hard_override() {
        let mut env = HashMap::new();
        env.insert("DREAM_SIDECAR_PYTHON", "C:\\dream\\venv\\python.exe");
        env.insert("DREAM_SIDECAR_MODULE", "custom.module");
        let config = SidecarConfig::from_env(&env_from(&env));

        // The override replaces the whole candidate list — `py`/`python3` are
        // never appended behind it.
        assert_eq!(config.python, vec!["C:\\dream\\venv\\python.exe"]);
        assert_eq!(config.module, "custom.module");
    }

    #[test]
    fn discovery_follows_the_fake_command_order() {
        // Fake command order: `python` and `py` fail to spawn, `python3` works.
        let candidates = ["python", "py", "python3"].map(String::from).to_vec();
        let mut probed = Vec::new();
        let found = spawn_first(&candidates, |exe| {
            probed.push(exe.to_string());
            if exe == "python3" {
                Ok(42usize)
            } else {
                Err(BridgeError::io(
                    "spawn sidecar",
                    io::Error::new(io::ErrorKind::NotFound, "no such interpreter"),
                ))
            }
        });

        let (index, exe, value) = found.expect("python3 must be discovered");
        assert_eq!((index, exe, value), (2, "python3", 42));
        // The walk stops at the first working candidate — in order.
        assert_eq!(probed, ["python", "py", "python3"]);
    }

    #[test]
    fn discovery_reports_none_when_no_candidate_spawns() {
        let candidates = ["python", "py", "python3"].map(String::from).to_vec();
        let mut attempts = 0usize;
        // Annotate the probe value type: every probe fails, so `usize` cannot
        // be inferred from the closure alone.
        let found: Option<(usize, &str, usize)> = spawn_first(&candidates, |_| {
            attempts += 1;
            Err(BridgeError::io(
                "spawn sidecar",
                io::Error::new(io::ErrorKind::NotFound, "missing"),
            ))
        });

        assert!(found.is_none(), "every candidate failed — give up");
        assert_eq!(attempts, 3);
    }

    #[test]
    fn sidecar_creation_flags_match_platform() {
        // On Windows the sidecar must hide its console; on POSIX there is no
        // such flag. Pure check, no process spawned.
        #[cfg(windows)]
        assert_ne!(
            sidecar_creation_flags() & CREATE_NO_WINDOW,
            0,
            "Windows sidecar must set CREATE_NO_WINDOW"
        );
        // SEC-09: without CREATE_SUSPENDED the child could run — and spawn
        // descendants — before it is assigned to the Job Object.
        #[cfg(windows)]
        assert_ne!(
            sidecar_creation_flags() & CREATE_SUSPENDED,
            0,
            "Windows sidecar must start suspended so containment precedes execution"
        );
        #[cfg(not(windows))]
        assert_eq!(
            sidecar_creation_flags(),
            0,
            "POSIX sidecar has no console-hiding flag"
        );
    }

    #[test]
    fn bundled_interpreter_paths_prefer_resource_then_resources_subdir_then_exe_side() {
        // Pure path construction + existence filter: create dummy `python.exe`
        // files in each location (never spawn a real interpreter) and assert
        // the priority order.
        let tmp = tempfile::tempdir().expect("temp dir");
        let exe_dir = tmp.path().join("exe");
        let resource_dir = tmp.path().join("resource");
        std::fs::create_dir_all(exe_dir.join("python")).unwrap();
        std::fs::create_dir_all(exe_dir.join("resources").join("python")).unwrap();
        std::fs::create_dir_all(resource_dir.join("python")).unwrap();
        std::fs::write(exe_dir.join("python").join("python.exe"), b"").unwrap();
        std::fs::write(
            exe_dir.join("resources").join("python").join("python.exe"),
            b"",
        )
        .unwrap();
        std::fs::write(resource_dir.join("python").join("python.exe"), b"").unwrap();

        let paths = bundled_interpreter_paths(&exe_dir, Some(&resource_dir));
        assert_eq!(
            paths,
            vec![
                resource_dir.join("python").join("python.exe"),
                exe_dir.join("resources").join("python").join("python.exe"),
                exe_dir.join("python").join("python.exe"),
            ]
        );
    }

    #[test]
    fn bundled_interpreter_paths_finds_nsis_layout_without_resource_dir() {
        // Mirrors the measured stock install:
        //   C:\Program Files\Dream\dream-desktop.exe
        //   C:\Program Files\Dream\resources\python\python.exe
        // `resource_dir` is missing (None) — the exe-side `resources` subdir
        // must be found and come first, before any exe-side `python` dir.
        let tmp = tempfile::tempdir().expect("temp dir");
        let install_root = tmp.path().join("Program Files").join("Dream");
        let exe_dir = install_root.clone();
        let bundled = install_root
            .join("resources")
            .join("python")
            .join("python.exe");
        std::fs::create_dir_all(bundled.parent().unwrap()).unwrap();
        std::fs::write(&bundled, b"").unwrap();

        let paths = bundled_interpreter_paths(&exe_dir, None);
        assert_eq!(paths, vec![bundled]);
    }

    #[test]
    fn bundled_interpreter_paths_finds_nsis_layout_with_wrong_resource_dir() {
        // Same NSIS layout, but the resolver reports a resource dir that does
        // not exist (or points somewhere else). Discovery must still find the
        // measured `{exe_dir}/resources/python/python.exe` first.
        let tmp = tempfile::tempdir().expect("temp dir");
        let install_root = tmp.path().join("Program Files").join("Dream");
        let exe_dir = install_root.clone();
        let bundled = install_root
            .join("resources")
            .join("python")
            .join("python.exe");
        std::fs::create_dir_all(bundled.parent().unwrap()).unwrap();
        std::fs::write(&bundled, b"").unwrap();

        let wrong_resource_dir = tmp.path().join("does-not-exist");
        let paths = bundled_interpreter_paths(&exe_dir, Some(&wrong_resource_dir));
        assert_eq!(paths, vec![bundled]);
    }

    #[test]
    fn bundled_interpreter_paths_prefers_resources_subdir_over_exe_side_python() {
        // When both `{exe_dir}/python/python.exe` and
        // `{exe_dir}/resources/python/python.exe` exist, the NSIS `resources`
        // layout wins — it is the layout the installer ships.
        let tmp = tempfile::tempdir().expect("temp dir");
        let exe_dir = tmp.path().join("exe");
        std::fs::create_dir_all(exe_dir.join("python")).unwrap();
        std::fs::create_dir_all(exe_dir.join("resources").join("python")).unwrap();
        std::fs::write(exe_dir.join("python").join("python.exe"), b"").unwrap();
        std::fs::write(
            exe_dir.join("resources").join("python").join("python.exe"),
            b"",
        )
        .unwrap();

        let paths = bundled_interpreter_paths(&exe_dir, None);
        assert_eq!(
            paths,
            vec![
                exe_dir.join("resources").join("python").join("python.exe"),
                exe_dir.join("python").join("python.exe"),
            ]
        );
    }

    #[test]
    fn bundled_interpreter_paths_accepts_a_resource_dir_that_is_the_python_folder() {
        // Some bundles point the resource dir directly at the python folder;
        // in that case `{resource_dir}/python.exe` is the right candidate.
        let tmp = tempfile::tempdir().expect("temp dir");
        let python_dir = tmp.path().join("python");
        std::fs::create_dir_all(&python_dir).unwrap();
        std::fs::write(python_dir.join("python.exe"), b"").unwrap();

        let paths = bundled_interpreter_paths(&python_dir, Some(&python_dir));
        assert_eq!(paths, vec![python_dir.join("python.exe")]);
    }

    #[test]
    fn bundled_interpreter_paths_checks_the_parent_of_exe_dir() {
        // The binary may live in a subfolder of the install root; the bundled
        // interpreter still sits at the install root.
        let tmp = tempfile::tempdir().expect("temp dir");
        let install_root = tmp.path().join("install");
        let exe_dir = install_root.join("bin");
        std::fs::create_dir_all(&exe_dir).unwrap();
        let bundled = install_root
            .join("resources")
            .join("python")
            .join("python.exe");
        std::fs::create_dir_all(bundled.parent().unwrap()).unwrap();
        std::fs::write(&bundled, b"").unwrap();

        let paths = bundled_interpreter_paths(&exe_dir, None);
        assert_eq!(paths, vec![bundled]);
    }

    #[test]
    fn bundled_interpreter_paths_only_returns_existing_files() {
        let tmp = tempfile::tempdir().expect("temp dir");
        let exe_dir = tmp.path().join("exe");
        let resource_dir = tmp.path().join("resource");
        std::fs::create_dir_all(exe_dir.join("python")).unwrap();
        std::fs::create_dir_all(&resource_dir).unwrap();
        // Only exe_dir/python/python.exe exists; the resource dir and the
        // exe_dir/resources subdir are empty and must be filtered out.
        std::fs::write(exe_dir.join("python").join("python.exe"), b"").unwrap();

        let paths = bundled_interpreter_paths(&exe_dir, Some(&resource_dir));
        assert_eq!(paths, vec![exe_dir.join("python").join("python.exe")]);
    }

    #[test]
    fn bundled_interpreter_paths_empty_when_nothing_present() {
        let tmp = tempfile::tempdir().expect("temp dir");
        let exe_dir = tmp.path().join("exe");
        std::fs::create_dir_all(&exe_dir).unwrap();

        let paths = bundled_interpreter_paths(&exe_dir, None);
        assert!(paths.is_empty());
    }

    #[test]
    fn prepend_bundled_puts_bundled_first() {
        let tmp = tempfile::tempdir().expect("temp dir");
        let exe_dir = tmp.path().join("exe");
        std::fs::create_dir_all(exe_dir.join("python")).unwrap();
        let bundled = exe_dir.join("python").join("python.exe");
        std::fs::write(&bundled, b"").unwrap();
        let bundled_str = bundled.to_string_lossy().into_owned();

        let mut config = SidecarConfig::from_env(&env_from(&HashMap::new()));
        config.prepend_bundled(&exe_dir, None, false);

        assert_eq!(
            config.python,
            vec![
                bundled_str.clone(),
                "python".to_string(),
                "py".to_string(),
                "python3".to_string(),
            ]
        );
        assert!(config.is_bundled(&bundled_str));
    }

    #[test]
    fn dream_sidecar_python_override_is_not_shadowed_by_bundled() {
        // Even when a bundled interpreter exists on disk, an explicit
        // `DREAM_SIDECAR_PYTHON` override must stay the only candidate and
        // must not be treated as a bundled runtime.
        let tmp = tempfile::tempdir().expect("temp dir");
        let exe_dir = tmp.path().join("exe");
        std::fs::create_dir_all(exe_dir.join("python")).unwrap();
        std::fs::write(exe_dir.join("python").join("python.exe"), b"").unwrap();

        let mut env = HashMap::new();
        env.insert("DREAM_SIDECAR_PYTHON", "C:\\dream\\venv\\python.exe");
        let mut config = SidecarConfig::from_env(&env_from(&env));

        config.prepend_bundled(&exe_dir, None, true);

        assert_eq!(config.python, vec!["C:\\dream\\venv\\python.exe"]);
        assert!(!config.is_bundled("C:\\dream\\venv\\python.exe"));
    }

    #[test]
    fn override_that_is_the_bundled_exe_is_still_marked_bundled() {
        let tmp = tempfile::tempdir().expect("temp dir");
        let exe_dir = tmp.path().join("exe");
        std::fs::create_dir_all(exe_dir.join("python")).unwrap();
        let bundled = exe_dir.join("python").join("python.exe");
        std::fs::write(&bundled, b"").unwrap();
        let bundled_str = bundled.to_string_lossy().into_owned();

        let mut env = HashMap::new();
        env.insert("DREAM_SIDECAR_PYTHON", bundled_str.as_str());
        let mut config = SidecarConfig::from_env(&env_from(&env));
        config.prepend_bundled(&exe_dir, None, true);

        assert_eq!(config.python, vec![bundled_str.clone()]);
        assert!(config.is_bundled(&bundled_str));
    }

    #[test]
    fn sidecar_python_env_always_forces_utf8() {
        let host = sidecar_python_env(false);
        assert!(host.contains(&("PYTHONUTF8", "1")));
        assert!(host.contains(&("PYTHONIOENCODING", "utf-8")));
        assert!(!host.iter().any(|(key, _)| *key == "PYTHONNOUSERSITE"));

        let bundled = sidecar_python_env(true);
        assert!(bundled.contains(&("PYTHONUTF8", "1")));
        assert!(bundled.contains(&("PYTHONNOUSERSITE", "1")));
    }

    #[test]
    fn sidecar_data_root_prefers_dream_home() {
        let tmp = tempfile::tempdir().expect("temp dir");
        let home = tmp.path().join("custom-home");
        let previous = std::env::var_os("DREAM_HOME");
        std::env::set_var("DREAM_HOME", &home);
        let root = sidecar_data_root();
        match previous {
            Some(value) => std::env::set_var("DREAM_HOME", value),
            None => std::env::remove_var("DREAM_HOME"),
        }
        assert_eq!(root, home);
    }

    #[test]
    fn ensure_sidecar_data_root_creates_data_subdir() {
        let tmp = tempfile::tempdir().expect("temp dir");
        let root = tmp.path().join("Dream");
        let got = ensure_sidecar_data_root(&root).expect("create");
        assert_eq!(got, root);
        assert!(root.join("data").is_dir());
    }

    #[test]
    fn missing_piped_stdio_returns_error_instead_of_panicking() {
        let err = require_piped_stdio::<i32, i32>(None, Some(1)).expect_err("stdin");
        assert!(
            err.message.contains("stdin"),
            "expected missing-stdin crash, got {err:?}"
        );

        let err = require_piped_stdio::<i32, i32>(Some(1), None).expect_err("stdout");
        assert!(
            err.message.contains("stdout"),
            "expected missing-stdout crash, got {err:?}"
        );

        let (stdin, stdout) = require_piped_stdio(Some(1), Some(2)).expect("both present");
        assert_eq!((stdin, stdout), (1, 2));
    }

    // ---- SEC-10: supervisor / transport tests -------------------------------
    //
    // Pure-logic tests run everywhere. The end-to-end supervisor tests drive
    // `run_supervisor` against a fake sidecar written as a `/bin/sh` script
    // (never the installed interpreter, never matched by process name), with
    // millisecond timings and pid-file assertions, following the SEC-09
    // ground rules above. They are `#[cfg(unix)]` because the fake sidecar
    // is a POSIX shell script; the Windows job runs `cargo clippy` over them
    // and skips `cargo test` for an unrelated reason (see desktop-ci.yml).

    fn short_timing() -> SupervisorTiming {
        // Generous enough that a loaded CI runner cannot fake a hang while
        // the responsive fake sidecar is answering pings (`/bin/sh` + `sed`
        // per line), short enough that a real hang is caught in seconds.
        SupervisorTiming {
            heartbeat_interval: Duration::from_millis(50),
            heartbeat_timeout: Duration::from_millis(1500),
            restart_backoff: vec![Duration::from_millis(10)],
            stable_after: Duration::from_secs(3600),
        }
    }

    #[test]
    fn default_timing_matches_documented_constants() {
        let timing = SupervisorTiming::default();
        assert_eq!(timing.heartbeat_interval, Duration::from_secs(5));
        assert_eq!(timing.heartbeat_timeout, Duration::from_secs(15));
        assert_eq!(
            timing.restart_backoff,
            vec![
                Duration::from_secs(2),
                Duration::from_secs(5),
                Duration::from_secs(10)
            ]
        );
        assert_eq!(SidecarConfig::default().timing, timing);
    }

    #[test]
    fn heartbeat_ids_live_in_the_reserved_band() {
        assert!(HEARTBEAT_ID_BASE >= RESERVED_ID_FLOOR);
        // The old base sat inside the frontend's counter range.
        assert!(HEARTBEAT_ID_BASE > 1_000_000);
    }

    #[test]
    fn restart_request_is_remembered_until_consumed() {
        let control = SupervisorControl::default();
        assert!(!control.take_restart_request());
        control.request_restart();
        control.request_restart();
        assert!(control.take_restart_request(), "one request is kept");
        assert!(!control.take_restart_request(), "and consumed exactly once");
    }

    #[tokio::test]
    async fn wait_for_restart_returns_immediately_for_an_earlier_request() {
        // The request arrives *before* anyone waits: no lost wake-up.
        let control = Arc::new(SupervisorControl::default());
        control.request_restart();
        tokio::time::timeout(Duration::from_secs(2), control.wait_for_restart())
            .await
            .expect("an earlier request is not lost");
        // And a request that arrives *while* waiting wakes the waiter.
        let waiter = Arc::clone(&control);
        let waiting = tokio::spawn(async move { waiter.wait_for_restart().await });
        control.request_restart();
        tokio::time::timeout(Duration::from_secs(2), waiting)
            .await
            .expect("bounded")
            .expect("waiter task");
        assert!(!control.take_restart_request(), "consumed by the waiter");
    }

    #[tokio::test]
    async fn heartbeat_watchdog_fires_after_silence() {
        let writer_tx: Arc<Mutex<Option<mpsc::Sender<String>>>> = Arc::new(Mutex::new(None));
        let last_activity = Arc::new(std::sync::Mutex::new(Instant::now()));
        let hung = Arc::new(Notify::new());
        let timing = SupervisorTiming {
            heartbeat_interval: Duration::from_millis(5),
            heartbeat_timeout: Duration::from_millis(40),
            ..short_timing()
        };
        let watchdog = tokio::spawn(heartbeat_watchdog(
            writer_tx,
            Arc::clone(&last_activity),
            timing,
            Arc::clone(&hung),
        ));
        tokio::time::timeout(Duration::from_secs(5), hung.notified())
            .await
            .expect("watchdog flags the silence within the bound");
        tokio::time::timeout(Duration::from_secs(2), watchdog)
            .await
            .expect("bounded")
            .expect("watchdog task exits after firing");
    }

    #[tokio::test]
    async fn heartbeat_watchdog_sends_reserved_ids_and_tolerates_a_full_channel() {
        let (tx, mut rx) = mpsc::channel::<String>(1);
        let writer_tx = Arc::new(Mutex::new(Some(tx)));
        let last_activity = Arc::new(std::sync::Mutex::new(Instant::now()));
        let hung = Arc::new(Notify::new());
        let timing = SupervisorTiming {
            heartbeat_interval: Duration::from_millis(5),
            heartbeat_timeout: Duration::from_millis(60),
            ..short_timing()
        };
        let watchdog = tokio::spawn(heartbeat_watchdog(
            Arc::clone(&writer_tx),
            last_activity,
            timing,
            Arc::clone(&hung),
        ));
        let first = tokio::time::timeout(Duration::from_secs(5), rx.recv())
            .await
            .expect("bounded")
            .expect("a ping is written");
        let value: serde_json::Value = serde_json::from_str(&first).expect("ping is JSON");
        assert_eq!(value["method"], "health.check");
        let id = value["id"].as_u64().expect("numeric id");
        assert!(
            id >= RESERVED_ID_FLOOR,
            "ping id {id} is in the reserved band"
        );
        // Nobody drains the channel any more: `try_send` must not block the
        // watchdog, which still has to detect the silence.
        tokio::time::timeout(Duration::from_secs(5), hung.notified())
            .await
            .expect("watchdog is not wedged behind a full writer channel");
        watchdog.abort();
    }

    #[tokio::test]
    async fn writer_end_is_signalled_even_when_the_task_is_aborted() {
        let done = Arc::new(Notify::new());
        let guard_done = Arc::clone(&done);
        let task = tokio::spawn(async move {
            let _guard = NotifyOnDrop(guard_done);
            std::future::pending::<()>().await;
        });
        task.abort();
        tokio::time::timeout(Duration::from_secs(2), done.notified())
            .await
            .expect("abort drops the guard, which notifies");
    }

    /// Where the supervisor tests write their fake sidecars and pid files.
    #[cfg(unix)]
    fn write_fake_sidecar(dir: &Path, name: &str, body: &str) -> String {
        use std::os::unix::fs::PermissionsExt;
        let path = dir.join(name);
        std::fs::write(&path, format!("#!/bin/sh\n{body}\n")).expect("write fake sidecar");
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755))
            .expect("chmod fake sidecar");
        path.to_string_lossy().into_owned()
    }

    /// A sidecar that completes the handshake and answers every request
    /// (including heartbeats) with a result carrying the same id.
    #[cfg(unix)]
    fn responsive_sidecar_body(pid_file: &Path) -> String {
        format!(
            "printf '%s\\n' \"$$\" >> '{pid}'\n\
             printf 'DREAM-PROTOCOL: 1.0\\n'\n\
             while IFS= read -r line; do\n\
               id=$(printf '%s' \"$line\" | sed -n 's/.*\"id\":[ ]*\\([0-9][0-9]*\\).*/\\1/p')\n\
               if [ -n \"$id\" ]; then\n\
                 printf '{{\"jsonrpc\":\"2.0\",\"id\":%s,\"result\":{{\"echo\":true}}}}\\n' \"$id\"\n\
               fi\n\
             done",
            pid = pid_file.display()
        )
    }

    /// A sidecar that hangs after the handshake — unless `flag` exists, in
    /// which case it behaves like [`responsive_sidecar_body`].
    #[cfg(unix)]
    fn hang_until_flag_sidecar_body(pid_file: &Path, flag: &Path) -> String {
        format!(
            "if [ -e '{flag}' ]; then\n{responsive}\nexit 0\nfi\n\
             printf '%s\\n' \"$$\" >> '{pid}'\n\
             printf 'DREAM-PROTOCOL: 1.0\\n'\n\
             exec sleep 30",
            flag = flag.display(),
            responsive = responsive_sidecar_body(pid_file),
            pid = pid_file.display()
        )
    }

    #[cfg(unix)]
    fn read_pids(path: &Path) -> Vec<u32> {
        std::fs::read_to_string(path)
            .unwrap_or_default()
            .lines()
            .filter_map(|line| line.trim().parse().ok())
            .collect()
    }

    /// Bounded poll for a connection state.
    #[cfg(unix)]
    async fn wait_for_state(state: &SharedState, target: ConnectionState, deadline: Duration) {
        let start = Instant::now();
        while state.get() != target {
            assert!(
                start.elapsed() < deadline,
                "state did not reach {target:?} within {deadline:?} (now {:?})",
                state.get()
            );
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    }

    /// Everything a supervisor test needs, spawned on a runtime the test owns
    /// so teardown is deterministic.
    #[cfg(unix)]
    struct SupervisorHarness {
        state: Arc<SharedState>,
        dispatcher: Arc<Mutex<Dispatcher>>,
        writer_tx: Arc<Mutex<Option<mpsc::Sender<String>>>>,
        killed: Arc<std::sync::atomic::AtomicBool>,
        control: Arc<SupervisorControl>,
    }

    #[cfg(unix)]
    impl SupervisorHarness {
        fn start(app: &tauri::AppHandle<tauri::test::MockRuntime>, config: SidecarConfig) -> Self {
            let harness = Self {
                state: Arc::new(SharedState::default()),
                dispatcher: Arc::new(Mutex::new(Dispatcher::new())),
                writer_tx: Arc::new(Mutex::new(None)),
                killed: Arc::new(std::sync::atomic::AtomicBool::new(false)),
                control: Arc::new(SupervisorControl::default()),
            };
            tokio::spawn(run_supervisor(
                app.clone(),
                Arc::clone(&harness.state),
                Arc::clone(&harness.dispatcher),
                Arc::clone(&harness.writer_tx),
                config,
                Arc::clone(&harness.killed),
                Arc::clone(&harness.control),
            ));
            harness
        }

        /// Register `id`, write the request, return the final receiver.
        async fn send(&self, id: u64) -> tokio::sync::oneshot::Receiver<Outcome> {
            let channels = self.dispatcher.lock().await.register(id).expect("register");
            let tx = self
                .writer_tx
                .lock()
                .await
                .as_ref()
                .cloned()
                .expect("writer present while Ready");
            tx.send(framing::request_line(id, "health.check", &json!({})))
                .await
                .expect("request written");
            channels.final_rx
        }

        /// Mirror of `Bridge::kill`: no more restarts, close stdin.
        async fn kill(&self) {
            self.killed
                .store(true, std::sync::atomic::Ordering::Release);
            *self.writer_tx.lock().await = None;
        }
    }

    #[cfg(unix)]
    fn mock_app() -> tauri::AppHandle<tauri::test::MockRuntime> {
        use tauri::Manager as _;
        let app = tauri::test::mock_builder()
            .build(tauri::test::mock_context(tauri::test::noop_assets()))
            .expect("mock app");
        app.handle().clone()
    }

    #[cfg(unix)]
    fn test_runtime() -> tokio::runtime::Runtime {
        tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()
            .expect("test runtime")
    }

    #[cfg(unix)]
    fn supervisor_config(python: Vec<String>) -> SidecarConfig {
        let mut config = SidecarConfig::from_env(&|_key: &str| -> Option<String> { None });
        config.python = python;
        config.timing = short_timing();
        config
    }

    /// Full path: a candidate that dies before the handshake is skipped, the
    /// next one reaches `Ready`, a request round-trips, and `kill` ends the
    /// instance (pid dead) and parks the supervisor in `Disconnected` with no
    /// pending requests left behind.
    #[cfg(unix)]
    #[test]
    fn unix_supervisor_skips_dead_candidate_answers_requests_and_parks_on_kill() {
        let dir = tempfile::tempdir().expect("temp dir");
        let pid_file = dir.path().join("pids");
        let dead = write_fake_sidecar(dir.path(), "dead.sh", "exit 0");
        let good = write_fake_sidecar(dir.path(), "good.sh", &responsive_sidecar_body(&pid_file));
        // The mock app is built outside any runtime (Tauri's builder may
        // block_on internally).
        let app = mock_app();
        let rt = test_runtime();
        rt.block_on(async move {
            let harness = SupervisorHarness::start(&app, supervisor_config(vec![dead, good]));
            wait_for_state(
                &harness.state,
                ConnectionState::Ready,
                Duration::from_secs(20),
            )
            .await;

            let rx = harness.send(7).await;
            match tokio::time::timeout(Duration::from_secs(10), rx)
                .await
                .expect("bounded")
                .expect("dispatcher delivers")
            {
                Outcome::Result(value) => assert_eq!(value["echo"], true),
                other => panic!("expected a result, got {other:?}"),
            }
            assert!(harness.dispatcher.lock().await.is_empty());

            let leader = *read_pids(&pid_file).last().expect("leader pid recorded");
            harness.kill().await;
            wait_for_state(
                &harness.state,
                ConnectionState::Disconnected,
                Duration::from_secs(20),
            )
            .await;
            assert!(
                wait_unix_pid_dead(leader, DEADLINE_AFTER_TEARDOWN).await,
                "killed instance is reaped"
            );
            assert!(harness.writer_tx.lock().await.is_none());
            assert_eq!(read_pids(&pid_file).len(), 1, "no respawn after kill");
        });
    }

    /// R1 + R2: a sidecar that goes silent after the handshake is detected
    /// by the heartbeat and torn down (pid dead); the in-flight request is
    /// rejected exactly once with a transport-tagged INTERNAL_ERROR; after the
    /// retry budget is spent the bridge is `Disconnected`, and a manual
    /// restart revives it with a fresh attempt.
    #[cfg(unix)]
    #[test]
    fn unix_heartbeat_kills_hung_sidecar_rejects_pending_and_manual_restart_revives() {
        let dir = tempfile::tempdir().expect("temp dir");
        let pid_file = dir.path().join("pids");
        let flag = dir.path().join("behave");
        let script = write_fake_sidecar(
            dir.path(),
            "hang.sh",
            &hang_until_flag_sidecar_body(&pid_file, &flag),
        );
        let app = mock_app();
        let rt = test_runtime();
        rt.block_on(async move {
            let harness = SupervisorHarness::start(&app, supervisor_config(vec![script]));
            wait_for_state(
                &harness.state,
                ConnectionState::Ready,
                Duration::from_secs(20),
            )
            .await;
            let first_leader = *read_pids(&pid_file).last().expect("first leader pid");

            // In flight while the sidecar hangs.
            let rx = harness.send(1).await;
            match tokio::time::timeout(Duration::from_secs(30), rx)
                .await
                .expect("pending request is rejected within the bound")
                .expect("rejected, not dropped")
            {
                Outcome::Error {
                    code,
                    message,
                    data,
                } => {
                    assert_eq!(code, code::INTERNAL_ERROR);
                    assert_eq!(message, "sidecar restarted");
                    assert_eq!(data.expect("tagged")["kind"], "transport");
                }
                other => panic!("expected a transport error, got {other:?}"),
            }
            assert!(
                wait_unix_pid_dead(first_leader, DEADLINE_AFTER_TEARDOWN).await,
                "hung leader was killed, not left running"
            );

            // Budget: one backoff entry ⇒ two instances, then Disconnected.
            wait_for_state(
                &harness.state,
                ConnectionState::Disconnected,
                Duration::from_secs(60),
            )
            .await;
            let pids = read_pids(&pid_file);
            assert_eq!(
                pids.len(),
                2,
                "one automatic restart, then give up: {pids:?}"
            );
            for pid in &pids {
                assert!(
                    wait_unix_pid_dead(*pid, DEADLINE_AFTER_TEARDOWN).await,
                    "every hung instance is dead"
                );
            }
            assert!(harness.dispatcher.lock().await.is_empty());

            // Manual restart after the budget is spent: fresh attempt, works.
            std::fs::write(&flag, b"1").expect("flag");
            harness.control.request_restart();
            wait_for_state(
                &harness.state,
                ConnectionState::Ready,
                Duration::from_secs(20),
            )
            .await;
            let rx = harness.send(2).await;
            match tokio::time::timeout(Duration::from_secs(10), rx)
                .await
                .expect("bounded")
                .expect("delivered")
            {
                Outcome::Result(value) => assert_eq!(value["echo"], true),
                other => panic!("revived sidecar answers, got {other:?}"),
            }

            let leader = *read_pids(&pid_file).last().expect("revived leader pid");
            harness.kill().await;
            wait_for_state(
                &harness.state,
                ConnectionState::Disconnected,
                Duration::from_secs(20),
            )
            .await;
            assert!(wait_unix_pid_dead(leader, DEADLINE_AFTER_TEARDOWN).await);
        });
    }

    /// A sidecar announcing an unsupported protocol major never becomes
    /// `Ready`; the supervisor treats it as a failed candidate.
    #[cfg(unix)]
    #[test]
    fn unix_unsupported_protocol_major_never_becomes_ready() {
        let dir = tempfile::tempdir().expect("temp dir");
        let pid_file = dir.path().join("pids");
        let script = write_fake_sidecar(
            dir.path(),
            "future.sh",
            &format!(
                "printf '%s\\n' \"$$\" >> '{pid}'\nprintf 'DREAM-PROTOCOL: 2.0\\n'\nexec sleep 30",
                pid = pid_file.display()
            ),
        );
        let app = mock_app();
        let rt = test_runtime();
        rt.block_on(async move {
            let harness = SupervisorHarness::start(&app, supervisor_config(vec![script]));
            wait_for_state(
                &harness.state,
                ConnectionState::Disconnected,
                Duration::from_secs(60),
            )
            .await;
            // Never Ready: no writer was ever handed to a caller as usable.
            assert!(harness.writer_tx.lock().await.is_none());
            for pid in read_pids(&pid_file) {
                assert!(
                    wait_unix_pid_dead(pid, DEADLINE_AFTER_TEARDOWN).await,
                    "refused instance is torn down"
                );
            }
            harness.kill().await;
        });
    }

    // ---- SEC-09: containment lifecycle tests --------------------------------
    //
    // Contract: a contained child and every descendant it spawns must die with
    // the containment teardown; teardown must be idempotent; an already-exited
    // child must clean up without errors; containment setup failure must never
    // leave a running uncontained child behind.
    //
    // Ground rules these tests follow (see
    // `docs/dev/how-to/sidecar-lifecycle.md`):
    // - helper children are `/bin/sh` (POSIX) or `powershell.exe` (Windows),
    //   never the installed interpreter and never matched by process name;
    // - every assertion is by explicit PID reported through a pid file in a
    //   temp dir, with bounded polling (no unbounded waits, no sleeps without
    //   a deadline);
    // - the tests never signal any process other than the children they
    //   spawned, and never kill the test runner.
    //
    // Platform coverage:
    // - the process-group tests below run on every Unix (Linux and macOS are
    //   the supported matrix);
    // - the Job Object tests are `#[cfg(windows)]`: they compile and lint on
    //   Windows CI (`clippy --all-targets`) but the CI job skips `cargo test`
    //   on Windows for the tauri-winres/ComCtl32 reason documented in
    //   `.github/workflows/desktop-ci.yml`, so they execute on Windows dev
    //   machines (`cargo test --lib`) — documented in the SEC-09 audit;
    // - `PR_SET_PDEATHSIG` is deliberately absent (parent-*thread* semantics
    //   clash with tokio worker reaping) and Linux-only anyway, so there is
    //   nothing Linux-specific left to skip; the parent-death guarantees
    //   tested here are cross-platform.

    /// Bounded deadline for the helper to start and write its pid files.
    /// PowerShell can be slow to cold-start on Windows, hence 20 s.
    const HELPER_START_DEADLINE: Duration = Duration::from_secs(20);
    /// Bounded deadline for a *killed* pid to disappear (signal delivery +
    /// reparent reap by init). Generous; real teardown is sub-millisecond.
    const DEADLINE_AFTER_TEARDOWN: Duration = Duration::from_secs(10);

    /// Poll `path` until it holds a positive pid (the helper writes it right
    /// after it starts). `None` if the deadline expires — the caller asserts.
    async fn read_pid_file(path: &Path, deadline: Duration) -> Option<u32> {
        let start = Instant::now();
        loop {
            if let Ok(text) = std::fs::read_to_string(path) {
                if let Ok(pid) = text.trim().parse::<u32>() {
                    if pid > 0 {
                        return Some(pid);
                    }
                }
            }
            if start.elapsed() > deadline {
                return None;
            }
            tokio::time::sleep(Duration::from_millis(25)).await;
        }
    }

    #[cfg(unix)]
    fn unix_helper_command(dir: &Path, script: &str) -> tokio::process::Command {
        let mut cmd = tokio::process::Command::new("/bin/sh");
        cmd.arg("-c")
            .arg(script)
            .current_dir(dir)
            .env("DREAM_LIFECYCLE_DIR", dir)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .kill_on_drop(true);
        // Same containment configuration the production spawner applies.
        configure_containment(&mut cmd);
        cmd
    }

    #[cfg(unix)]
    async fn spawn_contained_unix_helper(dir: &Path, script: &str) -> (Child, SidecarContainment) {
        let mut cmd = unix_helper_command(dir, script);
        let child = cmd.spawn().expect("spawn /bin/sh helper");
        let containment = SidecarContainment::establish(&child)
            .expect("process-group containment on a freshly spawned helper");
        (child, containment)
    }

    #[cfg(unix)]
    fn unix_pid_alive(pid: u32) -> bool {
        let Ok(pid) = libc::pid_t::try_from(pid) else {
            return false;
        };
        // SAFETY: `kill(pid, 0)` is the standard POSIX liveness probe — it
        // validates the pid without delivering a signal and writes nothing.
        unsafe { libc::kill(pid, 0) == 0 }
    }

    #[cfg(unix)]
    async fn wait_unix_pid_dead(pid: u32, deadline: Duration) -> bool {
        let start = Instant::now();
        while unix_pid_alive(pid) {
            if start.elapsed() > deadline {
                return false;
            }
            tokio::time::sleep(Duration::from_millis(25)).await;
        }
        true
    }

    /// Teardown must terminate the contained child *and* its descendants, and
    /// the group id must be the child pid (a fresh group led by the sidecar —
    /// exactly what `killpg` needs to reach the whole tree).
    #[cfg(unix)]
    #[tokio::test]
    async fn unix_teardown_terminates_child_and_descendants() {
        let dir = tempfile::tempdir().expect("temp dir");
        let script = concat!(
            "printf %s \"$$\" > \"$DREAM_LIFECYCLE_DIR/leader.pid\"; ",
            "sleep 25 & ",
            "printf %s \"$!\" > \"$DREAM_LIFECYCLE_DIR/descendant.pid\"; ",
            "wait",
        );
        let (mut child, mut containment) = spawn_contained_unix_helper(dir.path(), script).await;

        let leader = read_pid_file(&dir.path().join("leader.pid"), HELPER_START_DEADLINE)
            .await
            .expect("helper writes its pid file promptly");
        let descendant = read_pid_file(&dir.path().join("descendant.pid"), HELPER_START_DEADLINE)
            .await
            .expect("helper reports its backgrounded sleep via pid file");
        assert_eq!(
            child.id(),
            Some(leader),
            "pid file matches the contained child"
        );

        // The child leads its own process group (the containment invariant),
        // and the descendant was born inside that group — both are reachable
        // by one `killpg`.
        assert_eq!(
            group_of(leader).expect("leader group"),
            i32::try_from(leader).expect("leader pid fits pid_t"),
            "contained child must lead its process group"
        );
        assert_eq!(
            group_of(descendant).expect("descendant group"),
            group_of(leader).expect("leader group"),
            "descendants inherit the containment group"
        );
        // The descendant must genuinely be alive before teardown, or the
        // post-teardown liveness check below could pass vacuously.
        assert!(unix_pid_alive(descendant), "descendant started");

        terminate_sidecar(&mut child, &mut containment)
            .await
            .expect("group teardown completes without error");

        // Leader: reaped by the teardown itself (no zombies, no spurious
        // errors). Descendant: must have been swept via the group signal.
        assert!(
            child.try_wait().expect("try_wait").is_some(),
            "teardown reaps the leader"
        );
        assert!(
            wait_unix_pid_dead(descendant, DEADLINE_AFTER_TEARDOWN).await,
            "the containment sweep must kill the descendant (pid {descendant})"
        );
    }

    /// Repeated teardown and teardown of an already-exited child must be
    /// no-op successes — cleanup is idempotent and must never fabricate an
    /// error, panic, or signal an unrelated process.
    #[cfg(unix)]
    #[tokio::test]
    async fn unix_teardown_is_idempotent_and_safe_after_natural_exit() {
        // (a) already-exited child: the grace wait sees the exit, the sweep
        // tolerates ESRCH, everything completes clean.
        let dir = tempfile::tempdir().expect("temp dir");
        let script = "printf %s \"$$\" > \"$DREAM_LIFECYCLE_DIR/leader.pid\"; sleep 1; exit 0";
        let (mut child, mut containment) = spawn_contained_unix_helper(dir.path(), script).await;
        child.wait().await.expect("helper exits on its own");
        terminate_sidecar(&mut child, &mut containment)
            .await
            .expect("teardown of an exited child is a clean no-op");

        // (b) repeated teardown on a live helper: the second call finds the
        // containment closed and the child reaped — still Ok, no signals sent
        // (a group that is empty answers ESRCH, which `close` absorbs).
        let dir = tempfile::tempdir().expect("temp dir");
        let script = "printf %s \"$$\" > \"$DREAM_LIFECYCLE_DIR/leader.pid\"; sleep 25";
        let (mut child, mut containment) = spawn_contained_unix_helper(dir.path(), script).await;
        terminate_sidecar(&mut child, &mut containment)
            .await
            .expect("first teardown");
        let leader = read_pid_file(&dir.path().join("leader.pid"), HELPER_START_DEADLINE)
            .await
            .expect("pid file written");
        assert!(
            wait_unix_pid_dead(leader, DEADLINE_AFTER_TEARDOWN).await,
            "first teardown kills the leader"
        );
        terminate_sidecar(&mut child, &mut containment)
            .await
            .expect("second teardown is idempotent");
    }

    /// When containment cannot be established the spawner must not hand the
    /// child to the supervisor: it is killed (and reaped via `kill_on_drop`)
    /// so an *uncontained* process can never linger. This drives the same
    /// `discard_uncontained_child` policy `spawn` uses.
    #[cfg(unix)]
    #[tokio::test]
    async fn unix_containment_setup_failure_does_not_leave_an_orphan() {
        let dir = tempfile::tempdir().expect("temp dir");
        let mut cmd = unix_helper_command(dir.path(), "sleep 25");
        let mut child = cmd.spawn().expect("spawn helper");
        let leader = child.id().expect("fresh child has a pid");
        assert!(unix_pid_alive(leader), "child is live before the discard");

        discard_uncontained_child(&mut child);

        let start = Instant::now();
        loop {
            if child.try_wait().expect("try_wait").is_some() {
                break;
            }
            assert!(
                start.elapsed() <= HELPER_START_DEADLINE,
                "a discarded uncontained child must terminate promptly"
            );
            tokio::time::sleep(Duration::from_millis(25)).await;
        }
        assert!(!unix_pid_alive(leader), "the child is gone");
    }

    /// The supervisor's restart ordering ("the old group is killed before the
    /// new instance starts") is structural: `terminate_sidecar` is awaited
    /// before the next spawn. This test mirrors that hand-off and asserts the
    /// new instance is contained in a *fresh* group.
    #[cfg(unix)]
    #[tokio::test]
    async fn unix_restart_tears_down_old_group_before_new_instance() {
        let dir_a = tempfile::tempdir().expect("temp dir a");
        let script = "printf %s \"$$\" > \"$DREAM_LIFECYCLE_DIR/leader.pid\"; sleep 25";
        let (mut child_a, mut containment_a) =
            spawn_contained_unix_helper(dir_a.path(), script).await;
        let leader_a = read_pid_file(&dir_a.path().join("leader.pid"), HELPER_START_DEADLINE)
            .await
            .expect("first helper reports its pid");

        // Awaited full teardown *before* the "restart" spawn:
        terminate_sidecar(&mut child_a, &mut containment_a)
            .await
            .expect("old instance torn down first");

        let dir_b = tempfile::tempdir().expect("temp dir b");
        let script_b = "printf %s \"$$\" > \"$DREAM_LIFECYCLE_DIR/leader.pid\"; sleep 25 & wait";
        let (mut child_b, mut containment_b) =
            spawn_contained_unix_helper(dir_b.path(), script_b).await;
        let leader_b = read_pid_file(&dir_b.path().join("leader.pid"), HELPER_START_DEADLINE)
            .await
            .expect("second helper reports its pid");
        assert_ne!(
            leader_a, leader_b,
            "the new instance is a different process"
        );
        assert_eq!(
            group_of(leader_b).expect("new leader group"),
            i32::try_from(leader_b).expect("pid fits pid_t"),
            "the new instance leads its own group"
        );

        terminate_sidecar(&mut child_b, &mut containment_b)
            .await
            .expect("second teardown");
        assert!(
            wait_unix_pid_dead(leader_a, DEADLINE_AFTER_TEARDOWN).await,
            "old leader stays dead (pid recycling never aliases a live group member we signal)"
        );
    }

    #[cfg(windows)]
    fn windows_helper_command(dir: &Path, script: &str) -> tokio::process::Command {
        // Prefer the well-known absolute path (no PATH dependence); fall back
        // to the bare name if SystemRoot is somehow unavailable.
        let powershell = match std::env::var("SystemRoot") {
            Ok(root) => Path::new(&root)
                .join("System32")
                .join("WindowsPowerShell")
                .join("v1.0")
                .join("powershell.exe"),
            Err(_) => std::path::PathBuf::from("powershell.exe"),
        };
        let mut cmd = tokio::process::Command::new(powershell);
        cmd.arg("-NoProfile")
            .arg("-NonInteractive")
            .arg("-Command")
            .arg(script)
            .current_dir(dir)
            .env("DREAM_LIFECYCLE_DIR", dir)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .kill_on_drop(true)
            // The sidecar's production console policy is applied to helpers
            // too, so the CREATE_NO_WINDOW + job combination is exercised.
            .creation_flags(sidecar_creation_flags());
        configure_containment(&mut cmd);
        cmd
    }

    #[cfg(windows)]
    async fn spawn_contained_windows_helper(
        dir: &Path,
        script: &str,
    ) -> (Child, SidecarContainment) {
        let mut cmd = windows_helper_command(dir, script);
        let child = cmd
            .spawn()
            .expect("spawn powershell helper (present on every Windows install)");
        let mut containment =
            SidecarContainment::establish(&child).expect("job object containment");
        // Mirror production ordering exactly: the helper is created suspended
        // and only starts running once it is a job member.
        let pid = child.id().expect("helper pid");
        assert!(
            windows_process_has_no_descendant(pid),
            "a suspended child cannot have created any descendant before assignment"
        );
        containment
            .release_startup_suspension()
            .expect("resume contained helper");
        (child, containment)
    }

    /// True when no live process reports `pid` as its parent. Used to prove the
    /// containment race is closed: before the resume, the suspended leader has
    /// executed nothing and therefore owns no descendant.
    #[cfg(windows)]
    fn windows_process_has_no_descendant(pid: u32) -> bool {
        use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
        use windows_sys::Win32::System::Diagnostics::ToolHelp::{
            CreateToolhelp32Snapshot, Process32First, Process32Next, PROCESSENTRY32,
            TH32CS_SNAPPROCESS,
        };
        // SAFETY: process-only snapshot; the `0` pid argument is ignored for
        // `TH32CS_SNAPPROCESS`.
        let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) };
        if snapshot == INVALID_HANDLE_VALUE {
            return true;
        }
        // SAFETY: plain-data struct; `dwSize` must be pre-filled.
        let mut entry: PROCESSENTRY32 = unsafe { core::mem::zeroed() };
        entry.dwSize = core::mem::size_of::<PROCESSENTRY32>() as u32;
        // SAFETY: valid snapshot handle and live out-param.
        let mut more = unsafe { Process32First(snapshot, &mut entry) };
        let mut found = false;
        while more != 0 {
            if entry.th32ParentProcessID == pid {
                found = true;
                break;
            }
            // SAFETY: same contract as `Process32First`.
            more = unsafe { Process32Next(snapshot, &mut entry) };
        }
        // SAFETY: closing the snapshot handle opened above.
        unsafe { CloseHandle(snapshot) };
        !found
    }

    /// `OpenProcess` + `GetExitCodeProcess` liveness probe on a pid *this test
    /// created*: cannot open ⇒ fully gone; openable with a real exit code ⇒
    /// exited (possibly still a handle-holding zombie) ⇒ treated as dead.
    #[cfg(windows)]
    fn windows_pid_dead(pid: u32) -> bool {
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::Threading::{
            GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
        };
        /// `StillActive` from winerror/winbase (no windows-sys 0.52 constant).
        const STILL_ACTIVE: u32 = 259;
        // SAFETY: `PROCESS_QUERY_LIMITED_INFORMATION` is read-only; the `0`
        // inherit flag (false) prevents handle inheritance.
        let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
        if handle == 0 {
            return true;
        }
        let mut code = 0u32;
        // SAFETY: `handle` is the handle opened directly above (NULL handled
        // already); `code` is a live out-param.
        let ok = unsafe { GetExitCodeProcess(handle, &mut code) };
        // SAFETY: closing the handle this probe opened, in every branch.
        unsafe { CloseHandle(handle) };
        ok == 0 || code != STILL_ACTIVE
    }

    #[cfg(windows)]
    async fn wait_windows_pid_dead(pid: u32, deadline: Duration) -> bool {
        let start = Instant::now();
        while !windows_pid_dead(pid) {
            if start.elapsed() > deadline {
                return false;
            }
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        true
    }

    #[cfg(windows)]
    fn windows_process_in_job(pid: u32, job: windows_sys::Win32::Foundation::HANDLE) -> bool {
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::JobObjects::IsProcessInJob;
        use windows_sys::Win32::System::Threading::{
            OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
        };
        // SAFETY: read-only query rights, no inheritance (`0` == false).
        let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
        if handle == 0 {
            return false;
        }
        let mut member = 0i32;
        // SAFETY: the just-opened process handle, the owned job handle and a
        // valid out-param — exactly the contract `IsProcessInJob` documents.
        let ok = unsafe { IsProcessInJob(handle, job, &mut member) };
        // SAFETY: close the handle this function opened, regardless of result.
        unsafe { CloseHandle(handle) };
        ok != 0 && member != 0
    }

    /// The Job Object must contain the child and every process it starts, and
    /// the teardown (TerminateJobObject + handle close, both kill-on-close)
    /// must take the whole tree down. No `taskkill`, no name matching.
    #[cfg(windows)]
    #[tokio::test]
    async fn windows_job_object_contains_child_and_descendants() {
        let dir = tempfile::tempdir().expect("temp dir");
        // The helper writes its own pid, starts a detached `ping.exe` that
        // writes its own pid, then idles. `Start-Process` inherits the job, so
        // the grandchild must end up inside the same job object.
        let script = concat!(
            r#"Set-Content -LiteralPath "$env:DREAM_LIFECYCLE_DIR\leader.pid" -Value $PID; "#,
            r#"$d = Start-Process -FilePath "$env:SystemRoot\System32\PING.EXE" "#,
            r#"-ArgumentList '-n','25','127.0.0.1' -PassThru -WindowStyle Hidden; "#,
            r#"Set-Content -LiteralPath "$env:DREAM_LIFECYCLE_DIR\descendant.pid" -Value $d.Id; "#,
            r#"Start-Sleep -Seconds 25"#,
        );
        let (mut child, mut containment) = spawn_contained_windows_helper(dir.path(), script).await;

        let leader = read_pid_file(&dir.path().join("leader.pid"), HELPER_START_DEADLINE)
            .await
            .expect("leader writes its pid file");
        let descendant = read_pid_file(&dir.path().join("descendant.pid"), HELPER_START_DEADLINE)
            .await
            .expect("leader reports the ping child via pid file");
        assert_eq!(
            child.id(),
            Some(leader),
            "pid file matches the contained child"
        );
        assert_ne!(leader, descendant, "the descendant is a separate process");
        assert!(
            !windows_pid_dead(descendant),
            "descendant is alive pre-teardown"
        );

        let job = containment
            .job
            .as_raw()
            .expect("job handle still open before teardown");
        assert!(
            windows_process_in_job(leader, job),
            "the sidecar child must be a member of the containment job"
        );
        assert!(
            windows_process_in_job(descendant, job),
            "processes spawned by a job member join the same job"
        );

        terminate_sidecar(&mut child, &mut containment)
            .await
            .expect("job teardown completes without error");

        assert!(
            child.try_wait().expect("try_wait").is_some(),
            "teardown reaps the leader"
        );
        assert!(
            wait_windows_pid_dead(descendant, DEADLINE_AFTER_TEARDOWN).await,
            "kill-on-close / TerminateJobObject must take the descendant down too"
        );
        assert!(
            wait_windows_pid_dead(leader, DEADLINE_AFTER_TEARDOWN).await,
            "the leader pid must stop answering the liveness probe"
        );
    }

    /// Repeated teardown + teardown of an already-exited child: the job handle
    /// close is take-based (idempotent) and `TerminateJobObject` on an empty
    /// job is absorbed, so both paths must complete `Ok`.
    #[cfg(windows)]
    #[tokio::test]
    async fn windows_teardown_is_idempotent_and_safe_after_natural_exit() {
        // (a) natural exit first.
        let dir = tempfile::tempdir().expect("temp dir");
        let script = concat!(
            r#"Set-Content -LiteralPath "$env:DREAM_LIFECYCLE_DIR\leader.pid" -Value $PID; "#,
            "Start-Sleep -Seconds 1; exit 0",
        );
        let (mut child, mut containment) = spawn_contained_windows_helper(dir.path(), script).await;
        child.wait().await.expect("helper exits on its own");
        terminate_sidecar(&mut child, &mut containment)
            .await
            .expect("teardown of an exited, contained child is a clean no-op");

        // (b) teardown twice on a live helper.
        let dir = tempfile::tempdir().expect("temp dir");
        let script = concat!(
            r#"Set-Content -LiteralPath "$env:DREAM_LIFECYCLE_DIR\leader.pid" -Value $PID; "#,
            "Start-Sleep -Seconds 25",
        );
        let (mut child, mut containment) = spawn_contained_windows_helper(dir.path(), script).await;
        let leader = read_pid_file(&dir.path().join("leader.pid"), HELPER_START_DEADLINE)
            .await
            .expect("helper reports its pid");
        terminate_sidecar(&mut child, &mut containment)
            .await
            .expect("first teardown");
        assert!(
            wait_windows_pid_dead(leader, DEADLINE_AFTER_TEARDOWN).await,
            "first teardown kills the leader"
        );
        terminate_sidecar(&mut child, &mut containment)
            .await
            .expect("second teardown is idempotent");
    }

    /// Setup-failure path (SEC-09): if anything between spawn and the resume
    /// fails, `spawn` closes the containment and discards the child. Because
    /// the child is still suspended it owns no descendant, so that teardown is
    /// provably complete. Simulated here by never resuming: closing the job
    /// must kill the suspended leader through KILL_ON_JOB_CLOSE.
    #[cfg(windows)]
    #[tokio::test]
    async fn windows_setup_failure_before_resume_leaves_nothing_running() {
        let dir = tempfile::tempdir().expect("temp dir");
        let script = "Start-Sleep -Seconds 25";
        let mut cmd = windows_helper_command(dir.path(), script);
        let mut child = cmd.spawn().expect("spawn powershell helper");
        let leader = child.id().expect("helper pid");
        let mut containment =
            SidecarContainment::establish(&child).expect("job object containment");
        // The pre-resume state the failure paths act on: contained, frozen,
        // childless.
        assert!(
            windows_process_has_no_descendant(leader),
            "a suspended leader cannot have spawned anything"
        );
        // Exactly what `spawn` does when the resume (or any later setup step)
        // fails.
        containment.close().expect("close job object");
        discard_uncontained_child(&mut child);
        assert!(
            wait_windows_pid_dead(leader, DEADLINE_AFTER_TEARDOWN).await,
            "the suspended leader is terminated by the setup-failure teardown"
        );
        assert!(
            windows_process_has_no_descendant(leader),
            "no descendant is left behind by the failure path"
        );
    }

    /// A pid that cannot exist must produce a typed establishment error, and
    /// must not be touched any other way (the helper never signals by guessed
    /// identity). This is the failure mode `spawn` reacts to by discarding the
    /// uncontained child rather than proceeding.
    #[cfg(windows)]
    #[test]
    fn windows_containment_setup_reports_typed_error_for_dead_pid() {
        // 0xFFFFFFFE sits above the system-reserved pid range (and 0xFFFFFFFF
        // is the API's own INVALID_HANDLE_VALUE sentinel) — guaranteed miss.
        let result = windows_job::contain_pid(0xFFFF_FFFE);
        let err = result.expect_err("a nonexistent pid cannot be contained");
        // An establishment error must never be a panic and must carry the OS
        // cause for the log line; nothing was created-and-leaked (JobHandle's
        // Drop closes any partial handle).
        assert!(
            err.raw_os_error().is_some(),
            "the platform cause is preserved"
        );
    }
}
