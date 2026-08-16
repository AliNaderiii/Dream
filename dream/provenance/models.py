"""Data models for the Dream Provenance System.

Provides tamper-evident provenance records with SHA-256 hash chaining, file
snapshots, and model metadata snapshots.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

EventType = Literal[
    "tool_call",
    "code_execution",
    "file_write",
    "file_read",
    "model_response",
    "user_message",
    "agent_message",
    "subagent_spawn",
    "subagent_result",
    "schedule_fire",
    "session_create",
    "session_export",
    "approval_granted",
    "approval_denied",
]

GENESIS_PREV_HASH = "0" * 64


@dataclass
class FileSnapshot:
    """Snapshot of a file's state (path, SHA-256 hash, size, timestamp)."""

    path: str
    hash: str
    size: int
    modified_at: float
    mime_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "hash": self.hash,
            "size": self.size,
            "modified_at": self.modified_at,
            "mime_type": self.mime_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileSnapshot:
        return cls(
            path=str(data.get("path", "")),
            hash=str(data.get("hash", "")),
            size=int(data.get("size", 0)),
            modified_at=float(data.get("modified_at", 0.0)),
            mime_type=data.get("mime_type"),
        )

    @classmethod
    def from_path(cls, file_path: str, base_dir: str | None = None) -> FileSnapshot | None:
        """Create a snapshot of an existing file on disk."""
        target = file_path
        if base_dir and not os.path.isabs(target):
            target = os.path.join(base_dir, target)

        if not os.path.exists(target) or not os.path.isfile(target):
            return None

        try:
            stat = os.stat(target)
            hasher = hashlib.sha256()
            with open(target, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
            rel_path = os.path.relpath(target, base_dir) if base_dir else file_path
            return cls(
                path=rel_path,
                hash=file_hash,
                size=stat.st_size,
                modified_at=stat.st_mtime,
            )
        except OSError:
            return None


@dataclass
class ModelSnapshot:
    """Snapshot of the model provider and configuration used for a generation."""

    provider: str
    model: str | None = None
    base_url: str | None = None
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # Redact any api keys or secrets
        clean_config = {}
        for k, v in self.config.items():
            if any(
                secret_term in k.lower()
                for secret_term in ("key", "secret", "token", "password", "auth")
            ):
                clean_config[k] = "[REDACTED]"
            else:
                clean_config[k] = v

        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "config": clean_config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ModelSnapshot | None:
        if not data:
            return None
        return cls(
            provider=str(data.get("provider", "unknown")),
            model=data.get("model"),
            base_url=data.get("base_url"),
            config=dict(data.get("config", {})),
        )


@dataclass
class ProvenanceRecord:
    """One immutable record in the tamper-evident provenance log."""

    record_id: str
    timestamp: str  # ISO 8601 UTC
    event_type: EventType
    agent_id: str
    parent_record_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    input_snapshot: list[FileSnapshot] = field(default_factory=list)
    output_snapshot: list[FileSnapshot] = field(default_factory=list)
    model_snapshot: ModelSnapshot | None = None
    token_count: int | None = None
    duration_ms: int | None = None
    prev_hash: str | None = None
    hash: str = ""

    def canonical_dict(self) -> dict[str, Any]:
        """Return the dictionary used for computing the SHA-256 hash."""
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "parent_record_id": self.parent_record_id,
            "payload": self.payload,
            "input_snapshot": [f.to_dict() for f in self.input_snapshot],
            "output_snapshot": [f.to_dict() for f in self.output_snapshot],
            "model_snapshot": self.model_snapshot.to_dict() if self.model_snapshot else None,
            "token_count": self.token_count,
            "duration_ms": self.duration_ms,
            "prev_hash": self.prev_hash or GENESIS_PREV_HASH,
        }

    def compute_hash(self) -> str:
        """Compute the SHA-256 hash of this record chained to prev_hash."""
        canonical_json = json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def seal(self, prev_hash: str | None = None) -> ProvenanceRecord:
        """Seal this record by attaching prev_hash and computing its hash."""
        self.prev_hash = prev_hash or GENESIS_PREV_HASH
        self.hash = self.compute_hash()
        return self

    def verify_hash(self) -> bool:
        """Verify that self.hash matches the computed SHA-256 hash."""
        return bool(self.hash and self.hash == self.compute_hash())

    def to_dict(self) -> dict[str, Any]:
        """Serialise the complete sealed record to JSON-friendly dict."""
        res = self.canonical_dict()
        res["hash"] = self.hash
        return res

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceRecord:
        input_snapshots = [
            FileSnapshot.from_dict(item) if isinstance(item, dict) else item
            for item in data.get("input_snapshot", [])
        ]
        output_snapshots = [
            FileSnapshot.from_dict(item) if isinstance(item, dict) else item
            for item in data.get("output_snapshot", [])
        ]
        model_snap = data.get("model_snapshot")
        if isinstance(model_snap, dict):
            model_snap = ModelSnapshot.from_dict(model_snap)

        rec = cls(
            record_id=str(data.get("record_id", "")),
            timestamp=str(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            event_type=data.get("event_type", "user_message"),  # type: ignore
            agent_id=str(data.get("agent_id", "default")),
            parent_record_id=data.get("parent_record_id"),
            payload=dict(data.get("payload", {})),
            input_snapshot=input_snapshots,  # type: ignore
            output_snapshot=output_snapshots,  # type: ignore
            model_snapshot=model_snap,
            token_count=data.get("token_count"),
            duration_ms=data.get("duration_ms"),
            prev_hash=data.get("prev_hash"),
            hash=str(data.get("hash", "")),
        )
        return rec
