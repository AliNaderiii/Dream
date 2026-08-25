#!/usr/bin/env python3
"""Offline workspace / agent-mode probe (does not modify Dream's main CLI)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dream.agentmodes.service import AgentModeService  # noqa: E402
from dream.workspace.service import WorkspaceService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Dream's local-first workspace")
    parser.add_argument("--folder", default="", help="folder to import in place")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    work = Path(args.folder) if args.folder else Path(tempfile.mkdtemp(prefix="dream-ws-"))
    if not args.folder:
        (work / "sales.csv").write_text("region,revenue\nNorth,120\nSouth,80\n", encoding="utf-8")
        (work / "README.md").write_text("# Demo\n", encoding="utf-8")
    os.environ.setdefault("DREAM_WORKSPACE_REGISTRY", str(work / "registry.json"))
    os.environ.setdefault("DREAM_PROJECTS_PATH", str(work / "projects.json"))
    workspace = WorkspaceService(
        registry_path=work / "registry.json", projects_path=work / "projects.json"
    )
    imported = workspace.import_folder(str(work), name="probe")
    root_id = imported["root"]["root_id"]
    listing = workspace.files_list(root_id, "")
    preview = workspace.files_preview(root_id, "sales.csv")
    modes = AgentModeService()
    planned = modes.plan("Summarise the sales table")
    continued = modes.continue_plan(planned["plan_id"])
    goal = modes.goal(
        "Keep the table honest",
        ["local CSV is readable", "must fetch live market prices"],
    )
    stopped = modes.stop()
    payload = {
        "copied": imported["copied"],
        "files": [entry["name"] for entry in listing["entries"]],
        "chart": preview.get("chart"),
        "plan_status": continued["status"],
        "goal_status": goal["status"],
        "goal_report": goal["report"],
        "stopped": stopped["stopped"],
        "live": stopped["live"],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"PASS: copied={payload['copied']}; files={payload['files']}; "
            f"plan={payload['plan_status']}; goal={payload['goal_status']}"
        )
        print(payload["goal_report"])
    return 0 if imported["copied"] is False and preview.get("chart") else 1


if __name__ == "__main__":
    raise SystemExit(main())
