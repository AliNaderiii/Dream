//! Window management commands.
//!
//! Window *geometry* persistence is handled by `tauri-plugin-window-state`, which
//! saves position, size and maximized/fullscreen flags on exit and restores them
//! on launch. These commands cover the operations the custom title bar needs
//! (minimise/maximise/close), multi-window management, and minimise-to-tray.

use tauri::{AppHandle, Manager, Runtime, WebviewUrl, WebviewWindowBuilder, Window};

use crate::error::{Error, Result};
use crate::state::AppState;

/// Label of the primary application window.
pub const MAIN_WINDOW: &str = "main";

/// Resolves a window by label, or the caller's own window when `label` is `None`.
fn resolve<R: Runtime>(app: &AppHandle<R>, window: &Window<R>, label: Option<&str>) -> Result<Window<R>> {
    match label {
        Some(label) => app
            .get_window(label)
            .ok_or_else(|| Error::WindowNotFound(label.to_string())),
        None => Ok(window.clone()),
    }
}

/// Minimises a window. When `minimizeToTray` is enabled the window is hidden
/// instead, so it disappears from the taskbar and is reachable only from the tray.
#[tauri::command]
pub fn minimize_window<R: Runtime>(
    app: AppHandle<R>,
    window: Window<R>,
    label: Option<String>,
) -> Result<()> {
    let target = resolve(&app, &window, label.as_deref())?;
    let to_tray = app.state::<AppState>().lock().minimize_to_tray;

    if to_tray && target.label() == MAIN_WINDOW {
        target.hide()?;
    } else {
        target.minimize()?;
    }
    Ok(())
}

/// Toggles the maximised state of a window (used by the title bar button and
/// by double-clicking the drag region).
#[tauri::command]
pub fn toggle_maximize<R: Runtime>(
    app: AppHandle<R>,
    window: Window<R>,
    label: Option<String>,
) -> Result<bool> {
    let target = resolve(&app, &window, label.as_deref())?;
    if target.is_maximized()? {
        target.unmaximize()?;
        Ok(false)
    } else {
        target.maximize()?;
        Ok(true)
    }
}

/// Toggles fullscreen for a window.
#[tauri::command]
pub fn toggle_fullscreen<R: Runtime>(
    app: AppHandle<R>,
    window: Window<R>,
    label: Option<String>,
) -> Result<bool> {
    let target = resolve(&app, &window, label.as_deref())?;
    let next = !target.is_fullscreen()?;
    target.set_fullscreen(next)?;
    Ok(next)
}

/// Closes a window. The main window honours the `closeToTray` preference and
/// hides instead of closing; the `CloseRequested` handler in `lib.rs` enforces
/// the same rule for OS-initiated closes.
#[tauri::command]
pub fn close_window<R: Runtime>(
    app: AppHandle<R>,
    window: Window<R>,
    label: Option<String>,
) -> Result<()> {
    let target = resolve(&app, &window, label.as_deref())?;
    target.close()?;
    Ok(())
}

/// Shows, unminimises and focuses a window — the "bring to front" primitive
/// used by tray clicks and notification activations.
#[tauri::command]
pub fn focus_window<R: Runtime>(app: AppHandle<R>, label: Option<String>) -> Result<()> {
    let label = label.unwrap_or_else(|| MAIN_WINDOW.to_string());
    let target = app
        .get_webview_window(&label)
        .ok_or_else(|| Error::WindowNotFound(label))?;

    if target.is_minimized().unwrap_or(false) {
        target.unminimize()?;
    }
    target.show()?;
    target.set_focus()?;
    Ok(())
}

/// Shows the main window if hidden, hides it if currently visible and focused.
/// Bound to tray left-click.
#[tauri::command]
pub fn toggle_main_window<R: Runtime>(app: AppHandle<R>) -> Result<bool> {
    let window = app
        .get_webview_window(MAIN_WINDOW)
        .ok_or_else(|| Error::WindowNotFound(MAIN_WINDOW.to_string()))?;

    let visible = window.is_visible().unwrap_or(false);
    let focused = window.is_focused().unwrap_or(false);

    if visible && focused {
        window.hide()?;
        Ok(false)
    } else {
        if window.is_minimized().unwrap_or(false) {
            window.unminimize()?;
        }
        window.show()?;
        window.set_focus()?;
        Ok(true)
    }
}

/// Opens an additional application window pointing at `route`.
///
/// Returns the label of the created window. When a window with the requested
/// label already exists it is focused instead of duplicated.
#[tauri::command]
pub async fn open_window<R: Runtime>(
    app: AppHandle<R>,
    label: Option<String>,
    route: Option<String>,
    title: Option<String>,
) -> Result<String> {
    let label = label.unwrap_or_else(|| format!("dream-{}", uid()));

    if let Some(existing) = app.get_webview_window(&label) {
        existing.show()?;
        existing.set_focus()?;
        return Ok(label);
    }

    // Route is a hash fragment so it works for both the dev server and the
    // bundled `tauri://localhost` asset protocol.
    let route = route.unwrap_or_else(|| "/".to_string());
    let url = format!("index.html#{}", if route.starts_with('/') { route } else { format!("/{route}") });

    let mut builder = WebviewWindowBuilder::new(&app, &label, WebviewUrl::App(url.into()))
        .title(title.unwrap_or_else(|| "Dream".to_string()))
        .inner_size(1280.0, 800.0)
        .min_inner_size(800.0, 500.0)
        .resizable(true)
        .visible(true);

    // Match the main window's chrome: custom title bar everywhere, with macOS
    // keeping its native traffic lights via an overlay title bar.
    #[cfg(target_os = "macos")]
    {
        builder = builder
            .title_bar_style(tauri::TitleBarStyle::Overlay)
            .hidden_title(true);
    }
    #[cfg(not(target_os = "macos"))]
    {
        builder = builder.decorations(false);
    }

    builder.build()?;
    Ok(label)
}

/// Monotonic-ish unique suffix for generated window labels.
fn uid() -> u128 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

/// Returns the labels of all open windows.
#[tauri::command]
pub fn list_windows<R: Runtime>(app: AppHandle<R>) -> Vec<String> {
    app.webview_windows().keys().cloned().collect()
}

/// Sets whether minimising the main window hides it to the tray.
#[tauri::command]
pub fn set_minimize_to_tray<R: Runtime>(app: AppHandle<R>, enabled: bool) -> Result<()> {
    app.state::<AppState>().lock().minimize_to_tray = enabled;
    Ok(())
}

/// Sets whether closing the main window hides it to the tray instead of quitting.
#[tauri::command]
pub fn set_close_to_tray<R: Runtime>(app: AppHandle<R>, enabled: bool) -> Result<()> {
    app.state::<AppState>().lock().close_to_tray = enabled;
    Ok(())
}
