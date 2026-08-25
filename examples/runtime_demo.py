#!/usr/bin/env python3
"""Offline demo of the provider-hubs catalog, parsers, and diagnostics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dream.providerhubs.parsers import parse_tool_calls  # noqa: E402
from dream.providerhubs.service import ProviderHubsService  # noqa: E402
from dream.providerhubs.types import RUNTIME_IDS  # noqa: E402


def main() -> int:
    service = ProviderHubsService(state_path=Path("/tmp/dream-providerhubs-demo.json"))
    print("route", service.route()["priority"])
    print("catalog", service.catalog()["count"])
    for runtime_id in RUNTIME_IDS:
        diagnosis = service.diagnose(runtime_id)
        print(runtime_id, "firing=", diagnosis["firing"], "fix=", diagnosis["fix"][:60])
    sample = '<tool_call>{"name": "search", "arguments": {"q": "tehran"}}</tool_call>'
    calls = parse_tool_calls(sample, "qwen")
    print("parsed", json.dumps(calls, ensure_ascii=False))
    print("gateway optional", service.gateway_status()["optional"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
