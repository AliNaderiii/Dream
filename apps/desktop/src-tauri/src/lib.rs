//! Dream desktop shell — plugin registration and application setup.
//!
//! Layering: `lib.rs` wires plugins, state, tray and window behaviour; the modules
//! in [`commands`] implement the callable surface. Nothing here talks to the
//! Python core — that bridge arrives in P-02.

pub mod commands;
pub mod error;
pub mod state;
mod single_instance;

// The Python sidecar bridge is desktop-only: mobile platforms cannot spawn the
// sidecar process. Its commands degrade to a `not_ready` error when uninitialised.
pub mod bridge;

#[cfg(test)]
mod tests;

use tauri::{Manager, Runtime, WindowEvent};

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
        .plugin(tauri_plugin_store::Builder::new().build())
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
                // Single instance: a second launch focuses the running window
                // and exits instead of creating a second process (and with it a
                // second tray icon — the observed "two icons per cycle" leak).
                let Ok(app_data_dir) = app.path().app_data_dir() else {
                    log::warn!(
                        "single-instance: app data dir unavailable — skipping \
                         single-instance protection"
                    );
                    tray::init(app.handle())?;
                    bridge::init(app.handle());
                    return Ok(());
                };
                match single_instance::acquire(&app_data_dir) {
                    single_instance::AcquireOutcome::Primary => {
                        single_instance::spawn_focus_watcher(app.handle().clone(), app_data_dir);
                        tray::init(app.handle())?;
                        // Spawn the Python sidecar and begin supervision. The
                        // frontend learns the connection state via
                        // `bridge://state` events.
                        bridge::init(app.handle());
                    }
                    single_instance::AcquireOutcome::Secondary => {
                        single_instance::request_focus(&app_data_dir);
                        // Hide the briefly-created window so the handoff looks
                        // like a plain "bring to front", then exit. `app` here
                        // is the builder's &mut App; the AppHandle owns exit().
                        if let Some(window) = app.get_webview_window(window::MAIN_WINDOW) {
                            let _ = window.hide();
                        }
                        app.handle().exit(0);
                    }
                }
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the main window honours the `closeToTray` preference;
            // secondary windows really close. When not hiding to tray, the
            // close is a real quit: the tray icon is destroyed first (a tray
            // icon keeps the process alive on Windows — the root cause of the
            // ghost-icon accumulation), the sidecar is killed, then the event
            // loop exits.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == window::MAIN_WINDOW {
                    let close_to_tray =
                        window.app_handle().state::<AppState>().lock().close_to_tray;
                    if close_to_tray {
                        api.prevent_close();
                        if let Err(error) = window.hide() {
                            log::warn!("failed to hide Dream window to tray: {error}");
                        }
                    } else {
                        teardown_and_exit(window.app_handle(), 0);
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Dream desktop application");
}

/// Full application teardown shared by every quit path (window close with
/// `close_to_tray == false`, tray-menu Quit):
///
/// 1. destroy the tray icon — a lingering tray icon is what kept old processes
///    alive and stacked duplicate icons in the notification area;
/// 2. kill the sidecar so no Python child outlives the shell;
/// 3. clean single-instance markers so the next launch starts fresh;
/// 4. exit the event loop (the window-state plugin saves geometry on the way).
pub fn teardown_and_exit<R: Runtime>(app: &tauri::AppHandle<R>, code: i32) {
    // `remove_tray_by_id` returns `Option<TrayIcon<R>>` (None when the tray
    // was already gone or never created), not a Result.
    if app.remove_tray_by_id(tray::TRAY_ID).is_some() {
        log::info!("teardown: tray icon removed");
    } else {
        log::debug!("teardown: no tray icon present");
    }
    crate::bridge::kill_bridge_on_quit(app);
    if let Ok(app_data_dir) = app.path().app_data_dir() {
        single_instance::cleanup_markers(&app_data_dir);
    }
    log::info!("teardown: exiting with code {code}");
    app.exit(code);
}
