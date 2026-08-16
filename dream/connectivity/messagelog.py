"""Per-platform message log: a bounded ring buffer persisted as JSONL.

Each platform keeps its most recent messages (default 100). Entries for
end-to-end-encrypted platforms are stored by the gateway with an empty
``text`` — the log records that a message happened, never its content.
"""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from datetime import datetime
from typing import Any

from dream.connectivity.models import MessageLogEntry, utc_now

DEFAULT_CAPACITY = 100
#: Log lines are capped so a megabyte-scale message cannot bloat the file.
MAX_LINE_TEXT = 4000


class MessageLog:
    """Thread-safe ring buffer per platform, append-persisted to JSONL."""

    def __init__(self, path: str, *, capacity: int = DEFAULT_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.path = str(path)
        self.capacity = capacity
        self._lock = threading.RLock()
        self._platforms: dict[str, deque[MessageLogEntry]] = {}
        self._load()

    # -- persistence ----------------------------------------------------- #

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            return
        # Load newest-first so the cap keeps the freshest entries.
        for line in reversed(lines):
            try:
                row = json.loads(line)
                entry = MessageLogEntry(
                    platform=str(row["platform"]),
                    direction=str(row["direction"]),
                    user_id=str(row["user_id"]),
                    text=str(row.get("text", "")),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    message_id=row.get("message_id"),
                    attachments=int(row.get("attachments", 0)),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            buffer = self._platforms.setdefault(entry.platform, deque(maxlen=self.capacity))
            if len(buffer) >= self.capacity:
                break
            buffer.appendleft(entry)

    def _append_line(self, entry: MessageLogEntry) -> None:
        try:
            directory = os.path.dirname(os.path.abspath(self.path)) or "."
            os.makedirs(directory, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as handle:
                json.dump(entry.to_dict(), handle, ensure_ascii=False)
                handle.write("\n")
        except OSError:
            pass

    # -- access ---------------------------------------------------------- #

    def add(
        self,
        platform: str,
        direction: str,
        user_id: str,
        text: str,
        *,
        message_id: str | None = None,
        timestamp: datetime | None = None,
        attachments: int = 0,
    ) -> MessageLogEntry:
        """Record one inbound/outbound message (``direction``: in|out)."""
        entry = MessageLogEntry(
            platform=str(platform),
            direction=direction,
            user_id=str(user_id),
            text=str(text)[:MAX_LINE_TEXT],
            timestamp=timestamp or utc_now(),
            message_id=message_id,
            attachments=int(attachments),
        )
        with self._lock:
            buffer = self._platforms.setdefault(entry.platform, deque(maxlen=self.capacity))
            buffer.append(entry)
            self._append_line(entry)
        return entry

    def entries(
        self, platform: str | None = None, limit: int | None = None
    ) -> list[MessageLogEntry]:
        """Newest-first entries for one platform (or all, when ``None``)."""
        limit = self.capacity if limit is None else max(1, int(limit))
        with self._lock:
            rows: list[MessageLogEntry] = []
            if platform is not None:
                rows = list(self._platforms.get(platform, ()))
            else:
                for buffer in self._platforms.values():
                    rows.extend(buffer)
            rows.sort(key=lambda entry: entry.timestamp, reverse=True)
            return rows[:limit]

    def to_dict(self, platform: str | None = None, limit: int | None = None) -> dict[str, Any]:
        """The wire shape of §3.11 ``gateway.logs``."""
        entries = self.entries(platform, limit)
        return {
            "platform": platform,
            "entries": [entry.to_dict() for entry in entries],
            "total": len(entries),
        }
