"""JSON roster for Space bots. Bounded."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from dream.bots.errors import BotError

_DEFAULT = "data/bots.json"
_MAX_BOTS = 24


class BotStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or os.environ.get("DREAM_BOTS_STORE", _DEFAULT))
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"bots": {}}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.is_file():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("bots"), dict):
                    self._data["bots"] = payload["bots"]
        except (OSError, ValueError):
            self._data = {"bots": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = json.dumps(self._data, ensure_ascii=False, indent=2) + "\n"
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self.path)

    def put(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            bots = self._data["bots"]
            if record["bot_id"] not in bots and len(bots) >= _MAX_BOTS:
                raise BotError("bot limit reached (24).\nسقف بات‌ها پر شد (۲۴).")
            bots[record["bot_id"]] = record
            self._save()
            return dict(record)

    def get(self, bot_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._data["bots"].get(bot_id)
            if not record or record.get("archived"):
                raise BotError(f"no bot with id {bot_id}\nباتی با این شناسه نیست")
            return dict(record)

    def list(self, space_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._data["bots"].values()]
        rows = [row for row in rows if not row.get("archived")]
        if space_id:
            rows = [row for row in rows if row.get("space_id") == space_id]
        rows.sort(key=lambda row: float(row.get("updated_at") or 0), reverse=True)
        return rows


_store: BotStore | None = None
_lock = threading.Lock()


def get_store() -> BotStore:
    global _store
    with _lock:
        if _store is None:
            _store = BotStore()
        return _store


def reset_store(store: BotStore | None = None) -> BotStore | None:
    global _store
    with _lock:
        _store = store
        return _store


def now() -> float:
    return time.time()
