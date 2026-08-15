"""RPC method handlers for the Dream bridge.

Each public method on :class:`BridgeMethods` is one JSON-RPC method (see
``docs/bridge/protocol.md`` §3). Handlers may be ``async def`` or plain ``def``,
and may return either:

* a JSON-serialisable value → sent as the ``result``;
* an async generator → each ``yield`` becomes a ``stream.chunk`` notification
  and the generator's return value becomes the final ``result`` (streaming).

The class owns four registries layered over the **shared, durable**
:class:`dream.memory.MemoryStore`:

* **sessions** — one independent :class:`dream.agent.Dream` per conversation;
* **providers** — saved provider configs (persisted to JSON);
* **approvals** — pending dangerous-tool approvals;
* **subagents** — background Dream turns.

Nothing here mutates the ``dream/`` package: it only consumes its public API,
so the 956 existing tests stay green.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from dream.agent import (
    ApprovalPolicy,
    Dream,
    EchoBackend,
    OllamaBackend,
    OpenAIBackend,
    build_backend,
)
from dream.memory import KINDS, Memory, MemoryStore
from dream.store.sessions import SessionStore

from .errors import APPROVAL_REQUIRED, BridgeError, invalid_params
from .streams import Chunk, Stream, stream_text, tokenise

#: Provider kinds the bridge knows how to build and persist.
PROVIDER_KINDS: tuple[str, ...] = ("echo", "openai", "ollama")

#: How long a provider probe may take before it is reported unreachable.
PROBE_TIMEOUT_SECONDS = 10.0


# --------------------------------------------------------------------------- #
# Serialisation helpers — core dataclasses → JSON-friendly dicts.
# --------------------------------------------------------------------------- #


def memory_to_dict(memory: Memory) -> dict[str, Any]:
    """Serialise a :class:`Memory` to the wire shape documented in §3.4."""
    return {
        "id": memory.id,
        "kind": memory.kind,
        "content": memory.content,
        "tags": list(memory.tags),
        "importance": memory.importance,
        "created_at": memory.created_at,
        "last_used_at": memory.last_used_at,
        "use_count": memory.use_count,
        "source": memory.source,
        "archived": memory.archived,
        "pinned": memory.pinned,
        "score": memory.score,
    }


def _fact_to_dict(fact: Any) -> dict[str, Any]:
    return {
        "content": getattr(fact, "content", ""),
        "kind": getattr(fact, "kind", "semantic"),
        "importance": getattr(fact, "importance", 0.5),
    }


def _extraction_to_dict(extraction: Any) -> dict[str, Any]:
    if extraction is None:
        return {"status": "disabled", "facts": [], "raw_text": ""}
    facts = [_fact_to_dict(f) for f in getattr(extraction, "facts", []) or []]
    return {
        "status": getattr(extraction, "status", ""),
        "facts": facts,
        "raw_text": getattr(extraction, "raw_text", ""),
    }


def turn_to_dict(turn: Any) -> dict[str, Any]:
    """Serialise a :class:`dream.agent.Turn` to the wire shape in §3.2."""
    memories_used = getattr(turn, "memories_used", []) or []
    injected = getattr(turn, "memories_injected", None)
    injected_ids = {m.id for m in (injected or [])}
    return {
        "reply": getattr(turn, "reply", ""),
        "tool_calls": list(getattr(turn, "tool_calls", []) or []),
        "memories_used": [memory_to_dict(m) for m in memories_used],
        "memories_injected_ids": sorted(injected_ids),
        "memories_created": [
            memory_to_dict(m) for m in getattr(turn, "memories_created", []) or []
        ],
        "memories_superseded": [
            memory_to_dict(m) for m in getattr(turn, "memories_superseded", []) or []
        ],
        "memories_merged": [memory_to_dict(m) for m in getattr(turn, "memories_merged", []) or []],
        "elapsed_seconds": getattr(turn, "elapsed_seconds", 0.0),
        "extraction": _extraction_to_dict(getattr(turn, "extraction", None)),
        "memory_errors": list(getattr(turn, "memory_errors", []) or []),
    }


def skill_to_dict(skill: Any) -> dict[str, Any]:
    return {
        "name": skill.name,
        "description": skill.description,
        "steps": list(skill.steps),
        "filename": skill.filename,
    }


def reminder_to_dict(reminder: Any) -> dict[str, Any]:
    return {
        "id": getattr(reminder, "id", None),
        "text": getattr(reminder, "text", ""),
        "due_at": getattr(reminder, "due_at", 0.0),
        "repeat_days": getattr(reminder, "repeat_days", None),
        "repeat_months": getattr(reminder, "repeat_months", None),
        "active": getattr(reminder, "active", True),
    }


# --------------------------------------------------------------------------- #
# Backend construction from a persisted provider config.
# --------------------------------------------------------------------------- #


def build_configured_backend(config: dict[str, Any] | None) -> Any:
    """Build a backend instance from a provider config dict.

    Falls back to :func:`build_backend` (which honours ``DREAM_BACKEND``) when no
    config or an unknown kind is given, so the bridge always produces a working
    backend.
    """
    kind = ((config or {}).get("kind") or "").lower()
    if kind == "openai":
        return OpenAIBackend(
            model=config.get("model") or None,
            api_key=config.get("api_key") or None,
            base_url=config.get("base_url") or None,
        )
    if kind == "ollama":
        return OllamaBackend(
            model=config.get("model") or None,
            base_url=config.get("base_url") or None,
        )
    if kind == "echo":
        return EchoBackend()
    return build_backend(os.environ.get("DREAM_BACKEND", "echo"))


# --------------------------------------------------------------------------- #
# Registries.
# --------------------------------------------------------------------------- #


@dataclass
class SessionState:
    """One conversation: its own agent history, sharing the durable store."""

    id: str
    title: str
    created_at: float
    updated_at: float
    message_count: int = 0
    provider: str = "echo"
    dream: Dream = None  # type: ignore[assignment]
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    def to_index(self) -> dict[str, Any]:
        """Metadata only — never the conversation history (that is not persisted)."""
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
            "provider": self.provider,
        }


@dataclass
class ApprovalState:
    """A pending dangerous-tool approval awaiting a human decision."""

    id: str
    name: str
    arguments: dict[str, Any]
    risk: str
    summary: str
    resolved: bool = False
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 60.0)
    decision: str | None = None
    execute_on_resolve: bool = True
    waiter: threading.Event = field(default_factory=threading.Event, repr=False)


@dataclass
class SubagentState:
    """A background Dream turn, observable until it finishes."""

    id: str
    status: str = "running"  # running | completed | failed | cancelled
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel_requested: bool = False


class BridgeMethods:
    """Owns the bridge's state and implements every RPC method."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        sessions_path: str | None = None,
        providers_path: str | None = None,
        default_provider: str | None = None,
        sessions_db_path: str | None = None,
    ) -> None:
        self.store = store or MemoryStore(os.environ.get("DREAM_DB", "data/dream.db"))
        self.sessions: dict[str, SessionState] = {}
        self.approvals: dict[str, ApprovalState] = {}
        self.approval_history: list[dict[str, Any]] = []
        self.always_allowed: set[str] = set()
        self.subagents: dict[str, SubagentState] = {}
        self._lock = threading.RLock()

        self._sessions_path = sessions_path or os.environ.get(
            "DREAM_SESSIONS_PATH", "data/bridge_sessions.json"
        )
        self._providers_path = providers_path or os.environ.get(
            "DREAM_PROVIDERS_PATH", "data/bridge_providers.json"
        )
        self._approvals_path = os.environ.get(
            "DREAM_APPROVALS_PATH", f"{self._sessions_path}.approvals.json"
        )
        self._load_approval_settings()
        if sessions_db_path is None:
            sessions_db_path = os.environ.get("DREAM_SESSIONS_DB")
        if sessions_db_path is None:
            sessions_db_path = f"{self._sessions_path}.db" if sessions_path else "data/sessions.db"
        self.session_store = SessionStore(sessions_db_path)
        self._providers, self._default_provider = self._load_providers()
        if default_provider:
            self._default_provider = default_provider

        self._started_at = time.time()
        self._load_sessions_index()

        #: The dispatcher reads this to route method → handler.
        self.handlers: dict[str, Callable[..., Any]] = self._build_handler_table()

    # -- lifecycle -------------------------------------------------------- #

    def shutdown(self) -> None:
        """Persist state and close the store. Safe to call more than once."""
        self._save_sessions_index()
        self._save_providers()
        self._save_approval_settings()
        try:
            self.store.close()
        except Exception:
            pass
        try:
            self.session_store.close()
        except Exception:
            pass

    # -- handler table ---------------------------------------------------- #

    def _build_handler_table(self) -> dict[str, Callable[..., Any]]:
        return {
            "session.create": self.session_create,
            "session.list": self.session_list,
            "session.get": self.session_get,
            "session.delete": self.session_delete,
            "session.rename": self.session_rename,
            "session.update": self.session_update,
            "session.messages": self.session_messages,
            "session.export": self.session_export,
            "conversation.send": self.conversation_send,
            "conversation.stop": self.conversation_stop,
            "provider.list": self.provider_list,
            "provider.test": self.provider_test,
            "provider.configure": self.provider_configure,
            "memory.list": self.memory_list,
            "memory.search": self.memory_search,
            "memory.get": self.memory_get,
            "memory.update": self.memory_update,
            "memory.delete": self.memory_delete,
            "skill.list": self.skill_list,
            "skill.get": self.skill_get,
            "skill.install": self.skill_install,
            "skill.remove": self.skill_remove,
            "tool.list": self.tool_list,
            "tool.execute": self.tool_execute,
            "approval.request": self.approval_request,
            "approval.resolve": self.approval_resolve,
            "approval.list": self.approval_list,
            "approval.history": self.approval_history_list,
            "subagent.spawn": self.subagent_spawn,
            "subagent.list": self.subagent_list,
            "subagent.status": self.subagent_status,
            "subagent.cancel": self.subagent_cancel,
            "health.check": self.health_check,
            "sidecar.version": self.sidecar_version,
        }

    # ------------------------------------------------------------------ #
    # session.*
    # ------------------------------------------------------------------ #

    def _new_dream(self, provider: str | None) -> Dream:
        config = self._providers.get(provider or self._default_provider)
        backend = build_configured_backend(config)

        def ask(name: str, arguments: dict[str, Any]) -> bool:
            if name in self.always_allowed:
                return True
            approval = self._register_approval(
                name, arguments, "dangerous", execute_on_resolve=False
            )
            approval.waiter.wait(timeout=60.0)
            if not approval.resolved:
                with self._lock:
                    approval.resolved = True
                    approval.decision = "deny"
                    self.approval_history.append(self._approval_to_dict(approval))
                    self._save_approval_settings()
            return approval.decision in {"allow", "always_allow"}

        return Dream(self.store, backend, ApprovalPolicy(ask=ask))

    def session_create(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        title = str(params.get("title") or "New session").strip()
        provider = str(params.get("provider") or self._default_provider)
        requested_id = params.get("session_id")
        sid = (
            str(requested_id)
            if isinstance(requested_id, str) and requested_id
            else f"sess_{uuid.uuid4().hex[:20]}"
        )
        with self._lock:
            existing = self.sessions.get(sid)
        if existing is not None:
            return {
                "session_id": sid,
                "id": sid,
                "title": existing.title,
                "created_at": existing.created_at,
            }
        now = time.time()
        session = SessionState(
            id=sid,
            title=title,
            created_at=now,
            updated_at=now,
            provider=provider,
            dream=self._new_dream(provider),
        )
        with self._lock:
            self.sessions[sid] = session
            self.session_store.create(
                title,
                session_id=sid,
                model_provider=provider,
                model_name=str(params.get("model") or ""),
                project_id=params.get("project_id"),
            )
            self._save_sessions_index()
        return {
            "session_id": sid,
            "id": sid,
            "title": session.title,
            "created_at": session.created_at,
        }

    def session_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        rows, total = self.session_store.list(
            limit=int(params.get("limit", 50)),
            offset=int(params.get("offset", 0)),
            search=str(params.get("search") or ""),
            archived=bool(params.get("archived", False)),
        )
        sessions = [
            {
                "id": row.id,
                "title": row.name,
                "name": row.name,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "message_count": row.message_count,
                "provider": row.model_provider,
                "model_name": row.model_name,
                "is_archived": row.is_archived,
                "project_id": row.project_id,
            }
            for row in rows
        ]
        return {
            "sessions": sessions,
            "total": total,
            "limit": int(params.get("limit", 50)),
            "offset": int(params.get("offset", 0)),
        }

    def session_get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session(params)
        return session.to_index()

    def session_delete(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session(params)
        with self._lock:
            self.sessions.pop(session.id, None)
            self.session_store.delete(session.id)
            self._save_sessions_index()
        return {"deleted": True, "session_id": session.id}

    def session_rename(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        session = self._require_session(params)
        title = str(params.get("title", "")).strip()
        if not title:
            raise invalid_params("title must be a non-empty string")
        session.title = title
        session.updated_at = time.time()
        with self._lock:
            self.session_store.update(session.id, name=title)
            self._save_sessions_index()
        return session.to_index()

    def session_update(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        session = self._require_session(params)
        if "title" in params or "name" in params:
            return self.session_rename(
                {"session_id": session.id, "title": params.get("title", params.get("name"))}
            )
        archived = params.get("is_archived")
        if archived is not None:
            row = self.session_store.update(session.id, is_archived=bool(archived))
            return {
                **session.to_index(),
                "is_archived": bool(getattr(row, "is_archived", archived)),
            }
        return session.to_index()

    def session_messages(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        session = self._require_session(params)
        messages = self.session_store.messages(session.id, limit=int(params.get("limit", 10_000)))
        return {
            "messages": [
                {
                    "id": m.id,
                    "session_id": m.session_id,
                    "role": m.role,
                    "content": m.content,
                    "tool_calls": m.tool_calls,
                    "created_at": m.created_at,
                    "token_count": m.token_count,
                }
                for m in messages
            ]
        }

    def session_export(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        session = self._require_session(params)
        try:
            content, content_type, filename = self.session_store.export(
                session.id, str(params.get("format") or "json")
            )
        except ValueError as exc:
            raise invalid_params(str(exc)) from exc
        return {"content": content, "content_type": content_type, "filename": filename}

    # ------------------------------------------------------------------ #
    # conversation.*
    # ------------------------------------------------------------------ #

    async def conversation_send(self, params: dict[str, Any] | None = None) -> Stream:
        """Run a turn, streaming the reply token-by-token, returning the full Turn."""
        params = params or {}
        session = self._require_session(params)
        message = params.get("message")
        if not isinstance(message, str) or not message.strip():
            raise invalid_params("message must be a non-empty string")

        if len(message) > 100_000:
            raise invalid_params("message exceeds the 100000 character limit")

        # Auto-save the user half before provider work, so even a network/provider
        # failure leaves a recoverable transcript.
        self.session_store.add_message(session.id, "user", message)
        session.stop_event.clear()
        dream = session.dream
        cancellation = session.stop_event

        def produce() -> Any:
            if cancellation.is_set():
                return None
            return dream.run(message)

        # Run the blocking turn in a worker thread, then chunk the reply text.
        result = await asyncio.to_thread(produce)
        session.message_count += 1
        session.updated_at = time.time()
        with self._lock:
            self._save_sessions_index()

        if result is None:
            # Stop requested before/during the turn: end the stream cleanly.
            return Stream(
                final={"stopped": True, "session_id": session.id},
                chunks=stream_text(""),
            )

        turn_dict = turn_to_dict(result)
        self.session_store.add_message(
            session.id,
            "assistant",
            turn_dict["reply"],
            tool_calls=turn_dict.get("tool_calls", []),
        )
        cancel = cancellation

        async def _chunks() -> AsyncIterator[Chunk]:
            for piece in tokenise(turn_dict["reply"]):
                if cancel.is_set():
                    break
                yield {"token": piece}

        return Stream(final=turn_dict, chunks=_chunks())

    async def conversation_stop(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session(params)
        session.stop_event.set()
        return {"stopped": True, "session_id": session.id}

    # ------------------------------------------------------------------ #
    # provider.*
    # ------------------------------------------------------------------ #

    def provider_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        providers = [
            {
                "id": pid,
                "kind": cfg.get("kind", "echo"),
                "label": cfg.get("label") or pid,
                "model": cfg.get("model"),
                "base_url": cfg.get("base_url"),
                "local": cfg.get("kind", "echo") in {"echo", "ollama"},
                "status": "connected" if cfg.get("kind") == "echo" else "untested",
            }
            for pid, cfg in self._providers.items()
        ]
        return {"providers": providers, "default": self._default_provider}

    async def provider_test(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        provider_id = str(params.get("provider") or self._default_provider)
        config = self._providers.get(provider_id) or {"kind": provider_id}
        kind = (config.get("kind") or provider_id).lower()

        if kind == "echo":
            return {"ok": True, "provider": provider_id, "latency_ms": 0}

        backend = build_configured_backend(config)

        def probe() -> Any:
            return backend.chat([{"role": "user", "content": "ping"}])

        started = time.monotonic()
        try:
            await asyncio.wait_for(asyncio.to_thread(probe), timeout=PROBE_TIMEOUT_SECONDS)
        except TimeoutError:
            return {"ok": False, "provider": provider_id, "detail": "timed out"}
        except Exception as exc:
            return {"ok": False, "provider": provider_id, "detail": f"{type(exc).__name__}: {exc}"}
        latency_ms = round((time.monotonic() - started) * 1000.0, 2)
        return {"ok": True, "provider": provider_id, "latency_ms": latency_ms}

    def provider_configure(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        config = params.get("provider")
        if not isinstance(config, dict):
            raise invalid_params("provider config must be an object")
        kind = str(config.get("kind", "")).lower()
        if kind not in PROVIDER_KINDS:
            raise invalid_params(f"kind must be one of {PROVIDER_KINDS}, got {kind!r}")
        provider_id = str(params.get("id") or config.get("label") or kind)
        stored = {
            "kind": kind,
            "label": str(config.get("label") or provider_id),
            "model": config.get("model"),
            "base_url": config.get("base_url"),
            "api_key": config.get("api_key"),
        }
        with self._lock:
            self._providers[provider_id] = stored
            if params.get("set_default") or not self._default_provider:
                self._default_provider = provider_id
            self._save_providers()
        return {"saved": True, "id": provider_id, "default": self._default_provider}

    # ------------------------------------------------------------------ #
    # memory.*
    # ------------------------------------------------------------------ #

    def memory_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        kinds = params.get("kind")
        if kinds is not None and not isinstance(kinds, list):
            raise invalid_params("kind must be a list when provided")
        include_archived = bool(params.get("include_archived", False))
        limit = params.get("limit")
        kwargs: dict[str, Any] = {"include_archived": include_archived}
        if kinds is not None:
            kwargs["kinds"] = kinds
        if isinstance(limit, int) and limit > 0:
            kwargs["limit"] = limit
        memories = [memory_to_dict(m) for m in self.store.all(**kwargs)]
        return {"memories": memories}

    def memory_search(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        query = params.get("query")
        if not isinstance(query, str) or not query.strip():
            raise invalid_params("query must be a non-empty string")
        limit = int(params.get("limit", 8))
        memories = [memory_to_dict(m) for m in self.store.recall(query, limit=limit)]
        return {"memories": memories}

    def memory_get(self, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        params = params or {}
        memory_id = self._require_int_id(params, "memory_id")
        # A soft-deleted (archived) memory is hidden from get() by default; ask
        # for include_archived to see it, mirroring memory.list.
        include_archived = bool(params.get("include_archived", False))
        memory = self.store.get(memory_id, include_archived=include_archived)
        if memory is None:
            return None
        return memory_to_dict(memory)

    def memory_update(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        memory_id = self._require_int_id(params, "memory_id")
        kwargs: dict[str, Any] = {}
        for key, caster in (("content", str), ("kind", str), ("importance", float)):
            if key in params and params[key] is not None:
                value = caster(params[key])  # type: ignore[call-arg]
                if key == "kind" and value not in KINDS:
                    raise invalid_params(f"kind must be one of {KINDS}")
                if key == "importance" and not 0.0 <= value <= 1.0:
                    raise invalid_params("importance must be between 0.0 and 1.0")
                kwargs[key] = value
        if "tags" in params and params["tags"] is not None:
            tags = params["tags"]
            if not isinstance(tags, list):
                raise invalid_params("tags must be a list")
            kwargs["tags"] = [str(t) for t in tags]
        updated = self.store.update_memory(memory_id, **kwargs)
        if updated is None:
            raise invalid_params(f"no active memory with id {memory_id}")
        return {"memory": memory_to_dict(updated)}

    def memory_delete(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        memory_id = self._require_int_id(params, "memory_id")
        hard = bool(params.get("hard", False))
        deleted = self.store.forget(memory_id, hard=hard)
        if not deleted:
            raise invalid_params(f"no active memory with id {memory_id}")
        return {"deleted": True, "memory_id": memory_id}

    # ------------------------------------------------------------------ #
    # skill.*
    # ------------------------------------------------------------------ #

    def skill_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        from dream import skills as skills_module

        loaded, problems = skills_module.load_skills()
        return {
            "skills": [skill_to_dict(s) for s in loaded],
            "problems": [{"filename": p.filename, "detail": p.detail} for p in problems],
        }

    def skill_get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        query = params.get("query")
        if not isinstance(query, str) or not query.strip():
            raise invalid_params("query must be a non-empty string")
        from dream import skills as skills_module

        skill = skills_module.find_skill(query, permissive=True)
        return {"match": skill_to_dict(skill) if skill else None}

    def skill_install(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        name = params.get("name")
        description = params.get("description")
        steps = params.get("steps")
        if not isinstance(name, str) or not name.strip():
            raise invalid_params("name must be a non-empty string")
        if not isinstance(description, str) or not description.strip():
            raise invalid_params("description must be a non-empty string")
        if not isinstance(steps, list) or not steps:
            raise invalid_params("steps must be a non-empty list")
        from dream import skills as skills_module

        filename = skills_module.save_skill(name, description, steps)
        return {"filename": filename, "status": "installed"}

    def skill_remove(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise invalid_params("name must be a non-empty string")
        from dream import skills as skills_module
        from dream.tools import _safe_path

        cleaned = skills_module.validate_name(name)
        path = _safe_path(f"skills/{cleaned}.txt")
        if not path.exists():
            raise invalid_params(f"no skill named {cleaned!r}")
        path.unlink()
        return {"removed": True, "filename": f"skills/{cleaned}.txt"}

    # ------------------------------------------------------------------ #
    # tool.*
    # ------------------------------------------------------------------ #

    def tool_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        from dream.tools import REGISTRY

        tools = [
            {
                "name": name,
                "risk": registered.risk,
                "description": registered.description,
                "schema": registered.schema,
            }
            for name, registered in sorted(REGISTRY.items())
        ]
        return {"tools": tools}

    def tool_execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        from dream.tools import REGISTRY, execute

        params = params or {}
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise invalid_params("name must be a non-empty string")
        registered = REGISTRY.get(name)
        if registered is None:
            raise invalid_params(f"unknown tool: {name}")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise invalid_params("arguments must be an object")

        # Dangerous tools require an explicit, resolved approval.
        if (
            registered.risk == "dangerous"
            and name not in self.always_allowed
            and not bool(params.get("approved"))
        ):
            approval = self._register_approval(name, arguments, registered.risk)
            raise BridgeError(
                APPROVAL_REQUIRED,
                f"{name} requires human approval",
                data={"approval_id": approval.id, "risk": registered.risk},
            )

        approved = bool(params.get("approved")) or registered.risk != "dangerous"
        raw = execute(name, arguments, approved=approved)
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            decoded = {"status": "ok", "result": raw}
        return decoded

    # ------------------------------------------------------------------ #
    # approval.*
    # ------------------------------------------------------------------ #

    def approval_request(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        from dream.tools import REGISTRY

        params = params or {}
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise invalid_params("name must be a non-empty string")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise invalid_params("arguments must be an object")
        registered = REGISTRY.get(name)
        risk = registered.risk if registered else "dangerous"
        approval = self._register_approval(name, arguments, risk)
        return {
            "approval_id": approval.id,
            "risk": approval.risk,
            "summary": approval.summary,
        }

    def approval_resolve(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        approval_id = params.get("approval_id")
        if not isinstance(approval_id, str) or not approval_id:
            raise invalid_params("approval_id must be a non-empty string")
        requested = params.get("decision")
        decision = (
            str(requested)
            if requested is not None
            else ("allow" if bool(params.get("allowed")) else "deny")
        )
        if decision not in {"allow", "deny", "always_allow"}:
            raise invalid_params("decision must be allow, deny, or always_allow")
        with self._lock:
            approval = self.approvals.get(approval_id)
            if approval is None:
                raise invalid_params(f"no pending approval with id {approval_id!r}")
            if approval.resolved:
                raise invalid_params(f"approval {approval_id!r} already resolved")
            if time.time() >= approval.expires_at:
                decision = "deny"
            approval.resolved = True
            approval.decision = decision
            name, arguments = approval.name, approval.arguments
            if decision == "always_allow":
                self.always_allowed.add(name)
            self.approval_history.append(self._approval_to_dict(approval))
            self._save_approval_settings()
            approval.waiter.set()

        if decision == "deny":
            return {
                "blocked": True,
                "reason": "denied by user or timed out",
                "approval_id": approval_id,
            }

        if not approval.execute_on_resolve:
            return {"status": "approved", "approval_id": approval_id, "decision": decision}

        from dream.tools import execute

        raw = execute(name, arguments, approved=True)
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {"status": "ok", "result": raw}

    def approval_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        now = time.time()
        with self._lock:
            for approval in self.approvals.values():
                if not approval.resolved and now >= approval.expires_at:
                    approval.resolved = True
                    approval.decision = "deny"
                    approval.waiter.set()
                    self.approval_history.append(self._approval_to_dict(approval))
                    self._save_approval_settings()
            pending = [self._approval_to_dict(a) for a in self.approvals.values() if not a.resolved]
        pending.sort(key=lambda item: item["created_at"])
        return {"approvals": pending, "always_allowed": sorted(self.always_allowed)}

    def approval_history_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        limit = int((params or {}).get("limit", 100))
        return {"approvals": self.approval_history[-max(1, min(limit, 1000)) :]}

    @staticmethod
    def _approval_to_dict(approval: ApprovalState) -> dict[str, Any]:
        return {
            "approval_id": approval.id,
            "name": approval.name,
            "arguments": approval.arguments,
            "risk": approval.risk,
            "summary": approval.summary,
            "created_at": approval.created_at,
            "expires_at": approval.expires_at,
            "decision": approval.decision,
        }

    def _register_approval(
        self,
        name: str,
        arguments: dict[str, Any],
        risk: str,
        *,
        execute_on_resolve: bool = True,
    ) -> ApprovalState:
        approval_id = f"appr_{uuid.uuid4().hex[:16]}"
        summary = _approval_summary(name, arguments)
        approval = ApprovalState(
            id=approval_id,
            name=name,
            arguments=dict(arguments),
            risk=risk,
            summary=summary,
            execute_on_resolve=execute_on_resolve,
        )
        with self._lock:
            self.approvals[approval_id] = approval
        return approval

    # ------------------------------------------------------------------ #
    # subagent.*
    # ------------------------------------------------------------------ #

    async def subagent_spawn(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        message = params.get("message")
        if not isinstance(message, str) or not message.strip():
            raise invalid_params("message must be a non-empty string")
        provider = str(params.get("provider") or self._default_provider)

        sub_id = f"sub_{uuid.uuid4().hex[:16]}"
        state = SubagentState(id=sub_id, message=message)
        with self._lock:
            self.subagents[sub_id] = state

        session_id = params.get("session_id")
        dream = (
            self._require_session({"session_id": session_id}).dream
            if session_id
            else self._new_dream(provider)
        )

        def run_turn() -> None:
            try:
                if state.cancel_requested:
                    state.status = "cancelled"
                    return
                turn = dream.run(message)
                state.result = turn_to_dict(turn)
                state.status = "cancelled" if state.cancel_requested else "completed"
            except Exception as exc:  # never let a subagent crash the sidecar
                state.error = f"{type(exc).__name__}: {exc}"
                state.status = "failed"
            finally:
                state.finished_at = time.time()

        asyncio.get_running_loop().run_in_executor(None, run_turn)
        return {"subagent_id": sub_id, "status": "running"}

    def subagent_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        with self._lock:
            snapshots = [_subagent_to_dict(s) for s in self.subagents.values()]
        return {"subagents": snapshots}

    def subagent_status(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        sub_id = params.get("subagent_id")
        if not isinstance(sub_id, str) or not sub_id:
            raise invalid_params("subagent_id must be a non-empty string")
        with self._lock:
            state = self.subagents.get(sub_id)
        if state is None:
            raise invalid_params(f"no subagent with id {sub_id!r}")
        return _subagent_to_dict(state)

    def subagent_cancel(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        sub_id = params.get("subagent_id")
        if not isinstance(sub_id, str) or not sub_id:
            raise invalid_params("subagent_id must be a non-empty string")
        with self._lock:
            state = self.subagents.get(sub_id)
        if state is None:
            raise invalid_params(f"no subagent with id {sub_id!r}")
        state.cancel_requested = True
        if state.status == "running":
            state.status = "cancelled"
            state.finished_at = time.time()
        return {"cancelled": True, "subagent_id": sub_id}

    # ------------------------------------------------------------------ #
    # health / version
    # ------------------------------------------------------------------ #

    def health_check(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        return {
            "status": "ok",
            "sessions": len(self.sessions),
            "provider": self._default_provider,
            "uptime_seconds": round(time.time() - self._started_at, 3),
        }

    def sidecar_version(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        import sys

        from dream import __version__ as core_version
        from dream.bridge import __version__ as sidecar_version

        return {
            "protocol": "1.0",
            "core": core_version,
            "sidecar": sidecar_version,
            "python": ".".join(map(str, sys.version_info[:3])),
        }

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    def _require_session(self, params: dict[str, Any] | None) -> SessionState:
        params = params or {}
        session_id = params.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise invalid_params("session_id must be a non-empty string")
        with self._lock:
            session = self.sessions.get(session_id)
        if session is None:
            raise invalid_params(f"no session with id {session_id!r}")
        return session

    @staticmethod
    def _require_int_id(params: dict[str, Any] | None, key: str) -> int:
        params = params or {}
        raw = params.get(key)
        try:
            return int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise invalid_params(f"{key} must be an integer") from exc

    # -- persistence ------------------------------------------------------ #

    def _load_approval_settings(self) -> None:
        try:
            with open(self._approvals_path, encoding="utf-8") as handle:
                blob = json.load(handle)
        except (OSError, ValueError):
            return
        if isinstance(blob, dict):
            self.always_allowed = {str(name) for name in blob.get("always_allowed", [])}
            history = blob.get("history", [])
            if isinstance(history, list):
                self.approval_history = [item for item in history[-1000:] if isinstance(item, dict)]

    def _save_approval_settings(self) -> None:
        self._write_json(
            self._approvals_path,
            {
                "always_allowed": sorted(self.always_allowed),
                "history": self.approval_history[-1000:],
            },
        )

    def _load_providers(self) -> tuple[dict[str, dict[str, Any]], str]:
        default = os.environ.get("DREAM_BACKEND", "echo")
        try:
            with open(self._providers_path, encoding="utf-8") as handle:
                blob = json.load(handle)
        except (OSError, ValueError):
            return {}, default
        providers = blob.get("providers", {}) if isinstance(blob, dict) else {}
        saved_default = blob.get("default") if isinstance(blob, dict) else None
        return dict(providers), str(saved_default or default)

    def _save_providers(self) -> None:
        self._write_json(
            self._providers_path,
            {"providers": self._providers, "default": self._default_provider},
        )

    def _load_sessions_index(self) -> None:
        # SQLite is authoritative. The legacy JSON index is imported once for
        # users upgrading from P-02, then kept only for backwards compatibility.
        stored, _ = self.session_store.list(limit=200, archived=False)
        archived, _ = self.session_store.list(limit=200, archived=True)
        rows: list[dict[str, Any]] = [
            {
                "id": s.id,
                "title": s.name,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "message_count": s.message_count,
                "provider": s.model_provider,
            }
            for s in [*stored, *archived]
        ]
        if not rows:
            try:
                with open(self._sessions_path, encoding="utf-8") as handle:
                    legacy = json.load(handle)
                rows = legacy if isinstance(legacy, list) else []
            except (OSError, ValueError):
                rows = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            sid = str(row["id"])
            title = str(row.get("title", "New session"))
            provider = str(row.get("provider", self._default_provider))
            if self.session_store.get(sid) is None:
                self.session_store.create(title, session_id=sid, model_provider=provider)
            self.sessions[sid] = SessionState(
                id=sid,
                title=title,
                created_at=float(row.get("created_at", time.time())),
                updated_at=float(row.get("updated_at", time.time())),
                message_count=int(row.get("message_count", 0)),
                provider=provider,
                dream=self._new_dream(provider),
            )

    def _save_sessions_index(self) -> None:
        rows = [s.to_index() for s in self.sessions.values()]
        self._write_json(self._sessions_path, rows)

    def _write_json(self, path: str, payload: Any) -> None:
        try:
            directory = os.path.dirname(os.path.abspath(path))
            os.makedirs(directory, exist_ok=True)
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError:
            # Persistence is best-effort: a read-only data dir must not crash
            # the sidecar. The in-memory registries still serve requests.
            pass


def _approval_summary(name: str, arguments: dict[str, Any]) -> str:
    """A short, safe, human-readable summary of a tool call for approval UX."""
    try:
        rendered = json.dumps(arguments, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = repr(arguments)
    if len(rendered) > 160:
        rendered = rendered[:157] + "..."
    return f"{name}({rendered})"


def _subagent_to_dict(state: SubagentState) -> dict[str, Any]:
    return {
        "id": state.id,
        "status": state.status,
        "message": state.message,
        "result": state.result,
        "error": state.error,
        "created_at": state.created_at,
        "finished_at": state.finished_at,
    }


__all__ = [
    "PROVIDER_KINDS",
    "BridgeMethods",
    "SessionState",
    "ApprovalState",
    "SubagentState",
    "build_configured_backend",
    "memory_to_dict",
    "turn_to_dict",
    "skill_to_dict",
    "reminder_to_dict",
]
