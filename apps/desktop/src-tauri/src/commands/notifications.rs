//! Native notification commands.
//!
//! # Platform behaviour
//!
//! The desktop backend of `tauri-plugin-notification` wraps `notify-rust`, which
//! delivers title/body/icon/sound and nothing else: it exposes **no action buttons
//! and no click callback** on macOS, Windows or Linux. Only the mobile backends
//! implement `registerActionTypes` / `onAction`.
//!
//! Dream therefore keeps interactive approvals inside the app (the approval sheet
//! specified in the design system) and treats a notification purely as an alert.
//! [`send_notification`] returns whether the notification was actually shown so the
//! frontend can raise an in-app toast whenever the OS path is unavailable, and
//! duplicate suppression is handled here rather than by an OS-level tag, which the
//! desktop backend does not support.

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Runtime};
use tauri_plugin_notification::{NotificationExt, PermissionState};

use crate::error::{Error, Result};

/// Window during which a repeat of the same notification `id` is suppressed.
const DEDUPE_WINDOW: Duration = Duration::from_secs(5);

/// Remembers when each notification id was last shown, to satisfy the
/// "no duplicate notifications" gate without OS tag support.
#[derive(Default)]
pub struct NotificationLog(Mutex<HashMap<String, Instant>>);

impl NotificationLog {
    /// Returns `true` when this id was shown recently and should be skipped.
    fn is_duplicate(&self, id: &str) -> bool {
        let mut guard = self
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());

        guard.retain(|_, seen| seen.elapsed() < DEDUPE_WINDOW);

        match guard.get(id) {
            Some(_) => true,
            None => {
                guard.insert(id.to_string(), Instant::now());
                false
            }
        }
    }
}

/// Payload accepted by [`send_notification`].
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NotificationRequest {
    /// Bold heading line.
    pub title: String,
    /// Body text.
    pub body: String,
    /// Optional correlation id. Used for duplicate suppression; also echoed back
    /// to the frontend so a click handled in-app can be routed to the right item.
    pub id: Option<String>,
    /// Thread/group identifier (macOS thread identifier, Android group).
    pub group: Option<String>,
    /// Android-only: notification cannot be dismissed by the user.
    pub ongoing: Option<bool>,
}

/// Outcome of a send attempt.
#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum SendOutcome {
    /// Handed to the OS notification service.
    Shown,
    /// Skipped: the same id was shown within the dedupe window.
    Duplicate,
    /// Skipped: the user denied notification permission.
    Denied,
}

/// Result of a permission query or request.
#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Permission {
    /// The user allowed notifications.
    Granted,
    /// The user denied notifications.
    Denied,
    /// No decision has been recorded yet.
    Prompt,
}

impl From<PermissionState> for Permission {
    fn from(state: PermissionState) -> Self {
        match state {
            PermissionState::Granted => Permission::Granted,
            PermissionState::Denied => Permission::Denied,
            _ => Permission::Prompt,
        }
    }
}

/// Returns the current notification permission without prompting.
///
/// On desktop the plugin always reports `granted`; the real gate is the OS
/// notification centre, which the app cannot query.
#[tauri::command]
pub fn notification_permission<R: Runtime>(app: AppHandle<R>) -> Result<Permission> {
    app.notification()
        .permission_state()
        .map(Permission::from)
        .map_err(|e| Error::Notification(e.to_string()))
}

/// Requests notification permission, prompting the user when undecided.
///
/// Called once on first launch. Platforms without a permission model resolve to
/// `granted` immediately.
#[tauri::command]
pub fn request_notification_permission<R: Runtime>(app: AppHandle<R>) -> Result<Permission> {
    let current = app
        .notification()
        .permission_state()
        .map_err(|e| Error::Notification(e.to_string()))?;

    if matches!(current, PermissionState::Granted | PermissionState::Denied) {
        return Ok(current.into());
    }

    app.notification()
        .request_permission()
        .map(Permission::from)
        .map_err(|e| Error::Notification(e.to_string()))
}

/// Sends a native notification, suppressing repeats of the same `id`.
#[tauri::command]
pub fn send_notification<R: Runtime>(
    app: AppHandle<R>,
    request: NotificationRequest,
) -> Result<SendOutcome> {
    use tauri::Manager;

    if let Some(id) = &request.id {
        if app.state::<NotificationLog>().is_duplicate(id) {
            return Ok(SendOutcome::Duplicate);
        }
    }

    let state = app
        .notification()
        .permission_state()
        .map_err(|e| Error::Notification(e.to_string()))?;

    let granted = match state {
        PermissionState::Granted => true,
        PermissionState::Denied => false,
        _ => matches!(
            app.notification()
                .request_permission()
                .map_err(|e| Error::Notification(e.to_string()))?,
            PermissionState::Granted
        ),
    };

    if !granted {
        return Ok(SendOutcome::Denied);
    }

    let mut builder = app
        .notification()
        .builder()
        .title(&request.title)
        .body(&request.body);

    if let Some(group) = &request.group {
        builder = builder.group(group);
    }
    if request.ongoing.unwrap_or(false) {
        builder = builder.ongoing();
    }

    builder
        .show()
        .map_err(|e| Error::Notification(e.to_string()))?;

    Ok(SendOutcome::Shown)
}
