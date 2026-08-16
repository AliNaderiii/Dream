"""Per-channel agent sessions: one Dream per ``(platform, user_id)``.

The gateway guarantees a single agent (with its own conversation history)
per chat identity across every message from that surface, and ``/new_session``
resets it. Metadata persists as JSON so the registry survives restarts; agent
history itself is in-memory (mirroring the bridge session index).
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ChannelSession:
    """Metadata for one ``(platform, user_id)`` conversation."""

    platform: str
    user_id: str
    created_at: float
    last_activity: float
    message_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "message_count": self.message_count,
        }


class SessionRegistry:
    """Owns the (platform, user) → Dream mapping and its JSON index."""

    def __init__(self, path: str, *, dream_factory: Callable[[], Any]) -> None:
        self.path = str(path)
        self._dream_factory = dream_factory
        self._lock = threading.RLock()
        self._sessions: dict[tuple[str, str], tuple[Any, ChannelSession]] = {}
        self._index: dict[str, dict[str, ChannelSession]] = self._load()

    # -- persistence ----------------------------------------------------- #

    def _load(self) -> dict[str, dict[str, ChannelSession]]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return {}
        index: dict[str, dict[str, ChannelSession]] = {}
        if not isinstance(raw, dict):
            return index
        for platform, users in raw.items():
            if not isinstance(users, dict):
                continue
            index[str(platform)] = {}
            for user_id, row in users.items():
                if not isinstance(row, dict):
                    continue
                index[str(platform)][str(user_id)] = ChannelSession(
                    platform=str(platform),
                    user_id=str(user_id),
                    created_at=float(row.get("created_at", 0.0) or 0.0),
                    last_activity=float(row.get("last_activity", 0.0) or 0.0),
                    message_count=int(row.get("message_count", 0)),
                )
        return index

    def save(self) -> None:
        """Persist the session index atomically; best-effort on failure."""
        with self._lock:
            payload = {
                platform: {
                    user_id: session.to_dict() for user_id, session in users.items()
                }
                for platform, users in self._index.items()
            }
            try:
                directory = os.path.dirname(os.path.abspath(self.path)) or "."
                os.makedirs(directory, exist_ok=True)
                tmp = f"{self.path}.tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                try:
                    os.chmod(tmp, 0o600)
                except OSError:
                    pass
                os.replace(tmp, self.path)
            except OSError:
                pass

    # -- access ---------------------------------------------------------- #

    def get(self, platform: str, user_id: str) -> Any:
        """The stable Dream instance for this channel, created on demand."""
        key = (platform, str(user_id))
        with self._lock:
            entry = self._sessions.get(key)
            if entry is None:
                now = time.time()
                metadata = self._index.get(platform, {}).get(str(user_id))
                session = metadata or ChannelSession(
                    platform=platform,
                    user_id=str(user_id),
                    created_at=now,
                    last_activity=now,
                )
                entry = (self._dream_factory(), session)
                self._sessions[key] = entry
                self._index.setdefault(platform, {})[str(user_id)] = session
                self.save()
            return entry[0]

    def touch(self, platform: str, user_id: str) -> None:
        """Record activity on one channel (message count + timestamp)."""
        key = (platform, str(user_id))
        with self._lock:
            entry = self._sessions.get(key)
            if entry is None:
                return
            session = entry[1]
            session.message_count += 1
            session.last_activity = time.time()
            self.save()

    def reset(self, platform: str, user_id: str) -> Any:
        """Start a fresh conversation for one channel (``/new_session``)."""
        key = (platform, str(user_id))
        with self._lock:
            now = time.time()
            session = ChannelSession(
                platform=platform,
                user_id=str(user_id),
                created_at=now,
                last_activity=now,
            )
            entry = (self._dream_factory(), session)
            self._sessions[key] = entry
            self._index.setdefault(platform, {})[str(user_id)] = session
            self.save()
            return entry[0]

    def stats(self, platform: str | None = None) -> list[dict[str, Any]]:
        """Session index rows (metadata only — never conversation content)."""
        with self._lock:
            rows: list[dict[str, Any]] = []
            for name, users in self._index.items():
                if platform is not None and name != platform:
                    continue
                rows.extend(user.to_dict() for user in users.values())
            return sorted(rows, key=lambda row: row["last_activity"], reverse=True)
