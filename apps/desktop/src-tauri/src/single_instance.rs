//! Single-instance enforcement and cross-process focus handoff.
//!
//! One Dream process owns one tray icon; a second launch must not create a
//! second process (and therefore a second tray icon) — it should bring the
//! running window to the front and exit. The `tauri-plugin-single-instance`
//! crate was removed (S15) and crates.io is unreachable from the release
//! environment, so this module implements the same contract with zero extra
//! dependencies:
//!
//! - **Windows**: a per-session named mutex (`Local\DreamDesktop.SingleInstance`)
//!   created through a minimal direct FFI to `kernel32`. The mutex handle is
//!   deliberately leaked for the process lifetime — the OS destroys the kernel
//!   object when the last handle closes, i.e. when the primary exits.
//! - **Other platforms**: a PID lockfile in the app data directory with stale
//!   lock recovery (a lockfile whose recorded PID is no longer alive is taken
//!   over).
//!
//! The secondary instance writes a timestamped `focus-request` marker into the
//! app data directory; the primary polls for it (400 ms) and focuses its main
//! window when it appears. The marker is deleted once handled and on startup,
//! so a stale marker can never self-focus a fresh launch.

use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Runtime};

use crate::commands::window::focus_window;

/// Per-session named mutex (Windows). `Local\` scopes the object to the
/// interactive logon session — right for a per-user desktop app; `Global\`
/// would require privileges we must not assume.
#[cfg(windows)]
const MUTEX_NAME: &str = "Local\\DreamDesktop.SingleInstance";

/// Lockfile name used on non-Windows platforms (Windows uses the named mutex).
#[cfg(not(windows))]
const LOCKFILE_NAME: &str = "dream-desktop.lock";

/// Marker file the secondary instance writes to ask the primary for focus.
const FOCUS_REQUEST_NAME: &str = "focus-request";

/// Poll interval of the focus-request watcher.
const FOCUS_POLL_INTERVAL: Duration = Duration::from_millis(400);

/// Markers older than this are stale and are not acted on (seconds).
const FOCUS_REQUEST_MAX_AGE_SECS: u128 = 60;

/// Outcome of the single-instance check.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AcquireOutcome {
    /// This process is the first (or only) instance — proceed normally.
    Primary,
    /// Another instance is already running — request focus and exit.
    Secondary,
}

/// Check whether another Dream process is already running.
///
/// The check is advisory, not a security boundary: on any error the caller
/// proceeds as primary (fail open) so a broken mutex can never prevent the app
/// from launching.
pub fn acquire(_app_data_dir: &Path) -> AcquireOutcome {
    #[cfg(windows)]
    {
        acquire_windows()
    }
    #[cfg(not(windows))]
    {
        acquire_lockfile(_app_data_dir)
    }
}

#[cfg(windows)]
mod win {
    //! Minimal, dependency-free FFI to `kernel32` for a named mutex.
    //!
    //! `windows-sys` is already in the dependency tree of `tauri`, but adding
    //! it to `Cargo.toml` would require crates.io access at build time; the
    //! release environment has none. These four symbols are stable Win32 API.

    use std::ffi::c_void;

    #[link(name = "kernel32")]
    extern "system" {
        /// Creates or opens a named mutex object.
        fn CreateMutexW(
            lp_mutex_attributes: *const c_void,
            b_initial_owner: i32,
            lp_name: *const u16,
        ) -> *mut c_void;
        /// Returns the calling thread's last-error code.
        fn GetLastError() -> u32;
        /// Closes an open object handle.
        fn CloseHandle(h_object: *mut c_void) -> i32;
    }

    /// ERROR_ALREADY_EXISTS: the mutex name was created by another handle —
    /// i.e. a previous instance is running.
    pub const ERROR_ALREADY_EXISTS: u32 = 183;

    /// Outcome of [`try_create_mutex`].
    pub enum MutexOutcome {
        /// This process created the mutex — it is the primary instance.
        /// Carries the handle that must stay open for the process lifetime.
        Primary(*mut c_void),
        /// Another instance already holds the mutex name.
        Secondary,
        /// The mutex could not be created at all (`GetLastError` code).
        Failed(u32),
    }

    /// Create (or open) the named mutex and report who owns the name.
    pub fn try_create_mutex(name: &str) -> MutexOutcome {
        let wide: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();
        // SAFETY: `wide` is a NUL-terminated UTF-16 buffer that stays alive for
        // the whole call; attributes are null (default security descriptor) and
        // initial ownership is off so a second instance opens the existing
        // mutex instead of creating a new one.
        let handle = unsafe { CreateMutexW(std::ptr::null(), 0, wide.as_ptr()) };
        if handle.is_null() {
            // SAFETY: GetLastError has no preconditions.
            return MutexOutcome::Failed(unsafe { GetLastError() });
        }
        // SAFETY: GetLastError has no preconditions. A successful open of an
        // existing mutex reports ERROR_ALREADY_EXISTS via the last-error code.
        if unsafe { GetLastError() } == ERROR_ALREADY_EXISTS {
            // SAFETY: `handle` is a valid open handle this thread owns; no
            // other code references it.
            unsafe { CloseHandle(handle) };
            return MutexOutcome::Secondary;
        }
        MutexOutcome::Primary(handle)
    }
}

/// Windows single-instance check via the named mutex.
#[cfg(windows)]
fn acquire_windows() -> AcquireOutcome {
    match win::try_create_mutex(MUTEX_NAME) {
        win::MutexOutcome::Primary(handle) => {
            // Deliberately leak the handle: the kernel mutex must stay alive
            // for this process's lifetime (the OS destroys it when the last
            // handle closes, i.e. when the primary exits). A few bytes of
            // leaked memory are the standard price of a process-lifetime
            // kernel object.
            std::mem::forget(handle);
            log::info!("single-instance: primary — created named mutex {MUTEX_NAME}");
            AcquireOutcome::Primary
        }
        win::MutexOutcome::Secondary => {
            log::info!(
                "single-instance: secondary — mutex {MUTEX_NAME} is held by another process"
            );
            AcquireOutcome::Secondary
        }
        win::MutexOutcome::Failed(code) => {
            log::warn!(
                "single-instance: could not create mutex (error {code}); \
                 continuing without single-instance protection"
            );
            AcquireOutcome::Primary
        }
    }
}

/// Non-Windows single-instance check via a PID lockfile.
#[cfg(not(windows))]
fn acquire_lockfile(app_data_dir: &Path) -> AcquireOutcome {
    use std::io::Write;

    if let Err(err) = std::fs::create_dir_all(app_data_dir) {
        log::warn!(
            "single-instance: cannot create {} — continuing without single-instance protection ({err})",
            app_data_dir.display()
        );
        return AcquireOutcome::Primary;
    }
    let lockfile = app_data_dir.join(LOCKFILE_NAME);
    let pid = std::process::id();

    for _ in 0..2 {
        match std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&lockfile)
        {
            Ok(mut file) => {
                if let Err(err) = writeln!(file, "{pid}") {
                    log::warn!(
                        "single-instance: could not write lockfile {} — continuing without \
                         single-instance protection ({err})",
                        lockfile.display()
                    );
                    let _ = std::fs::remove_file(&lockfile);
                    return AcquireOutcome::Primary;
                }
                log::info!("single-instance: primary — lockfile {}", lockfile.display());
                return AcquireOutcome::Primary;
            }
            Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {
                let owner_alive = std::fs::read_to_string(&lockfile)
                    .ok()
                    .and_then(|content| content.trim().parse::<u32>().ok())
                    .is_some_and(is_pid_alive);
                if owner_alive {
                    log::info!(
                        "single-instance: secondary — lockfile {} belongs to a live process",
                        lockfile.display()
                    );
                    return AcquireOutcome::Secondary;
                }
                log::warn!(
                    "single-instance: lockfile {} is stale — removing it and retrying",
                    lockfile.display()
                );
                if let Err(err) = std::fs::remove_file(&lockfile) {
                    log::warn!(
                        "single-instance: could not remove stale lockfile {} — continuing \
                         without single-instance protection ({err})",
                        lockfile.display()
                    );
                    return AcquireOutcome::Primary;
                }
            }
            Err(err) => {
                log::warn!(
                    "single-instance: could not create lockfile {} — continuing without \
                     single-instance protection ({err})",
                    lockfile.display()
                );
                return AcquireOutcome::Primary;
            }
        }
    }
    log::warn!(
        "single-instance: lockfile {} stayed contended — continuing without single-instance protection",
        lockfile.display()
    );
    AcquireOutcome::Primary
}

/// Best-effort liveness probe for the PID recorded in a lockfile.
///
/// `kill(pid, 0)` sends no signal; it only reports whether the process exists
/// and is signalable. A return of 0 means alive; -1 with EPERM (1 on every
/// POSIX platform we target) means alive but owned by another user.
#[cfg(not(windows))]
fn is_pid_alive(pid: u32) -> bool {
    if pid == 0 || pid > i32::MAX as u32 {
        return false;
    }
    // SAFETY: kill(pid, 0) sends no signal; errno is read via the safe
    // std::io::Error::last_os_error API.
    let result = unsafe { kill(pid as i32, 0) };
    if result == 0 {
        return true;
    }
    std::io::Error::last_os_error().raw_os_error() == Some(1) // EPERM: exists, not ours
}

/// POSIX kill(2), declared at module scope so the `#[link]` attribute sits on
/// a top-level extern block. Only compiled on non-Windows targets (Windows
/// uses the named mutex, never the lockfile).
#[cfg(not(windows))]
#[link(name = "c")]
extern "C" {
    fn kill(pid: i32, sig: i32) -> i32;
}

/// Marker file the secondary instance writes to ask the primary for focus.
fn focus_request_path(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join(FOCUS_REQUEST_NAME)
}

/// Ask the running (primary) instance to focus its main window. Called by the
/// secondary instance right before it exits; the primary notices the marker
/// within one poll interval and shows/focuses its window.
pub fn request_focus(app_data_dir: &Path) {
    let path = focus_request_path(app_data_dir);
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_millis())
        .unwrap_or(0);
    if let Err(err) = std::fs::write(&path, timestamp.to_string()) {
        log::warn!(
            "single-instance: could not write focus request {}: {err}",
            path.display()
        );
    } else {
        log::info!("single-instance: focus request written to {}", path.display());
    }
}

/// Watch for focus-request markers written by secondary instances and focus
/// the main window when one appears. Runs until the process exits.
pub fn spawn_focus_watcher<R: Runtime>(app: AppHandle<R>, app_data_dir: PathBuf) {
    let path = focus_request_path(&app_data_dir);
    // A marker left behind by a crashed previous run must not self-focus a
    // fresh launch.
    let _ = std::fs::remove_file(&path);
    let result = std::thread::Builder::new()
        .name("dream-focus-watcher".to_string())
        .spawn(move || {
            let mut last_handled: u128 = 0;
            loop {
                std::thread::sleep(FOCUS_POLL_INTERVAL);
                let now = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map(|elapsed| elapsed.as_millis())
                    .unwrap_or(0);
                let marker = std::fs::read_to_string(&path)
                    .ok()
                    .and_then(|content| content.trim().parse::<u128>().ok());
                let Some(timestamp) = marker else {
                    continue;
                };
                if timestamp > last_handled
                    && now.saturating_sub(timestamp) <= FOCUS_REQUEST_MAX_AGE_SECS * 1000
                {
                    last_handled = timestamp;
                    log::info!(
                        "single-instance: focus request received — showing the main window"
                    );
                    let _ = focus_window(app.clone(), None);
                    let _ = std::fs::remove_file(&path);
                }
            }
        });
    if let Err(err) = result {
        log::warn!("single-instance: could not start focus watcher: {err}");
    }
}

/// Remove single-instance markers (lockfile + focus request). Called during
/// full teardown so the next launch starts clean and never sees a stale
/// focus request or lock.
pub fn cleanup_markers(app_data_dir: &Path) {
    let _ = std::fs::remove_file(focus_request_path(app_data_dir));
    #[cfg(not(windows))]
    {
        let _ = std::fs::remove_file(app_data_dir.join(LOCKFILE_NAME));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(not(windows))]
    #[test]
    fn acquire_returns_primary_then_secondary_for_the_same_lockfile() {
        let tmp = tempfile::tempdir().expect("temp dir");

        // First acquisition creates the lockfile and wins.
        assert_eq!(acquire(tmp.path()), AcquireOutcome::Primary);
        assert!(tmp.path().join(LOCKFILE_NAME).is_file());

        // A second acquisition while the owner PID is alive must report
        // Secondary — this is the "second launch focuses and exits" path.
        let outcome = acquire(tmp.path());
        assert_eq!(outcome, AcquireOutcome::Secondary);

        // Cleaning up lets the next launch become primary again.
        cleanup_markers(tmp.path());
        assert_eq!(acquire(tmp.path()), AcquireOutcome::Primary);
    }

    #[cfg(not(windows))]
    #[test]
    fn acquire_recovers_from_a_stale_lockfile() {
        let tmp = tempfile::tempdir().expect("temp dir");
        std::fs::create_dir_all(tmp.path()).unwrap();

        // A lockfile whose PID cannot be alive (u32::MAX is beyond any real
        // PID) must be taken over, not treated as a running instance.
        std::fs::write(tmp.path().join(LOCKFILE_NAME), format!("{}\n", u32::MAX)).unwrap();

        assert_eq!(acquire(tmp.path()), AcquireOutcome::Primary);
        let owner = std::fs::read_to_string(tmp.path().join(LOCKFILE_NAME)).unwrap();
        assert_eq!(owner.trim(), std::process::id().to_string());
    }

    #[test]
    fn request_focus_writes_a_parseable_timestamp_marker() {
        let tmp = tempfile::tempdir().expect("temp dir");
        request_focus(tmp.path());

        let marker = focus_request_path(tmp.path());
        let content = std::fs::read_to_string(&marker).expect("marker file");
        let timestamp: u128 = content.trim().parse().expect("timestamp");
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|elapsed| elapsed.as_millis())
            .unwrap_or(0);
        assert!(now >= timestamp, "marker must be in the past");
    }

    #[test]
    fn cleanup_markers_removes_both_markers() {
        let tmp = tempfile::tempdir().expect("temp dir");
        request_focus(tmp.path());
        #[cfg(not(windows))]
        std::fs::write(tmp.path().join(LOCKFILE_NAME), "1\n").unwrap();

        cleanup_markers(tmp.path());
        assert!(!focus_request_path(tmp.path()).exists());
        #[cfg(not(windows))]
        assert!(!tmp.path().join(LOCKFILE_NAME).exists());
    }
}
