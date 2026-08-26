"""Durable JSON store for spaces, instruction docs, and automation drafts."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from dream.space.errors import SpaceError

_DEFAULT = "data/spaces.json"
_MAX_SPACES = 40
_MAX_DRAFTS = 80


class SpaceStore:
    """Process-wide JSON document. Lists stay bounded."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or os.environ.get("DREAM_SPACE_STORE", _DEFAULT))
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"spaces": {}, "drafts": {}}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.is_file():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    spaces = payload.get("spaces")
                    drafts = payload.get("drafts")
                    self._data["spaces"] = spaces if isinstance(spaces, dict) else {}
                    self._data["drafts"] = drafts if isinstance(drafts, dict) else {}
        except (OSError, ValueError):
            self._data = {"spaces": {}, "drafts": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = json.dumps(self._data, ensure_ascii=False, indent=2) + "\n"
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self.path)

    def put_space(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            spaces = self._data["spaces"]
            if record["space_id"] not in spaces and len(spaces) >= _MAX_SPACES:
                raise SpaceError(
                    "space limit reached (40).\nسقف فضاها پر شد (۴۰)."
                )
            spaces[record["space_id"]] = record
            self._save()
            return dict(record)

    def get_space(self, space_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["spaces"].get(space_id)
            if not record or record.get("archived"):
                raise SpaceError(f"no space with id {space_id}\nفضایی با این شناسه نیست")
            return dict(record)

    def list_spaces(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._data["spaces"].values()]
        if not include_archived:
            rows = [row for row in rows if not row.get("archived")]
        rows.sort(key=lambda row: float(row.get("updated_at") or 0), reverse=True)
        return rows

    def put_draft(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            drafts = self._data["drafts"]
            if record["draft_id"] not in drafts and len(drafts) >= _MAX_DRAFTS:
                raise SpaceError(
                    "draft limit reached (80).\nسقف پیشنویس‌ها پر شد (۸۰)."
                )
            drafts[record["draft_id"]] = record
            self._save()
            return dict(record)

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["drafts"].get(draft_id)
            if not record:
                raise SpaceError(f"no draft with id {draft_id}\nپیشنویسی با این شناسه نیست")
            return dict(record)

    def list_drafts(self, space_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = [
                dict(row)
                for row in self._data["drafts"].values()
                if row.get("space_id") == space_id
            ]
        rows.sort(key=lambda row: float(row.get("updated_at") or 0), reverse=True)
        return rows


_store: SpaceStore | None = None
_lock = threading.Lock()


def get_store() -> SpaceStore:
    global _store
    with _lock:
        if _store is None:
            _store = SpaceStore()
        return _store


def reset_store(store: SpaceStore | None = None) -> SpaceStore | None:
    global _store
    with _lock:
        _store = store
        return _store


def now() -> float:
    return time.time()
