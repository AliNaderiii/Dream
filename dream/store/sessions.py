"""SQLite-backed conversation sessions and transcripts.

The store owns its connection, serialises access with a re-entrant lock, and
uses WAL mode so reads (session search/sidebar refreshes) do not block turn
auto-saves. All user values are bound parameters; exports escape HTML and never
interpret message content as markup.
"""

from __future__ import annotations

import html
import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Role = Literal["user", "assistant", "system", "tool"]


@dataclass(frozen=True, slots=True)
class SessionRecord:
    id: str
    name: str
    created_at: float
    updated_at: float
    model_provider: str
    model_name: str
    message_count: int
    is_archived: bool
    project_id: str | None


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: str
    session_id: str
    role: Role
    content: str
    tool_calls: list[dict[str, Any]]
    created_at: float
    token_count: int


class SessionStore:
    """A small, migration-friendly SQLite repository for conversations."""

    def __init__(self, path: str | os.PathLike[str] = "data/sessions.db") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._db.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    model_provider TEXT NOT NULL DEFAULT 'echo',
                    model_name TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    project_id TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
                    content TEXT NOT NULL,
                    tool_calls TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    token_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_messages_content ON messages(content);
                """
            )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def create(
        self,
        name: str = "New session",
        *,
        session_id: str | None = None,
        model_provider: str = "echo",
        model_name: str = "",
        project_id: str | None = None,
    ) -> SessionRecord:
        name = name.strip()
        if not name:
            raise ValueError("session name must not be empty")
        now = time.time()
        sid = session_id or str(uuid.uuid4())
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)",
                (sid, name, now, now, model_provider, model_name, project_id),
            )
        return self.get(sid)  # type: ignore[return-value]

    def get(
        self, session_id: str, *, include_messages: bool = False
    ) -> SessionRecord | dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        session = self._session(row)
        if not include_messages:
            return session
        return {**asdict(session), "messages": [asdict(m) for m in self.messages(session_id)]}

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str = "",
        archived: bool = False,
    ) -> tuple[list[SessionRecord], int]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        pattern = f"%{search.strip()}%"
        where = "s.is_archived = ?"
        params: list[Any] = [int(archived)]
        if search.strip():
            where += (
                " AND (s.name LIKE ? ESCAPE '\\' OR EXISTS "
                "(SELECT 1 FROM messages m WHERE m.session_id=s.id "
                "AND m.content LIKE ? ESCAPE '\\'))"
            )
            params.extend([pattern, pattern])
        with self._lock:
            count = self._db.execute(
                f"SELECT count(*) FROM sessions s WHERE {where}", params
            ).fetchone()[0]
            query = (
                f"SELECT s.* FROM sessions s WHERE {where} "
                "ORDER BY s.updated_at DESC LIMIT ? OFFSET ?"
            )
            rows = self._db.execute(query, [*params, limit, offset]).fetchall()
        return [self._session(row) for row in rows], int(count)

    def update(
        self,
        session_id: str,
        *,
        name: str | None = None,
        is_archived: bool | None = None,
        project_id: str | None = None,
    ) -> SessionRecord | None:
        fields: list[str] = []
        values: list[Any] = []
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("session name must not be empty")
            fields.append("name = ?")
            values.append(name)
        if is_archived is not None:
            fields.append("is_archived = ?")
            values.append(int(is_archived))
        if project_id is not None:
            fields.append("project_id = ?")
            values.append(project_id)
        if fields:
            fields.append("updated_at = ?")
            values.append(time.time())
            with self._lock, self._db:
                self._db.execute(
                    f"UPDATE sessions SET {', '.join(fields)} WHERE id = ?", [*values, session_id]
                )
        return self.get(session_id)  # type: ignore[return-value]

    def delete(self, session_id: str) -> bool:
        with self._lock, self._db:
            cursor = self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cursor.rowcount > 0

    def add_message(
        self,
        session_id: str,
        role: Role,
        content: str,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        token_count: int = 0,
        message_id: str | None = None,
        created_at: float | None = None,
    ) -> MessageRecord:
        mid = message_id or str(uuid.uuid4())
        created = created_at or time.time()
        calls = tool_calls or []
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    mid,
                    session_id,
                    role,
                    content,
                    json.dumps(calls, ensure_ascii=False),
                    created,
                    max(0, token_count),
                ),
            )
            self._db.execute(
                "UPDATE sessions SET updated_at = ?, "
                "message_count = message_count + 1 WHERE id = ?",
                (created, session_id),
            )
        return MessageRecord(mid, session_id, role, content, calls, created, max(0, token_count))

    def messages(
        self, session_id: str, *, limit: int = 10_000, before: float | None = None
    ) -> list[MessageRecord]:
        params: list[Any] = [session_id]
        where = "session_id = ?"
        if before is not None:
            where += " AND created_at < ?"
            params.append(before)
        params.append(max(1, min(limit, 50_000)))
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM messages WHERE {where} ORDER BY created_at, rowid LIMIT ?", params
            ).fetchall()
        return [self._message(row) for row in rows]

    def export(self, session_id: str, format: str = "json") -> tuple[str, str, str]:
        payload = self.get(session_id, include_messages=True)
        if not isinstance(payload, dict):
            raise KeyError(session_id)
        fmt = format.lower()
        if fmt == "json":
            body = json.dumps({"version": 1, "session": payload}, ensure_ascii=False, indent=2)
            return body, "application/json", f"{session_id}.json"
        messages = payload["messages"]
        if fmt in {"md", "markdown"}:
            lines = [
                f"# {payload['name']}",
                "",
                f"_Created: {self._date(payload['created_at'])}_",
                "",
            ]
            for message in messages:
                lines.extend(
                    [f"## {str(message['role']).title()}", "", str(message["content"]), ""]
                )
            return "\n".join(lines), "text/markdown", f"{session_id}.md"
        if fmt == "html":
            article_rows = []
            for message in messages:
                role = html.escape(str(message["role"]))
                content = html.escape(str(message["content"]))
                article_rows.append(
                    f'<article class="{role}"><h2>{role.title()}</h2><pre>{content}</pre></article>'
                )
            articles = "".join(article_rows)
            title = html.escape(str(payload["name"]))
            style = (
                "body{font:16px system-ui;max-width:850px;margin:auto;padding:2rem;"
                "background:#111116;color:#ececf1}"
                "article{padding:1rem;border-bottom:1px solid #333}"
                "pre{white-space:pre-wrap;font:inherit}.user{background:#1b1b22}"
            )
            body = (
                f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>'
                f"<style>{style}</style></head><body><h1>{title}</h1>"
                f"{articles}</body></html>"
            )
            return body, "text/html", f"{session_id}.html"
        raise ValueError("format must be json, markdown, or html")

    @staticmethod
    def _session(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            model_provider=row["model_provider"],
            model_name=row["model_name"],
            message_count=row["message_count"],
            is_archived=bool(row["is_archived"]),
            project_id=row["project_id"],
        )

    @staticmethod
    def _message(row: sqlite3.Row) -> MessageRecord:
        try:
            calls = json.loads(row["tool_calls"])
        except (TypeError, ValueError):
            calls = []
        return MessageRecord(
            row["id"],
            row["session_id"],
            row["role"],
            row["content"],
            calls,
            row["created_at"],
            row["token_count"],
        )

    @staticmethod
    def _date(timestamp: float) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
