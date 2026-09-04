//! Pending-request tracking for the bridge.
//!
//! When the frontend calls `bridge_send`, the dispatcher reserves an id and
//! hands back two channels: a oneshot for the final result/error and an
//! unbounded MPSC for stream chunks. The stdout reader fulfils them as the
//! sidecar responds. Pure coordination logic — no I/O — so it is unit-tested.

use std::collections::HashMap;

use tokio::sync::{mpsc, oneshot};

use crate::bridge::framing::Outcome;
use crate::error::BridgeError;

/// One in-flight request: a oneshot for its final outcome and a sink for
/// `stream.chunk` notifications addressed to it.
struct PendingRequest {
    final_tx: Option<oneshot::Sender<Outcome>>,
    stream_tx: Option<mpsc::UnboundedSender<serde_json::Value>>,
}

/// Maps request id → in-flight request. Cheap to clone is *not* required: the
/// dispatcher lives behind an `Arc<Mutex<_>>` on the bridge.
#[derive(Default)]
pub struct Dispatcher {
    pending: HashMap<u64, PendingRequest>,
}

/// What `register` returns: the receiver ends the caller awaits.
#[derive(Debug)]
pub struct RequestChannels {
    /// Resolves with the final result or structured error.
    pub final_rx: oneshot::Receiver<Outcome>,
    /// Yields each `stream.chunk` params object.
    pub stream_rx: mpsc::UnboundedReceiver<serde_json::Value>,
}

impl Dispatcher {
    /// Create a fresh, empty dispatcher.
    pub fn new() -> Self {
        Self::default()
    }

    /// Reserve *id*. Returns [`BridgeError::invalid_argument`] if it is already
    /// in flight (the bridge increments ids monotonically; a duplicate is a
    /// caller error, not a reason to take the process down).
    pub fn register(&mut self, id: u64) -> std::result::Result<RequestChannels, BridgeError> {
        if self.pending.contains_key(&id) {
            return Err(BridgeError::invalid_argument(format!(
                "duplicate bridge request id {id}"
            )));
        }
        let (final_tx, final_rx) = oneshot::channel();
        let (stream_tx, stream_rx) = mpsc::unbounded_channel();
        let request = PendingRequest {
            final_tx: Some(final_tx),
            stream_tx: Some(stream_tx),
        };
        self.pending.insert(id, request);
        Ok(RequestChannels {
            final_rx,
            stream_rx,
        })
    }

    /// Deliver a stream chunk to the request with this id, if any. Returns
    /// `false` when there is no listener (a late chunk after the stream ended).
    pub fn route_stream(&mut self, id: u64, chunk: serde_json::Value) -> bool {
        if let Some(req) = self.pending.get(&id) {
            if let Some(tx) = &req.stream_tx {
                return tx.send(chunk).is_ok();
            }
        }
        false
    }

    /// Resolve a request with its final outcome, dropping the entry. Returns
    /// `true` if a matching request existed.
    pub fn resolve(&mut self, id: u64, outcome: Outcome) -> bool {
        let Some(req) = self.pending.remove(&id) else {
            return false;
        };
        // Dropping `stream_tx` closes the chunk channel, ending the drain task.
        if let Some(tx) = req.final_tx {
            // A send error means the caller dropped the receiver (e.g. the
            // frontend cancelled); that is benign.
            let _ = tx.send(outcome);
        }
        true
    }

    /// Forget *id* without delivering anything: the caller gave up before the
    /// request reached the sidecar (writer gone), so no response can ever
    /// arrive for it. Dropping the senders closes both channels. Returns
    /// `true` if the entry existed. Idempotent.
    pub fn cancel(&mut self, id: u64) -> bool {
        self.pending.remove(&id).is_some()
    }

    /// Number of in-flight requests (diagnostics / tests).
    pub fn len(&self) -> usize {
        self.pending.len()
    }

    /// Whether any requests are in flight.
    pub fn is_empty(&self) -> bool {
        self.pending.is_empty()
    }

    /// Reject every in-flight request with the same error outcome. Called when
    /// the sidecar crashes/restarts so awaiting callers fail fast instead of
    /// hanging until their own timeout. Each request is resolved exactly once
    /// (the entry is removed as it is failed); a second call is a no-op.
    /// Returns how many requests were rejected.
    pub fn fail_all(&mut self, code: i32, message: &str) -> usize {
        let ids: Vec<u64> = self.pending.keys().copied().collect();
        let count = ids.len();
        for id in ids {
            let outcome = Outcome::Error {
                code,
                message: message.to_string(),
                data: Some(serde_json::json!({ "kind": "transport" })),
            };
            self.resolve(id, outcome);
        }
        count
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bridge::framing::code;
    use serde_json::json;

    #[tokio::test]
    async fn register_then_resolve_delivers_outcome() {
        let mut d = Dispatcher::new();
        let RequestChannels {
            final_rx,
            mut stream_rx,
        } = d.register(1).expect("register");
        assert!(d.route_stream(1, json!({"token": "hi"})));
        // The chunk is buffered and readable.
        assert_eq!(stream_rx.recv().await.unwrap()["token"], "hi");

        assert!(d.resolve(1, Outcome::Result(json!({"ok": true}))));
        match final_rx.await.unwrap() {
            Outcome::Result(v) => assert_eq!(v["ok"], true),
            _ => panic!("expected result"),
        }
        assert!(d.is_empty());
    }

    #[tokio::test]
    async fn resolve_unknown_id_is_false() {
        let mut d = Dispatcher::new();
        assert!(!d.resolve(999, Outcome::Result(json!(null))));
    }

    #[tokio::test]
    async fn route_stream_unknown_id_is_false() {
        let mut d = Dispatcher::new();
        assert!(!d.route_stream(42, json!({"token": "x"})));
    }

    #[tokio::test]
    async fn resolving_closes_the_stream_channel() {
        let mut d = Dispatcher::new();
        let RequestChannels {
            final_rx,
            mut stream_rx,
        } = d.register(7).expect("register");
        drop(final_rx);
        d.resolve(7, Outcome::Result(json!(null)));
        // After resolve, the stream sender is dropped → recv returns None.
        assert!(stream_rx.recv().await.is_none());
    }

    #[test]
    fn register_tracks_count() {
        let mut d = Dispatcher::new();
        d.register(1).expect("register 1");
        d.register(2).expect("register 2");
        assert_eq!(d.len(), 2);
        d.resolve(1, Outcome::Result(json!(null)));
        assert_eq!(d.len(), 1);
    }

    #[tokio::test]
    async fn fail_all_rejects_every_pending_request_exactly_once() {
        let mut d = Dispatcher::new();
        let RequestChannels { final_rx: r1, .. } = d.register(1).expect("register 1");
        let RequestChannels { final_rx: r2, .. } = d.register(2).expect("register 2");
        assert_eq!(d.fail_all(code::INTERNAL_ERROR, "sidecar restarted"), 2);
        for rx in [r1, r2] {
            match rx.await.unwrap() {
                Outcome::Error { code, data, .. } => {
                    assert_eq!(code, code::INTERNAL_ERROR);
                    assert_eq!(data.unwrap()["kind"], "transport");
                }
                _ => panic!("expected error"),
            }
        }
        assert!(d.is_empty());
        // Second sweep: nothing left, nothing double-completed.
        assert_eq!(d.fail_all(code::INTERNAL_ERROR, "again"), 0);
    }

    #[tokio::test]
    async fn late_response_after_fail_all_is_dropped() {
        let mut d = Dispatcher::new();
        let RequestChannels { final_rx, .. } = d.register(5).expect("register");
        d.fail_all(code::INTERNAL_ERROR, "sidecar restarted");
        // The old instance's answer arrives after the sweep: no listener.
        assert!(!d.resolve(5, Outcome::Result(json!({"stale": true}))));
        assert!(!d.route_stream(5, json!({"token": "stale"})));
        match final_rx.await.unwrap() {
            Outcome::Error { .. } => {}
            other => panic!("the caller saw the rejection first, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn cancel_forgets_the_request_and_closes_channels() {
        let mut d = Dispatcher::new();
        let RequestChannels {
            final_rx,
            mut stream_rx,
        } = d.register(3).expect("register");
        assert!(d.cancel(3));
        assert!(!d.cancel(3), "idempotent");
        assert!(d.is_empty());
        // Nothing is ever delivered; both receivers observe closure.
        assert!(final_rx.await.is_err());
        assert!(stream_rx.recv().await.is_none());
        // The id is free for reuse (no stale "duplicate id" error).
        d.register(3).expect("re-register after cancel");
    }

    #[tokio::test]
    async fn duplicate_response_resolves_only_once() {
        let mut d = Dispatcher::new();
        let RequestChannels { final_rx, .. } = d.register(8).expect("register");
        assert!(d.resolve(8, Outcome::Result(json!(1))));
        assert!(
            !d.resolve(8, Outcome::Result(json!(2))),
            "second answer is dropped"
        );
        match final_rx.await.unwrap() {
            Outcome::Result(v) => assert_eq!(v, json!(1)),
            other => panic!("expected the first result, got {other:?}"),
        }
    }

    #[test]
    fn register_duplicate_id_returns_error_instead_of_panicking() {
        let mut d = Dispatcher::new();
        d.register(1).expect("first register");
        let err = d.register(1).expect_err("duplicate id must fail");
        assert!(
            err.message.contains("duplicate"),
            "expected invalid-argument duplicate, got {err:?}"
        );
        assert_eq!(d.len(), 1, "the original registration must stay in place");
    }
}
