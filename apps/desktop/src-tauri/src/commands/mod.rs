//! Tauri command handlers exposed to the frontend.
//!
//! Every command returns [`crate::error::Result`], so failures surface to the
//! frontend as rejected promises carrying a readable message rather than panicking
//! the WebView.

pub mod dialogs;
pub mod notifications;
pub mod tray;
pub mod window;
