"""Bounded company workrooms, seats, and outbound drafts."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from dream.workroom.errors import WorkroomError

_DEFAULT = "data/workroom.json"
_MAX_ROOMS = 8


class WorkroomStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or os.environ.get("DREAM_WORKROOM_STORE", _DEFAULT))
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"rooms": {}, "seats": {}, "drafts": {}}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.is_file():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    for key in ("rooms", "seats", "drafts"):
                        if isinstance(payload.get(key), dict):
                            self._data[key] = payload[key]
        except (OSError, ValueError):
            self._data = {"rooms": {}, "seats": {}, "drafts": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        body = json.dumps(self._data, ensure_ascii=False, indent=2) + "\n"
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(self.path)

    def put_room(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            rooms = self._data["rooms"]
            if record["room_id"] not in rooms and len(rooms) >= _MAX_ROOMS:
                raise WorkroomError("workroom limit reached (8).\nسقف اتاق کار پر شد (۸).")
            rooms[record["room_id"]] = record
            self._save()
            return dict(record)

    def get_room(self, room_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["rooms"].get(room_id)
            if not record:
                raise WorkroomError(f"no workroom {room_id}\nاتاق کاری با این شناسه نیست")
            return dict(record)

    def list_rooms(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._data["rooms"].values()]
        rows.sort(key=lambda row: float(row.get("updated_at") or 0), reverse=True)
        return rows

    def put_seat(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._data["seats"][record["seat_id"]] = record
            self._save()
            return dict(record)

    def list_seats(self, room_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._data["seats"].values()]
        rows = [row for row in rows if row.get("room_id") == room_id]
        rows.sort(key=lambda row: float(row.get("created_at") or 0))
        return rows

    def put_draft(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._data["drafts"][record["draft_id"]] = record
            self._save()
            return dict(record)

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["drafts"].get(draft_id)
            if not record:
                raise WorkroomError(f"no workroom draft {draft_id}\nپیشنویس اتاق کار نیست")
            return dict(record)

    def pop_draft(self, draft_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["drafts"].pop(draft_id, None)
            if not record:
                raise WorkroomError(f"no workroom draft {draft_id}\nپیشنویس اتاق کار نیست")
            self._save()
            return dict(record)

    def list_drafts(self, room_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._data["drafts"].values()]
        rows = [row for row in rows if row.get("room_id") == room_id]
        rows.sort(key=lambda row: float(row.get("created_at") or 0), reverse=True)
        return rows


def now() -> float:
    return time.time()
