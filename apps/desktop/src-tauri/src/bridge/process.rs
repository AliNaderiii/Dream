//! Sidecar process supervision.
//!
//! Spawns the Python sidecar (`<python> -m dream.bridge`), wires its stdin/stdout
//! to the dispatcher, monitors it with a heartbeat, and restarts it on crash
//! with backoff (per the failure-recovery table in the master prompt):
//!
//! - max 3 restarts, 2 s / 5 s / 10 s backoff;
//! - heartbeat ping every 5 s; no traffic for 15 s ⇒ hang ⇒ kill ⇒ restart;
//! - on restart, every in-flight request is rejected with `INTERNAL_ERROR`.
//!
//! State transitions are written to the shared [`SharedState`] and emitted as
//! `bridge://state` events so the frontend status indicator stays in sync.

use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde_json::json;
use tauri::{Emitter, Runtime};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdout};
use tokio::sync::{mpsc, Mutex};

use crate::bridge::dispatcher::Dispatcher;
use crate::bridge::framing::{self, code, ParsedMessage};
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
pub(crate) fn ensure_sidecar_data_root(root: &Path) -> Result<PathBuf, BridgeError> {
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
const STATE_EVENT: &str = "bridge://state";

/// Run the supervisor loop until the sidecar stays up or all retries are spent.
///
/// Returns when the bridge gives up (state `Disconnected`) — the frontend can
/// kick it again with `bridge_restart`.
pub async fn run_supervisor<R: Runtime>(
    app: tauri::AppHandle<R>,
    state: Arc<SharedState>,
    dispatcher: Arc<Mutex<Dispatcher>>,
    writer_tx: Arc<Mutex<Option<mpsc::Sender<String>>>>,
    config: SidecarConfig,
    killed: Arc<std::sync::atomic::AtomicBool>,
) {
    let mut attempt = 0usize;
    loop {
        if killed.load(std::sync::atomic::Ordering::Acquire) {
            set_state(&app, &state, ConnectionState::Disconnected);
            return;
        }
        set_state(&app, &state, ConnectionState::Connecting);

        let ended = start_instance(&app, &state, &dispatcher, &writer_tx, &config).await;
        // Reject everything that was in flight when the instance died.
        reject_pending(&dispatcher).await;
        // Both exit causes take the same recovery path; the distinction is kept
        // for diagnostics/logging.
        match ended {
            InstanceOutcome::Exited | InstanceOutcome::Hung => {}
        }

        if killed.load(std::sync::atomic::Ordering::Acquire) {
            set_state(&app, &state, ConnectionState::Disconnected);
            return;
        }
        if attempt >= RESTART_BACKOFF_SECS.len() {
            set_state(&app, &state, ConnectionState::Disconnected);
            return;
        }
        set_state(&app, &state, ConnectionState::Restarting);
        let backoff = RESTART_BACKOFF_SECS[attempt];
        attempt += 1;
        tokio::time::sleep(Duration::from_secs(backoff)).await;
    }
}

/// Outcome of one sidecar instance's lifetime.
#[derive(Debug)]
enum InstanceOutcome {
    /// The process exited or its stdout closed.
    Exited,
    /// The heartbeat timed out and the process was killed.
    Hung,
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
) -> InstanceOutcome {
    let mut remaining: &[String] = config.candidates();
    loop {
        let Some((index, exe, mut child)) = spawn_first(remaining, |exe| spawn(config, exe)) else {
            // No candidate could even be launched. Leave the state to the
            // supervisor (it goes Disconnected after the retries) and say why
            // in both languages.
            log_python_required(config.candidates());
            return InstanceOutcome::Exited;
        };
        // Drop the used candidates so the next discovery round resumes where
        // this one stopped.
        remaining = &remaining[index + 1..];

        let (stdin, stdout) = match take_piped_stdio(&mut child) {
            Ok(pair) => pair,
            Err(err) => {
                log::error!("bridge: `{exe}` cannot be used as a sidecar: {err}");
                if let Err(kill_err) = child.start_kill() {
                    log::warn!(
                        "bridge: killing `{exe}` after stdio failure: {}",
                        BridgeError::io("kill sidecar", kill_err)
                    );
                }
                if let Err(wait_err) = child.wait().await {
                    log::warn!(
                        "bridge: waiting for `{exe}` after stdio failure: {}",
                        BridgeError::io("wait for sidecar", wait_err)
                    );
                }
                continue;
            }
        };

        // Writer task: drains the request channel and writes newline-framed lines.
        let (tx, mut rx) = mpsc::channel::<String>(64);
        {
            let mut guard = writer_tx.lock().await;
            *guard = Some(tx);
        }
        let writer = tauri::async_runtime::spawn(async move {
            let mut stdin = stdin;
            while let Some(line) = rx.recv().await {
                if let Err(err) = stdin.write_all(line.as_bytes()).await {
                    log::warn!(
                        "bridge: writing to sidecar stdin failed: {}",
                        BridgeError::io("write sidecar stdin", err)
                    );
                    break;
                }
                if let Err(err) = stdin.write_all(b"\n").await {
                    log::warn!(
                        "bridge: writing newline to sidecar stdin failed: {}",
                        BridgeError::io("write sidecar stdin newline", err)
                    );
                    break;
                }
                if let Err(err) = stdin.flush().await {
                    log::warn!(
                        "bridge: flushing sidecar stdin failed: {}",
                        BridgeError::io("flush sidecar stdin", err)
                    );
                    break;
                }
            }
            // Closing stdin signals EOF to the sidecar → graceful shutdown.
            if let Err(err) = stdin.shutdown().await {
                log::warn!(
                    "bridge: shutting down sidecar stdin failed: {}",
                    BridgeError::io("shutdown sidecar stdin", err)
                );
            }
        });

        let last_activity = Arc::new(Mutex::new(Instant::now()));
        let instance = supervise_reader(app, state, dispatcher, writer_tx, stdout, &last_activity);
        let (outcome, reached_ready) = instance.await;

        // Tear down: kill the child if still running and drop the writer sender.
        {
            let mut guard = writer_tx.lock().await;
            *guard = None;
        }
        writer.abort();
        if let Err(err) = child.start_kill() {
            log::warn!(
                "bridge: killing sidecar failed: {}",
                BridgeError::io("kill sidecar", err)
            );
        }
        if let Err(err) = child.wait().await {
            log::warn!(
                "bridge: waiting for sidecar exit failed: {}",
                BridgeError::io("wait for sidecar", err)
            );
        }

        if reached_ready {
            log::info!("bridge: instance running under `{exe}` ended ({outcome:?})");
            return outcome;
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
    F: FnMut(&'a str) -> std::io::Result<T>,
{
    for (index, candidate) in candidates.iter().enumerate() {
        match probe(candidate) {
            Ok(item) => return Some((index, candidate.as_str(), item)),
            Err(err) => log::warn!(
                "bridge: failed to spawn `{candidate}`: {}",
                BridgeError::io("spawn sidecar", err)
            ),
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
) -> Result<(tokio::process::ChildStdin, ChildStdout), BridgeError> {
    require_piped_stdio(child.stdin.take(), child.stdout.take())
}

/// Map optional stdio handles to a typed error. Extracted so the missing-pipe
/// path can be unit-tested without spawning a process.
pub(crate) fn require_piped_stdio<I, O>(
    stdin: Option<I>,
    stdout: Option<O>,
) -> Result<(I, O), BridgeError> {
    let stdin = stdin
        .ok_or_else(|| BridgeError::SidecarCrashed("sidecar spawned without piped stdin".into()))?;
    let stdout = stdout.ok_or_else(|| {
        BridgeError::SidecarCrashed("sidecar spawned without piped stdout".into())
    })?;
    Ok((stdin, stdout))
}

/// Read stdout until EOF, routing messages to the dispatcher. Returns `Hung`
/// if the heartbeat watchdog fired (it kills the child via the returned signal),
/// plus whether the protocol handshake (`DREAM-PROTOCOL:`) was ever seen.
async fn supervise_reader<R: Runtime>(
    app: &tauri::AppHandle<R>,
    state: &Arc<SharedState>,
    dispatcher: &Arc<Mutex<Dispatcher>>,
    writer_tx: &Arc<Mutex<Option<mpsc::Sender<String>>>>,
    stdout: ChildStdout,
    last_activity: &Arc<Mutex<Instant>>,
) -> (InstanceOutcome, bool) {
    let mut reader = BufReader::new(stdout).lines();
    let hung = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let hung_clone = Arc::clone(&hung);
    let mut reached_ready = false;

    // Heartbeat watchdog: ping every 5 s; if no traffic for 15 s, flag a hang.
    let writer_hb = Arc::clone(writer_tx);
    let last_hb = Arc::clone(last_activity);
    let heartbeat = tauri::async_runtime::spawn(async move {
        let mut seq: u64 = 1_000_000; // heartbeat ids live above frontend ids
        loop {
            tokio::time::sleep(HEARTBEAT_INTERVAL).await;
            // Send a ping through the writer. The ping id is not registered with
            // the dispatcher, so its response is dropped — but reading it still
            // refreshes `last_activity`, proving the sidecar is responsive.
            // Clone the sender out of the guard before awaiting the send.
            let tx = writer_hb.lock().await.as_ref().cloned();
            if let Some(tx) = tx {
                let line = framing::request_line(seq, "health.check", &json!({}));
                let _ = tx.send(line).await;
                seq += 1;
            }
            let stale = {
                let last = *last_hb.lock().await;
                last.elapsed() > HEARTBEAT_TIMEOUT
            };
            if stale {
                hung_clone.store(true, std::sync::atomic::Ordering::Release);
                return;
            }
        }
    });

    // Reader loop. I/O and UTF-8 failures are logged and treated as instance
    // death (the supervisor restarts); malformed JSON-RPC is skipped with
    // context so a single bad line cannot take the sidecar down.
    loop {
        match reader.next_line().await {
            Ok(Some(line)) => {
                *last_activity.lock().await = Instant::now();

                if line.starts_with("DREAM-PROTOCOL:") {
                    set_state(app, state, ConnectionState::Ready);
                    reached_ready = true;
                    continue;
                }

                match framing::parse(&line) {
                    Ok(ParsedMessage::Response { id, outcome }) => {
                        dispatcher.lock().await.resolve(id, outcome);
                    }
                    Ok(ParsedMessage::Notification { method, params }) => {
                        if method == "stream.chunk" {
                            if let Some(id) = params.get("id").and_then(|v| v.as_u64()) {
                                dispatcher.lock().await.route_stream(id, params);
                            }
                        }
                    }
                    Err(err) => {
                        log::debug!("bridge: skipping unparseable line: {err}");
                    }
                }
            }
            Ok(None) => break,
            Err(err) => {
                log::warn!(
                    "bridge: failed reading sidecar stdout: {}",
                    BridgeError::io("read sidecar stdout", err)
                );
                break;
            }
        }
    }

    heartbeat.abort();
    let outcome = if hung.load(std::sync::atomic::Ordering::Acquire) {
        log::warn!("bridge: sidecar heartbeat timed out — restarting");
        InstanceOutcome::Hung
    } else {
        InstanceOutcome::Exited
    };
    (outcome, reached_ready)
}

/// Windows `CREATE_NO_WINDOW` (0x08000000): spawn the sidecar without a
/// visible console window, so discovery retries (and the Windows Store
/// `python` stub) do not flash a cmd window at the user.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

/// Creation flags for the sidecar process on the host platform.
///
/// On Windows we hide the console window (CREATE_NO_WINDOW); on POSIX there is
/// no such flag and the function returns 0. The POSIX variant is only compiled
/// in test builds to avoid a `dead_code` lint on the lib target.
///
/// The function is pure and cfg-gated so it can be unit-tested without spawning
/// a real process.
#[cfg(windows)]
pub(crate) fn sidecar_creation_flags() -> u32 {
    CREATE_NO_WINDOW
}

/// POSIX stub — only compiled in test builds so `cargo clippy --lib` does not
/// report it as dead code.
#[cfg(all(not(windows), test))]
pub(crate) fn sidecar_creation_flags() -> u32 {
    0
}

/// Spawn the Python sidecar with piped stdio under interpreter `exe`.
fn spawn(config: &SidecarConfig, exe: &str) -> std::io::Result<Child> {
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
    cmd.spawn()
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

/// Reject every in-flight request after a crash/restart.
async fn reject_pending(dispatcher: &Arc<Mutex<Dispatcher>>) {
    dispatcher
        .lock()
        .await
        .fail_all(code::INTERNAL_ERROR, "sidecar restarted");
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
                Err(io::Error::new(
                    io::ErrorKind::NotFound,
                    "no such interpreter",
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
            Err(io::Error::new(io::ErrorKind::NotFound, "missing"))
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
            matches!(err, BridgeError::SidecarCrashed(ref msg) if msg.contains("stdin")),
            "expected SidecarCrashed for missing stdin, got {err:?}"
        );

        let err = require_piped_stdio::<i32, i32>(Some(1), None).expect_err("stdout");
        assert!(
            matches!(err, BridgeError::SidecarCrashed(ref msg) if msg.contains("stdout")),
            "expected SidecarCrashed for missing stdout, got {err:?}"
        );

        let (stdin, stdout) = require_piped_stdio(Some(1), Some(2)).expect("both present");
        assert_eq!((stdin, stdout), (1, 2));
    }
}
