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
import re
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
from dream.memory import KINDS, Memory, MemoryStore, normalize_fa
from dream.model_providers import (
    PROVIDER_CATALOG,
    AnthropicBackend,
    GoogleBackend,
    KeychainCredentialStore,
    OAuthPKCEManager,
    ProviderRegistry,
)
from dream.skills import SKILL_SUFFIX, parse_skill_text

from .errors import APPROVAL_REQUIRED, BridgeError, invalid_params
from .streams import Chunk, Stream, stream_text, tokenise

#: Provider kinds the bridge knows how to build and persist.
PROVIDER_KINDS: tuple[str, ...] = ("echo", *PROVIDER_CATALOG.keys())

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


def skill_to_dict(skill: Any, enabled: bool = True) -> dict[str, Any]:
    return {
        "name": skill.name,
        "description": skill.description,
        "steps": list(skill.steps),
        "filename": skill.filename,
        "enabled": enabled,
    }


def skill_detail_to_dict(
    skill: Any, disabled: set[str] | None = None
) -> dict[str, Any] | None:
    """Full skill detail, including rendered file text and metadata.

    Returns ``None`` when *skill* is ``None`` so callers can pass the result of
    :func:`_resolve_skill` straight through.
    """
    if skill is None:
        return None
    from dream import skills as skills_module

    created_at = 0.0
    try:
        leaf = skill.filename.split("/")[-1]
        path = skills_module._skills_dir() / leaf
        if path.exists():
            created_at = path.stat().st_mtime
    except OSError:
        created_at = 0.0
    return {
        "name": skill.name,
        "description": skill.description,
        "steps": list(skill.steps),
        "filename": skill.filename,
        "enabled": skill.name not in (disabled or set()),
        "created_at": created_at,
        "content": skills_module.render_skill_text(
            skill.name, skill.description, list(skill.steps)
        ),
    }


# --------------------------------------------------------------------------- #
# Sanitisation & safety — input validation shared by memory/skill CRUD.
# --------------------------------------------------------------------------- #

# Script/style blocks are stripped whole (they never belong in a memory).
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
# Inline event-handler attributes: onload=, onclick='...', onerror=...
_ON_ATTR_RE = re.compile(
    r"""\son\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE
)
_JAVASCRIPT_RE = re.compile(r"javascript:", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# Absolute paths (unix / win) or parent traversal smuggled into a skill.
_PATH_SKILL_RE = re.compile(r"\.\.[\\/]|\.[\\/]\.\.")
_ABS_PATH_RE = re.compile(r"(?:^|[\s\"'])(/[^\s\"']+|[A-Za-z]:[\\/])")
# Code-style imports of dangerous stdlib modules. Plain prose that uses the word
# "import" (e.g. a skill literally named "import test") must NOT be flagged, so
# only specific execution-capable modules are rejected.
_DANGEROUS_MODULES = (
    "os", "sys", "subprocess", "shutil", "pathlib", "socket", "ctypes",
    "importlib", "pickle", "marshal", "builtins", "code", "io", "glob",
    "tempfile", "platform",
)
_CODE_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+(?:"
    + "|".join(_DANGEROUS_MODULES)
    + r")\b|from\s+(?:"
    + "|".join(_DANGEROUS_MODULES)
    + r")\s+import\b)",
    re.MULTILINE | re.IGNORECASE,
)

# Caps shared with the UI (see docs/bridge/protocol.md §3 memory/skill CRUD).
MAX_MEMORY_CONTENT_BYTES = 50 * 1024
MAX_SKILL_CONTENT_BYTES = 100 * 1024


def _sanitize_memory_text(text: str) -> str:
    """Strip script/style blocks, event-handler attrs and stray tags.

    Memories are user prose, not markup. Removing script/style and inline
    handlers neutralises the obvious stored-XSS vectors while keeping the text
    the user actually wrote.
    """
    text = _SCRIPT_STYLE_RE.sub("", text)
    text = _ON_ATTR_RE.sub("", text)
    text = _JAVASCRIPT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    return text.strip()


def _validate_skill_safety(name: str, description: str, steps: list[str]) -> None:
    """Refuse skills that smuggle filesystem paths or code-style imports.

    Skills are plain ``name:/description:/steps:`` prose. An absolute path or a
    ``..`` traversal could be abused by an import; a Python ``import`` statement
    at the start of a line is almost certainly code being mislabelled as a
    procedure. Both are rejected with ``INVALID_PARAMS``.
    """
    joined = "\n".join(
        [str(name), str(description), *[str(s) for s in steps]]
    )
    if _PATH_SKILL_RE.search(joined):
        raise invalid_params("skill content must not contain '..' path segments")
    if _ABS_PATH_RE.search(joined):
        raise invalid_params("skill content must not contain absolute file paths")
    if _CODE_IMPORT_RE.search(joined):
        raise invalid_params("skill content must not contain import statements")


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
    """Build a backend from non-secret metadata plus an in-memory credential.

    ``credential`` is injected only after a keychain read and must never be
    passed to the registry's persistence layer. OpenAI-compatible providers all
    share :class:`OpenAIBackend`; Anthropic and Google use small wire adapters.
    """
    config = config or {}
    kind = str(config.get("kind") or "").lower()
    model = str(
        config.get("model")
        or next(iter(config.get("enabled_models") or []), "")
        or next(iter(config.get("models") or []), "")
    )
    endpoint = config.get("endpoint") or config.get("base_url") or None
    credential = str(config.get("credential") or config.get("api_key") or "")
    effort = config.get("reasoning_effort")

    if kind in {"openai", "groq", "together", "openrouter", "vllm", "llamacpp"}:
        return OpenAIBackend(
            model=model or None,
            api_key=credential,
            base_url=endpoint,
            reasoning_effort=effort if kind in {"openai", "openrouter"} else None,
        )
    if kind == "ollama":
        # Catalog endpoints already end in /v1. Legacy P-02 configs stored the
        # host only and still need OllamaBackend's suffix handling.
        if endpoint and str(endpoint).rstrip("/").endswith("/v1"):
            return OpenAIBackend(model=model or None, api_key="", base_url=endpoint)
        return OllamaBackend(model=model or None, base_url=endpoint)
    if kind == "anthropic":
        return AnthropicBackend(
            model,
            credential,
            str(endpoint or "https://api.anthropic.com"),
            reasoning_effort=effort,
        )
    if kind == "google":
        return GoogleBackend(
            model,
            credential,
            str(endpoint or "https://generativelanguage.googleapis.com/v1beta"),
            oauth=bool(config.get("oauth")),
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
    model: str = ""
    reasoning_effort: float = 0.0
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
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
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
        disabled_skills_path: str | None = None,
        default_provider: str | None = None,
        credential_store: KeychainCredentialStore | None = None,
    ) -> None:
        self.store = store or MemoryStore(os.environ.get("DREAM_DB", "data/dream.db"))
        self.sessions: dict[str, SessionState] = {}
        self.approvals: dict[str, ApprovalState] = {}
        self.subagents: dict[str, SubagentState] = {}
        self._lock = threading.RLock()

        self._sessions_path = sessions_path or os.environ.get(
            "DREAM_SESSIONS_PATH", "data/bridge_sessions.json"
        )
        self._providers_path = providers_path or os.environ.get(
            "DREAM_PROVIDERS_PATH", "data/bridge_providers.json"
        )
        self.provider_registry = ProviderRegistry(
            self._providers_path, credentials=credential_store
        )
        # Kept as aliases for P-02 callers that introspect these attributes.
        self._providers = self.provider_registry._providers
        self._default_provider = default_provider or self.provider_registry.default_provider
        self.oauth = OAuthPKCEManager(self.provider_registry)

        self._started_at = time.time()
        self._disabled_skills_path = (
            disabled_skills_path
            or os.environ.get(
                "DREAM_DISABLED_SKILLS_PATH", "data/bridge_disabled_skills.json"
            )
        )
        self._disabled_skills: set[str] = self._load_disabled_skills()
        self._load_sessions_index()

        #: The dispatcher reads this to route method → handler.
        self.handlers: dict[str, Callable[..., Any]] = self._build_handler_table()

    # -- lifecycle -------------------------------------------------------- #

    def shutdown(self) -> None:
        """Persist state and close the store. Safe to call more than once."""
        self._save_sessions_index()
        self._save_providers()
        self._save_disabled_skills()
        try:
            self.store.close()
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
            "session.configure": self.session_configure,
            "conversation.send": self.conversation_send,
            "conversation.stop": self.conversation_stop,
            "provider.catalog": self.provider_catalog,
            "provider.list": self.provider_list,
            "provider.get": self.provider_get,
            "provider.create": self.provider_create,
            "provider.update": self.provider_update,
            "provider.delete": self.provider_delete,
            "provider.models": self.provider_models,
            "provider.test": self.provider_test,
            "provider.configure": self.provider_configure,
            "provider.oauth.begin": self.provider_oauth_begin,
            "provider.oauth.complete": self.provider_oauth_complete,
            "memory.list": self.memory_list,
            "memory.search": self.memory_search,
            "memory.get": self.memory_get,
            "memory.update": self.memory_update,
            "memory.delete": self.memory_delete,
            "memory.count": self.memory_count,
            "memory.create": self.memory_create,
            "skill.list": self.skill_list,
            "skill.get": self.skill_get,
            "skill.install": self.skill_install,
            "skill.remove": self.skill_delete,
            "skill.delete": self.skill_delete,
            "skill.enable": self.skill_enable,
            "skill.disable": self.skill_disable,
            "skill.export": self.skill_export,
            "tool.list": self.tool_list,
            "tool.execute": self.tool_execute,
            "approval.request": self.approval_request,
            "approval.resolve": self.approval_resolve,
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

    @staticmethod
    def _effort_label(value: Any) -> str | None:
        try:
            effort = float(value)
        except (TypeError, ValueError):
            return None
        if effort <= 0:
            return None
        if effort < 0.5:
            return "low"
        if effort < 0.85:
            return "medium"
        return "high"

    def _backend_for(
        self, provider: str | None, model: str | None = None, reasoning_effort: Any = 0.0
    ) -> Any:
        provider_id = provider or self._default_provider
        if provider_id == "echo":
            return EchoBackend()
        config = self.provider_registry.raw(provider_id)
        if config is None:
            return build_configured_backend({"kind": provider_id})
        try:
            credential = self.provider_registry.credential(provider_id) or ""
            oauth = self.provider_registry.credentials.has(provider_id, "oauth_access_token")
        except Exception:
            credential, oauth = "", False
        return build_configured_backend(
            {
                **config,
                "model": model or None,
                "credential": credential,
                "oauth": oauth,
                "reasoning_effort": self._effort_label(reasoning_effort),
            }
        )

    def _new_dream(
        self, provider: str | None, model: str | None = None, reasoning_effort: Any = 0.0
    ) -> Dream:
        backend = self._backend_for(provider, model, reasoning_effort)
        return Dream(self.store, backend, ApprovalPolicy())

    def session_create(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        title = str(params.get("title") or "New session").strip()
        provider = str(params.get("provider") or self._default_provider)
        model = str(params.get("model") or "")
        reasoning_effort = min(1.0, max(0.0, float(params.get("reasoning_effort") or 0.0)))
        sid = f"sess_{uuid.uuid4().hex[:20]}"
        now = time.time()
        session = SessionState(
            id=sid,
            title=title,
            created_at=now,
            updated_at=now,
            provider=provider,
            model=model,
            reasoning_effort=reasoning_effort,
            dream=self._new_dream(provider, model, reasoning_effort),
        )
        with self._lock:
            self.sessions[sid] = session
            self._save_sessions_index()
        return {
            "session_id": sid,
            "id": sid,
            "title": session.title,
            "created_at": session.created_at,
        }

    def session_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        with self._lock:
            sessions = sorted(
                (s.to_index() for s in self.sessions.values()),
                key=lambda s: s["updated_at"],
                reverse=True,
            )
        return {"sessions": sessions}

    def session_get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session(params)
        return session.to_index()

    def session_delete(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session(params)
        with self._lock:
            self.sessions.pop(session.id, None)
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
            self._save_sessions_index()
        return session.to_index()

    def session_configure(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Switch one session's backend without affecting any other pane."""
        params = params or {}
        session = self._require_session(params)
        provider = str(params.get("provider") or session.provider)
        if provider != "echo" and self.provider_registry.raw(provider) is None:
            raise invalid_params(f"no provider with id {provider!r}")
        model = str(params.get("model") or session.model)
        try:
            effort = min(
                1.0, max(0.0, float(params.get("reasoning_effort", session.reasoning_effort)))
            )
        except (TypeError, ValueError) as exc:
            raise invalid_params("reasoning_effort must be between 0 and 1") from exc
        session.provider = provider
        session.model = model
        session.reasoning_effort = effort
        # Preserve the conversation history while replacing only the backend.
        session.dream.backend = self._backend_for(provider, model, effort)
        session.updated_at = time.time()
        with self._lock:
            self._save_sessions_index()
        return session.to_index()

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

    def provider_catalog(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        return {"catalog": self.provider_registry.catalog()}

    def provider_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        providers = [
            {
                "id": "echo",
                "kind": "echo",
                "name": "Echo (offline)",
                "label": "Echo (offline)",
                "local": True,
                "status": "connected",
                "models": ["echo"],
                "enabled_models": ["echo"],
                "credential_configured": True,
                "supports_reasoning": False,
            },
            *self.provider_registry.list(),
        ]
        return {"providers": providers, "default": self._default_provider}

    def provider_get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        provider_id = self._provider_id(params)
        if provider_id == "echo":
            return {"provider": self.provider_list({})["providers"][0]}
        provider = self.provider_registry.get(provider_id)
        if provider is None:
            raise invalid_params(f"no provider with id {provider_id!r}")
        return {"provider": provider}

    def provider_create(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        config = params.get("provider")
        if not isinstance(config, dict):
            raise invalid_params("provider config must be an object")
        credential = params.get("credential") or config.get("api_key")
        try:
            provider = self.provider_registry.add(
                config,
                provider_id=str(params.get("id") or config.get("id") or "") or None,
                credential=str(credential) if credential else None,
                set_default=bool(params.get("set_default")),
            )
        except (KeyError, ValueError, RuntimeError) as exc:
            raise invalid_params(str(exc)) from exc
        self._default_provider = self.provider_registry.default_provider
        return {
            "saved": True,
            "id": provider["id"],
            "provider": provider,
            "default": self._default_provider,
        }

    def provider_update(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        provider_id = self._provider_id(params)
        changes = params.get("provider")
        if not isinstance(changes, dict):
            raise invalid_params("provider config must be an object")
        credential = params.get("credential") or changes.get("api_key")
        try:
            provider = self.provider_registry.update(
                provider_id,
                changes,
                credential=str(credential) if credential else None,
                clear_credential=bool(params.get("clear_credential")),
                set_default=bool(params.get("set_default")),
            )
        except KeyError as exc:
            raise invalid_params(f"no provider with id {provider_id!r}") from exc
        except (ValueError, RuntimeError) as exc:
            raise invalid_params(str(exc)) from exc
        self._default_provider = self.provider_registry.default_provider
        return {
            "saved": True,
            "id": provider_id,
            "provider": provider,
            "default": self._default_provider,
        }

    def provider_delete(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        provider_id = self._provider_id(params)
        if provider_id == "echo":
            raise invalid_params("the offline Echo provider cannot be deleted")
        try:
            deleted = self.provider_registry.delete(provider_id)
        except RuntimeError as exc:
            raise invalid_params(str(exc)) from exc
        if not deleted:
            raise invalid_params(f"no provider with id {provider_id!r}")
        self._default_provider = self.provider_registry.default_provider
        return {"deleted": True, "id": provider_id, "default": self._default_provider}

    async def provider_models(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        provider_id = self._provider_id(params)
        if provider_id == "echo":
            return {"provider": "echo", "models": ["echo"], "cached": True}
        try:
            models = await asyncio.to_thread(
                self.provider_registry.models, provider_id, force=bool(params.get("force"))
            )
        except KeyError as exc:
            raise invalid_params(f"no provider with id {provider_id!r}") from exc
        except ConnectionError as exc:
            return {"provider": provider_id, "models": [], "error": str(exc)}
        return {"provider": provider_id, "models": models}

    async def provider_test(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        provider_id = self._provider_id(params, default=self._default_provider)
        if provider_id == "echo":
            return {"ok": True, "provider": provider_id, "latency_ms": 0}
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.provider_registry.test_connection, provider_id),
                timeout=PROBE_TIMEOUT_SECONDS + 1,
            )
        except KeyError as exc:
            raise invalid_params(f"no provider with id {provider_id!r}") from exc
        except TimeoutError:
            return {"ok": False, "provider": provider_id, "detail": "timed out"}
        except Exception:
            # Never include provider-library errors here: they can contain an
            # Authorization header or a Google key-bearing URL.
            return {"ok": False, "provider": provider_id, "detail": "Connection failed"}

    def provider_configure(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Backward-compatible P-02 upsert, now backed by secure CRUD."""
        params = dict(params or {})
        config = params.get("provider")
        if not isinstance(config, dict):
            raise invalid_params("provider config must be an object")
        if str(config.get("kind") or "").lower() == "echo":
            if params.get("set_default"):
                self._default_provider = "echo"
                self.provider_registry.default_provider = "echo"
                self._save_providers()
            return {"saved": True, "id": "echo", "default": self._default_provider}
        provider_id = str(params.get("id") or config.get("label") or config.get("kind") or "")
        params["id"] = provider_id
        if self.provider_registry.get(provider_id):
            return self.provider_update(params)
        return self.provider_create(params)

    def provider_oauth_begin(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        provider_id = self._provider_id(params)
        redirect_uri = str(params.get("redirect_uri") or "")
        try:
            return self.oauth.begin(provider_id, redirect_uri)
        except (KeyError, ValueError) as exc:
            raise invalid_params(str(exc)) from exc

    async def provider_oauth_complete(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        provider_id = self._provider_id(params)
        state = str(params.get("state") or "")
        code = str(params.get("code") or "")
        try:
            return await asyncio.to_thread(self.oauth.complete, provider_id, state, code)
        except (KeyError, ValueError, ConnectionError, RuntimeError) as exc:
            raise invalid_params(str(exc)) from exc

    # ------------------------------------------------------------------ #
    # memory.*
    # ------------------------------------------------------------------ #

    def memory_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """List memories with kind/search/date/importance filters, sort & cursor.

        Returns a page plus ``total``/``next_cursor``/``has_more`` so the UI can
        drive infinite scroll. Filtering is done in Python over the active set;
        the store owns persistence, not query shaping.
        """
        params = params or {}
        kind_filter = params.get("kind_filter", params.get("kind"))
        if kind_filter is not None and not isinstance(kind_filter, list):
            kind_filter = [kind_filter]
        if kind_filter and any(k not in KINDS for k in kind_filter):
            raise invalid_params(f"kind_filter must contain one of {KINDS}")
        include_archived = bool(params.get("include_archived", False))
        search_query = params.get("search_query") or None
        if search_query is not None and not str(search_query).strip():
            search_query = None
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        min_importance = params.get("min_importance")
        sort_by = str(params.get("sort_by") or "date_newest")
        if sort_by not in ("relevance", "date_newest", "date_oldest", "importance"):
            raise invalid_params(
                "sort_by must be one of relevance|date_newest|date_oldest|importance"
            )
        try:
            limit = int(params.get("limit", 50))
        except (TypeError, ValueError) as exc:
            raise invalid_params("limit must be an integer") from exc
        if limit <= 0 or limit > 500:
            raise invalid_params("limit must be between 1 and 500")
        try:
            cursor = int(params.get("cursor", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise invalid_params("cursor must be an integer") from exc
        if cursor < 0:
            cursor = 0

        kwargs: dict[str, Any] = {"include_archived": include_archived}
        if kind_filter:
            kwargs["kinds"] = kind_filter
        memories = self.store.all(**kwargs)

        # Non-kind filters applied over the (bounded) active set.
        if search_query:
            nq = normalize_fa(str(search_query)).strip().lower()
            memories = [m for m in memories if nq in m.norm.lower()]
        if date_from is not None:
            try:
                memories = [m for m in memories if float(m.created_at) >= float(date_from)]
            except (TypeError, ValueError):
                pass
        if date_to is not None:
            try:
                memories = [m for m in memories if float(m.created_at) <= float(date_to)]
            except (TypeError, ValueError):
                pass
        if min_importance is not None:
            try:
                memories = [
                    m for m in memories if float(m.importance) >= float(min_importance)
                ]
            except (TypeError, ValueError):
                pass

        def _relevance(m: Memory) -> float:
            if not search_query:
                return 0.0
            q_tokens = set(normalize_fa(str(search_query)).split())
            if not q_tokens:
                return 0.0
            return len(q_tokens & set(m.norm.split())) / len(q_tokens)

        if sort_by == "relevance" and search_query:
            memories.sort(key=lambda m: (_relevance(m), m.created_at), reverse=True)
        elif sort_by == "date_oldest":
            memories.sort(key=lambda m: m.created_at)
        elif sort_by == "importance":
            memories.sort(key=lambda m: (m.importance, m.created_at), reverse=True)
        else:  # date_newest
            memories.sort(key=lambda m: m.created_at, reverse=True)

        total = len(memories)
        page = memories[cursor : cursor + limit]
        has_more = cursor + limit < total
        next_cursor = str(cursor + limit) if has_more else None
        return {
            "memories": [memory_to_dict(m) for m in page],
            "total": total,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    def memory_count(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Counts for dashboard badges, optionally scoped by kind_filter."""
        params = params or {}
        kind_filter = params.get("kind_filter")
        if kind_filter is not None and not isinstance(kind_filter, list):
            kind_filter = [kind_filter]
        if kind_filter and any(k not in KINDS for k in kind_filter):
            raise invalid_params(f"kind_filter must contain one of {KINDS}")
        kwargs: dict[str, Any] = {}
        if kind_filter:
            kwargs["kinds"] = kind_filter
        active = self.store.all(include_archived=False, **kwargs)
        by_kind = {k: 0 for k in KINDS}
        for m in active:
            if m.kind in by_kind:
                by_kind[m.kind] += 1
        all_rows = self.store.all(include_archived=True)
        archived = sum(1 for m in all_rows if m.archived)
        return {"total": len(active), "by_kind": by_kind, "archived": archived}

    def memory_create(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create a new memory (semantic/episodic/procedural) via manual entry."""
        params = params or {}
        content = params.get("content")
        if not isinstance(content, str) or not content.strip():
            raise invalid_params("content must be a non-empty string")
        if len(content.encode("utf-8")) > MAX_MEMORY_CONTENT_BYTES:
            raise invalid_params("memory content exceeds the 50KB limit")
        content = _sanitize_memory_text(content)
        kind = str(params.get("kind") or "semantic")
        if kind not in KINDS:
            raise invalid_params(f"kind must be one of {KINDS}")
        importance = params.get("importance", 0.5)
        try:
            importance = float(importance)
        except (TypeError, ValueError) as exc:
            raise invalid_params("importance must be a number") from exc
        if not 0.0 <= importance <= 1.0:
            raise invalid_params("importance must be between 0.0 and 1.0")
        tags = params.get("tags")
        if tags is not None and not isinstance(tags, list):
            raise invalid_params("tags must be a list")
        source = str(params.get("source") or "manual")
        try:
            memory = self.store.remember(
                content,
                kind=kind,
                tags=tags or None,
                importance=importance,
                source=source,
            )
        except ValueError as exc:
            raise invalid_params(str(exc)) from exc
        return {"memory": memory_to_dict(memory)}

    def memory_search(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        query = params.get("query")
        if not isinstance(query, str) or not query.strip():
            raise invalid_params("query must be a non-empty string")
        limit = int(params.get("limit", 8))
        kinds = params.get("kinds")
        if kinds is not None and not isinstance(kinds, list):
            raise invalid_params("kinds must be a list when provided")
        memories = [
            memory_to_dict(m) for m in self.store.recall(query, limit=limit, kinds=kinds)
        ]
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
            "skills": [
                skill_to_dict(s, enabled=s.name not in self._disabled_skills) for s in loaded
            ],
            "problems": [{"filename": p.filename, "detail": p.detail} for p in problems],
        }

    def skill_get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        skill_id = params.get("skill_id")
        query = params.get("query")
        skill = None
        if skill_id is not None:
            skill = self._resolve_skill(skill_id)
        elif query is not None:
            from dream import skills as skills_module

            skill = skills_module.find_skill(str(query), permissive=True)
        return {"match": skill_detail_to_dict(skill, self._disabled_skills)}

    def skill_install(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Install a skill — either structured fields or a pasted/imported body.

        ``content`` carries a full skill file (the paste/import path); when given
        it is parsed and its fields default the structured ones. ``overwrite``
        controls conflict behaviour: when a same-named skill exists and
        ``overwrite`` is false the call returns ``status: "conflict"`` (with the
        existing filename) instead of raising, so the UI can offer diff/overwrite/
        rename.
        """
        params = params or {}
        content = params.get("content")
        name = params.get("name")
        description = params.get("description")
        steps = params.get("steps")
        overwrite = bool(params.get("overwrite", False))

        if content is not None and not isinstance(content, str):
            raise invalid_params("content must be a string")
        if content is not None:
            if len(content.encode("utf-8")) > MAX_SKILL_CONTENT_BYTES:
                raise invalid_params("skill content exceeds the 100KB limit")
            try:
                parsed_name, parsed_desc, parsed_steps = parse_skill_text(content)
            except ValueError as exc:
                raise invalid_params(f"invalid skill file: {exc}") from exc
            name = name or parsed_name
            description = description or parsed_desc
            steps = steps or parsed_steps

        if not isinstance(name, str) or not name.strip():
            raise invalid_params("name must be a non-empty string")
        if not isinstance(description, str) or not description.strip():
            raise invalid_params("description must be a non-empty string")
        if not isinstance(steps, list) or not steps:
            raise invalid_params("steps must be a non-empty list")

        _validate_skill_safety(name, description, steps)

        from dream import skills as skills_module

        loaded, _ = skills_module.load_skills()
        existing = next((s for s in loaded if s.name == name.strip()), None)
        if existing is not None and not overwrite:
            return {
                "filename": existing.filename,
                "status": "conflict",
                "name": existing.name,
                "conflict": True,
                "existing_filename": existing.filename,
            }

        filename = skills_module.save_skill(name, description, steps)
        return {"filename": filename, "status": "installed", "name": name.strip()}

    def skill_remove(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        # Kept for backward compatibility; delegates to the id-based delete but
        # preserves the legacy ``removed`` key the old handler returned.
        result = self.skill_delete(params)
        return {"removed": result.get("deleted", False), "filename": result.get("filename")}

    def skill_delete(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        skill_id = params.get("skill_id") or params.get("name")
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise invalid_params("skill_id must be a non-empty string")
        skill = self._resolve_skill(skill_id)
        if skill is None:
            raise invalid_params(f"no skill matches {skill_id!r}")
        from dream.tools import _safe_path

        path = _safe_path(skill.filename)
        if not path.exists():
            raise invalid_params(f"no skill file for {skill.filename!r}")
        path.unlink()
        self._disabled_skills.discard(skill.name)
        self._save_disabled_skills()
        return {"deleted": True, "filename": skill.filename, "name": skill.name}

    def skill_enable(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        skill_id = params.get("skill_id") or params.get("name")
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise invalid_params("skill_id must be a non-empty string")
        skill = self._resolve_skill(skill_id)
        if skill is None:
            raise invalid_params(f"no skill matches {skill_id!r}")
        self._disabled_skills.discard(skill.name)
        self._save_disabled_skills()
        return {"name": skill.name, "filename": skill.filename, "enabled": True}

    def skill_disable(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        skill_id = params.get("skill_id") or params.get("name")
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise invalid_params("skill_id must be a non-empty string")
        skill = self._resolve_skill(skill_id)
        if skill is None:
            raise invalid_params(f"no skill matches {skill_id!r}")
        self._disabled_skills.add(skill.name)
        self._save_disabled_skills()
        return {"name": skill.name, "filename": skill.filename, "enabled": False}

    def skill_export(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        skill_id = params.get("skill_id") or params.get("name")
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise invalid_params("skill_id must be a non-empty string")
        skill = self._resolve_skill(skill_id)
        if skill is None:
            raise invalid_params(f"no skill matches {skill_id!r}")
        from dream import skills as skills_module

        content = skills_module.render_skill_text(
            skill.name, skill.description, list(skill.steps)
        )
        return {"name": skill.name, "filename": skill.filename, "content": content}

    # -- skill helpers ----------------------------------------------------- #

    def _resolve_skill(self, name_or_id: str) -> Any | None:
        """Resolve a skill from a filename, ``name``, or ``skills/name.txt`` id."""
        from dream import skills as skills_module

        raw = str(name_or_id).strip()
        cleaned = raw
        if cleaned.startswith("skills/"):
            cleaned = cleaned[len("skills/"):]
        if cleaned.endswith(SKILL_SUFFIX):
            cleaned = cleaned[: -len(SKILL_SUFFIX)]
        loaded, _ = skills_module.load_skills()
        for skill in loaded:
            if (
                skill.filename == raw
                or skill.name == raw
                or skill.name == cleaned
                or skill.filename == f"skills/{cleaned}{SKILL_SUFFIX}"
            ):
                return skill
        return skills_module.find_skill(raw, permissive=True)

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
        if registered.risk == "dangerous" and not bool(params.get("approved")):
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
        allowed = bool(params.get("allowed"))
        if not isinstance(approval_id, str) or not approval_id:
            raise invalid_params("approval_id must be a non-empty string")
        with self._lock:
            approval = self.approvals.get(approval_id)
            if approval is None:
                raise invalid_params(f"no pending approval with id {approval_id!r}")
            if approval.resolved:
                raise invalid_params(f"approval {approval_id!r} already resolved")
            approval.resolved = True
            name, arguments = approval.name, approval.arguments

        if not allowed:
            return {
                "blocked": True,
                "reason": "denied by user",
                "approval_id": approval_id,
            }

        from dream.tools import execute

        raw = execute(name, arguments, approved=True)
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {"status": "ok", "result": raw}

    def _register_approval(self, name: str, arguments: dict[str, Any], risk: str) -> ApprovalState:
        approval_id = f"appr_{uuid.uuid4().hex[:16]}"
        summary = _approval_summary(name, arguments)
        approval = ApprovalState(
            id=approval_id, name=name, arguments=dict(arguments), risk=risk, summary=summary
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

    @staticmethod
    def _provider_id(params: dict[str, Any] | None, *, default: str = "") -> str:
        params = params or {}
        provider_id = params.get("id") or params.get("provider") or default
        if isinstance(provider_id, dict):
            provider_id = provider_id.get("id")
        if not isinstance(provider_id, str) or not provider_id:
            raise invalid_params("provider id must be a non-empty string")
        return provider_id

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

    def _load_providers(self) -> tuple[dict[str, dict[str, Any]], str]:
        """Legacy helper retained for callers; registry owns loading now."""
        return self.provider_registry._providers, self.provider_registry.default_provider

    def _save_providers(self) -> None:
        self.provider_registry.default_provider = self._default_provider
        self.provider_registry._save()

    def _load_disabled_skills(self) -> set[str]:
        """Load the set of disabled skill names; missing/corrupt → empty set."""
        try:
            with open(self._disabled_skills_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return set()
        if isinstance(data, list):
            return {str(n) for n in data if n}
        if isinstance(data, dict) and isinstance(data.get("disabled"), list):
            return {str(n) for n in data["disabled"] if n}
        return set()

    def _save_disabled_skills(self) -> None:
        self._write_json(self._disabled_skills_path, sorted(self._disabled_skills))

    def _load_sessions_index(self) -> None:
        try:
            with open(self._sessions_path, encoding="utf-8") as handle:
                rows = json.load(handle)
        except (OSError, ValueError):
            return
        if not isinstance(rows, list):
            return
        # Reconstruct sessions with fresh agent history (history is not persisted
        # until P-03's session store; the metadata index survives restarts).
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            sid = str(row["id"])
            self.sessions[sid] = SessionState(
                id=sid,
                title=str(row.get("title", "New session")),
                created_at=float(row.get("created_at", time.time())),
                updated_at=float(row.get("updated_at", time.time())),
                message_count=int(row.get("message_count", 0)),
                provider=str(row.get("provider", self._default_provider)),
                model=str(row.get("model", "")),
                reasoning_effort=float(row.get("reasoning_effort", 0.0)),
                dream=self._new_dream(
                    row.get("provider"), row.get("model"), row.get("reasoning_effort", 0.0)
                ),
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
