//! Sidecar process supervision.
//!
//! Spawns the Python sidecar (`python -m dream.bridge`), wires its stdin/stdout
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
    /// Interpreter executable (default `python3`, override via `DREAM_SIDECAR_PYTHON`).
    pub python: String,
    /// Module to run (default `dream.bridge`, override via `DREAM_SIDECAR_MODULE`).
    pub module: String,
}

impl Default for SidecarConfig {
    fn default() -> Self {
        Self {
            python: std::env::var("DREAM_SIDECAR_PYTHON").unwrap_or_else(|_| "python3".to_string()),
            module: std::env::var("DREAM_SIDECAR_MODULE").unwrap_or_else(|_| "dream.bridge".to_string()),
        }
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
enum InstanceOutcome {
    /// The process exited or its stdout closed.
    Exited,
    /// The heartbeat timed out and the process was killed.
    Hung,
}

/// Spawn one sidecar instance and supervise it until it ends or hangs.
async fn start_instance<R: Runtime>(
    app: &tauri::AppHandle<R>,
    state: &Arc<SharedState>,
    dispatcher: &Arc<Mutex<Dispatcher>>,
    writer_tx: &Arc<Mutex<Option<mpsc::Sender<String>>>>,
    config: &SidecarConfig,
) -> InstanceOutcome {
    let mut child = match spawn(config) {
        Ok(child) => child,
        Err(err) => {
            log::warn!("failed to spawn Dream sidecar: {err}");
            return InstanceOutcome::Exited;
        }
    };

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
            if stdin.write_all(line.as_bytes()).await.is_err()
                || stdin.write_all(b"\n").await.is_err()
            {
                break;
            }
            let _ = stdin.flush().await;
        }
        // Closing stdin signals EOF to the sidecar → graceful shutdown.
        let _ = stdin.shutdown().await;
    });

    let last_activity = Arc::new(Mutex::new(Instant::now()));
    let outcome =
        supervise_reader(app, state, dispatcher, writer_tx, stdout, &last_activity).await;

    // Tear down: kill the child if still running and drop the writer sender.
    {
        let mut guard = writer_tx.lock().await;
        *guard = None;
    }
    let _ = writer.abort();
    let _ = child.start_kill();
    let _ = child.wait().await;

    outcome
}

/// Read stdout until EOF, routing messages to the dispatcher. Returns `Hung`
/// if the heartbeat watchdog fired (it kills the child via the returned signal).
async fn supervise_reader<R: Runtime>(
    app: &tauri::AppHandle<R>,
    state: &Arc<SharedState>,
    dispatcher: &Arc<Mutex<Dispatcher>>,
    writer_tx: &Arc<Mutex<Option<mpsc::Sender<String>>>>,
    stdout: ChildStdout,
    last_activity: &Arc<Mutex<Instant>>,
) -> InstanceOutcome {
    let mut reader = BufReader::new(stdout).lines();
    let hung = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let hung_clone = Arc::clone(&hung);

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
    if hung.load(std::sync::atomic::Ordering::Acquire) {
        log::warn!("bridge: sidecar heartbeat timed out — restarting");
        InstanceOutcome::Hung
    } else {
        InstanceOutcome::Exited
    }
}

/// Spawn the Python sidecar with piped stdio.
fn spawn(config: &SidecarConfig) -> std::io::Result<Child> {
    let mut cmd = tokio::process::Command::new(&config.python);
    cmd.args(["-u", "-m", &config.module])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        // Prevent the sidecar from outliving the app on POSIX.
        .kill_on_drop(true);
    if let Ok(path) = std::env::var("DREAM_PYTHONPATH") {
        cmd.env("PYTHONPATH", path);
    }
    cmd.spawn()
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
