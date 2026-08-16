"""Artifact linking and sidecar provenance metadata management."""

from __future__ import annotations

import json
import os
from typing import Any

from .models import FileSnapshot, ModelSnapshot
from .tracker import ProvenanceTracker


class ArtifactManager:
    """Links created files/figures/reports to their generating provenance records."""

    def __init__(
        self,
        tracker: ProvenanceTracker,
        base_dir: str | None = None,
    ) -> None:
        self.tracker = tracker
        self.base_dir = base_dir or os.getcwd()
        self._tracked_paths: set[str] = set()

    def _sidecar_path(self, file_path: str) -> str:
        """Compute the .provenance.json sidecar path for an artifact."""
        if not os.path.isabs(file_path):
            abs_path = os.path.join(self.base_dir, file_path)
        else:
            abs_path = file_path
        return f"{abs_path}.provenance.json"

    def link_artifact(
        self,
        file_path: str,
        record_id: str,
        *,
        tool_name: str | None = None,
        agent_id: str | None = None,
        model_snapshot: ModelSnapshot | dict[str, Any] | None = None,
        custom_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a .provenance.json sidecar file for the artifact."""
        abs_target = (
            file_path if os.path.isabs(file_path) else os.path.join(self.base_dir, file_path)
        )
        snapshot = FileSnapshot.from_path(abs_target)
        record = self.tracker.get(record_id)

        model_dict = None
        if isinstance(model_snapshot, ModelSnapshot):
            model_dict = model_snapshot.to_dict()
        elif isinstance(model_snapshot, dict):
            model_dict = model_snapshot
        elif record and record.model_snapshot:
            model_dict = record.model_snapshot.to_dict()

        effective_tool = tool_name or (record.payload.get("tool_name") if record else "unknown")
        effective_agent = agent_id or (record.agent_id if record else "default")
        created_at = record.timestamp if record else ""

        sidecar_data = {
            "artifact_path": file_path,
            "record_id": record_id,
            "tool_name": effective_tool,
            "agent_id": effective_agent,
            "created_at": created_at,
            "hash": snapshot.hash if snapshot else "",
            "size": snapshot.size if snapshot else 0,
            "model_snapshot": model_dict,
            "metadata": custom_metadata or {},
        }

        self._tracked_paths.add(file_path)

        sidecar_file = self._sidecar_path(file_path)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(sidecar_file)), exist_ok=True)
            with open(sidecar_file, "w", encoding="utf-8") as f:
                json.dump(sidecar_data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

        return sidecar_data

    def get_artifact(self, file_path: str) -> dict[str, Any] | None:
        """Get artifact metadata, generating provenance record, and lineage description."""
        sidecar_file = self._sidecar_path(file_path)
        sidecar_data: dict[str, Any] = {}

        if os.path.exists(sidecar_file):
            try:
                with open(sidecar_file, encoding="utf-8") as f:
                    sidecar_data = json.load(f)
            except Exception:
                pass

        record_id = sidecar_data.get("record_id")
        record = self.tracker.get(record_id) if record_id else None

        if not record:
            # Fallback: search outputs in tracker log
            rel_path = (
                file_path
                if not os.path.isabs(file_path)
                else os.path.relpath(file_path, self.base_dir)
            )
            records, _ = self.tracker.list_records(limit=500)
            for r in records:
                for out_f in r.output_snapshot:
                    if out_f.path == rel_path or out_f.path == file_path:
                        record = r
                        record_id = r.record_id
                        break
                if record:
                    break

        abs_target = (
            file_path if os.path.isabs(file_path) else os.path.join(self.base_dir, file_path)
        )
        snapshot = FileSnapshot.from_path(abs_target)

        tool_name = sidecar_data.get("tool_name") or (
            record.payload.get("tool_name") if record else "unknown"
        )
        agent_id = sidecar_data.get("agent_id") or (record.agent_id if record else "unknown")
        model_name = "unknown model"
        if sidecar_data.get("model_snapshot"):
            m = sidecar_data["model_snapshot"]
            model_name = m.get("model") or m.get("provider", "unknown")
        elif record and record.model_snapshot:
            model_name = record.model_snapshot.model or record.model_snapshot.provider

        created_at = sidecar_data.get("created_at") or (
            record.timestamp if record else "unknown date"
        )

        lineage_statement = (
            f"This artifact was generated by tool {tool_name!r} in session {agent_id!r} "
            f"using model {model_name!r} on {created_at}"
        )

        tree = (
            self.tracker.get_tree(record_id=record_id, artifact_path=file_path)
            if record_id
            else {"nodes": [], "edges": []}
        )

        return {
            "artifact_path": file_path,
            "exists": os.path.exists(abs_target),
            "size": snapshot.size if snapshot else sidecar_data.get("size", 0),
            "hash": snapshot.hash if snapshot else sidecar_data.get("hash", ""),
            "record_id": record_id,
            "tool_name": tool_name,
            "agent_id": agent_id,
            "created_at": created_at,
            "model": model_name,
            "lineage_statement": lineage_statement,
            "generating_record": record.to_dict() if record else None,
            "lineage_tree": tree,
            "sidecar": sidecar_data,
        }

    def list_artifacts(self) -> list[dict[str, Any]]:
        """List all tracked artifacts in workspace and provenance log."""
        artifacts: dict[str, dict[str, Any]] = {}

        # 1. Directly tracked
        for p in self._tracked_paths:
            info = self.get_artifact(p)
            if info:
                artifacts[p] = info

        # 2. Find from sidecars on disk
        if os.path.exists(self.base_dir):
            for root, _, files in os.walk(self.base_dir):
                for fname in files:
                    if fname.endswith(".provenance.json"):
                        sidecar_f = os.path.join(root, fname)
                        try:
                            with open(sidecar_f, encoding="utf-8") as f:
                                data = json.load(f)
                            art_path = data.get("artifact_path")
                            if art_path and art_path not in artifacts:
                                artifacts[art_path] = self.get_artifact(art_path) or data
                        except Exception:
                            pass

        # 3. Find from provenance outputs
        records, _ = self.tracker.list_records(limit=200)
        for r in records:
            for out in r.output_snapshot:
                if out.path and out.path not in artifacts:
                    art_info = self.get_artifact(out.path)
                    if art_info:
                        artifacts[out.path] = art_info

        return list(artifacts.values())
