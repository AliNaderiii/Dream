#!/usr/bin/env python3
"""Bounded local-runtime probe. Never sends secrets. Never blocks startup."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dream.providerhubs.service import ProviderHubsService  # noqa: E402
from dream.providerhubs.types import RUNTIME_IDS  # noqa: E402


def main() -> int:
    service = ProviderHubsService(state_path=Path("/tmp/dream-providerhubs-probe.json"))
    report = {
        "route": service.route(),
        "runtimes": service.runtimes(),
        "probes": [service.test(runtime_id) for runtime_id in RUNTIME_IDS],
        "gateway": service.gateway_status(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
