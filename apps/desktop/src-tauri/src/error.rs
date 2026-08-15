//! Error type shared by every Tauri command in the desktop shell.
//!
//! Tauri requires a command's error type to implement [`serde::Serialize`], which
//! `Box<dyn std::error::Error>` does not. This enum is the idiomatic Tauri 2
//! equivalent: it implements [`std::error::Error`] (via `thiserror`) so it composes
//! with the `?` operator, and serializes to a plain string for the frontend.

use serde::{Serialize, Serializer};

/// Every failure mode a Dream desktop command can surface to the frontend.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// A Tauri core operation failed (window creation, menu building, ...).
    #[error("{0}")]
    Tauri(#[from] tauri::Error),

    /// Filesystem access failed.
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    /// A window with the requested label does not exist.
    #[error("window `{0}` was not found")]
    WindowNotFound(String),

    /// A path failed validation (missing, outside the workspace, not canonicalizable).
    #[error("{0}")]
    InvalidPath(String),

    /// A native dialog could not be shown or its result could not be read.
    #[error("dialog error: {0}")]
    Dialog(String),

    /// A native notification could not be delivered.
    #[error("notification error: {0}")]
    Notification(String),

    /// The tray icon or its menu could not be updated.
    #[error("tray error: {0}")]
    Tray(String),
}

impl Serialize for Error {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

/// Convenience alias used by all command signatures.
pub type Result<T, E = Error> = std::result::Result<T, E>;
