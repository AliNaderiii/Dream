//! Dream desktop shell — plugin registration and application setup.
//!
//! Layering: `lib.rs` wires plugins, state, tray and window behaviour; the modules
//! in [`commands`] implement the callable surface. Nothing here talks to the
//! Python core — that bridge arrives in P-02.

pub mod commands;
pub mod error;
pub mod state;

// The Python sidecar bridge is desktop-only: mobile platforms cannot spawn the
// sidecar process. Its commands degrade to a `not_ready` error when uninitialised.
pub mod bridge;

#[cfg(test)]
mod tests;

use tauri::{Manager, WindowEvent};

use crate::commands::notifications::NotificationLog;
use crate::commands::{dialogs, notifications, tray, window};
use crate::state::AppState;

/// Builds and runs the Tauri application.
///
/// # Panics
/// Panics only if the Tauri context itself cannot be initialised, which indicates
/// a corrupt bundle rather than a recoverable runtime condition.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[allow(unused_mut)]
    let mut builder = tauri::Builder::default();

    // ---- Desktop-only plugins -------------------------------------------------
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    {
        use tauri_plugin_window_state::StateFlags;

        builder = builder
            // Restores position, size and maximized/fullscreen state on launch.
            // VISIBLE is excluded so a window hidden to the tray at exit does not
            // come back invisible and unreachable on the next launch.
            .plugin(
                tauri_plugin_window_state::Builder::default()
                    .with_state_flags(StateFlags::all() & !StateFlags::VISIBLE)
                    .build(),
            )
            .plugin(tauri_plugin_updater::Builder::new().build())
            .plugin(
                tauri_plugin_log::Builder::new()
                    .level(log::LevelFilter::Info)
                    .build(),
            );
    }

    builder
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .manage(AppState::default())
        .manage(NotificationLog::default())
        .invoke_handler(tauri::generate_handler![
            // window
            window::minimize_window,
            window::toggle_maximize,
            window::toggle_fullscreen,
            window::close_window,
            window::focus_window,
            window::toggle_main_window,
            window::open_window,
            window::list_windows,
            window::set_minimize_to_tray,
            window::set_close_to_tray,
            // tray / state
            tray::set_agent_status,
            tray::set_pending_approvals,
            tray::get_app_state,
            // notifications
            notifications::notification_permission,
            notifications::request_notification_permission,
            notifications::send_notification,
            // dialogs
            dialogs::open_file_dialog,
            dialogs::save_file_dialog,
            dialogs::select_folder_dialog,
            dialogs::set_workspace_root,
            dialogs::validate_paths,
            // bridge (Python sidecar)
            bridge::bridge_send,
            bridge::bridge_status,
            bridge::bridge_restart,
            bridge::bridge_kill,
        ])
        .setup(|app| {
            #[cfg(not(any(target_os = "android", target_os = "ios")))]
            {
                tray::init(app.handle())?;
                // Spawn the Python sidecar and begin supervision. The frontend
                // learns the connection state via `bridge://state` events.
                bridge::init(app.handle());
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the main window hides it to the tray by default, matching
            // comparable agent apps; secondary windows really close.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == window::MAIN_WINDOW {
                    let close_to_tray =
                        window.app_handle().state::<AppState>().lock().close_to_tray;
                    if close_to_tray {
                        api.prevent_close();
                        let _ = window.hide();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Dream desktop application");
}
