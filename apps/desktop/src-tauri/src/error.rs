//! Error types shared by the desktop shell and the Python sidecar bridge.
//!
//! [`Error`] is the command-facing type for window, tray, dialog and
//! notification handlers. [`BridgeError`] is the typed error used by the
//! sidecar bridge (process supervision, JSON-RPC framing, dispatcher) and by
//! the `bridge_*` Tauri commands.
//!
//! Tauri requires a command's error type to implement [`serde::Serialize`].
//! [`Error`] serialises to a plain string. [`BridgeError`] serialises to
//! `{ code, message, data? }` so the frontend can keep branching on JSON-RPC
//! taxonomy (`src/lib/bridge/errors.ts`). Neither payload includes secrets,
//! API keys, command arguments, or raw filesystem paths.

use std::fmt;
use std::time::Duration;

use serde::{Serialize, Serializer};
use serde_json::Value;

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

/// Convenience alias used by all non-bridge command signatures.
pub type Result<T, E = Error> = std::result::Result<T, E>;

/// JSON-RPC `parse error` (kept in lock-step with `framing::code::PARSE_ERROR`).
const RPC_PARSE_ERROR: i32 = -32700;
/// JSON-RPC `invalid params`.
const RPC_INVALID_PARAMS: i32 = -32602;
/// JSON-RPC `internal error`.
const RPC_INTERNAL_ERROR: i32 = -32603;
/// Dream `auth error`.
const RPC_AUTH_ERROR: i32 = -32002;

/// Typed failure for every recoverable bridge/sidecar operation.
///
/// Variants are chosen to match the actual failure classes of the stdio
/// supervisor: I/O on pipes, JSON framing, missing interpreters, crashed
/// children, bad arguments, timeouts, and permission failures. [`Self::Other`]
/// is the fallback for internal coordination failures (closed oneshot, missing
/// writer) that do not fit a more specific variant; its message must never
/// include secrets or filesystem paths.
#[derive(Debug)]
pub enum BridgeError {
    /// An I/O operation failed. Only the operation name and [`std::io::ErrorKind`]
    /// are retained so the original `Display` (which often embeds local paths)
    /// never reaches the frontend.
    Io {
        /// Short name of the failed operation (`spawn sidecar`, `write stdin`, …).
        operation: &'static str,
        /// OS error class without path or argument details.
        kind: std::io::ErrorKind,
    },

    /// JSON serialisation or deserialisation failed.
    Serde(serde_json::Error),

    /// A required process or interpreter could not be found.
    ProcessNotFound(String),

    /// The sidecar process exited, lost its pipes, or otherwise became unusable.
    SidecarCrashed(String),

    /// A caller-supplied argument was invalid (duplicate request id, …).
    InvalidArgument(String),

    /// An operation exceeded its deadline.
    Timeout(Duration),

    /// The OS denied an operation (spawn, create directory, …).
    PermissionDenied(String),

    /// The sidecar is not connected, or the stdin writer channel is gone.
    NotReady,

    /// Structured JSON-RPC error forwarded from the sidecar. `data` is passed
    /// through unchanged (the Python core owns that object); Rust-constructed
    /// errors always set `data` to `None`.
    Rpc {
        /// JSON-RPC error code.
        code: i32,
        /// Human-readable message from the sidecar.
        message: String,
        /// Optional structured payload (`approval_id`, …).
        data: Option<Value>,
    },

    /// A newline-delimited frame was empty, not an object, missing required
    /// JSON-RPC fields, or not valid UTF-8. The stored string is a reason, never
    /// the raw frame (frames may contain conversation content).
    MalformedFrame(String),

    /// A single frame exceeded [`crate::bridge::framing::MAX_FRAME_BYTES`].
    FrameTooLarge {
        /// Observed frame size in bytes.
        size: usize,
        /// Configured maximum.
        max: usize,
    },

    /// Catch-all for internal bridge failures that do not fit a more specific
    /// variant. Justified because oneshot/channel closures and unexpected
    /// supervisor states are real, recoverable conditions, but they are not I/O,
    /// JSON, or process-lifecycle errors. Messages must stay free of secrets.
    Other(String),
}

impl fmt::Display for BridgeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io { operation, kind } => {
                write!(f, "I/O error during {operation}: {kind:?}")
            }
            Self::Serde(err) => write!(f, "JSON error: {err}"),
            Self::ProcessNotFound(name) => write!(f, "process not found: {name}"),
            Self::SidecarCrashed(reason) => write!(f, "sidecar crashed: {reason}"),
            Self::InvalidArgument(reason) => write!(f, "invalid argument: {reason}"),
            Self::Timeout(duration) => write!(f, "operation timed out after {duration:?}"),
            Self::PermissionDenied(reason) => write!(f, "permission denied: {reason}"),
            Self::NotReady => write!(f, "bridge is not connected"),
            Self::Rpc { code, message, .. } => write!(f, "RPC error {code}: {message}"),
            Self::MalformedFrame(reason) => write!(f, "malformed frame: {reason}"),
            Self::FrameTooLarge { size, max } => {
                write!(f, "frame of {size} bytes exceeds the {max} byte limit")
            }
            Self::Other(reason) => write!(f, "bridge error: {reason}"),
        }
    }
}

impl std::error::Error for BridgeError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Serde(err) => Some(err),
            _ => None,
        }
    }
}

impl BridgeError {
    /// Wrap a structured RPC error from the sidecar.
    pub fn rpc(code: i32, message: String, data: Option<Value>) -> Self {
        Self::Rpc {
            code,
            message,
            data,
        }
    }

    /// The sidecar is not connected / not yet ready.
    pub fn not_ready() -> Self {
        Self::NotReady
    }

    /// An internal bridge failure (channel closed, etc.).
    pub fn internal(message: &str) -> Self {
        Self::Other(message.to_string())
    }

    /// Convert an I/O error for a named operation without embedding paths.
    pub fn io(operation: &'static str, err: std::io::Error) -> Self {
        match err.kind() {
            std::io::ErrorKind::NotFound => Self::ProcessNotFound(operation.to_string()),
            std::io::ErrorKind::PermissionDenied => Self::PermissionDenied(operation.to_string()),
            kind => Self::Io { operation, kind },
        }
    }

    /// JSON-RPC numeric code used when this error crosses the Tauri boundary.
    pub fn rpc_code(&self) -> i32 {
        match self {
            Self::Rpc { code, .. } => *code,
            Self::Serde(_) | Self::MalformedFrame(_) | Self::FrameTooLarge { .. } => {
                RPC_PARSE_ERROR
            }
            Self::InvalidArgument(_) => RPC_INVALID_PARAMS,
            Self::PermissionDenied(_) => RPC_AUTH_ERROR,
            Self::NotReady
            | Self::Io { .. }
            | Self::ProcessNotFound(_)
            | Self::SidecarCrashed(_)
            | Self::Timeout(_)
            | Self::Other(_) => RPC_INTERNAL_ERROR,
        }
    }

    /// Frontend-facing message. RPC errors keep the sidecar text; other
    /// variants use their [`Display`] form, except [`Self::Other`] which
    /// preserves the inner string so existing `internal(...)` payloads stay
    /// stable (`"sidecar closed"`, not `"bridge error: sidecar closed"`).
    pub fn rpc_message(&self) -> String {
        match self {
            Self::Rpc { message, .. } => message.clone(),
            Self::Other(message) => message.clone(),
            Self::NotReady => "bridge is not connected".to_string(),
            other => other.to_string(),
        }
    }

    /// Optional structured payload. Only sidecar RPC errors carry `data`.
    pub fn rpc_data(&self) -> Option<&Value> {
        match self {
            Self::Rpc { data, .. } => data.as_ref(),
            _ => None,
        }
    }
}

impl From<std::io::Error> for BridgeError {
    fn from(err: std::io::Error) -> Self {
        Self::io("bridge I/O", err)
    }
}

impl From<serde_json::Error> for BridgeError {
    fn from(err: serde_json::Error) -> Self {
        Self::Serde(err)
    }
}

/// Wire shape expected by `src/lib/bridge/errors.ts` (`toBridgeError`).
#[derive(Serialize)]
struct BridgeErrorWire<'a> {
    code: i32,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<&'a Value>,
}

impl Serialize for BridgeError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        BridgeErrorWire {
            code: self.rpc_code(),
            message: self.rpc_message(),
            data: self.rpc_data(),
        }
        .serialize(serializer)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn display_representative_variants() {
        assert_eq!(
            BridgeError::ProcessNotFound("python3".into()).to_string(),
            "process not found: python3"
        );
        assert_eq!(
            BridgeError::SidecarCrashed("missing piped stdin".into()).to_string(),
            "sidecar crashed: missing piped stdin"
        );
        assert_eq!(
            BridgeError::InvalidArgument("duplicate bridge request id 7".into()).to_string(),
            "invalid argument: duplicate bridge request id 7"
        );
        assert_eq!(
            BridgeError::PermissionDenied("create sidecar data root".into()).to_string(),
            "permission denied: create sidecar data root"
        );
        assert_eq!(
            BridgeError::not_ready().to_string(),
            "bridge is not connected"
        );
        let timed_out = BridgeError::Timeout(Duration::from_secs(15)).to_string();
        assert!(
            timed_out.contains("timed out"),
            "timeout display should mention the condition, got {timed_out}"
        );
        assert!(
            timed_out.contains("15"),
            "timeout display should include the duration, got {timed_out}"
        );
    }

    #[test]
    fn from_io_error_preserves_kind_without_path() {
        let io = std::io::Error::new(
            std::io::ErrorKind::BrokenPipe,
            "write /home/alice/.config/dream/secrets.env failed",
        );
        let err = BridgeError::from(io);
        let displayed = err.to_string();
        match err {
            BridgeError::Io { operation, kind } => {
                assert_eq!(operation, "bridge I/O");
                assert_eq!(kind, std::io::ErrorKind::BrokenPipe);
            }
            other => panic!("expected Io variant, got {other:?}"),
        }
        assert!(displayed.contains("BrokenPipe") || displayed.contains("broken pipe"));
        assert!(
            !displayed.contains("alice"),
            "I/O display must not leak a home-directory path: {displayed}"
        );
        assert!(
            !displayed.contains("secrets.env"),
            "I/O display must not leak a filename: {displayed}"
        );
    }

    #[test]
    fn from_io_not_found_and_permission_map_to_specific_variants() {
        let missing = BridgeError::io(
            "spawn sidecar",
            std::io::Error::new(std::io::ErrorKind::NotFound, "/usr/bin/python3"),
        );
        assert!(matches!(
            missing,
            BridgeError::ProcessNotFound(ref op) if op == "spawn sidecar"
        ));
        assert!(!missing.to_string().contains("/usr/bin"));

        let denied = BridgeError::from(std::io::Error::new(
            std::io::ErrorKind::PermissionDenied,
            "/etc/shadow",
        ));
        assert!(matches!(denied, BridgeError::PermissionDenied(_)));
        assert!(!denied.to_string().contains("shadow"));
        assert_eq!(denied.rpc_code(), RPC_AUTH_ERROR);
    }

    #[test]
    fn from_serde_json_error() {
        let serde_err = serde_json::from_str::<Value>("{\"oops\":").unwrap_err();
        let err = BridgeError::from(serde_err);
        assert!(
            matches!(err, BridgeError::Serde(_)),
            "expected Serde variant, got {err:?}"
        );
        let displayed = err.to_string();
        assert!(
            displayed.starts_with("JSON error:"),
            "serde conversion should keep JSON context, got {displayed}"
        );
        assert_eq!(err.rpc_code(), RPC_PARSE_ERROR);
    }

    #[test]
    fn serializes_as_structured_rpc_object() {
        let ready = serde_json::to_value(BridgeError::not_ready()).expect("serialize not_ready");
        assert_eq!(ready["code"], RPC_INTERNAL_ERROR);
        assert_eq!(ready["message"], "bridge is not connected");
        assert!(ready.get("data").is_none());

        let rpc = BridgeError::rpc(
            -32005,
            "approval required".into(),
            Some(json!({"approval_id": "appr_1"})),
        );
        let value = serde_json::to_value(&rpc).expect("serialize rpc");
        assert_eq!(value["code"], -32005);
        assert_eq!(value["message"], "approval required");
        assert_eq!(value["data"]["approval_id"], "appr_1");

        let internal = serde_json::to_value(BridgeError::internal("sidecar closed"))
            .expect("serialize internal");
        assert_eq!(internal["code"], RPC_INTERNAL_ERROR);
        assert_eq!(internal["message"], "sidecar closed");
        assert!(internal.get("data").is_none());
    }

    #[test]
    fn malformed_and_oversize_frames_use_parse_error_code() {
        let malformed = BridgeError::MalformedFrame("empty frame".into());
        assert_eq!(malformed.rpc_code(), RPC_PARSE_ERROR);
        assert!(malformed.to_string().contains("empty frame"));

        let oversized = BridgeError::FrameTooLarge { size: 99, max: 10 };
        assert_eq!(oversized.rpc_code(), RPC_PARSE_ERROR);
        let json = serde_json::to_value(&oversized).expect("serialize frame too large");
        assert_eq!(json["code"], RPC_PARSE_ERROR);
        assert!(
            json["message"].as_str().unwrap().contains("99"),
            "oversize message should mention the observed size"
        );
    }
}
