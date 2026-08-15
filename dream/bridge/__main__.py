"""``python -m dream.bridge`` — run the stdio JSON-RPC sidecar."""

from __future__ import annotations

from dream.bridge.server import run_stdio

if __name__ == "__main__":
    raise SystemExit(run_stdio())
