//! JSON-RPC 2.0 framing for the bridge.
//!
//! One message per line, newline-delimited (see `docs/bridge/protocol.md` §1).
//! This module is pure data work — no I/O — so it is exhaustively unit-tested
//! and reused by both the writer (encoding requests) and the reader (parsing
//! responses/notifications from the sidecar).

use serde_json::{json, Value};

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

/// Parse one stdout line into a [`ParsedMessage`], or `None` if it is not a
/// recognised JSON-RPC 2.0 message (the caller logs and skips it).
#[allow(clippy::too_many_lines)] // classification is inherently branchy
pub fn parse(line: &str) -> Option<ParsedMessage> {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return None;
    }
    let value: Value = serde_json::from_str(trimmed).ok()?;

    // The protocol header line is emitted before JSON messages; skip it.
    if trimmed.starts_with("DREAM-PROTOCOL:") {
        return None;
    }
    let obj = value.as_object()?;

    let id = obj.get("id").and_then(id_as_u64);

    // A response carries a result or an error alongside an id.
    if let Some(result) = obj.get("result").cloned() {
        let id = id?;
        return Some(ParsedMessage::Response {
            id,
            outcome: Outcome::Result(result),
        });
    }
    if let Some(error) = obj.get("error").cloned() {
        let id = id?;
        let err_code = error.get("code").and_then(Value::as_i64);
        let err_code = err_code.unwrap_or(code::INTERNAL_ERROR as i64) as i32;
        let message = error
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("error")
            .to_string();
        let data = error.get("data").cloned();
        return Some(ParsedMessage::Response {
            id,
            outcome: Outcome::Error {
                code: err_code,
                message,
                data,
            },
        });
    }

    // Otherwise it must be a notification: a `method` with optional `params`.
    let method = obj.get("method").and_then(Value::as_str)?.to_string();
    let params = obj.get("params").cloned().unwrap_or(Value::Null);
    Some(ParsedMessage::Notification { method, params })
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
    fn parse_skips_header_blank_and_garbage() {
        assert!(parse("DREAM-PROTOCOL: 1.0").is_none());
        assert!(parse("").is_none());
        assert!(parse("   ").is_none());
        assert!(parse("not json").is_none());
        assert!(parse(r#"{"no":"method"}"#).is_none());
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
        // A non-numeric id cannot be matched to a pending request, so it is dropped.
        assert!(parse(r#"{"jsonrpc":"2.0","id":"abc","result":1}"#).is_none());
    }
}
