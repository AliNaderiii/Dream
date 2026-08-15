//! Unit tests for the pieces of the shell that carry real logic: path
//! validation (the security boundary) and notification deduplication.

use crate::commands::dialogs::validate_path;
use crate::state::{AgentStatus, AppState};

use tauri::test::{mock_builder, mock_context, noop_assets, MockRuntime};
use tauri::{AppHandle, Manager};

/// Builds a headless Tauri app with `AppState` managed, for command-level tests.
fn test_app() -> AppHandle<MockRuntime> {
    let app = mock_builder()
        .manage(AppState::default())
        .build(mock_context(noop_assets()))
        .expect("failed to build mock app");
    app.handle().clone()
}

#[test]
fn agent_status_labels_are_stable() {
    assert_eq!(AgentStatus::Idle.label(), "Idle");
    assert_eq!(AgentStatus::Running.label(), "Running");
    assert_eq!(AgentStatus::Paused.label(), "Paused");
    assert_eq!(AgentStatus::Error.label(), "Error");
    assert_eq!(AgentStatus::Offline.label(), "Offline");
}

#[test]
fn app_state_defaults_to_idle_and_close_to_tray() {
    let state = AppState::default();
    let snapshot = state.snapshot();

    assert_eq!(snapshot.agent_status, AgentStatus::Idle);
    assert_eq!(snapshot.pending_approvals, 0);
    assert!(snapshot.workspace_root.is_none());
    assert!(snapshot.close_to_tray);
    assert!(!snapshot.minimize_to_tray);
}

#[test]
fn validate_path_accepts_a_file_inside_the_workspace() {
    let app = test_app();
    let dir = tempfile::tempdir().expect("tempdir");
    let root = std::fs::canonicalize(dir.path()).expect("canonicalize root");

    let file = root.join("notes.md");
    std::fs::write(&file, b"hello").expect("write file");

    app.state::<AppState>().lock().workspace_root = Some(root.clone());

    let validated = validate_path(&app, &file).expect("file inside the workspace is valid");
    assert!(validated.starts_with(&root));
}

#[test]
fn validate_path_rejects_traversal_outside_the_workspace() {
    let app = test_app();
    let dir = tempfile::tempdir().expect("tempdir");
    let root = std::fs::canonicalize(dir.path()).expect("canonicalize root");

    let inside = root.join("workspace");
    std::fs::create_dir(&inside).expect("create workspace dir");

    let outside = root.join("secret.txt");
    std::fs::write(&outside, b"secret").expect("write outside file");

    app.state::<AppState>().lock().workspace_root = Some(inside.clone());

    // `../secret.txt` resolves outside the root and must be refused.
    let escape = inside.join("..").join("secret.txt");
    let result = validate_path(&app, &escape);

    assert!(
        result.is_err(),
        "traversal outside the workspace must be rejected, got {result:?}"
    );
}

#[test]
fn validate_path_rejects_a_missing_file() {
    let app = test_app();
    let dir = tempfile::tempdir().expect("tempdir");

    let missing = dir.path().join("does-not-exist.csv");
    assert!(validate_path(&app, &missing).is_err());
}

#[test]
fn validate_path_allows_any_existing_file_when_no_workspace_is_set() {
    let app = test_app();
    let dir = tempfile::tempdir().expect("tempdir");

    let file = dir.path().join("free.txt");
    std::fs::write(&file, b"x").expect("write file");

    assert!(validate_path(&app, &file).is_ok());
}
