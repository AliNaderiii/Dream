"""Session management and platform user tracking for the Gateway."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dream.gateway.types import PlatformType


@dataclass
class PlatformSession:
    """Individual user session bound to an external messaging platform."""

    session_id: str
    platform: PlatformType
    user_id: str
    user_name: str
    channel_id: str | None = None
    is_paired: bool = False
    paired_at: datetime | None = None
    preferred_language: str = "fa"
    active_provider: str | None = None
    active_model: str | None = None
    permissions: list[str] = field(default_factory=lambda: ["chat", "reminders", "tools"])
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        """Update the last active timestamp."""
        self.last_active = datetime.now(timezone.utc)


class GatewaySessionStore:
    """Thread-safe persistent and in-memory session manager for gateway platforms."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._memory_cache: dict[str, PlatformSession] = {}

        if self.db_path and self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()
        elif self.db_path == ":memory:":
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Initialize the SQLite database schema if file-backed."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_sessions (
                    session_key TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    channel_id TEXT,
                    is_paired INTEGER NOT NULL DEFAULT 0,
                    paired_at TEXT,
                    preferred_language TEXT NOT NULL DEFAULT 'fa',
                    active_provider TEXT,
                    active_model TEXT,
                    permissions TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    last_active TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Return an active SQLite connection."""
        assert self.db_path is not None
        return sqlite3.connect(self.db_path, timeout=10.0)

    @staticmethod
    def _make_key(platform: PlatformType, user_id: str) -> str:
        """Generate unique lookup key for platform and user."""
        return f"{platform.value}:{user_id}"

    def get_or_create_session(
        self,
        platform: PlatformType,
        user_id: str,
        user_name: str,
        channel_id: str | None = None,
        auto_pair: bool = False,
    ) -> PlatformSession:
        """Retrieve existing session or instantiate and register a new one."""
        with self._lock:
            key = self._make_key(platform, user_id)
            if key in self._memory_cache:
                sess = self._memory_cache[key]
                sess.touch()
                return sess

            # Attempt DB retrieval if configured
            if self.db_path:
                session_from_db = self._load_from_db(key)
                if session_from_db:
                    self._memory_cache[key] = session_from_db
                    session_from_db.touch()
                    return session_from_db

            # Create fresh session
            session_id = f"sess_{platform.value}_{user_id}"
            now = datetime.now(timezone.utc)
            new_sess = PlatformSession(
                session_id=session_id,
                platform=platform,
                user_id=user_id,
                user_name=user_name,
                channel_id=channel_id,
                is_paired=auto_pair,
                paired_at=now if auto_pair else None,
                created_at=now,
                last_active=now,
            )
            self._memory_cache[key] = new_sess
            if self.db_path:
                self._save_to_db(new_sess)
            return new_sess

    def save_session(self, session: PlatformSession) -> None:
        """Persist session modifications."""
        with self._lock:
            key = self._make_key(session.platform, session.user_id)
            session.touch()
            self._memory_cache[key] = session
            if self.db_path:
                self._save_to_db(session)

    def mark_paired(self, platform: PlatformType, user_id: str) -> bool:
        """Mark a user's platform session as authenticated and paired."""
        with self._lock:
            key = self._make_key(platform, user_id)
            sess = self._memory_cache.get(key)
            if not sess and self.db_path:
                sess = self._load_from_db(key)
            if not sess:
                return False

            sess.is_paired = True
            sess.paired_at = datetime.now(timezone.utc)
            self.save_session(sess)
            return True

    def list_all_sessions(self) -> list[PlatformSession]:
        """Return all active registered sessions."""
        with self._lock:
            return list(self._memory_cache.values())

    def _load_from_db(self, key: str) -> PlatformSession | None:
        """Load session record from SQLite."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM gateway_sessions WHERE session_key = ?", (key,))
            row = cur.fetchone()
            if not row:
                return None

            return PlatformSession(
                session_id=row[1],
                platform=PlatformType(row[2]),
                user_id=row[3],
                user_name=row[4],
                channel_id=row[5],
                is_paired=bool(row[6]),
                paired_at=datetime.fromisoformat(row[7]) if row[7] else None,
                preferred_language=row[8],
                active_provider=row[9],
                active_model=row[10],
                permissions=json.loads(row[11]),
                metadata=json.loads(row[12]),
                created_at=datetime.fromisoformat(row[13]),
                last_active=datetime.fromisoformat(row[14]),
            )

    def _save_to_db(self, sess: PlatformSession) -> None:
        """Write session record to SQLite."""
        key = self._make_key(sess.platform, sess.user_id)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO gateway_sessions (
                    session_key, session_id, platform, user_id, user_name, channel_id,
                    is_paired, paired_at, preferred_language, active_provider, active_model,
                    permissions, metadata, created_at, last_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    sess.session_id,
                    sess.platform.value,
                    sess.user_id,
                    sess.user_name,
                    sess.channel_id,
                    1 if sess.is_paired else 0,
                    sess.paired_at.isoformat() if sess.paired_at else None,
                    sess.preferred_language,
                    sess.active_provider,
                    sess.active_model,
                    json.dumps(sess.permissions),
                    json.dumps(sess.metadata),
                    sess.created_at.isoformat(),
                    sess.last_active.isoformat(),
                ),
            )
            conn.commit()
