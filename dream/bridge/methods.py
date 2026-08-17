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
import logging
import os
import re
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from dream import scheduler
from dream.acp import (
    ACPAgentManager,
    ACPBackend,
    ACPServer,
)
from dream.agent import (
    ApprovalPolicy,
    Dream,
    EchoBackend,
    OllamaBackend,
    OpenAIBackend,
    build_backend,
)
from dream.mcp import (
    MCPServerConfig,
    MCPServerManager,
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
from dream.nl_schedule import ScheduleParseError
from dream.provenance import (
    ArtifactManager,
    ProvenanceTracker,
    ReproducibilityExporter,
)
from dream.scheduler import Schedule, run_to_dict, schedule_to_dict
from dream.skills import SKILL_SUFFIX, parse_skill_text
from dream.skills.data_science import (
    DataScienceError,
    DataScienceRuntime,
)
from dream.skills.notebooks import NotebookManager, NotebookUnavailableError
from dream.subagents import (
    DEFAULT_MAX_DURATION,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TURNS,
    SubAgent,
    SubAgentManager,
    SubAgentSpec,
    subagent_to_dict,
)

from .errors import APPROVAL_REQUIRED, RESOURCE_EXHAUSTED, BridgeError, invalid_params
from .streams import Chunk, Stream, stream_text, tokenise

logger = logging.getLogger(__name__)

#: Optional infrastructure imports — enabled lazily so the sidecar runs even
#: when Docker/Playwright/FastAPI are not installed.
try:  # pragma: no cover - import guard
    from dream.docker_sandbox import DockerSandbox, ResourceLimits
except ImportError:  # pragma: no cover
    DockerSandbox = None  # type: ignore[assignment,misc]
    ResourceLimits = None  # type: ignore[assignment,misc]

try:  # pragma: no cover - import guard
    from dream.browser_controller import (
        BrowserController,
        BrowserSecurityError,
        PageContent,
    )
except ImportError:  # pragma: no cover
    BrowserController = None  # type: ignore[assignment,misc]
    BrowserSecurityError = None  # type: ignore[assignment,misc]
    PageContent = None  # type: ignore[assignment,misc]

try:  # pragma: no cover - import guard
    from dream.gateway_server import TokenManager, TokenScope
except ImportError:  # pragma: no cover
    TokenManager = None  # type: ignore[assignment,misc]
    TokenScope = None  # type: ignore[assignment,misc]

#: Provider kinds the bridge knows how to build and persist.
PROVIDER_KINDS: tuple[str, ...] = ("echo", *PROVIDER_CATALOG.keys(), "acp")

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
    if kind == "acp":
        acp_endpoint = config.get("base_url") or config.get("endpoint") or "http://localhost:8000"
        acp_token = config.get("api_key") or config.get("token") or credential or None
        return ACPBackend(endpoint=acp_endpoint, token=acp_token)
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
    last_record_id: str | None = None

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
    #: ``None`` until a human answers. ``schedule.approve`` sets it, and the
    #: scheduler's gate waits on it.
    decision: bool | None = None


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
        sandbox: Any = None,
        browser: Any = None,
        token_manager: Any = None,
        provenance_dir: str | None = None,
        mcp_config_path: str | None = None,
        acp_config_path: str | None = None,
        data_runtime: Any = None,
        notebook_manager: Any = None,
    ) -> None:
        self.store = store or MemoryStore(os.environ.get("DREAM_DB", "data/dream.db"))
        self.sessions: dict[str, SessionState] = {}
        self.approvals: dict[str, ApprovalState] = {}
        #: Child agents live in their own asyncio Tasks with their own stores;
        #: the manager owns that isolation (see ``docs/architecture/subagents.md``).
        self.subagents = SubAgentManager()
        self._daemon: scheduler.SchedulerDaemon | None = None
        self._lock = threading.RLock()

        # Provenance, MCP, and ACP subsystems (P-10)
        self.provenance = ProvenanceTracker(log_dir=provenance_dir)
        self.artifacts = ArtifactManager(self.provenance)
        self.reproducibility = ReproducibilityExporter(self.provenance)
        self.mcp = MCPServerManager(config_path=mcp_config_path)
        self.acp_agents = ACPAgentManager(config_path=acp_config_path)
        self.acp_server = ACPServer(store=self.store)

        # Infrastructure services (P-08): Docker sandbox, browser control,
        # web gateway tokens. Lazily created so an unavailable dependency
        # degrades to a clear error instead of failing startup.
        if sandbox is not None:
            self.sandbox: Any = sandbox
        elif DockerSandbox is not None:
            self.sandbox = DockerSandbox()
        else:
            self.sandbox = None

        if browser is not None:
            self.browser: Any = browser
        elif BrowserController is not None:
            self.browser = BrowserController()
        else:
            self.browser = None

        if token_manager is not None:
            self.gateway_tokens: Any = token_manager
        elif TokenManager is not None:
            self.gateway_tokens = TokenManager()
        else:
            self.gateway_tokens = None

        # Data science pipeline (P-09): dataset registry + sandboxed executor
        # + notebook kernels. Created lazily unless injected (tests inject a
        # runtime wired to fakes).
        self._data_runtime: Any = data_runtime
        self._notebooks: Any = notebook_manager

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
        # The connectivity gateway (P-07) is created lazily on the first
        # gateway.* call; its loop thread is independent of the bridge loop.
        self._gateway: Any | None = None
        self._connectivity_config_path = os.environ.get(
            "DREAM_CONNECTIVITY_PATH", "data/connectivity.json"
        )
        scheduler.ensure_schedule_tables(self.store)
        self._load_sessions_index()

        #: The dispatcher reads this to route method → handler.
        self.handlers: dict[str, Callable[..., Any]] = self._build_handler_table()

    # -- lifecycle -------------------------------------------------------- #

    async def aclose(self) -> None:
        """Async half of shutdown: stop the daemon and the children, then close.

        Anything owning an asyncio Task has to be torn down while the loop is
        still running, which :meth:`shutdown` cannot do — the server calls this
        first and keeps :meth:`shutdown` as the synchronous fallback.
        """
        await self.stop_scheduler()
        await self._stop_gateway()
        try:
            await self.subagents.cancel_all()
        except Exception:  # pragma: no cover - teardown must never mask exit
            logger.exception("failed to cancel subagents during shutdown")
        self.shutdown()

    def shutdown(self) -> None:
        """Persist state and close the store. Safe to call more than once."""
        self._save_sessions_index()
        self._save_providers()
        self._save_disabled_skills()
        if self._notebooks is not None:
            try:
                self._notebooks.shutdown_all()
            except Exception:  # pragma: no cover - teardown must never mask exit
                logger.exception("notebook shutdown failed")
        try:
            self.store.close()
        except Exception:
            pass
        # Clean up infrastructure services.
        if self.browser is not None:
            try:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        loop.create_task(self._close_browser())
                except RuntimeError:
                    pass
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
            "subagent.pipeline": self.subagent_pipeline,
            "subagent.list": self.subagent_list,
            "subagent.get": self.subagent_get,
            "subagent.status": self.subagent_status,
            "subagent.cancel": self.subagent_cancel,
            "subagent.pause": self.subagent_pause,
            "subagent.resume": self.subagent_resume,
            "subagent.logs": self.subagent_logs,
            "schedule.create": self.schedule_create,
            "schedule.list": self.schedule_list,
            "schedule.get": self.schedule_get,
            "schedule.update": self.schedule_update,
            "schedule.delete": self.schedule_delete,
            "schedule.toggle": self.schedule_toggle,
            "schedule.history": self.schedule_history,
            "schedule.preview": self.schedule_preview,
            "schedule.run_now": self.schedule_run_now,
            "schedule.approve": self.schedule_approve,
            "gateway.start": self.gateway_start,
            "gateway.stop": self.gateway_stop,
            "gateway.status": self.gateway_status,
            "gateway.configure": self.gateway_configure,
            "gateway.logs": self.gateway_logs,
            "gateway.link_code": self.gateway_link_code,
            "gateway.linked_users": self.gateway_linked_users,
            "gateway.unlink_user": self.gateway_unlink_user,
            "gateway.platforms": self.gateway_platforms,
            "health.check": self.health_check,
            "sidecar.version": self.sidecar_version,
            # P-08: Docker sandbox.
            "sandbox.status": self.sandbox_status,
            "sandbox.run_code": self.sandbox_run_code,
            "sandbox.run_notebook": self.sandbox_run_notebook,
            "sandbox.install_packages": self.sandbox_install_packages,
            # P-08: Chrome browser control.
            "browser.attach": self.browser_attach,
            "browser.launch_isolated": self.browser_launch_isolated,
            "browser.request_approval": self.browser_request_approval,
            "browser.approve": self.browser_approve,
            "browser.deny": self.browser_deny,
            "browser.navigate": self.browser_navigate,
            "browser.get_content": self.browser_get_content,
            "browser.execute_js": self.browser_execute_js,
            "browser.fill_form": self.browser_fill_form,
            "browser.click": self.browser_click,
            "browser.screenshot": self.browser_screenshot,
            "browser.get_cookies": self.browser_get_cookies,
            "browser.status": self.browser_status,
            "browser.close": self.browser_close,
            # P-08: Web gateway tokens.
            "gateway.get_tokens": self.gateway_get_tokens,
            "gateway.create_token": self.gateway_create_token,
            "gateway.rotate_token": self.gateway_rotate_token,
            "gateway.revoke_token": self.gateway_revoke_token,
            # provenance.* (P-10)
            "provenance.list": self.provenance_list,
            "provenance.get": self.provenance_get,
            "provenance.tree": self.provenance_tree,
            "provenance.export": self.provenance_export,
            "provenance.verify": self.provenance_verify,
            # artifact.* (P-10)
            "artifact.get": self.artifact_get,
            "artifact.list": self.artifact_list,
            # mcp.* (P-10)
            "mcp.add_server": self.mcp_add_server,
            "mcp.remove_server": self.mcp_remove_server,
            "mcp.list_servers": self.mcp_list_servers,
            "mcp.get_server": self.mcp_get_server,
            "mcp.toggle_server": self.mcp_toggle_server,
            "mcp.toggle_tool": self.mcp_toggle_tool,
            "mcp.test_connection": self.mcp_test_connection,
            "mcp.list_tools": self.mcp_list_tools,
            "mcp.call_tool": self.mcp_call_tool,
            "mcp.list_resources": self.mcp_list_resources,
            "mcp.read_resource": self.mcp_read_resource,
            # acp.* (P-10)
            "acp.server.status": self.acp_server_status,
            "acp.server.start": self.acp_server_start,
            "acp.server.stop": self.acp_server_stop,
            "acp.client.list_agents": self.acp_client_list_agents,
            "acp.client.add_agent": self.acp_client_add_agent,
            "acp.client.remove_agent": self.acp_client_remove_agent,
            "acp.client.test_agent": self.acp_client_test_agent,
            "acp.client.send": self.acp_client_send,
            "acp.client.replay_history": self.acp_client_replay_history,
            # data.* — data science pipeline (P-09)
            "data.load_data": self.data_load_data,
            "data.profile_data": self.data_profile_data,
            "data.clean_data": self.data_clean_data,
            "data.analyze_data": self.data_analyze_data,
            "data.auto_chart": self.data_auto_chart,
            "data.create_chart": self.data_create_chart,
            "data.generate_report": self.data_generate_report,
            "data.get_report": self.data_get_report,
            "data.list_datasets": self.data_list_datasets,
            "data.get_dataset": self.data_get_dataset,
            "data.delete_dataset": self.data_delete_dataset,
            # notebook.* — Jupyter integration (P-09)
            "notebook.create": self.notebook_create,
            "notebook.execute": self.notebook_execute,
            "notebook.run_cell": self.notebook_run_cell,
            "notebook.read": self.notebook_read,
            "notebook.open_lab": self.notebook_open_lab,
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

        # Record provenance for session creation
        rec = self.provenance.record(
            event_type="session_create",
            agent_id=sid,
            payload={"title": title, "provider": provider, "model": model},
        )
        session.last_record_id = rec.record_id

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

        # Provenance: record user message
        user_rec = self.provenance.record(
            event_type="user_message",
            agent_id=session.id,
            parent_record_id=session.last_record_id,
            payload={"message": message},
        )
        session.last_record_id = user_rec.record_id

        turn_start = time.monotonic()

        def produce() -> Any:
            if cancellation.is_set():
                return None
            return dream.run(message)

        # Run the blocking turn in a worker thread, then chunk the reply text.
        result = await asyncio.to_thread(produce)
        turn_duration_ms = int((time.monotonic() - turn_start) * 1000)

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

        # Provenance: record tool calls
        parent_id = user_rec.record_id
        for call in turn_dict.get("tool_calls", []):
            tool_rec = self.provenance.record(
                event_type="tool_call",
                agent_id=session.id,
                parent_record_id=parent_id,
                payload={
                    "tool_name": call.get("name"),
                    "arguments": call.get("arguments"),
                    "allowed": call.get("allowed"),
                    "result": call.get("result"),
                },
                model_snapshot={"provider": session.provider},
            )
            parent_id = tool_rec.record_id

        # Provenance: record model response
        resp_rec = self.provenance.record(
            event_type="model_response",
            agent_id=session.id,
            parent_record_id=parent_id,
            payload={"reply": turn_dict["reply"]},
            duration_ms=turn_duration_ms,
            token_count=len(turn_dict["reply"].split()),
            model_snapshot={"provider": session.provider},
        )
        session.last_record_id = resp_rec.record_id

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

        # Provenance recording for standalone tool execution
        self.provenance.record(
            event_type="tool_call",
            agent_id="bridge",
            payload={"tool_name": name, "arguments": arguments, "result": decoded},
        )

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

        # Provenance: record approval event
        self.provenance.record(
            event_type="approval_granted" if allowed else "approval_denied",
            agent_id="bridge",
            payload={"approval_id": approval_id, "tool_name": name, "allowed": allowed},
        )

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

    def _require_subagent(self, params: dict[str, Any]) -> SubAgent:
        sub_id = params.get("subagent_id") or params.get("id")
        if not isinstance(sub_id, str) or not sub_id:
            raise invalid_params("subagent_id must be a non-empty string")
        agent = self.subagents.get(sub_id)
        if agent is None:
            raise invalid_params(f"no subagent with id {sub_id!r}")
        return agent

    def _spec_from_params(self, params: dict[str, Any]) -> SubAgentSpec:
        """Validate spawn params into a spec.

        ``message`` is accepted as an alias for ``prompt`` so the P-02 shape of
        this call keeps working for any client that has not been updated yet.
        """
        prompt = params.get("prompt")
        if prompt is None:
            prompt = params.get("message")
        if not isinstance(prompt, str) or not prompt.strip():
            raise invalid_params("prompt must be a non-empty string")

        tools = params.get("tools")
        if tools is not None:
            if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
                raise invalid_params("tools must be an array of strings")

        provider = str(params.get("provider") or params.get("model_provider") or "")
        provider = provider or self._default_provider
        config = self._providers.get(provider) or {}

        try:
            return SubAgentSpec(
                prompt=prompt,
                name=str(params.get("name") or ""),
                context=str(params.get("context") or ""),
                system_prompt=str(params.get("system_prompt") or ""),
                model_provider=provider,
                model_name=str(params.get("model_name") or config.get("model") or ""),
                tools=tools,
                max_turns=_positive_int(params, "max_turns", DEFAULT_MAX_TURNS),
                max_tokens=_positive_int(params, "max_tokens", DEFAULT_MAX_TOKENS),
                max_duration=_positive_float(params, "max_duration", DEFAULT_MAX_DURATION),
                parent_session_id=params.get("session_id") or params.get("parent_session_id"),
                allow_dangerous=bool(params.get("allow_dangerous", False)),
            )
        except ValueError as exc:
            raise invalid_params(str(exc)) from exc

    async def subagent_spawn(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        spec = self._spec_from_params(params)
        try:
            agent = self.subagents.spawn(spec)
        except ResourceWarning as exc:
            # The cap exists so one runaway parent cannot starve the sidecar.
            raise BridgeError(RESOURCE_EXHAUSTED, str(exc)) from exc
        return subagent_to_dict(agent, include_log=False)

    async def subagent_pipeline(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Spawn a chain in which each stage receives the previous result."""
        params = params or {}
        raw_stages = params.get("stages")
        if not isinstance(raw_stages, list) or not raw_stages:
            raise invalid_params("stages must be a non-empty array")
        shared = {k: v for k, v in params.items() if k not in {"stages", "name"}}
        specs: list[SubAgentSpec] = []
        for index, stage in enumerate(raw_stages):
            if not isinstance(stage, dict):
                raise invalid_params(f"stages[{index}] must be an object")
            specs.append(self._spec_from_params({**shared, **stage}))
        try:
            pipeline_id, agents = self.subagents.spawn_pipeline(
                specs, name=str(params.get("name") or "")
            )
        except ResourceWarning as exc:
            raise BridgeError(RESOURCE_EXHAUSTED, str(exc)) from exc
        except ValueError as exc:
            raise invalid_params(str(exc)) from exc
        return {
            "pipeline_id": pipeline_id,
            "subagents": [subagent_to_dict(a, include_log=False) for a in agents],
        }

    def subagent_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        agents = self.subagents.list()
        pipeline_id = params.get("pipeline_id")
        if isinstance(pipeline_id, str) and pipeline_id:
            agents = [a for a in agents if a.pipeline_id == pipeline_id]
        session_id = params.get("session_id")
        if isinstance(session_id, str) and session_id:
            agents = [a for a in agents if a.parent_session_id == session_id]
        return {
            "subagents": [subagent_to_dict(a, include_log=False) for a in agents],
            "active": self.subagents.active_count(),
        }

    def subagent_get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        agent = self._require_subagent(params or {})
        return subagent_to_dict(agent, include_log=True)

    #: ``subagent.status`` is the P-02 name for ``subagent.get``.
    def subagent_status(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.subagent_get(params)

    async def subagent_cancel(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        agent = self._require_subagent(params)
        grace = params.get("grace_seconds")
        cancelled = await self.subagents.cancel(
            agent.id, grace_seconds=float(grace) if grace is not None else None
        )
        payload = subagent_to_dict(cancelled or agent, include_log=False)
        payload["cancelled"] = True
        return payload

    def subagent_pause(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        agent = self._require_subagent(params or {})
        paused = self.subagents.pause(agent.id)
        if paused is None or paused.status != "paused":
            status = "gone" if paused is None else paused.status
            raise invalid_params(f"subagent {agent.id!r} is not running (status {status})")
        return subagent_to_dict(paused, include_log=False)

    def subagent_resume(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        agent = self._require_subagent(params or {})
        # ``resume`` is a no-op on anything that is not paused, so compare the
        # status we started from: a running child must not silently "resume".
        if agent.status != "paused":
            raise invalid_params(f"subagent {agent.id!r} is not paused (status {agent.status})")
        resumed = self.subagents.resume(agent.id)
        if resumed is None:
            raise invalid_params(f"no subagent with id {agent.id!r}")
        return subagent_to_dict(resumed, include_log=False)

    async def subagent_logs(self, params: dict[str, Any] | None = None) -> Stream:
        """Stream a subagent's log: history first, then live lines until it ends.

        Returning a :class:`Stream` makes each log line a ``stream.chunk``
        notification, so the dashboard renders output as it happens instead of
        polling for it.
        """
        agent = self._require_subagent(params or {})
        follow = self.subagents.follow_logs(agent.id)

        async def chunks() -> AsyncIterator[Chunk]:
            async for entry in follow:
                yield {"subagent_id": agent.id, "entry": entry, "token": entry["message"]}

        return Stream(final=subagent_to_dict(agent, include_log=False), chunks=chunks())

    # ------------------------------------------------------------------ #
    # schedule.*
    # ------------------------------------------------------------------ #

    def _require_schedule(self, params: dict[str, Any]) -> Schedule:
        schedule_id = params.get("schedule_id") or params.get("id")
        if not isinstance(schedule_id, str) or not schedule_id:
            raise invalid_params("schedule_id must be a non-empty string")
        schedule = scheduler.get_schedule(self.store, schedule_id)
        if schedule is None:
            raise invalid_params(f"no schedule with id {schedule_id!r}")
        return schedule

    def schedule_create(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise invalid_params("name must be a non-empty string")
        prompt = params.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise invalid_params("prompt must be a non-empty string")
        try:
            schedule = scheduler.create_schedule(
                self.store,
                name=name,
                prompt=prompt,
                description=str(params.get("description") or ""),
                cron_expression=params.get("cron_expression"),
                natural_language=params.get("natural_language"),
                session_id=params.get("session_id"),
                enabled=bool(params.get("enabled", True)),
                max_runs=params.get("max_runs"),
                require_approval=bool(params.get("require_approval", False)),
            )
        except (ScheduleParseError, ValueError) as exc:
            raise invalid_params(str(exc)) from exc
        return schedule_to_dict(schedule)

    def schedule_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        schedules = scheduler.list_schedules(
            self.store, include_disabled=bool(params.get("include_disabled", True))
        )
        return {"schedules": [schedule_to_dict(s) for s in schedules]}

    def schedule_get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        schedule = self._require_schedule(params or {})
        payload = schedule_to_dict(schedule)
        payload["runs"] = [
            run_to_dict(r) for r in scheduler.list_runs(self.store, schedule_id=schedule.id)
        ]
        return payload

    def schedule_update(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        schedule = self._require_schedule(params)
        fields = {
            key: params[key]
            for key in (
                "name",
                "description",
                "prompt",
                "cron_expression",
                "natural_language",
                "session_id",
                "enabled",
                "max_runs",
                "require_approval",
            )
            if key in params
        }
        try:
            updated = scheduler.update_schedule(self.store, schedule.id, **fields)
        except (ScheduleParseError, ValueError) as exc:
            raise invalid_params(str(exc)) from exc
        return schedule_to_dict(updated or schedule)

    def schedule_delete(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        schedule = self._require_schedule(params or {})
        deleted = scheduler.delete_schedule(self.store, schedule.id)
        return {"deleted": deleted, "schedule_id": schedule.id}

    def schedule_toggle(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        schedule = self._require_schedule(params)
        enabled = params.get("enabled")
        toggled = scheduler.toggle_schedule(
            self.store, schedule.id, enabled=None if enabled is None else bool(enabled)
        )
        return schedule_to_dict(toggled or schedule)

    def schedule_history(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        schedule_id = params.get("schedule_id") or params.get("id")
        if schedule_id is not None and not isinstance(schedule_id, str):
            raise invalid_params("schedule_id must be a string")
        if schedule_id:
            self._require_schedule(params)
        limit = _positive_int(params, "limit", 50)
        runs = scheduler.list_runs(self.store, schedule_id=schedule_id, limit=limit)
        return {"runs": [run_to_dict(r) for r in runs]}

    def schedule_preview(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Translate prose to cron for the add form's live preview.

        Never raises on unparseable input: the user is mid-sentence, and an
        error dialog per keystroke would be unusable.
        """
        params = params or {}
        return scheduler.preview_schedule(
            natural_language=params.get("natural_language") or params.get("text"),
            cron_expression=params.get("cron_expression"),
        )

    async def schedule_run_now(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        schedule = self._require_schedule(params or {})
        run = await self._scheduler_daemon().run_now(schedule)
        return {
            "schedule": schedule_to_dict(
                scheduler.get_schedule(self.store, schedule.id) or schedule
            ),
            "run": run_to_dict(run) if run else None,
        }

    # -- scheduler wiring -------------------------------------------------- #

    def _scheduler_daemon(self) -> scheduler.SchedulerDaemon:
        """The lazily-built daemon that executes schedules through Dream."""
        if self._daemon is None:
            self._daemon = scheduler.SchedulerDaemon(
                store=self.store,
                runner=self._run_schedule,
                approval_gate=self._schedule_approval_gate,
            )
        return self._daemon

    def start_scheduler(self) -> scheduler.SchedulerDaemon:
        """Begin polling. Called by the server once it has a running loop."""
        daemon = self._scheduler_daemon()
        daemon.start()
        return daemon

    async def stop_scheduler(self) -> None:
        if self._daemon is not None:
            await self._daemon.stop()

    async def _run_schedule(self, schedule: Schedule) -> str:
        """Execute a schedule's prompt, reusing its session or creating one."""
        session = self.sessions.get(schedule.session_id or "")
        if session is not None:
            dream = session.dream
        else:
            dream = self._new_dream(self._default_provider)
        turn = await asyncio.to_thread(dream.run, schedule.prompt)
        if session is not None:
            session.message_count += 1
            session.updated_at = time.time()
        return str(getattr(turn, "reply", "") or "")

    async def _schedule_approval_gate(self, schedule: Schedule) -> bool:
        """Register an approval and wait for a human to resolve it.

        The pending approval is what ``schedule.approve`` resolves; if nobody
        does, the daemon's timeout denies the run (fail-closed, gate G11).
        """
        approval = self._register_approval(
            "schedule.execute",
            {"schedule_id": schedule.id, "name": schedule.name, "prompt": schedule.prompt},
            "dangerous",
        )
        approval.decision = None
        while approval.decision is None:
            await asyncio.sleep(0.05)
        return bool(approval.decision)

    def schedule_approve(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Resolve a scheduled run's approval request."""
        params = params or {}
        approval_id = params.get("approval_id")
        if not isinstance(approval_id, str) or not approval_id:
            raise invalid_params("approval_id must be a non-empty string")
        with self._lock:
            approval = self.approvals.get(approval_id)
            if approval is None:
                raise invalid_params(f"no approval with id {approval_id!r}")
            approval.decision = bool(params.get("allowed", False))
            approval.resolved = True
        return {"approval_id": approval_id, "allowed": approval.decision}

    # ------------------------------------------------------------------ #
    # gateway.* — multi-platform connectivity (P-07, §3.11)
    # ------------------------------------------------------------------ #

    def _ensure_gateway(self) -> Any:
        """Lazily build the connectivity gateway and start its loop thread.

        The gateway owns its own asyncio event loop on a dedicated thread, so
        adapter websockets and webhook servers stay alive between RPC calls.
        """
        if self._gateway is None:
            from dream.connectivity.config import ConnectivityConfig
            from dream.connectivity.gateway import Gateway

            base_dir = os.path.dirname(os.path.abspath(self._connectivity_config_path))
            gateway = Gateway(
                ConnectivityConfig(self._connectivity_config_path),
                store=self.store,
                sessions_path=os.path.join(base_dir, "connectivity_sessions.json"),
                links_path=os.path.join(base_dir, "connectivity_links.json"),
                log_path=os.path.join(base_dir, "connectivity_log.jsonl"),
                dream_factory=lambda: self._new_dream(self._default_provider),
            )
            gateway.register_default_adapters()
            gateway.start_loop()
            self._gateway = gateway
        return self._gateway

    async def _stop_gateway(self) -> None:
        """Stop every adapter and tear down the gateway loop (best-effort)."""
        gateway = self._gateway
        if gateway is None:
            return
        try:
            await gateway.submit_async(gateway.stop_all())
        except Exception:
            logger.exception("failed to stop connectivity adapters during shutdown")
        try:
            gateway.stop_loop()
        except Exception:
            logger.exception("failed to stop the connectivity loop during shutdown")

    async def gateway_start(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start every enabled, configured platform adapter and web gateway."""
        params = params or {}
        if "port" in params or "tls" in params:
            # Web gateway startup (P-08)
            port = int(params.get("port", 9090))
            tls = bool(params.get("tls", False))
            try:
                from dream.gateway_server import run_gateway

                thread = threading.Thread(
                    target=run_gateway,
                    kwargs={"host": "0.0.0.0", "port": port, "tls": tls},
                    daemon=True,
                )
                thread.start()
                return {"started": True, "port": port, "tls": tls}
            except Exception as exc:
                raise BridgeError(-32016, f"Failed to start gateway: {exc}") from exc

        # Connectivity adapters (P-07)
        gateway = self._ensure_gateway()
        await gateway.submit_async(gateway.start_all())
        return gateway.status()

    async def gateway_stop(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Stop every platform adapter (the gateway loop stays up)."""
        del params
        gateway = self._ensure_gateway()
        await gateway.submit_async(gateway.stop_all())
        return gateway.status()

    def gateway_status(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Aggregate gateway status: connectivity adapters and web gateway tokens."""
        del params
        status: dict[str, Any] = {}
        try:
            status = self._ensure_gateway().status()
        except Exception:
            pass

        if self.gateway_tokens is not None:
            tokens = self.gateway_tokens.list_tokens()
            status.update(
                {
                    "enabled": True,
                    "token_count": len(tokens),
                    "tokens": tokens,
                    "has_setup_token": self.gateway_tokens.get_setup_token() is not None,
                }
            )
        return status

    async def gateway_configure(
        self, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Merge one platform's config (secrets stay on disk, redacted in reply)."""
        params = params or {}
        from dream.connectivity.platforms import PLATFORM_CATALOG

        platform = str(params.get("platform") or "")
        if platform not in PLATFORM_CATALOG:
            raise invalid_params(
                f"platform must be one of {', '.join(PLATFORM_CATALOG)}"
            )
        config = params.get("config")
        if not isinstance(config, dict):
            raise invalid_params("config must be an object")
        gateway = self._ensure_gateway()
        redacted = gateway.configure(platform, config)
        # Restart the adapter when its configuration changed under it.
        adapter = gateway.adapter(platform)
        if adapter is not None and adapter.is_running:
            try:
                await gateway.submit_async(gateway.stop_adapter(platform))
                await gateway.submit_async(gateway.start_adapter(platform))
            except ValueError as exc:
                logger.warning("gateway adapter %s restart skipped: %s", platform, exc)
        return {"saved": True, "platform": platform, "config": redacted}

    def gateway_logs(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Last-N message-log entries for one platform (all when omitted)."""
        params = params or {}
        platform = params.get("platform")
        if platform is not None and not isinstance(platform, str):
            raise invalid_params("platform must be a string")
        try:
            limit = int(params.get("limit", 100)) if params.get("limit") is not None else None
        except (TypeError, ValueError) as exc:
            raise invalid_params("limit must be an integer") from exc
        return self._ensure_gateway().logs(platform, limit)

    def gateway_link_code(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Issue a single-use, 10-minute link code for one platform."""
        params = params or {}
        platform = str(params.get("platform") or "")
        if not platform:
            raise invalid_params("platform must be a non-empty string")
        return self._ensure_gateway().link_code(platform)

    def gateway_linked_users(
        self, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Chat identities authorised to talk to the agent."""
        params = params or {}
        platform = params.get("platform")
        if platform is not None and not isinstance(platform, str):
            raise invalid_params("platform must be a string")
        return {"linked_users": self._ensure_gateway().linked_users(platform)}

    def gateway_unlink_user(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Revoke one identity's access on one platform."""
        params = params or {}
        platform = str(params.get("platform") or "")
        user_id = str(params.get("user_id") or "")
        if not platform or not user_id:
            raise invalid_params("platform and user_id must be non-empty strings")
        return self._ensure_gateway().unlink_user(platform, user_id)

    def gateway_platforms(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """The six-platform catalog joined with redacted public config."""
        del params
        return {"platforms": self._ensure_gateway().platforms()}

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
    # sandbox.* — Docker sandbox (P-08)
    # ------------------------------------------------------------------ #

    def _require_sandbox(self) -> Any:
        if self.sandbox is None:
            raise BridgeError(-32010, "Docker sandbox is not available. "
                                      "Install docker and the dream package with Docker support.")
        return self.sandbox

    def sandbox_status(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Check Docker availability and return sandbox status."""
        del params
        sb = self._require_sandbox()
        try:
            # Use asyncio to run the async check in a synchronous context.
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    fut = asyncio.run_coroutine_threadsafe(sb.check_docker(), loop)
                    return fut.result(timeout=10)
            except RuntimeError:
                pass
        except Exception as exc:
            return {"available": False, "error": str(exc)}
        return {"available": False, "error": "Could not check Docker status"}

    async def sandbox_run_code(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute code inside a Docker sandbox container."""
        params = params or {}
        sb = self._require_sandbox()
        code = params.get("code")
        if not isinstance(code, str) or not code.strip():
            raise invalid_params("code must be a non-empty string")
        language = params.get("language", "python")
        if language not in ("python", "r", "bash"):
            raise invalid_params("language must be one of: python, r, bash")

        # Build resource limits.
        limits = ResourceLimits() if ResourceLimits is not None else None
        if limits is not None and "resource_limits" in params:
            rl = params["resource_limits"]
            if isinstance(rl, dict):
                limits.cpu_count = float(rl.get("cpu_count", 1.0))
                limits.memory_mb = int(rl.get("memory_mb", 2048))
                limits.timeout_seconds = int(rl.get("timeout_seconds", 60))
                limits.network_enabled = bool(rl.get("network_enabled", False))

        workspace_path = None
        if params.get("workspace_path"):
            from pathlib import Path
            workspace_path = Path(str(params["workspace_path"]))

        mount_rw = bool(params.get("mount_workspace_read_write", False))
        timeout = params.get("timeout")

        result = await sb.run_code(
            code=code,
            language=language,
            workspace_path=workspace_path,
            resource_limits=limits,
            mount_workspace_read_write=mount_rw,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.return_code,
            "timed_out": result.timed_out,
            "output_files": result.output_files,
            "elapsed_seconds": result.elapsed_seconds,
            "error": result.error,
        }

    async def sandbox_run_notebook(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a Jupyter notebook inside the sandbox."""
        params = params or {}
        sb = self._require_sandbox()
        notebook_path = params.get("notebook_path")
        if not isinstance(notebook_path, str) or not notebook_path:
            raise invalid_params("notebook_path must be a non-empty string")
        kernel = params.get("kernel", "python3")
        if kernel not in ("python3", "ir"):
            raise invalid_params("kernel must be one of: python3, ir")
        timeout = int(params.get("timeout", 300))

        from pathlib import Path
        result = await sb.run_notebook(
            notebook_path=Path(notebook_path),
            kernel=kernel,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.return_code,
            "timed_out": result.timed_out,
            "output_files": result.output_files,
            "elapsed_seconds": result.elapsed_seconds,
            "error": result.error,
        }

    async def sandbox_install_packages(
        self, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Install packages in the sandbox image."""
        params = params or {}
        sb = self._require_sandbox()
        packages = params.get("packages")
        if not isinstance(packages, list) or not packages:
            raise invalid_params("packages must be a non-empty list of strings")
        language = params.get("language", "python")
        if language not in ("python", "r"):
            raise invalid_params("language must be one of: python, r")
        success = await sb.install_packages(packages, language=language)
        return {"success": success, "packages": packages, "language": language}

    # ------------------------------------------------------------------ #
    # browser.* — Chrome browser control (P-08)
    # ------------------------------------------------------------------ #

    def _require_browser(self) -> Any:
        if self.browser is None:
            raise BridgeError(-32011, "Browser controller is not available. "
                                      "Install it with: pip install playwright")
        return self.browser

    async def browser_attach(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Attach to the user's existing Chrome browser via CDP."""
        params = params or {}
        bc = self._require_browser()
        port = int(params.get("port", 9222))
        try:
            result = await bc.attach_existing_browser(port=port)
            return result
        except Exception as exc:
            raise BridgeError(-32012, f"Failed to attach Chrome: {exc}") from exc

    async def browser_launch_isolated(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Launch a fresh isolated Chrome instance."""
        del params
        bc = self._require_browser()
        try:
            result = await bc.launch_isolated_browser()
            return result
        except Exception as exc:
            raise BridgeError(-32012, f"Failed to launch Chrome: {exc}") from exc

    def browser_request_approval(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Request approval for a browser navigation."""
        params = params or {}
        bc = self._require_browser()
        url = params.get("url")
        purpose = params.get("purpose", "Web browsing")
        if not isinstance(url, str) or not url:
            raise invalid_params("url must be a non-empty string")
        session = bc.request_approval(url, purpose)
        return {
            "session_id": session.id,
            "url": session.url,
            "purpose": session.purpose,
            "domain": session.domain,
            "status": session.status,
        }

    def browser_approve(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Approve a pending browser navigation."""
        params = params or {}
        bc = self._require_browser()
        session_id = params.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise invalid_params("session_id must be a non-empty string")
        always_allow = bool(params.get("always_allow", False))
        session = bc.approve_session(session_id, always_allow=always_allow)
        if session is None:
            raise invalid_params(f"No pending session with id {session_id!r}")
        return {"approved": True, "session_id": session_id, "always_allow": always_allow}

    def browser_deny(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Deny a pending browser navigation."""
        params = params or {}
        bc = self._require_browser()
        session_id = params.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise invalid_params("session_id must be a non-empty string")
        session = bc.deny_session(session_id)
        if session is None:
            raise invalid_params(f"No pending session with id {session_id!r}")
        return {"denied": True, "session_id": session_id}

    async def browser_navigate(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Navigate to a URL and return page content."""
        params = params or {}
        bc = self._require_browser()
        url = params.get("url")
        if not isinstance(url, str) or not url:
            raise invalid_params("url must be a non-empty string")
        purpose = params.get("purpose", "Web browsing")
        wait_until = params.get("wait_until", "load")
        timeout = int(params.get("timeout", 30))

        try:
            # If the domain is not approved, this raises BrowserSecurityError
            # with enough info for the frontend to show an approval dialog.
            content = await bc.navigate(
                url, purpose=purpose, wait_until=wait_until, timeout=timeout
            )
            return {
                "url": content.url,
                "title": content.title,
                "text": content.text,
                "links": content.links,
                "tables": content.tables,
            }
        except BrowserSecurityError as exc:
            # Return the approval-required info for the frontend.
            # The browser controller has registered a pending session.
            status = bc.get_status()
            pending = status.get("current_session", {})
            raise BridgeError(
                -32013,
                str(exc),
                data={
                    "approval_required": True,
                    "url": url,
                    "session_id": pending.get("id") if pending else None,
                },
            ) from exc
        except Exception as exc:
            raise BridgeError(-32014, f"Navigation failed: {exc}") from exc

    async def browser_get_content(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get the content of the current page."""
        del params
        bc = self._require_browser()
        content = await bc.get_content()
        return {
            "url": content.url,
            "title": content.title,
            "text": content.text,
            "links": content.links,
            "tables": content.tables,
        }

    async def browser_execute_js(self, params: dict[str, Any] | None = None) -> Any:
        """Execute JavaScript in the current page."""
        params = params or {}
        bc = self._require_browser()
        script = params.get("script")
        if not isinstance(script, str) or not script:
            raise invalid_params("script must be a non-empty string")
        return await bc.execute_js(script)

    async def browser_fill_form(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fill a form field identified by CSS selector."""
        params = params or {}
        bc = self._require_browser()
        selector = params.get("selector")
        value = params.get("value")
        if not isinstance(selector, str) or not selector:
            raise invalid_params("selector must be a non-empty string")
        if not isinstance(value, str):
            raise invalid_params("value must be a string")
        await bc.fill_form(selector, value)
        return {"filled": True, "selector": selector}

    async def browser_click(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Click an element identified by CSS selector."""
        params = params or {}
        bc = self._require_browser()
        selector = params.get("selector")
        if not isinstance(selector, str) or not selector:
            raise invalid_params("selector must be a non-empty string")
        await bc.click(selector)
        return {"clicked": True, "selector": selector}

    async def browser_screenshot(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Take a screenshot of the current page."""
        params = params or {}
        bc = self._require_browser()
        path = params.get("path")
        screenshot_path = await bc.screenshot(path=path)
        return {"screenshot_path": str(screenshot_path)}

    async def browser_get_cookies(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get cookies from the current browser context."""
        del params
        bc = self._require_browser()
        cookies = await bc.get_cookies()
        return {"cookies": cookies}

    def browser_status(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get browser controller status."""
        del params
        bc = self._require_browser()
        return bc.get_status()

    async def browser_close(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Close the browser and clean up."""
        del params
        bc = self._require_browser()
        await bc.close()
        return {"closed": True}

    async def _close_browser(self) -> None:
        """Internal helper to close browser on shutdown."""
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # gateway.* — Web gateway tokens (P-08)
    # ------------------------------------------------------------------ #

    def _require_gateway_tokens(self) -> Any:
        if self.gateway_tokens is None:
            raise BridgeError(-32015, "Gateway token manager is not available.")
        return self.gateway_tokens

    def gateway_get_tokens(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get all tokens (with full values for display)."""
        del params
        tm = self._require_gateway_tokens()
        tokens = tm.all_tokens()
        return {"tokens": tokens}

    def gateway_create_token(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create a new gateway token."""
        params = params or {}
        tm = self._require_gateway_tokens()
        scope_str = params.get("scope", "write")
        label = params.get("label", "New Token")
        scope = TokenScope.WRITE if scope_str == "write" else TokenScope.READ
        token = tm.create_token(scope=scope, label=label)
        return {"token": token, "scope": scope.value, "label": label}

    def gateway_rotate_token(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Rotate (regenerate) a gateway token."""
        params = params or {}
        tm = self._require_gateway_tokens()
        token = params.get("token")
        if not isinstance(token, str) or not token:
            raise invalid_params("token must be a non-empty string")
        new_token = tm.rotate_token(token)
        if new_token is None:
            raise invalid_params("Token not found")
        return {"token": new_token, "rotated": True}

    def gateway_revoke_token(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Revoke a gateway token."""
        params = params or {}
        tm = self._require_gateway_tokens()
        token = params.get("token")
        if not isinstance(token, str) or not token:
            raise invalid_params("token must be a non-empty string")
        revoked = tm.revoke_token(token)
        if not revoked:
            # Try matching by prefix.
            for t in list(tm.all_tokens().keys()):
                if t.startswith(token):
                    tm.revoke_token(t)
                    revoked = True
                    break
        return {"revoked": revoked}

    # ------------------------------------------------------------------ #
    # provenance.* (P-10)
    # ------------------------------------------------------------------ #

    def provenance_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        agent_id = params.get("agent_id") or params.get("session_id")
        event_type = params.get("event_type")
        search = params.get("search")
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))

        records, total = self.provenance.list_records(
            agent_id=str(agent_id) if agent_id else None,
            event_type=str(event_type) if event_type else None,
            search=str(search) if search else None,
            date_from=str(date_from) if date_from else None,
            date_to=str(date_to) if date_to else None,
            limit=limit,
            offset=offset,
        )
        return {"records": [r.to_dict() for r in records], "total": total}

    def provenance_get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        record_id = params.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise invalid_params("record_id must be a non-empty string")
        rec = self.provenance.get(record_id)
        if not rec:
            raise invalid_params(f"Provenance record {record_id} not found")
        return rec.to_dict()

    def provenance_tree(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        record_id = params.get("record_id")
        agent_id = params.get("agent_id") or params.get("session_id")
        artifact_path = params.get("artifact_path")
        return self.provenance.get_tree(
            record_id=str(record_id) if record_id else None,
            agent_id=str(agent_id) if agent_id else None,
            artifact_path=str(artifact_path) if artifact_path else None,
        )

    def provenance_export(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        record_id = params.get("record_id")
        session_id = params.get("session_id") or params.get("agent_id")
        artifact_path = params.get("artifact_path")
        output_file = params.get("output_file")
        return self.reproducibility.export(
            record_id=str(record_id) if record_id else None,
            session_id=str(session_id) if session_id else None,
            artifact_path=str(artifact_path) if artifact_path else None,
            output_file=str(output_file) if output_file else None,
        )

    def provenance_verify(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        return self.provenance.verify_chain()

    # ------------------------------------------------------------------ #
    # artifact.* (P-10)
    # ------------------------------------------------------------------ #

    def artifact_get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        path = params.get("path")
        if not isinstance(path, str) or not path:
            raise invalid_params("path must be a non-empty string")
        art = self.artifacts.get_artifact(path)
        if not art:
            raise invalid_params(f"Artifact {path} not found")
        return art

    def artifact_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        return {"artifacts": self.artifacts.list_artifacts()}

    # ------------------------------------------------------------------ #
    # mcp.* (P-10)
    # ------------------------------------------------------------------ #

    def mcp_add_server(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        name = params.get("name")
        server_type = params.get("type", "stdio")
        if not isinstance(name, str) or not name.strip():
            raise invalid_params("name must be a non-empty string")
        if server_type not in ("stdio", "sse", "ws"):
            raise invalid_params("type must be one of stdio, sse, ws")

        cfg = self.mcp.add_server(
            name=name.strip(),
            type=server_type,
            command=params.get("command"),
            args=params.get("args") or [],
            env=params.get("env") or {},
            url=params.get("url"),
            headers=params.get("headers") or {},
            enabled=bool(params.get("enabled", True)),
        )
        return cfg.to_dict()

    def mcp_remove_server(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        server_id = params.get("server_id")
        if not isinstance(server_id, str) or not server_id:
            raise invalid_params("server_id must be a non-empty string")
        removed = self.mcp.remove_server(server_id)
        return {"removed": removed, "server_id": server_id}

    def mcp_list_servers(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        return {"servers": self.mcp.list_servers()}

    def mcp_get_server(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        server_id = params.get("server_id")
        if not isinstance(server_id, str) or not server_id:
            raise invalid_params("server_id must be a non-empty string")
        for s in self.mcp.list_servers():
            if s["id"] == server_id:
                return s
        raise invalid_params(f"MCP server {server_id} not found")

    def mcp_toggle_server(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        server_id = params.get("server_id")
        enabled = bool(params.get("enabled", True))
        if not isinstance(server_id, str) or not server_id:
            raise invalid_params("server_id must be a non-empty string")
        cfg = self.mcp.toggle_server(server_id, enabled)
        if not cfg:
            raise invalid_params(f"MCP server {server_id} not found")
        return cfg.to_dict()

    def mcp_toggle_tool(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        server_id = params.get("server_id")
        tool_name = params.get("tool_name")
        enabled = bool(params.get("enabled", True))
        if not isinstance(server_id, str) or not isinstance(tool_name, str):
            raise invalid_params("server_id and tool_name must be non-empty strings")
        saved = self.mcp.toggle_tool(server_id, tool_name, enabled)
        return {
            "saved": saved,
            "server_id": server_id,
            "tool_name": tool_name,
            "enabled": enabled,
        }

    async def mcp_test_connection(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        server_id = params.get("server_id")
        if server_id:
            return await self.mcp.test_connection(str(server_id))
        if "type" in params:
            cfg = MCPServerConfig.from_dict(params)
            return await self.mcp.test_connection(cfg)
        raise invalid_params("Must provide server_id or server config parameters")

    async def mcp_list_tools(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        server_id = params.get("server_id")
        if server_id:
            client = await self.mcp.ensure_connected(str(server_id))
            tools = await client.list_tools()
            return {"tools": [t.to_dict() for t in tools]}
        tools = await self.mcp.list_all_tools()
        return {"tools": [t.to_dict() for t in tools]}

    async def mcp_call_tool(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        tool_name = params.get("tool_name") or params.get("name")
        arguments = params.get("arguments", {})
        server_id = params.get("server_id")
        if not isinstance(tool_name, str) or not tool_name:
            raise invalid_params("tool_name must be a non-empty string")
        result = await self.mcp.call_tool(
            tool_name, arguments, server_id=str(server_id) if server_id else None
        )
        return {"status": "ok", "result": result}

    async def mcp_list_resources(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        server_id = params.get("server_id")
        if server_id:
            client = await self.mcp.ensure_connected(str(server_id))
            resources = await client.list_resources()
            return {"resources": [r.to_dict() for r in resources]}
        resources = await self.mcp.list_all_resources()
        return {"resources": [r.to_dict() for r in resources]}

    async def mcp_read_resource(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        uri = params.get("uri")
        server_id = params.get("server_id")
        if not isinstance(uri, str) or not uri:
            raise invalid_params("uri must be a non-empty string")
        content = await self.mcp.read_resource(
            uri, server_id=str(server_id) if server_id else None
        )
        return {"uri": uri, "content": content}

    # ------------------------------------------------------------------ #
    # acp.* (P-10)
    # ------------------------------------------------------------------ #

    def acp_server_status(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        return {
            "status": "ready",
            "token_configured": bool(self.acp_server.token),
            "protocol": "acp/1.0",
        }

    def acp_server_start(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        token = params.get("token")
        if token is not None:
            self.acp_server.token = str(token)
        return {"started": True, "token_configured": bool(self.acp_server.token)}

    def acp_server_stop(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        return {"stopped": True}

    def acp_client_list_agents(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        del params
        return {"agents": self.acp_agents.list_agents()}

    def acp_client_add_agent(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        name = params.get("name")
        endpoint = params.get("endpoint")
        if not isinstance(name, str) or not isinstance(endpoint, str):
            raise invalid_params("name and endpoint must be non-empty strings")
        cfg = self.acp_agents.add_agent(
            name=name,
            endpoint=endpoint,
            token=params.get("token"),
            label=params.get("label") or name,
            description=params.get("description") or "",
            enabled=bool(params.get("enabled", True)),
        )
        return cfg.to_dict()

    def acp_client_remove_agent(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        agent_id = params.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            raise invalid_params("agent_id must be a non-empty string")
        removed = self.acp_agents.remove_agent(agent_id)
        return {"removed": removed, "agent_id": agent_id}

    async def acp_client_test_agent(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        agent_id = params.get("agent_id")
        if agent_id:
            return await self.acp_agents.test_agent(str(agent_id))
        endpoint = params.get("endpoint")
        if endpoint:
            from dream.acp.models import ACPAgentConfig

            cfg = ACPAgentConfig(
                id="temp", name="Probe", endpoint=str(endpoint), token=params.get("token")
            )
            return await self.acp_agents.test_agent(cfg)
        raise invalid_params("Must provide agent_id or endpoint")

    async def acp_client_send(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        agent_id = params.get("agent_id")
        message = params.get("message")
        session_id = params.get("session_id") or "default"
        if not isinstance(agent_id, str) or not isinstance(message, str):
            raise invalid_params("agent_id and message are required strings")

        client = self.acp_agents.get_client(agent_id)
        if not client:
            raise invalid_params(f"ACP agent {agent_id} not found")

        res = await client.send_message(session_id, message)
        return res

    async def acp_client_replay_history(
        self, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        params = params or {}
        agent_id = params.get("agent_id")
        messages = params.get("messages", [])
        session_id = params.get("session_id") or "replayed_session"
        instruction = params.get("instruction") or "Review this conversation history."
        if not isinstance(agent_id, str):
            raise invalid_params("agent_id must be a string")

        client = self.acp_agents.get_client(agent_id)
        if not client:
            raise invalid_params(f"ACP agent {agent_id} not found")

        res = await client.replay_history(session_id, messages, instruction=instruction)
        return res

    # ------------------------------------------------------------------ #
    # data.* — data science pipeline (P-09)
    # ------------------------------------------------------------------ #

    def _require_data(self) -> Any:
        """Lazily create the data-science runtime (sandboxed executor)."""
        if self._data_runtime is None:
            self._data_runtime = DataScienceRuntime()
        return self._data_runtime

    def _require_notebooks(self) -> Any:
        if self._notebooks is None:
            runtime = self._require_data()
            self._notebooks = NotebookManager(runtime.datasets.root)
        return self._notebooks

    @staticmethod
    def _dataset_id(params: dict[str, Any]) -> str:
        dataset_id = params.get("dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise invalid_params("dataset_id must be a non-empty string")
        return dataset_id.strip()

    async def _data_call(self, fn: Any, *args: Any) -> Any:
        """Run a runtime call in a worker thread, mapping validation errors."""
        try:
            return await asyncio.to_thread(fn, *args)
        except DataScienceError as exc:
            raise invalid_params(str(exc)) from exc

    async def data_load_data(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ingest a data file and register it as a dataset."""
        params = params or {}
        file_path = params.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            raise invalid_params("file_path must be a non-empty string")
        name = params.get("name")
        if name is not None and not isinstance(name, str):
            raise invalid_params("name must be a string")
        runtime = self._require_data()
        return await self._data_call(runtime.load_data, file_path, name)

    async def data_profile_data(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Per-column + summary statistics for a dataset."""
        params = params or {}
        max_categories = _positive_int(params, "max_categories", 20)
        runtime = self._require_data()
        return await self._data_call(
            runtime.profile_data, self._dataset_id(params), max_categories
        )

    async def data_clean_data(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Apply a validated pipeline of cleaning operations."""
        params = params or {}
        operations = params.get("operations")
        if not isinstance(operations, list) or not operations:
            raise invalid_params("operations must be a non-empty list")
        runtime = self._require_data()
        return await self._data_call(
            runtime.clean_data, self._dataset_id(params), operations
        )

    async def data_analyze_data(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run statistical analyses on a dataset."""
        params = params or {}
        analyses = params.get("analyses")
        if not isinstance(analyses, list) or not analyses:
            raise invalid_params("analyses must be a non-empty list")
        runtime = self._require_data()
        return await self._data_call(
            runtime.analyze_data, self._dataset_id(params), analyses
        )

    async def data_auto_chart(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Rank chart suggestions for a dataset."""
        params = params or {}
        max_charts = _positive_int(params, "max_charts", 6)
        runtime = self._require_data()
        return await self._data_call(
            runtime.auto_chart, self._dataset_id(params), max_charts
        )

    async def data_create_chart(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render a chart from a ChartSpec (png/svg/pdf/html)."""
        params = params or {}
        chart_spec = params.get("chart_spec")
        if not isinstance(chart_spec, dict):
            raise invalid_params("chart_spec must be an object")
        runtime = self._require_data()
        return await self._data_call(runtime.create_chart, chart_spec)

    async def data_generate_report(
        self, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Produce report.pdf + report.md for a dataset."""
        params = params or {}
        title = params.get("title")
        if not isinstance(title, str) or not title.strip():
            raise invalid_params("title must be a non-empty string")
        sections = params.get("sections")
        if sections is not None and not isinstance(sections, list):
            raise invalid_params("sections must be a list")
        runtime = self._require_data()
        return await self._data_call(
            runtime.generate_report, self._dataset_id(params), title, sections
        )

    async def data_get_report(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return the generated markdown report, if any."""
        params = params or {}
        runtime = self._require_data()
        markdown = await self._data_call(
            runtime.read_markdown_report, self._dataset_id(params)
        )
        return {"dataset_id": params.get("dataset_id"), "markdown": markdown}

    def data_list_datasets(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """List registered datasets, newest first."""
        del params
        runtime = self._require_data()
        return {"datasets": runtime.list_datasets()}

    def data_get_dataset(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return one dataset's registry record."""
        params = params or {}
        runtime = self._require_data()
        try:
            record = runtime.datasets.get(self._dataset_id(params))
        except DataScienceError as exc:
            raise invalid_params(str(exc)) from exc
        return record.to_dict()

    def data_delete_dataset(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Delete a dataset and its derived files."""
        params = params or {}
        runtime = self._require_data()
        dataset_id = self._dataset_id(params)
        try:
            deleted = runtime.delete_dataset(dataset_id)
        except DataScienceError as exc:
            raise invalid_params(str(exc)) from exc
        if self._notebooks is not None:
            self._notebooks.shutdown_kernel(dataset_id)
        return {"deleted": deleted, "dataset_id": dataset_id}

    # ------------------------------------------------------------------ #
    # notebook.* — Jupyter integration (P-09)
    # ------------------------------------------------------------------ #

    async def notebook_create(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create an .ipynb under the dataset's notebooks directory."""
        params = params or {}
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise invalid_params("name must be a non-empty string")
        cells = params.get("cells") or []
        if not isinstance(cells, list):
            raise invalid_params("cells must be a list")
        notebooks = self._require_notebooks()
        try:
            return await asyncio.to_thread(
                notebooks.create_notebook, self._dataset_id(params), name, cells
            )
        except (ValueError, PermissionError) as exc:
            raise invalid_params(str(exc)) from exc

    async def notebook_execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute every code cell of a notebook on its dataset kernel."""
        params = params or {}
        path = params.get("path")
        if not isinstance(path, str) or not path.strip():
            raise invalid_params("path must be a non-empty string")
        kernel_id = params.get("kernel_id")
        if kernel_id is not None and not isinstance(kernel_id, str):
            raise invalid_params("kernel_id must be a string")
        notebooks = self._require_notebooks()
        try:
            return await asyncio.to_thread(notebooks.execute_notebook, path, kernel_id)
        except NotebookUnavailableError as exc:
            raise BridgeError(-32012, str(exc)) from exc
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            raise invalid_params(str(exc)) from exc

    async def notebook_run_cell(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute one cell of a notebook by index."""
        params = params or {}
        path = params.get("path")
        if not isinstance(path, str) or not path.strip():
            raise invalid_params("path must be a non-empty string")
        cell_index = params.get("cell_index")
        if not isinstance(cell_index, int) or isinstance(cell_index, bool) or cell_index < 0:
            raise invalid_params("cell_index must be a non-negative integer")
        notebooks = self._require_notebooks()
        try:
            return await asyncio.to_thread(notebooks.run_cell, path, cell_index)
        except NotebookUnavailableError as exc:
            raise BridgeError(-32012, str(exc)) from exc
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            raise invalid_params(str(exc)) from exc

    async def notebook_read(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a notebook's cells + summarised outputs."""
        params = params or {}
        path = params.get("path")
        if not isinstance(path, str) or not path.strip():
            raise invalid_params("path must be a non-empty string")
        notebooks = self._require_notebooks()
        try:
            return await asyncio.to_thread(notebooks.read_notebook, path)
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            raise invalid_params(str(exc)) from exc

    async def notebook_open_lab(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Spawn (or reuse) JupyterLab and return the notebook's URL."""
        params = params or {}
        path = params.get("path")
        if not isinstance(path, str) or not path.strip():
            raise invalid_params("path must be a non-empty string")
        notebooks = self._require_notebooks()
        try:
            return await asyncio.to_thread(notebooks.open_jupyterlab, path)
        except NotebookUnavailableError as exc:
            raise BridgeError(-32012, str(exc)) from exc
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            raise invalid_params(str(exc)) from exc

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


def _positive_int(params: dict[str, Any], key: str, default: int) -> int:
    """Read an optional positive integer parameter."""
    value = params.get(key)
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise invalid_params(f"{key} must be an integer") from exc
    if number < 1:
        raise invalid_params(f"{key} must be at least 1")
    return number


def _positive_float(params: dict[str, Any], key: str, default: float) -> float:
    """Read an optional positive float parameter."""
    value = params.get(key)
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise invalid_params(f"{key} must be a number") from exc
    if number <= 0:
        raise invalid_params(f"{key} must be greater than 0")
    return number


__all__ = [
    "PROVIDER_KINDS",
    "BridgeMethods",
    "SessionState",
    "ApprovalState",
    "build_configured_backend",
    "memory_to_dict",
    "turn_to_dict",
    "skill_to_dict",
    "reminder_to_dict",
]
