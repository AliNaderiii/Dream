"""Append-only tamper-evident provenance log tracker with SHA-256 hash chaining."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .models import GENESIS_PREV_HASH, EventType, FileSnapshot, ModelSnapshot, ProvenanceRecord

DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MB


class ProvenanceTracker:
    """Manages append-only provenance logging with rotation and integrity checks."""

    def __init__(
        self,
        log_dir: str | None = None,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.log_dir = log_dir or os.environ.get("DREAM_PROVENANCE_DIR", "data/provenance")
        self.max_bytes = max_bytes
        self._lock = threading.RLock()
        self._active_file = os.path.join(self.log_dir, "provenance.jsonl")
        self._last_hash = GENESIS_PREV_HASH
        self._records_cache: dict[str, ProvenanceRecord] = {}

        os.makedirs(self.log_dir, exist_ok=True)
        self._init_state()

    def _get_log_files(self) -> list[str]:
        """Return all provenance log segment files sorted chronologically."""
        if not os.path.exists(self.log_dir):
            return []
        files = []
        for name in os.listdir(self.log_dir):
            if name.startswith("provenance") and name.endswith(".jsonl"):
                files.append(os.path.join(self.log_dir, name))
        files.sort()
        # Ensure active provenance.jsonl is last
        active = self._active_file
        if active in files:
            files.remove(active)
            files.append(active)
        return files

    def _init_state(self) -> None:
        """Scan existing logs to restore last hash and populate cache."""
        with self._lock:
            last_hash = GENESIS_PREV_HASH
            for fpath in self._get_log_files():
                if not os.path.exists(fpath):
                    continue
                try:
                    with open(fpath, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                rec = ProvenanceRecord.from_dict(data)
                                self._records_cache[rec.record_id] = rec
                                if rec.hash:
                                    last_hash = rec.hash
                            except Exception:
                                pass
                except OSError:
                    pass
            self._last_hash = last_hash

    def _rotate_if_needed(self) -> None:
        """Rotate provenance.jsonl if it exceeds max_bytes."""
        if not os.path.exists(self._active_file):
            return
        try:
            size = os.path.getsize(self._active_file)
            if size >= self.max_bytes:
                timestamp = int(time.time() * 1000)
                rotated_name = f"provenance.{timestamp}.jsonl"
                rotated_path = os.path.join(self.log_dir, rotated_name)
                os.rename(self._active_file, rotated_path)
        except OSError:
            pass

    def record(
        self,
        event_type: EventType,
        agent_id: str,
        *,
        parent_record_id: str | None = None,
        payload: dict[str, Any] | None = None,
        input_snapshot: list[FileSnapshot] | None = None,
        output_snapshot: list[FileSnapshot] | None = None,
        model_snapshot: ModelSnapshot | dict[str, Any] | None = None,
        token_count: int | None = None,
        duration_ms: int | None = None,
        timestamp: str | None = None,
    ) -> ProvenanceRecord:
        """Append a new tamper-evident record to the provenance chain.

        SEC Stage C (G-17): payloads are value-scanned before sealing, so a
        secret inside a tool argument or result never lands in the trail.
        """
        from dream.security.secrets import redact_structure

        if isinstance(model_snapshot, dict):
            model_snapshot = ModelSnapshot.from_dict(model_snapshot)
        payload = redact_structure(payload or {})

        rec_id = f"prov_{uuid.uuid4().hex}"
        ts = timestamp or datetime.now(timezone.utc).isoformat()

        rec = ProvenanceRecord(
            record_id=rec_id,
            timestamp=ts,
            event_type=event_type,
            agent_id=agent_id,
            parent_record_id=parent_record_id,
            payload=payload or {},
            input_snapshot=input_snapshot or [],
            output_snapshot=output_snapshot or [],
            model_snapshot=model_snapshot,
            token_count=token_count,
            duration_ms=duration_ms,
        )

        with self._lock:
            self._rotate_if_needed()
            rec.seal(self._last_hash)
            self._last_hash = rec.hash
            self._records_cache[rec.record_id] = rec

            serialized = json.dumps(rec.to_dict(), ensure_ascii=False)
            with open(self._active_file, "a", encoding="utf-8") as f:
                f.write(serialized + "\n")

        return rec

    def get(self, record_id: str) -> ProvenanceRecord | None:
        """Fetch a record by UUID."""
        with self._lock:
            if record_id in self._records_cache:
                return self._records_cache[record_id]

            # Search on disk if not in memory cache
            for fpath in reversed(self._get_log_files()):
                if not os.path.exists(fpath):
                    continue
                try:
                    with open(fpath, encoding="utf-8") as f:
                        for line in f:
                            if record_id in line:
                                data = json.loads(line.strip())
                                if data.get("record_id") == record_id:
                                    rec = ProvenanceRecord.from_dict(data)
                                    self._records_cache[record_id] = rec
                                    return rec
                except Exception:
                    pass
        return None

    def list_records(
        self,
        *,
        agent_id: str | None = None,
        event_type: str | None = None,
        search: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProvenanceRecord], int]:
        """List and filter provenance records with pagination."""
        with self._lock:
            records = list(self._records_cache.values())

        # Sort descending by timestamp / creation
        records.sort(key=lambda r: r.timestamp, reverse=True)

        filtered = []
        search_lower = search.lower() if search else None

        for rec in records:
            if agent_id and rec.agent_id != agent_id:
                continue
            if event_type and rec.event_type != event_type:
                continue
            if date_from and rec.timestamp < date_from:
                continue
            if date_to and rec.timestamp > date_to:
                continue
            if search_lower:
                dumped = json.dumps(rec.to_dict(), ensure_ascii=False).lower()
                if search_lower not in dumped:
                    continue
            filtered.append(rec)

        total = len(filtered)
        paged = filtered[offset : offset + limit]
        return paged, total

    def verify_chain(self) -> dict[str, Any]:
        """Verify the integrity of the SHA-256 hash chain across all log files.

        Returns:
            dict with 'valid', 'records_checked', 'broken_at', 'error'
        """
        with self._lock:
            expected_prev = GENESIS_PREV_HASH
            checked = 0

            for fpath in self._get_log_files():
                if not os.path.exists(fpath):
                    continue
                try:
                    with open(fpath, encoding="utf-8") as f:
                        for line_no, line in enumerate(f, 1):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                            except Exception as exc:
                                return {
                                    "valid": False,
                                    "records_checked": checked,
                                    "broken_at": None,
                                    "error": f"JSON parse error at {fpath}:{line_no}: {exc}",
                                }

                            rec = ProvenanceRecord.from_dict(data)
                            if rec.prev_hash != expected_prev:
                                return {
                                    "valid": False,
                                    "records_checked": checked,
                                    "broken_at": rec.record_id,
                                    "error": (
                                        f"Broken hash chain at record {rec.record_id}: "
                                        f"expected prev_hash {expected_prev}, got {rec.prev_hash}"
                                    ),
                                }

                            if not rec.verify_hash():
                                return {
                                    "valid": False,
                                    "records_checked": checked,
                                    "broken_at": rec.record_id,
                                    "error": (
                                        f"Tampered record content at {rec.record_id} "
                                        f"({rec.event_type})"
                                    ),
                                }

                            expected_prev = rec.hash
                            checked += 1
                except OSError as exc:
                    return {
                        "valid": False,
                        "records_checked": checked,
                        "broken_at": None,
                        "error": f"File read error on {fpath}: {exc}",
                    }

            return {
                "valid": True,
                "records_checked": checked,
                "broken_at": None,
                "error": None,
            }

    def get_tree(
        self,
        *,
        record_id: str | None = None,
        agent_id: str | None = None,
        artifact_path: str | None = None,
    ) -> dict[str, Any]:
        """Build a graph/tree of provenance nodes and directed edges."""
        with self._lock:
            all_records = list(self._records_cache.values())

        if record_id:
            # Build ancestor/descendant sub-tree for specific record
            target = self.get(record_id)
            if not target:
                return {"nodes": [], "edges": [], "root_id": record_id}
            selected_ids = {record_id}
            # Add parents
            curr: ProvenanceRecord | None = target
            while curr and curr.parent_record_id:
                selected_ids.add(curr.parent_record_id)
                curr = self.get(curr.parent_record_id)
            # Add children
            for r in all_records:
                if r.parent_record_id in selected_ids:
                    selected_ids.add(r.record_id)
            records = [r for r in all_records if r.record_id in selected_ids]
        elif agent_id:
            records = [r for r in all_records if r.agent_id == agent_id]
        elif artifact_path:
            records = []
            for r in all_records:
                matches_output = any(f.path == artifact_path for f in r.output_snapshot)
                matches_input = any(f.path == artifact_path for f in r.input_snapshot)
                if matches_output or matches_input:
                    records.append(r)
        else:
            records = all_records[-50:]  # Last 50 records by default

        nodes = []
        edges = []
        for r in records:
            lbl = r.payload.get("tool_name") or r.payload.get("command") or r.record_id[:8]
            nodes.append(
                {
                    "id": r.record_id,
                    "label": f"{r.event_type}: {lbl}",
                    "event_type": r.event_type,
                    "agent_id": r.agent_id,
                    "timestamp": r.timestamp,
                    "duration_ms": r.duration_ms,
                    "model": r.model_snapshot.to_dict() if r.model_snapshot else None,
                    "payload": r.payload,
                    "inputs": [f.to_dict() for f in r.input_snapshot],
                    "outputs": [f.to_dict() for f in r.output_snapshot],
                }
            )
            if r.parent_record_id:
                edges.append(
                    {
                        "source": r.parent_record_id,
                        "target": r.record_id,
                        "type": "parent_child",
                    }
                )

        return {
            "nodes": nodes,
            "edges": edges,
            "count": len(nodes),
        }
