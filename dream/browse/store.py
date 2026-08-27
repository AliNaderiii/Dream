"""Bounded pending and finished HITL page reads."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from dream.browse.errors import BrowseError

_DEFAULT = "data/browse.json"
_MAX = 20


class BrowseStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or os.environ.get("DREAM_BROWSE_STORE", _DEFAULT))
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"drafts": {}}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.is_file():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("drafts"), dict):
                    self._data["drafts"] = payload["drafts"]
        except (OSError, ValueError):
            self._data = {"drafts": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        body = json.dumps(self._data, ensure_ascii=False, indent=2) + "\n"
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(self.path)

    def put(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            drafts = self._data["drafts"]
            if record["draft_id"] not in drafts and len(drafts) >= _MAX:
                raise BrowseError("browse draft limit reached (20).\nسقف پیشنویس مرور پر شد (۲۰).")
            drafts[record["draft_id"]] = record
            self._save()
            return dict(record)

    def get(self, draft_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["drafts"].get(draft_id)
            if not record:
                raise BrowseError(f"no browse draft {draft_id}\nپیشنویس مروری با این شناسه نیست")
            return dict(record)

    def pop(self, draft_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["drafts"].pop(draft_id, None)
            if not record:
                raise BrowseError(f"no browse draft {draft_id}\nپیشنویس مروری با این شناسه نیست")
            self._save()
            return dict(record)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._data["drafts"].values()]
        rows.sort(key=lambda row: float(row.get("created_at") or 0), reverse=True)
        return rows


def now() -> float:
    return time.time()
