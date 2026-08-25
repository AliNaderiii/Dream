#!/usr/bin/env python3
"""Offline Data Q&A readiness probe (does not modify Dream's main CLI)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DREAM_WORKSPACE_ROOT", str(ROOT))

from dream.dataqa.service import DataQAError, DataQAService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Dream's offline Data Q&A pipeline")
    parser.add_argument(
        "--source", default="examples", help="workspace-relative dataset file/folder"
    )
    parser.add_argument("--question", default="What is the average sales by region?")
    parser.add_argument("--json", action="store_true", help="print complete JSON result")
    args = parser.parse_args()
    service = DataQAService()
    try:
        discovered = service.discover(args.question, args.source, limit=5)
        session = service.create_session(source=args.source, query=args.question)
        result = service.ask(session["session_id"], args.question)
    except DataQAError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(
            json.dumps(
                {"discovery": discovered, "session": session, "result": result},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        final = result["final_answer"]
        print(f"PASS: {discovered['count']} candidate(s); status={final['status']}")
        print(final["answer"])
        print(f"sandbox={final.get('sandbox', {}).get('kind', 'n/a')}; network=false")
    return 0 if result["final_answer"]["status"] in {"ok", "insufficient_data"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
