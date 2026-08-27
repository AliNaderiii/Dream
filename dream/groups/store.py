"""Bounded finished group runs."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from dream.groups.errors import GroupError

_DEFAULT = "data/groups.json"
_MAX = 20


class GroupStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or os.environ.get("DREAM_GROUPS_STORE", _DEFAULT))
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"groups": {}}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.is_file():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("groups"), dict):
                    self._data["groups"] = payload["groups"]
        except (OSError, ValueError):
            self._data = {"groups": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        body = json.dumps(self._data, ensure_ascii=False, indent=2) + "\n"
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(self.path)

    def put(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            groups = self._data["groups"]
            if record["group_id"] not in groups and len(groups) >= _MAX:
                raise GroupError("group run limit reached (20).\nسقف اجرای گروه پر شد (۲۰).")
            groups[record["group_id"]] = record
            self._save()
            return dict(record)

    def get(self, group_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["groups"].get(group_id)
            if not record:
                raise GroupError(f"no group run {group_id}\nاجرای گروهی با این شناسه نیست")
            return dict(record)

    def list(self, space_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._data["groups"].values()]
        if space_id:
            rows = [row for row in rows if row.get("space_id") == space_id]
        rows.sort(key=lambda row: float(row.get("created_at") or 0), reverse=True)
        return rows


def now() -> float:
    return time.time()
