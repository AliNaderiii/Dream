#!/usr/bin/env python3
"""End-to-end demo of Dream's autonomous research engine.

Seeds a small multi-source workspace (CSV + JSON + a methodology document),
runs the full pipeline — discover → plan → approve → iterate → write →
proofread → compile — and prints where the report landed.

Offline, with the deterministic Echo backend::

    python examples/research_demo.py

Against a local Ollama model (no VPN required)::

    python examples/research_demo.py --backend ollama

Everything is written under a temporary directory unless ``--keep`` is passed.
Code execution uses the Docker sandbox when available and falls back to the
guarded local subprocess (with a warning) when it is not; pass
``--local-exec`` to force the fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SALES_CSV = """month,region,revenue,units,discount_rate
2024-01,north,12000,300,0.05
2024-02,north,13500,332,0.05
2024-03,north,9000,220,0.15
2024-04,north,15000,360,0.02
2024-05,north,14200,344,0.03
2024-06,north,13800,338,0.04
2024-01,south,8000,200,0.10
2024-02,south,7600,190,0.10
2024-03,south,3000,80,0.30
2024-04,south,9100,214,0.05
2024-05,south,8800,208,0.06
2024-06,south,42000,980,0.00
"""

CHANNELS_JSON = json.dumps(
    [
        {"region": "north", "channel": "retail", "spend": 2400, "leads": 180},
        {"region": "north", "channel": "online", "spend": 3100, "leads": 260},
        {"region": "south", "channel": "retail", "spend": 1900, "leads": 90},
        {"region": "south", "channel": "online", "spend": 2600, "leads": 210},
    ],
    indent=2,
)

METHODOLOGY_MD = """# Methodology

Focus the study on the March revenue dip and the June south-region spike.
Prefer per-region comparisons over global aggregates, and report the discount
rate alongside every revenue statement.
"""


def seed_workspace(root: Path) -> Path:
    """Write a small heterogeneous research space."""
    space = root / "space"
    space.mkdir(parents=True, exist_ok=True)
    (space / "sales.csv").write_text(SALES_CSV, encoding="utf-8")
    (space / "channels.json").write_text(CHANNELS_JSON, encoding="utf-8")
    (space / "METHODOLOGY.md").write_text(METHODOLOGY_MD, encoding="utf-8")
    return space


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="echo", help="echo | ollama | openai | aval")
    parser.add_argument("--topic", default="Why did revenue dip in March and spike in June?")
    parser.add_argument("--language", default="en", choices=("en", "fa"))
    parser.add_argument("--max-iterations", type=int, default=2)
    parser.add_argument("--autonomous", action="store_true",
                        help="skip the approval checkpoint and use the degraded grant set")
    parser.add_argument("--local-exec", action="store_true",
                        help="force the guarded local subprocess instead of Docker")
    parser.add_argument("--keep", action="store_true", help="keep the temporary workspace")
    args = parser.parse_args(argv)

    if args.local_exec:
        os.environ["DREAM_DATA_LOCAL_EXEC"] = "1"

    root = Path(tempfile.mkdtemp(prefix="dream-research-demo-"))
    os.environ.setdefault("DREAM_DATASETS_DIR", str(root / "datasets"))
    os.environ.setdefault("DREAM_RESEARCH_DIR", str(root / "research"))
    space = seed_workspace(root)

    from dream.agent import build_backend
    from dream.research import ResearchEngine

    backend = build_backend(args.backend)
    engine = ResearchEngine(backend=backend)

    print(f"workspace : {space}")
    print(f"backend   : {type(backend).__name__}")

    session = engine.create(
        args.topic,
        str(space),
        config={
            "max_iterations": args.max_iterations,
            "language": args.language,
            "autonomous": args.autonomous,
            "max_sections": 4,
        },
    )
    session.subscribe(lambda event: print(f"  · {event['event']}"))

    plan = session.plan()
    print(f"\nplan (revision {plan.revision}, source={plan.source})")
    for index, section in enumerate(plan.sections, start=1):
        print(f"  {index}. {section.title}")
    print(f"\ncost estimate: {session.record.cost_estimate}")

    if not args.autonomous:
        session.approve()  # the human-in-the-loop checkpoint

    print("\nrunning …")
    session.start()

    record = session.record
    print(f"\nstatus     : {record.status}")
    if record.error:
        print(f"error      : {record.error}")
    print(f"markdown   : {record.report.markdown_path}")
    print(f"pdf        : {record.report.pdf_path} ({record.report.pages} pages)")
    audit = (record.report.proofread or {}).get("final") or {}
    print(f"grounded   : {(record.report.proofread or {}).get('grounded_values')} values")
    print(f"proofread  : ok={audit.get('ok')} ungrounded={len(audit.get('ungrounded') or [])}")
    if args.keep:
        print(f"\nartifacts kept under {root}")
    return 0 if record.status == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
