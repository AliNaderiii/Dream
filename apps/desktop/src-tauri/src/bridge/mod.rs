//! The Dream bridge: a supervised JSON-RPC sidecar over stdio.
//!
//! Architecture (see `docs/bridge/protocol.md`):
//!
//! - [`state`] — lock-free connection state, emitted as `bridge://state`.
//! - [`framing`] — pure JSON-RPC encode/decode (unit-tested).
//! - [`dispatcher`] — pending-request tracking with stream channels (unit-tested).
//! - [`process`] — sidecar spawn, read loop, heartbeat, restart-with-backoff.
//!
//! The frontend talks to four commands — `bridge_send`, `bridge_status`,
//! `bridge_restart`, `bridge_kill` — and listens to `bridge://chunk` /
//! `bridge://state` events (see `src/lib/bridge/`).

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use serde::Serialize;
use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager, Runtime};
use tokio::sync::Mutex;

use crate::bridge::dispatcher::{Dispatcher, RequestChannels};
use crate::bridge::framing::{self, Outcome};
use crate::bridge::process::{run_supervisor, SidecarConfig};
use crate::bridge::state::{ConnectionState, SharedState};

pub mod dispatcher;
pub mod framing;
pub mod process;
pub mod state;

/// Events emitted to the frontend.
const CHUNK_EVENT: &str = "bridge://chunk";
const STATE_EVENT: &str = "bridge://state";

/// A structured bridge error, serialised to `{ code, message, data? }` for the
/// frontend so it can branch on taxonomy (`src/lib/bridge/errors.ts`).
#[derive(Debug, Serialize)]
pub struct BridgeError {
    pub code: i32,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

impl BridgeError {
    /// Wrap a structured RPC error from the sidecar.
    pub fn rpc(code: i32, message: String, data: Option<Value>) -> Self {
        Self { code, message, data }
    }

    /// The sidecar is not connected / not yet ready.
    pub fn not_ready() -> Self {
        Self {
            code: framing::code::INTERNAL_ERROR,
            message: "bridge is not connected".to_string(),
            data: None,
        }
    }

    /// An internal bridge failure (channel closed, etc.).
    pub fn internal(message: &str) -> Self {
        Self {
            code: framing::code::INTERNAL_ERROR,
            message: message.to_string(),
            data: None,
        }
    }
}

impl std::fmt::Display for BridgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "bridge error {}: {}", self.code, self.message)
    }
}

impl std::error::Error for BridgeError {}

/// Owns the shared bridge components and exposes the operations the commands
/// need. Managed directly as `Arc<Bridge<R>>` (it is `Send + Sync`).
pub struct Bridge<R: Runtime> {
    app: AppHandle<R>,
    state: Arc<SharedState>,
    dispatcher: Arc<Mutex<Dispatcher>>,
    writer_tx: Arc<Mutex<Option<tokio::sync::mpsc::Sender<String>>>>,
    killed: Arc<AtomicBool>,
    config: SidecarConfig,
}

/// Build and register the bridge on the app. Call once from `setup`.
pub fn init<R: Runtime>(app: &AppHandle<R>) {
    let bridge = Arc::new(Bridge::new(app.clone()));
    app.manage(Arc::clone(&bridge));
    bridge.start();
}

impl<R: Runtime> Bridge<R> {
    /// Construct a bridge with fresh, empty coordination state.
    fn new(app: AppHandle<R>) -> Self {
        Self {
            app,
            state: Arc::new(SharedState::default()),
            dispatcher: Arc::new(Mutex::new(Dispatcher::new())),
            writer_tx: Arc::new(Mutex::new(None)),
            killed: Arc::new(AtomicBool::new(false)),
            config: SidecarConfig::default(),
        }
    }

    /// Start the sidecar supervisor. Returns immediately; supervision runs in
    /// the background for the lifetime of the app.
    fn start(self: &Arc<Self>) {
        let app = self.app.clone();
        let state = Arc::clone(&self.state);
        let dispatcher = Arc::clone(&self.dispatcher);
        let writer_tx = Arc::clone(&self.writer_tx);
        let config = self.config.clone();
        let killed = Arc::clone(&self.killed);
        tauri::async_runtime::spawn(async move {
            run_supervisor(app, state, dispatcher, writer_tx, config, killed).await;
        });
    }

    /// Send a request and await its final outcome. Stream chunks for this id are
    /// emitted as `bridge://chunk` events while we wait.
    pub async fn send_request(
        &self,
        id: u64,
        method: String,
        params: Value,
    ) -> Result<Value, BridgeError> {
        if self.state.get() != ConnectionState::Ready {
            return Err(BridgeError::not_ready());
        }

        let RequestChannels { final_rx, stream_rx } = self.dispatcher.lock().await.register(id);

        // Forward stream chunks to the frontend as they arrive.
        let app = self.app.clone();
        tauri::async_runtime::spawn(async move {
            let mut stream_rx = stream_rx;
            while let Some(chunk) = stream_rx.recv().await {
                let _ = app.emit(CHUNK_EVENT, chunk);
            }
        });

        // Write the request line to the sidecar. Clone the sender out of the
        // guard before awaiting the send (clippy:await_holding_lock).
        let line = framing::request_line(id, &method, &params);
        let tx = self.writer_tx.lock().await.as_ref().cloned();
        match tx {
            Some(tx) => tx.send(line).await.map_err(|_| BridgeError::not_ready())?,
            None => return Err(BridgeError::not_ready()),
        }

        match final_rx.await.map_err(|_| BridgeError::internal("sidecar closed"))? {
            Outcome::Result(value) => Ok(value),
            Outcome::Error { code, message, data } => Err(BridgeError::rpc(code, message, data)),
        }
    }

    /// Current connection state (for the status indicator).
    pub fn status(&self) -> ConnectionState {
        self.state.get()
    }

    /// Restart the sidecar: close the writer so the current instance exits and
    /// the supervisor respawns it (pending requests are rejected on exit).
    pub async fn restart(&self) {
        self.killed.store(false, Ordering::Release);
        self.state.set(ConnectionState::Restarting);
        let _ = self.app.emit(STATE_EVENT, ConnectionState::Restarting);
        *self.writer_tx.lock().await = None;
    }

    /// Stop the bridge for good (no further restarts). Used on quit / diagnostics.
    pub fn kill(&self) {
        self.killed.store(true, Ordering::Release);
        // Drop the writer sender to end the current instance promptly.
        if let Ok(mut guard) = self.writer_tx.try_lock() {
            *guard = None;
        }
        self.state.set(ConnectionState::Disconnected);
        let _ = self.app.emit(STATE_EVENT, ConnectionState::Disconnected);
    }
}

/// Look up the managed bridge and clone the `Arc` out. Returns `not_ready`
/// when the bridge has not been initialised (e.g. on mobile, or before
/// `init`), instead of panicking.
fn bridge<R: Runtime>(app: &AppHandle<R>) -> Result<Arc<Bridge<R>>, BridgeError> {
    app.try_state::<Arc<Bridge<R>>>()
        .map(|state| state.inner().clone())
        .ok_or_else(BridgeError::not_ready)
}

/// Send a JSON-RPC request to the sidecar and await its result.
///
/// Stream chunks for `id` are emitted as `bridge://chunk` events; the frontend
/// routes them by `id` (see `BridgeClient.stream`).
#[tauri::command]
pub async fn bridge_send<R: Runtime>(
    app: AppHandle<R>,
    id: u64,
    method: String,
    params: Value,
) -> Result<Value, BridgeError> {
    let bridge = bridge(&app)?;
    bridge.send_request(id, method, params).await
}

/// Read the current connection state.
#[tauri::command]
pub fn bridge_status<R: Runtime>(app: AppHandle<R>) -> Result<ConnectionState, BridgeError> {
    Ok(bridge(&app)?.status())
}

/// Restart the sidecar.
#[tauri::command]
pub async fn bridge_restart<R: Runtime>(app: AppHandle<R>) -> Result<(), BridgeError> {
    bridge(&app)?.restart().await;
    Ok(())
}

/// Kill the bridge (no further auto-restart).
#[tauri::command]
pub fn bridge_kill<R: Runtime>(app: AppHandle<R>) -> Result<(), BridgeError> {
    bridge(&app)?.kill();
    Ok(())
}
