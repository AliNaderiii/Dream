//! JSON-RPC 2.0 framing for the bridge.
//!
//! One message per line, newline-delimited (see `docs/bridge/protocol.md` §1).
//! This module is pure data work — no I/O — so it is exhaustively unit-tested
//! and reused by both the writer (encoding requests) and the reader (parsing
//! responses/notifications from the sidecar).

use serde_json::{json, Value};

use crate::error::BridgeError;

/// Maximum accepted size of a single newline-delimited frame, in bytes.
///
/// Oversized frames are rejected rather than parsed so a runaway sidecar
/// cannot force unbounded allocation in the shell. 16 MiB comfortably covers
/// conversation payloads and tool results without accepting multi-hundred-MB
/// blobs.
pub const MAX_FRAME_BYTES: usize = 16 * 1024 * 1024;

/// Prefix of the sidecar's startup handshake line (protocol §1.1).
pub const PROTOCOL_HEADER_PREFIX: &str = "DREAM-PROTOCOL:";
/// The only protocol major version this shell speaks. A sidecar announcing a
/// different major is refused (§1.1: a major mismatch is fatal, a minor
/// difference is additive and ignored).
pub const SUPPORTED_PROTOCOL_MAJOR: u32 = 1;

/// Request ids at or above this value are reserved for shell-originated
/// traffic (the heartbeat). Frontend ids must stay below it so a heartbeat
/// reply can never be matched to a frontend request, and vice versa
/// (SEC-10 request ownership).
pub const RESERVED_ID_FLOOR: u64 = 1 << 62;

/// Numeric error codes, kept in lock-step with `dream/bridge/errors.py`.
pub mod code {
    pub const PARSE_ERROR: i32 = -32700;
    pub const INVALID_REQUEST: i32 = -32600;
    pub const METHOD_NOT_FOUND: i32 = -32601;
    pub const INVALID_PARAMS: i32 = -32602;
    pub const INTERNAL_ERROR: i32 = -32603;
    pub const PROVIDER_ERROR: i32 = -32001;
    pub const AUTH_ERROR: i32 = -32002;
    pub const RATE_LIMITED: i32 = -32003;
    pub const CONTEXT_OVERFLOW: i32 = -32004;
    pub const APPROVAL_REQUIRED: i32 = -32005;
    pub const TOOL_ERROR: i32 = -32006;
    pub const RESOURCE_EXHAUSTED: i32 = -32007;
}

/// The outcome of a request: either a `result` value or a structured `error`.
#[derive(Debug, Clone)]
pub enum Outcome {
    /// A successful `result`.
    Result(Value),
    /// A structured RPC error.
    Error {
        code: i32,
        message: String,
        data: Option<Value>,
    },
}

/// A parsed line from the sidecar's stdout.
#[derive(Debug, Clone)]
pub enum ParsedMessage {
    /// A response (has an `id`) carrying a result or an error.
    Response { id: u64, outcome: Outcome },
    /// A server notification (no `id`), e.g. `stream.chunk` or `state`.
    Notification { method: String, params: Value },
}

/// Encode a request as a single JSON line (without the trailing newline).
///
/// # Errors
/// Never fails for serialisable inputs; returns a string for trait symmetry.
pub fn request_line(id: u64, method: &str, params: &Value) -> String {
    json!({"jsonrpc": "2.0", "id": id, "method": method, "params": params}).to_string()
}

/// Build a JSON-RPC error response object.
pub fn error_response(id: Option<u64>, code: i32, message: &str, data: Option<Value>) -> Value {
    let mut error = json!({"code": code, "message": message});
    if let Some(data) = data {
        error["data"] = data;
    }
    json!({"jsonrpc": "2.0", "id": id, "error": error})
}

/// A parsed `DREAM-PROTOCOL: <major>.<minor>` handshake line.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProtocolVersion {
    pub major: u32,
    pub minor: u32,
}

/// Whether `line` is the protocol handshake (regardless of validity).
pub fn is_protocol_header(line: &str) -> bool {
    line.trim_start().starts_with(PROTOCOL_HEADER_PREFIX)
}

/// Parse and validate the handshake line.
///
/// # Errors
/// A malformed version or an unsupported major returns a typed error; the
/// supervisor treats that as an unusable instance instead of marking the
/// bridge `Ready` on the strength of an unknown peer.
pub fn parse_header(line: &str) -> std::result::Result<ProtocolVersion, BridgeError> {
    let rest = line
        .trim()
        .strip_prefix(PROTOCOL_HEADER_PREFIX)
        .ok_or_else(|| BridgeError::malformed("not a protocol header"))?
        .trim();
    let (major, minor) = rest
        .split_once('.')
        .ok_or_else(|| BridgeError::malformed("protocol version must be MAJOR.MINOR"))?;
    let major: u32 = major
        .parse()
        .map_err(|_| BridgeError::malformed("protocol major version is not a number"))?;
    let minor: u32 = minor
        .parse()
        .map_err(|_| BridgeError::malformed("protocol minor version is not a number"))?;
    if major != SUPPORTED_PROTOCOL_MAJOR {
        return Err(BridgeError::protocol_version(
            major,
            SUPPORTED_PROTOCOL_MAJOR,
        ));
    }
    Ok(ProtocolVersion { major, minor })
}

/// Parse one stdout line into a [`ParsedMessage`].
///
/// Malformed frames, invalid JSON, missing JSON-RPC fields, oversized messages
/// and protocol headers return a [`BridgeError`] with a reason — never the raw
/// line, which may contain conversation content. Valid messages keep the same
/// shape they always did.
pub fn parse(line: &str) -> std::result::Result<ParsedMessage, BridgeError> {
    let trimmed = line.trim();
    validate_frame(trimmed)?;
    let value: Value = serde_json::from_str(trimmed)?;
    classify_message(value)
}

/// Parse a raw byte slice, rejecting invalid UTF-8 before JSON classification.
pub fn parse_bytes(bytes: &[u8]) -> std::result::Result<ParsedMessage, BridgeError> {
    if bytes.len() > MAX_FRAME_BYTES {
        return Err(BridgeError::frame_too_large(bytes.len(), MAX_FRAME_BYTES));
    }
    let line = std::str::from_utf8(bytes)
        .map_err(|_| BridgeError::malformed("frame is not valid UTF-8"))?;
    parse(line)
}

/// Reject empty, oversized, or protocol-header frames before JSON parsing.
fn validate_frame(trimmed: &str) -> std::result::Result<(), BridgeError> {
    if trimmed.is_empty() {
        return Err(BridgeError::malformed("empty frame"));
    }
    if trimmed.len() > MAX_FRAME_BYTES {
        return Err(BridgeError::frame_too_large(trimmed.len(), MAX_FRAME_BYTES));
    }
    if trimmed.starts_with(PROTOCOL_HEADER_PREFIX) {
        return Err(BridgeError::malformed(
            "protocol header is not a JSON-RPC message",
        ));
    }
    Ok(())
}

/// Classify a decoded JSON value as a response or a notification.
#[allow(clippy::too_many_lines)] // result / error / notification branches
fn classify_message(value: Value) -> std::result::Result<ParsedMessage, BridgeError> {
    let obj = value
        .as_object()
        .ok_or_else(|| BridgeError::malformed("JSON-RPC frame must be an object"))?;

    let id = obj.get("id").and_then(id_as_u64);

    // A response carries a result or an error alongside an id.
    if let Some(result) = obj.get("result").cloned() {
        let id = id.ok_or_else(|| BridgeError::malformed("response is missing a numeric id"))?;
        return Ok(ParsedMessage::Response {
            id,
            outcome: Outcome::Result(result),
        });
    }
    if let Some(error) = obj.get("error").cloned() {
        let id =
            id.ok_or_else(|| BridgeError::malformed("error response is missing a numeric id"))?;
        // An out-of-range code must not wrap into an unrelated taxonomy
        // entry: anything that does not fit `i32` is reported as internal.
        let err_code = error
            .get("code")
            .and_then(Value::as_i64)
            .and_then(|raw| i32::try_from(raw).ok())
            .unwrap_or(code::INTERNAL_ERROR);
        let message = error
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("error")
            .to_string();
        let data = error.get("data").cloned();
        return Ok(ParsedMessage::Response {
            id,
            outcome: Outcome::Error {
                code: err_code,
                message,
                data,
            },
        });
    }

    // Otherwise it must be a notification: a `method` with optional `params`.
    let method = obj
        .get("method")
        .and_then(Value::as_str)
        .ok_or_else(|| BridgeError::malformed("message is missing result, error, or method"))?
        .to_string();
    let params = obj.get("params").cloned().unwrap_or_default();
    Ok(ParsedMessage::Notification { method, params })
}

/// Coerce a JSON id (number or string) into a `u64`, if possible.
fn id_as_u64(value: &Value) -> Option<u64> {
    match value {
        Value::Number(n) => n.as_u64(),
        Value::String(s) => s.parse().ok(),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_line_is_single_json_object() {
        let line = request_line(7, "health.check", &json!({}));
        let v: Value = serde_json::from_str(&line).unwrap();
        assert_eq!(v["jsonrpc"], "2.0");
        assert_eq!(v["id"], 7);
        assert_eq!(v["method"], "health.check");
        assert!(!line.contains('\n'));
    }

    #[test]
    fn parse_result_response() {
        let msg = parse(r#"{"jsonrpc":"2.0","id":3,"result":{"status":"ok"}}"#).unwrap();
        match msg {
            ParsedMessage::Response { id, outcome } => {
                assert_eq!(id, 3);
                assert!(matches!(outcome, Outcome::Result(_)));
            }
            _ => panic!("expected response"),
        }
    }

    #[test]
    fn parse_error_response() {
        let line = error_response(Some(9), code::METHOD_NOT_FOUND, "x", None).to_string();
        let msg = parse(line.as_str()).unwrap();
        match msg {
            ParsedMessage::Response {
                id,
                outcome: Outcome::Error { code, .. },
            } => {
                assert_eq!(id, 9);
                assert_eq!(code, code::METHOD_NOT_FOUND);
            }
            _ => panic!("expected error response"),
        }
    }

    #[test]
    fn parse_stream_chunk_notification() {
        let msg =
            parse(r#"{"jsonrpc":"2.0","method":"stream.chunk","params":{"id":2,"token":"hi"}}"#)
                .unwrap();
        match msg {
            ParsedMessage::Notification { method, params } => {
                assert_eq!(method, "stream.chunk");
                assert_eq!(params["token"], "hi");
            }
            _ => panic!("expected notification"),
        }
    }

    #[test]
    fn parse_rejects_header_blank_and_garbage() {
        assert!(parse("DREAM-PROTOCOL: 1.0").is_err());
        assert!(parse("").is_err());
        assert!(parse("   ").is_err());
        assert!(parse("not json").is_err());
        assert!(parse(r#"{"no":"method"}"#).is_err());
        let empty = parse("").unwrap_err();
        assert!(
            empty.message.contains("empty"),
            "expected empty-frame error, got {empty:?}"
        );
        let garbage = parse("not json").unwrap_err();
        assert!(
            garbage.message.starts_with("JSON error:"),
            "incomplete JSON must surface as JSON error, got {garbage:?}"
        );
        let missing = parse(r#"{"no":"method"}"#).unwrap_err();
        assert!(
            missing.message.contains("malformed frame"),
            "expected malformed frame, got {missing:?}"
        );
    }

    #[test]
    fn parse_accepts_numeric_string_id() {
        // The bridge always sends numeric ids, but the wire format allows a
        // numeric *string* id; it should coerce to u64.
        let msg = parse(r#"{"jsonrpc":"2.0","id":"42","result":1}"#).unwrap();
        match msg {
            ParsedMessage::Response { id, .. } => assert_eq!(id, 42),
            _ => panic!("expected response"),
        }
    }

    #[test]
    fn parse_drops_non_numeric_string_id() {
        // A non-numeric id cannot be matched to a pending request.
        let err = parse(r#"{"jsonrpc":"2.0","id":"abc","result":1}"#).unwrap_err();
        assert!(
            err.message.contains("numeric id"),
            "expected missing-numeric-id error, got {err}"
        );
    }

    #[test]
    fn parse_rejects_invalid_json_with_serde_error() {
        let err = parse("{\"jsonrpc\":").unwrap_err();
        assert!(
            err.message.starts_with("JSON error:"),
            "incomplete JSON must surface as JSON error, got {err:?}"
        );
        assert!(err.to_string().starts_with("JSON error:"));
        // The reason must not echo the raw (possibly sensitive) frame.
        assert!(!err.to_string().contains("jsonrpc"));
    }

    #[test]
    fn parse_rejects_oversized_frame() {
        let oversized = "x".repeat(MAX_FRAME_BYTES + 1);
        let err = parse(&oversized).unwrap_err();
        assert_eq!(err.code, code::PARSE_ERROR);
        assert!(
            err.message.contains(&(MAX_FRAME_BYTES + 1).to_string()),
            "oversize message should mention the observed size, got {err:?}"
        );
    }

    #[test]
    fn parse_bytes_rejects_invalid_utf8() {
        let err = parse_bytes(&[0xff, 0xfe, 0xfd]).unwrap_err();
        assert!(
            err.message.contains("UTF-8"),
            "expected UTF-8 error, got {err}"
        );
    }

    #[test]
    fn parse_header_accepts_supported_major_and_any_minor() {
        assert_eq!(
            parse_header("DREAM-PROTOCOL: 1.0").unwrap(),
            ProtocolVersion { major: 1, minor: 0 }
        );
        assert_eq!(
            parse_header("DREAM-PROTOCOL: 1.7\r").unwrap(),
            ProtocolVersion { major: 1, minor: 7 }
        );
        assert!(is_protocol_header("DREAM-PROTOCOL: 1.0"));
        assert!(!is_protocol_header("{\"jsonrpc\":\"2.0\"}"));
    }

    #[test]
    fn parse_header_rejects_other_major_and_garbage() {
        let err = parse_header("DREAM-PROTOCOL: 2.0").unwrap_err();
        assert!(err.message.contains("major"), "got {err:?}");
        assert!(parse_header("DREAM-PROTOCOL: x.y").is_err());
        assert!(parse_header("DREAM-PROTOCOL: 1").is_err());
        assert!(parse_header("DREAM-PROTOCOL:").is_err());
        assert!(parse_header("hello").is_err());
    }

    #[test]
    fn out_of_range_error_code_maps_to_internal_error() {
        let msg = parse(r#"{"jsonrpc":"2.0","id":1,"error":{"code":99999999999,"message":"x"}}"#)
            .unwrap();
        match msg {
            ParsedMessage::Response {
                outcome: Outcome::Error { code, .. },
                ..
            } => assert_eq!(code, code::INTERNAL_ERROR),
            other => panic!("expected error response, got {other:?}"),
        }
    }

    #[test]
    fn reserved_id_floor_is_far_above_frontend_counters() {
        assert!(RESERVED_ID_FLOOR > u64::from(u32::MAX));
    }

    #[test]
    fn parse_bytes_accepts_valid_response() {
        let line = br#"{"jsonrpc":"2.0","id":1,"result":true}"#;
        let msg = parse_bytes(line).unwrap();
        match msg {
            ParsedMessage::Response { id, outcome } => {
                assert_eq!(id, 1);
                assert!(matches!(outcome, Outcome::Result(Value::Bool(true))));
            }
            _ => panic!("expected response"),
        }
    }
}
