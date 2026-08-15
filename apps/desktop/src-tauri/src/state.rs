//! Process-wide application state for the desktop shell.
//!
//! The shell owns only presentation state (agent status, pending approvals,
//! workspace root, window behaviour preferences). Conversation, memory and
//! provider state live in the Python core and arrive over the sidecar bridge
//! introduced in P-02.

use std::path::PathBuf;
use std::sync::{Mutex, MutexGuard};

use serde::{Deserialize, Serialize};
use tauri::menu::MenuItem;
use tauri::Runtime;

/// Lifecycle of the Dream agent, as reflected in the tray tooltip and status bar.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AgentStatus {
    /// Connected and waiting for work.
    #[default]
    Idle,
    /// Actively processing a turn.
    Running,
    /// Explicitly paused by the user from the tray or UI.
    Paused,
    /// The agent (or its bridge) reported a fault.
    Error,
    /// The Python core is not reachable yet.
    Offline,
}

impl AgentStatus {
    /// Human-readable label used in the tray tooltip.
    pub fn label(self) -> &'static str {
        match self {
            AgentStatus::Idle => "Idle",
            AgentStatus::Running => "Running",
            AgentStatus::Paused => "Paused",
            AgentStatus::Error => "Error",
            AgentStatus::Offline => "Offline",
        }
    }
}

/// Serializable view of [`AppState`], returned by `get_app_state` and emitted on change.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppStateSnapshot {
    /// Current agent lifecycle status.
    pub agent_status: AgentStatus,
    /// Number of tool calls waiting for human approval.
    pub pending_approvals: u32,
    /// Root directory every file operation is confined to, when set.
    pub workspace_root: Option<PathBuf>,
    /// Hide to tray instead of minimising to the taskbar.
    pub minimize_to_tray: bool,
    /// Hide to tray instead of quitting when the window is closed.
    pub close_to_tray: bool,
}

impl Default for AppStateSnapshot {
    fn default() -> Self {
        Self {
            agent_status: AgentStatus::default(),
            pending_approvals: 0,
            workspace_root: None,
            minimize_to_tray: false,
            close_to_tray: true,
        }
    }
}

/// Thread-safe container registered with `app.manage(...)`.
#[derive(Debug, Default)]
pub struct AppState {
    inner: Mutex<AppStateSnapshot>,
}

impl AppState {
    /// Locks the state, recovering from poisoning rather than propagating a panic.
    ///
    /// A poisoned lock means another thread panicked mid-update; the shell's state
    /// is plain data with no invariants to repair, so continuing is safe and is
    /// strongly preferable to taking the whole app down.
    pub fn lock(&self) -> MutexGuard<'_, AppStateSnapshot> {
        self.inner.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// Returns a copy of the current state.
    pub fn snapshot(&self) -> AppStateSnapshot {
        self.lock().clone()
    }
}

/// Handles to tray menu items whose enabled state tracks [`AgentStatus`].
///
/// Stored in managed state so `set_agent_status` can toggle them without
/// rebuilding the menu. Generic over the runtime so it matches the menu items
/// produced by a generic `init`, and so tests can use the mock runtime.
pub struct TrayHandles<R: Runtime> {
    /// "Pause Agent" — disabled while already paused.
    pub pause: MenuItem<R>,
    /// "Resume Agent" — enabled only while paused.
    pub resume: MenuItem<R>,
}
