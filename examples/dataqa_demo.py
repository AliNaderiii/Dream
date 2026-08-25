#!/usr/bin/env python3
"""Dependency-free, deterministic Data Q&A demo."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DREAM_WORKSPACE_ROOT", str(ROOT))

from dream.dataqa.service import DataQAService  # noqa: E402


def main() -> None:
    sample = ROOT / "data/dataqa/demo-sales.csv"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text(
        "region,revenue,month\nNorth,100,2026-01\nNorth,200,2026-02\n"
        "South,50,2026-01\nSouth,150,2026-02\n",
        encoding="utf-8",
    )
    runtime = DataQAService()
    print("Discovery:")
    found = runtime.discover("revenue by region", str(sample.relative_to(ROOT)), limit=3)
    print(json.dumps(found, ensure_ascii=False, indent=2))
    session = runtime.create_session(source=str(sample.relative_to(ROOT)), query="revenue region")
    print("\nAnswer:")
    answer = runtime.ask(session["session_id"], "What is the average revenue by region?")
    print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
