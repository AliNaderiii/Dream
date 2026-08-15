//! System tray construction and state-driven updates.
//!
//! The tray reflects two pieces of app state: [`AgentStatus`] (tooltip text and
//! Pause/Resume enablement) and the pending-approval count (icon badge). Both are
//! pushed from the frontend via [`set_agent_status`] / [`set_pending_approvals`],
//! and both are also emitted back to every window so all UI surfaces stay in sync.

use tauri::image::Image;
use tauri::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, Runtime};

use crate::commands::window::{focus_window, toggle_main_window};
use crate::error::{Error, Result};
use crate::state::{AgentStatus, AppState, TrayHandles};

/// Identifier of the single tray icon, used to look it up from commands.
pub const TRAY_ID: &str = "dream-tray";

// Icons are embedded at compile time so the tray works from any working directory.
const ICON_DEFAULT: &[u8] = include_bytes!("../../icons/tray/tray-32.png");
const ICON_ALERT: &[u8] = include_bytes!("../../icons/tray/tray-alert-32.png");
const ICON_TEMPLATE: &[u8] = include_bytes!("../../icons/tray/trayTemplate-32.png");

/// Builds the tray icon, its menu, and all event handlers. Called once from `setup`.
pub fn init<R: Runtime>(app: &AppHandle<R>) -> Result<()> {
    let open = MenuItem::with_id(app, "open", "Open Dream", true, None::<&str>)?;
    let new_session =
        MenuItem::with_id(app, "new-session", "New Session", true, Some("CmdOrCtrl+N"))?;
    let quick_ask = MenuItem::with_id(
        app,
        "quick-ask",
        "Quick Ask...",
        true,
        Some("CmdOrCtrl+Shift+Space"),
    )?;
    let pause = MenuItem::with_id(app, "pause", "Pause Agent", true, None::<&str>)?;
    let resume = MenuItem::with_id(app, "resume", "Resume Agent", false, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Dream", true, Some("CmdOrCtrl+Q"))?;

    let menu = Menu::with_items(
        app,
        &[
            &open,
            &new_session,
            &quick_ask,
            &separator,
            &pause,
            &resume,
            &separator,
            &quit,
        ],
    )?;

    // Keep handles so Pause/Resume enablement can follow agent status.
    app.manage(TrayHandles::<R> {
        pause: pause.clone(),
        resume: resume.clone(),
    });

    // `mut` is only consumed by the macOS-gated template call below.
    #[allow(unused_mut)]
    let mut builder = TrayIconBuilder::with_id(TRAY_ID)
        .icon(default_icon()?)
        .tooltip("Dream — Idle")
        .menu(&menu)
        // Left click toggles the window; the menu stays on right click.
        .show_menu_on_left_click(false)
        .on_menu_event(handle_menu_event)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let _ = toggle_main_window(tray.app_handle().clone());
            }
        });

    // macOS menu-bar icons must be monochrome templates to adapt to light/dark.
    #[cfg(target_os = "macos")]
    {
        builder = builder.icon_as_template(true);
    }

    builder.build(app)?;
    Ok(())
}

/// Platform-appropriate idle icon: template on macOS, full colour elsewhere.
fn default_icon() -> Result<Image<'static>> {
    let bytes = if cfg!(target_os = "macos") {
        ICON_TEMPLATE
    } else {
        ICON_DEFAULT
    };
    Image::from_bytes(bytes).map_err(|e| Error::Tray(e.to_string()))
}

/// Routes tray menu clicks. Window-affecting items act directly; the rest are
/// forwarded to the frontend as `tray://<id>` events.
fn handle_menu_event<R: Runtime>(app: &AppHandle<R>, event: MenuEvent) {
    let app = app.clone();
    match event.id.as_ref() {
        "open" => {
            let _ = focus_window(app, None);
        }
        "new-session" => {
            let _ = focus_window(app.clone(), None);
            let _ = app.emit("tray://new-session", ());
        }
        "quick-ask" => {
            let _ = focus_window(app.clone(), None);
            let _ = app.emit("tray://quick-ask", ());
        }
        "pause" => {
            let _ = set_agent_status(app, AgentStatus::Paused);
        }
        "resume" => {
            let _ = set_agent_status(app, AgentStatus::Idle);
        }
        "quit" => {
            // Give the frontend a chance to flush state, then exit.
            let _ = app.emit("tray://quit", ());
            app.exit(0);
        }
        _ => {}
    }
}

/// Recomputes tooltip, icon badge and Pause/Resume enablement from current state.
fn refresh<R: Runtime>(app: &AppHandle<R>) -> Result<()> {
    let snapshot = app.state::<AppState>().snapshot();

    let Some(tray) = app.tray_by_id(TRAY_ID) else {
        // No tray on this platform/session — state changes are still valid.
        return Ok(());
    };

    let tooltip = match snapshot.pending_approvals {
        0 => format!("Dream — {}", snapshot.agent_status.label()),
        1 => format!(
            "Dream — {} · 1 approval pending",
            snapshot.agent_status.label()
        ),
        n => format!(
            "Dream — {} · {n} approvals pending",
            snapshot.agent_status.label()
        ),
    };
    tray.set_tooltip(Some(&tooltip))
        .map_err(|e| Error::Tray(e.to_string()))?;

    // Badge: platforms have no cross-platform numeric tray badge, so a dot
    // variant of the icon signals "attention needed".
    let bytes = if snapshot.pending_approvals > 0 {
        ICON_ALERT
    } else if cfg!(target_os = "macos") {
        ICON_TEMPLATE
    } else {
        ICON_DEFAULT
    };
    let icon = Image::from_bytes(bytes).map_err(|e| Error::Tray(e.to_string()))?;
    tray.set_icon(Some(icon))
        .map_err(|e| Error::Tray(e.to_string()))?;

    // A badged icon is coloured, so it must not be drawn as a template.
    #[cfg(target_os = "macos")]
    tray.set_icon_as_template(snapshot.pending_approvals == 0)
        .map_err(|e| Error::Tray(e.to_string()))?;

    if let Some(handles) = app.try_state::<TrayHandles<R>>() {
        let paused = snapshot.agent_status == AgentStatus::Paused;
        handles.pause.set_enabled(!paused)?;
        handles.resume.set_enabled(paused)?;
    }

    // Taskbar/dock badge mirrors the approval count. `set_badge_count` is a no-op
    // on Windows (which uses overlay icons instead), so failures are non-fatal.
    if let Some(main) = app.get_webview_window(crate::commands::window::MAIN_WINDOW) {
        let count = (snapshot.pending_approvals > 0).then_some(snapshot.pending_approvals as i64);
        let _ = main.set_badge_count(count);
    }

    Ok(())
}

/// Updates the agent status, refreshes the tray, and notifies all windows.
#[tauri::command]
pub fn set_agent_status<R: Runtime>(app: AppHandle<R>, status: AgentStatus) -> Result<()> {
    app.state::<AppState>().lock().agent_status = status;
    refresh(&app)?;
    app.emit("agent://status", status)?;
    Ok(())
}

/// Updates the pending-approval count, refreshes the tray badge, and notifies windows.
#[tauri::command]
pub fn set_pending_approvals<R: Runtime>(app: AppHandle<R>, count: u32) -> Result<()> {
    app.state::<AppState>().lock().pending_approvals = count;
    refresh(&app)?;
    app.emit("agent://approvals", count)?;
    Ok(())
}

/// Returns the full app-state snapshot (used by the frontend on mount).
#[tauri::command]
pub fn get_app_state<R: Runtime>(app: AppHandle<R>) -> crate::state::AppStateSnapshot {
    app.state::<AppState>().snapshot()
}
