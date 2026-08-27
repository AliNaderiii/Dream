"""Bounded pending skill drafts."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from dream.experience.errors import ExperienceError

_DEFAULT = "data/experience.json"
_MAX = 20


class ExperienceStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or os.environ.get("DREAM_EXPERIENCE_STORE", _DEFAULT))
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
                raise ExperienceError("experience draft limit reached (20).")
            drafts[record["draft_id"]] = record
            self._save()
            return dict(record)

    def get(self, draft_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["drafts"].get(draft_id)
            if not record:
                raise ExperienceError(f"no experience draft {draft_id}")
            return dict(record)

    def pop(self, draft_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["drafts"].pop(draft_id, None)
            if not record:
                raise ExperienceError(f"no experience draft {draft_id}")
            self._save()
            return dict(record)

    def list(self, bot_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._data["drafts"].values()]
        if bot_id:
            rows = [row for row in rows if row.get("bot_id") == bot_id]
        rows.sort(key=lambda row: float(row.get("created_at") or 0))
        return rows


def now() -> float:
    return time.time()
