//! Native file dialog commands and workspace path validation.
//!
//! Every path that crosses the boundary into the app is validated by
//! [`validate_path`]: it must exist, canonicalize, and — when a workspace root is
//! configured — resolve inside that root. Canonicalizing *before* the prefix
//! comparison is what makes `../` traversal and symlink escapes detectable.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, Runtime};
use tauri_plugin_dialog::{DialogExt, FilePath};

use crate::error::{Error, Result};
use crate::state::AppState;

/// File type filters offered by Dream's open dialog.
const FILTERS: &[(&str, &[&str])] = &[
    ("Data", &["csv", "tsv", "xlsx", "xls", "parquet", "json"]),
    ("Documents", &["md", "markdown", "txt", "pdf", "docx"]),
    ("Notebooks & code", &["ipynb", "py", "r", "sql", "sh", "toml", "yaml", "yml"]),
    ("Spreadsheets", &["csv", "xlsx", "xls"]),
];

/// A validated path plus the metadata the frontend needs to render it.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileEntry {
    /// Absolute, canonicalized path.
    pub path: PathBuf,
    /// Final path component, for display.
    pub name: String,
    /// Lowercased extension without the dot, when present.
    pub extension: Option<String>,
    /// Size in bytes (0 for directories).
    pub size: u64,
    /// Whether the path is a directory.
    pub is_dir: bool,
}

impl FileEntry {
    /// Builds an entry from an already-validated path.
    fn from_path(path: PathBuf) -> Result<Self> {
        let meta = std::fs::metadata(&path)?;
        Ok(Self {
            name: path
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default(),
            extension: path
                .extension()
                .map(|e| e.to_string_lossy().to_lowercase()),
            size: if meta.is_dir() { 0 } else { meta.len() },
            is_dir: meta.is_dir(),
            path,
        })
    }
}

/// Canonicalizes `path` and confirms it exists and lies within the workspace root.
///
/// When no workspace root is configured the scope check is skipped and only
/// existence is enforced.
pub fn validate_path<R: Runtime>(app: &AppHandle<R>, path: &Path) -> Result<PathBuf> {
    let canonical = std::fs::canonicalize(path).map_err(|_| {
        Error::InvalidPath(format!("path does not exist or is unreadable: {}", path.display()))
    })?;

    let root = app.state::<AppState>().lock().workspace_root.clone();
    if let Some(root) = root {
        // The root itself is canonicalized on the way in (`set_workspace_root`),
        // but re-canonicalize defensively in case it changed on disk.
        let root = std::fs::canonicalize(&root).unwrap_or(root);
        if !canonical.starts_with(&root) {
            return Err(Error::InvalidPath(format!(
                "path `{}` is outside the workspace `{}`",
                canonical.display(),
                root.display()
            )));
        }
    }
    Ok(canonical)
}

/// Validates a batch of paths (used for drag-and-drop payloads).
///
/// Invalid entries are dropped rather than failing the whole drop; the frontend
/// compares lengths to report how many files were rejected.
#[tauri::command]
pub fn validate_paths<R: Runtime>(app: AppHandle<R>, paths: Vec<PathBuf>) -> Vec<FileEntry> {
    paths
        .iter()
        .filter_map(|p| validate_path(&app, p).ok())
        .filter_map(|p| FileEntry::from_path(p).ok())
        .collect()
}

/// Applies Dream's file-type filters to a dialog builder.
fn with_filters<R: Runtime>(
    mut builder: tauri_plugin_dialog::FileDialogBuilder<R>,
) -> tauri_plugin_dialog::FileDialogBuilder<R> {
    for (name, exts) in FILTERS {
        builder = builder.add_filter(*name, exts);
    }
    builder.add_filter("All files", &["*"])
}

/// Opens the native "Open file" dialog.
///
/// Returns validated entries; an empty vector means the user cancelled.
#[tauri::command]
pub async fn open_file_dialog<R: Runtime>(
    app: AppHandle<R>,
    multiple: Option<bool>,
    title: Option<String>,
) -> Result<Vec<FileEntry>> {
    let mut builder = app.dialog().file();
    if let Some(title) = title {
        builder = builder.set_title(title);
    }
    if let Some(dir) = app.state::<AppState>().lock().workspace_root.clone() {
        builder = builder.set_directory(dir);
    }
    let builder = with_filters(builder);

    let picked: Vec<FilePath> = if multiple.unwrap_or(false) {
        builder.blocking_pick_files().unwrap_or_default()
    } else {
        builder.blocking_pick_file().map(|f| vec![f]).unwrap_or_default()
    };

    let mut entries = Vec::with_capacity(picked.len());
    for file in picked {
        let path = file
            .into_path()
            .map_err(|e| Error::Dialog(e.to_string()))?;
        let validated = validate_path(&app, &path)?;
        entries.push(FileEntry::from_path(validated)?);
    }
    Ok(entries)
}

/// Opens the native "Save file" dialog. Returns `None` when cancelled.
///
/// The chosen path is *not* validated for existence (it usually does not exist
/// yet); when a workspace root is set, the parent directory must be inside it.
#[tauri::command]
pub async fn save_file_dialog<R: Runtime>(
    app: AppHandle<R>,
    default_name: Option<String>,
    title: Option<String>,
) -> Result<Option<PathBuf>> {
    let mut builder = app.dialog().file();
    if let Some(name) = default_name {
        builder = builder.set_file_name(name);
    }
    if let Some(title) = title {
        builder = builder.set_title(title);
    }
    if let Some(dir) = app.state::<AppState>().lock().workspace_root.clone() {
        builder = builder.set_directory(dir);
    }

    let Some(file) = with_filters(builder).blocking_save_file() else {
        return Ok(None);
    };
    let path = file.into_path().map_err(|e| Error::Dialog(e.to_string()))?;

    if let Some(parent) = path.parent() {
        validate_path(&app, parent)?;
    }
    Ok(Some(path))
}

/// Opens the native folder picker, used for choosing the workspace root.
#[tauri::command]
pub async fn select_folder_dialog<R: Runtime>(
    app: AppHandle<R>,
    title: Option<String>,
) -> Result<Option<PathBuf>> {
    let mut builder = app.dialog().file();
    if let Some(title) = title {
        builder = builder.set_title(title);
    }

    let Some(folder) = builder.blocking_pick_folder() else {
        return Ok(None);
    };
    let path = folder.into_path().map_err(|e| Error::Dialog(e.to_string()))?;
    Ok(Some(std::fs::canonicalize(&path).unwrap_or(path)))
}

/// Sets the workspace root that scopes all later path validation.
///
/// Passing `None` clears the restriction.
#[tauri::command]
pub fn set_workspace_root<R: Runtime>(app: AppHandle<R>, path: Option<PathBuf>) -> Result<()> {
    let resolved = match path {
        Some(p) => {
            let canonical = std::fs::canonicalize(&p)
                .map_err(|_| Error::InvalidPath(format!("workspace does not exist: {}", p.display())))?;
            if !canonical.is_dir() {
                return Err(Error::InvalidPath(format!(
                    "workspace is not a directory: {}",
                    canonical.display()
                )));
            }
            Some(canonical)
        }
        None => None,
    };

    app.state::<AppState>().lock().workspace_root = resolved;
    Ok(())
}
