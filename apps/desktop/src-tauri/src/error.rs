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
    fn serialize<S>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error>
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

/// Structured failure for every recoverable bridge/sidecar operation.
///
/// Constructors map I/O, JSON, process, argument, timeout and permission
/// failures onto JSON-RPC `{ code, message, data? }` so the frontend can keep
/// branching in `src/lib/bridge/errors.ts`. Messages never include secrets,
/// API keys, command arguments, or raw filesystem paths.
#[derive(Debug, Serialize)]
pub struct BridgeError {
    /// JSON-RPC error code.
    pub code: i32,
    /// Human-readable message. Rust-constructed values never embed paths.
    pub message: String,
    /// Optional structured payload (`approval_id`, …). Omitted when `None`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

impl fmt::Display for BridgeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for BridgeError {}

impl BridgeError {
    /// Wrap a structured RPC error from the sidecar.
    pub fn rpc(code: i32, message: String, data: Option<Value>) -> Self {
        Self {
            code,
            message,
            data,
        }
    }

    /// The sidecar is not connected / not yet ready.
    ///
    /// Carries `data.kind = "transport"` so the frontend can tell a shell
    /// transport failure from a Python `INTERNAL_ERROR` without parsing the
    /// message (SEC-10). The numeric code is unchanged for compatibility.
    pub fn not_ready() -> Self {
        Self {
            code: RPC_INTERNAL_ERROR,
            message: "bridge is not connected".to_string(),
            data: Some(transport_kind()),
        }
    }

    /// The sidecar went away (EOF, crash, heartbeat timeout, restart) while
    /// this request was in flight. Same code as before; tagged as transport.
    pub fn transport(message: &str) -> Self {
        Self {
            code: RPC_INTERNAL_ERROR,
            message: message.to_string(),
            data: Some(transport_kind()),
        }
    }

    /// The sidecar announced a protocol major this shell does not speak.
    pub fn protocol_version(found: u32, supported: u32) -> Self {
        Self {
            code: RPC_PARSE_ERROR,
            message: format!(
                "unsupported protocol major version {found} (this build speaks {supported})"
            ),
            data: Some(transport_kind()),
        }
    }

    /// An internal bridge failure (channel closed, etc.).
    pub fn internal(message: &str) -> Self {
        Self {
            code: RPC_INTERNAL_ERROR,
            message: message.to_string(),
            data: None,
        }
    }

    /// Convert an I/O error for a named operation without embedding paths.
    pub fn io(operation: &'static str, err: std::io::Error) -> Self {
        match err.kind() {
            std::io::ErrorKind::NotFound => Self {
                code: RPC_INTERNAL_ERROR,
                message: format!("process not found: {operation}"),
                data: None,
            },
            std::io::ErrorKind::PermissionDenied => Self {
                code: RPC_AUTH_ERROR,
                message: format!("permission denied: {operation}"),
                data: None,
            },
            kind => Self {
                code: RPC_INTERNAL_ERROR,
                message: format!("I/O error during {operation}: {kind:?}"),
                data: None,
            },
        }
    }

    /// Missing pipes / unusable child.
    pub fn sidecar_crashed(reason: impl Into<String>) -> Self {
        Self {
            code: RPC_INTERNAL_ERROR,
            message: format!("sidecar crashed: {}", reason.into()),
            data: None,
        }
    }

    /// Duplicate request id or other caller error.
    pub fn invalid_argument(reason: impl Into<String>) -> Self {
        Self {
            code: RPC_INVALID_PARAMS,
            message: format!("invalid argument: {}", reason.into()),
            data: None,
        }
    }

    /// Framing reason only — never the raw frame.
    pub fn malformed(reason: impl Into<String>) -> Self {
        Self {
            code: RPC_PARSE_ERROR,
            message: format!("malformed frame: {}", reason.into()),
            data: None,
        }
    }

    /// A single frame exceeded [`crate::bridge::framing::MAX_FRAME_BYTES`].
    pub fn frame_too_large(size: usize, max: usize) -> Self {
        Self {
            code: RPC_PARSE_ERROR,
            message: format!("frame of {size} bytes exceeds the {max} byte limit"),
            data: None,
        }
    }

    /// Explicit deadline (heartbeat still restarts the sidecar).
    pub fn timeout(duration: Duration) -> Self {
        Self {
            code: RPC_INTERNAL_ERROR,
            message: format!("operation timed out after {duration:?}"),
            data: Some(serde_json::json!({ "kind": "timeout" })),
        }
    }

    /// Whether this error originated in the shell transport rather than in
    /// the sidecar's handler taxonomy.
    pub fn is_transport(&self) -> bool {
        self.data
            .as_ref()
            .and_then(|d| d.get("kind"))
            .and_then(Value::as_str)
            .is_some_and(|k| k == "transport")
    }

    /// JSON-RPC numeric code used when this error crosses the Tauri boundary.
    pub fn rpc_code(&self) -> i32 {
        self.code
    }
}

/// The additive discriminator attached to shell-originated errors.
fn transport_kind() -> Value {
    serde_json::json!({ "kind": "transport" })
}

impl From<std::io::Error> for BridgeError {
    fn from(err: std::io::Error) -> Self {
        Self::io("bridge I/O", err)
    }
}

impl From<serde_json::Error> for BridgeError {
    fn from(err: serde_json::Error) -> Self {
        Self {
            code: RPC_PARSE_ERROR,
            message: format!("JSON error: {err}"),
            data: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn display_representative_variants() {
        assert_eq!(
            BridgeError {
                code: RPC_INTERNAL_ERROR,
                message: "process not found: python3".into(),
                data: None,
            }
            .to_string(),
            "process not found: python3"
        );
        assert_eq!(
            BridgeError::sidecar_crashed("missing piped stdin").to_string(),
            "sidecar crashed: missing piped stdin"
        );
        assert_eq!(
            BridgeError::invalid_argument("duplicate bridge request id 7").to_string(),
            "invalid argument: duplicate bridge request id 7"
        );
        assert_eq!(
            BridgeError::io(
                "create sidecar data root",
                std::io::Error::new(std::io::ErrorKind::PermissionDenied, "/etc/shadow"),
            )
            .to_string(),
            "permission denied: create sidecar data root"
        );
        assert_eq!(
            BridgeError::not_ready().to_string(),
            "bridge is not connected"
        );
        let timed_out = BridgeError::timeout(Duration::from_secs(15)).to_string();
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
        assert_eq!(err.code, RPC_INTERNAL_ERROR);
        assert!(displayed.contains("BrokenPipe") || displayed.contains("broken pipe"));
        assert!(
            displayed.contains("bridge I/O"),
            "I/O display should name the operation, got {displayed}"
        );
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
        assert_eq!(missing.message, "process not found: spawn sidecar");
        assert!(!missing.to_string().contains("/usr/bin"));

        let denied = BridgeError::from(std::io::Error::new(
            std::io::ErrorKind::PermissionDenied,
            "/etc/shadow",
        ));
        assert_eq!(denied.code, RPC_AUTH_ERROR);
        assert!(!denied.to_string().contains("shadow"));
        assert_eq!(denied.rpc_code(), RPC_AUTH_ERROR);
    }

    #[test]
    fn from_serde_json_error() {
        let serde_err = serde_json::from_str::<Value>("{\"oops\":").unwrap_err();
        let err = BridgeError::from(serde_err);
        assert_eq!(err.code, RPC_PARSE_ERROR);
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
        // Shell-originated: tagged so the frontend can tell it from a sidecar
        // INTERNAL_ERROR; the code itself is unchanged.
        assert_eq!(ready["data"]["kind"], "transport");
        assert!(BridgeError::not_ready().is_transport());
        assert!(BridgeError::transport("sidecar restarted").is_transport());
        assert!(!BridgeError::internal("x").is_transport());
        assert!(!BridgeError::rpc(-32603, "py".into(), None).is_transport());

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
    fn protocol_version_error_is_typed_and_transport_tagged() {
        let err = BridgeError::protocol_version(2, 1);
        assert_eq!(err.rpc_code(), RPC_PARSE_ERROR);
        assert!(err.is_transport());
        assert!(err.message.contains('2') && err.message.contains('1'));
    }

    #[test]
    fn timeout_is_tagged_as_timeout_not_transport() {
        let err = BridgeError::timeout(Duration::from_secs(1));
        assert_eq!(err.data.as_ref().unwrap()["kind"], "timeout");
        assert!(!err.is_transport());
    }

    #[test]
    fn malformed_and_oversize_frames_use_parse_error_code() {
        let malformed = BridgeError::malformed("empty frame");
        assert_eq!(malformed.rpc_code(), RPC_PARSE_ERROR);
        assert!(malformed.to_string().contains("empty frame"));

        let oversized = BridgeError::frame_too_large(99, 10);
        assert_eq!(oversized.rpc_code(), RPC_PARSE_ERROR);
        let json = serde_json::to_value(&oversized).expect("serialize frame too large");
        assert_eq!(json["code"], RPC_PARSE_ERROR);
        assert!(
            json["message"].as_str().unwrap().contains("99"),
            "oversize message should mention the observed size"
        );
    }
}
