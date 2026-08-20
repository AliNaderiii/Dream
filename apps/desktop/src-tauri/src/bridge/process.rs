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

/// How the sidecar binary is launched.
#[derive(Clone, Debug)]
pub struct SidecarConfig {
    /// Interpreter candidates, tried in order until one starts.
    /// `DREAM_SIDECAR_PYTHON` is a hard override: when set, it is the only
    /// candidate. Otherwise the order is `python`, `py` (the Windows
    /// launcher), `python3`.
    pub python: Vec<String>,
    /// Module to run (default `dream.bridge`, override via `DREAM_SIDECAR_MODULE`).
    pub module: String,
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
        Self { python, module }
    }

    /// Interpreter candidates to try, in order.
    pub fn candidates(&self) -> &[String] {
        &self.python
    }
}

impl Default for SidecarConfig {
    fn default() -> Self {
        Self::from_env(&|key| std::env::var(key).ok())
    }
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

        let stdin = child.stdin.take().expect("piped stdin");
        let stdout = child.stdout.take().expect("piped stdout");

        // Writer task: drains the request channel and writes newline-framed lines.
        let (tx, mut rx) = mpsc::channel::<String>(64);
        {
            let mut guard = writer_tx.lock().await;
            *guard = Some(tx);
        }
        let writer = tauri::async_runtime::spawn(async move {
            let mut stdin = stdin;
            while let Some(line) = rx.recv().await {
                if stdin.write_all(line.as_bytes()).await.is_err() {
                    break;
                }
                if stdin.write_all(b"\n").await.is_err() {
                    break;
                }
                let _ = stdin.flush().await;
            }
            // Closing stdin signals EOF to the sidecar → graceful shutdown.
            let _ = stdin.shutdown().await;
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
        let _ = child.start_kill();
        let _ = child.wait().await;

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
            Err(err) => log::warn!("bridge: failed to spawn `{candidate}`: {err}"),
        }
    }
    None
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

    // Reader loop.
    while let Ok(Some(line)) = reader.next_line().await {
        *last_activity.lock().await = Instant::now();

        if line.starts_with("DREAM-PROTOCOL:") {
            set_state(app, state, ConnectionState::Ready);
            reached_ready = true;
            continue;
        }

        let Some(parsed) = framing::parse(&line) else {
            log::debug!("bridge: skipping unparseable line");
            continue;
        };
        match parsed {
            ParsedMessage::Response { id, outcome } => {
                dispatcher.lock().await.resolve(id, outcome);
            }
            ParsedMessage::Notification { method, params } => {
                if method == "stream.chunk" {
                    if let Some(id) = params.get("id").and_then(|v| v.as_u64()) {
                        dispatcher.lock().await.route_stream(id, params);
                    }
                }
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

/// Spawn the Python sidecar with piped stdio under interpreter `exe`.
fn spawn(config: &SidecarConfig, exe: &str) -> std::io::Result<Child> {
    // kill_on_drop prevents the sidecar from outliving the app on POSIX.
    let mut cmd = tokio::process::Command::new(exe);
    cmd.args(["-u", "-m", &config.module])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .kill_on_drop(true);
    if let Ok(path) = std::env::var("DREAM_PYTHONPATH") {
        cmd.env("PYTHONPATH", path);
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
}
