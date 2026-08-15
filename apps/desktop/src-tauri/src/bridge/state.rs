//! Bridge connection state, shared between the supervisor and the frontend.
//!
//! The supervisor writes the state; `bridge_status` reads it; transitions are
//! emitted as `bridge://state` events so the React status indicator updates live.

use std::sync::atomic::{AtomicU8, Ordering};

use serde::{Deserialize, Serialize};

/// Lifecycle of the bridge to the Python sidecar.
///
/// Stored as a `u8` atomic so reads are lock-free; the string form is what the
/// frontend and tray see.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ConnectionState {
    /// Spawning the sidecar / awaiting the protocol header.
    Connecting,
    /// Sidecar is up and answering heartbeats.
    Ready,
    /// Sidecar died and is being restarted (backoff).
    Restarting,
    /// Out of retries; the frontend shows "Disconnected" and offers manual reconnect.
    Disconnected,
}

impl Default for ConnectionState {
    fn default() -> Self {
        Self::Connecting
    }
}

impl ConnectionState {
    /// Stable discriminant for the atomic store.
    const fn as_u8(self) -> u8 {
        match self {
            Self::Connecting => 0,
            Self::Ready => 1,
            Self::Restarting => 2,
            Self::Disconnected => 3,
        }
    }

    const fn from_u8(value: u8) -> Self {
        match value {
            1 => Self::Ready,
            2 => Self::Restarting,
            3 => Self::Disconnected,
            _ => Self::Connecting,
        }
    }
}

/// Lock-free shared state cell.
#[derive(Default)]
pub struct SharedState {
    inner: AtomicU8,
}

impl SharedState {
    /// Read the current state.
    pub fn get(&self) -> ConnectionState {
        ConnectionState::from_u8(self.inner.load(Ordering::Acquire))
    }

    /// Write the state, returning the previous one.
    pub fn set(&self, state: ConnectionState) -> ConnectionState {
        ConnectionState::from_u8(self.inner.swap(state.as_u8(), Ordering::AcqRel))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_to_connecting() {
        assert_eq!(SharedState::default().get(), ConnectionState::Connecting);
    }

    #[test]
    fn round_trips_every_variant() {
        let s = SharedState::default();
        for state in [
            ConnectionState::Connecting,
            ConnectionState::Ready,
            ConnectionState::Restarting,
            ConnectionState::Disconnected,
        ] {
            s.set(state);
            assert_eq!(s.get(), state);
        }
    }

    #[test]
    fn set_returns_previous() {
        let s = SharedState::default();
        s.set(ConnectionState::Ready);
        assert_eq!(s.set(ConnectionState::Restarting), ConnectionState::Ready);
    }

    #[test]
    fn serde_round_trip() {
        for state in [
            ConnectionState::Connecting,
            ConnectionState::Ready,
            ConnectionState::Restarting,
            ConnectionState::Disconnected,
        ] {
            let json = serde_json::to_string(&state).unwrap();
            let back: ConnectionState = serde_json::from_str(&json).unwrap();
            assert_eq!(state, back);
        }
    }
}
