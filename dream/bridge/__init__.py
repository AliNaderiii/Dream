"""Dream bridge: a JSON-RPC 2.0 sidecar over stdio.

This package is a new layer *above* the existing ``dream/`` core. It does not
modify any core public API, so the existing test suite stays green. The public
surface mirrors the protocol in ``docs/bridge/protocol.md``.

Run the sidecar with either::

    dream --bridge
    python -m dream.bridge
"""

from __future__ import annotations

__version__ = "0.1.0"

from dream.bridge.errors import (
    APPROVAL_REQUIRED,
    AUTH_ERROR,
    CODE_NAMES,
    CONTEXT_OVERFLOW,
    ERRORS,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROVIDER_ERROR,
    RATE_LIMITED,
    RESOURCE_EXHAUSTED,
    TOOL_ERROR,
    BridgeError,
    error_from_code,
    invalid_params,
    serialise_error,
)
from dream.bridge.methods import (
    ApprovalState,
    BridgeMethods,
    SessionState,
    build_configured_backend,
    memory_to_dict,
    reminder_to_dict,
    skill_to_dict,
    turn_to_dict,
)

try:  # pragma: no cover - optional infrastructure
    from dream.browser_controller import (
        BrowserController,
        BrowserSecurityError,
        BrowserSession,
        BrowserTimeoutError,
        BrowserUnavailableError,
        PageContent,
    )
except ImportError:  # pragma: no cover
    pass

try:  # pragma: no cover - optional infrastructure
    from dream.docker_sandbox import (
        DockerSandbox,
        DockerUnavailableError,
        Language,
        ResourceLimits,
        SandboxResult,
    )
except ImportError:  # pragma: no cover
    pass

try:  # pragma: no cover - optional infrastructure
    from dream.gateway_server import (
        MDNSAdvertiser,
        TLSCertificateManager,
        TokenManager,
        TokenScope,
        gateway_config,
        run_gateway,
        token_manager,
    )
except ImportError:  # pragma: no cover
    pass
from dream.bridge.server import (
    PROTOCOL_HEADER,
    BridgeServer,
    ListLineReader,
    MemoryLineWriter,
    StdinLineReader,
    StdoutLineWriter,
    run_stdio,
    serve_forever,
)
from dream.bridge.streams import (
    Stream,
    is_async_generator,
    stream_chunks,
    stream_text,
    tokenise,
)
from dream.scheduler import Schedule, SchedulerDaemon
from dream.subagents import SubAgent, SubAgentManager, SubAgentSpec

__all__ = [
    "APPROVAL_REQUIRED",
    "ApprovalState",
    "AUTH_ERROR",
    "BridgeError",
    "BridgeMethods",
    "BridgeServer",
    "BrowserController",
    "BrowserSecurityError",
    "BrowserSession",
    "BrowserTimeoutError",
    "BrowserUnavailableError",
    "CODE_NAMES",
    "CONTEXT_OVERFLOW",
    "DockerSandbox",
    "DockerUnavailableError",
    "ERRORS",
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "Language",
    "ListLineReader",
    "MDNSAdvertiser",
    "METHOD_NOT_FOUND",
    "MemoryLineWriter",
    "PageContent",
    "PROTOCOL_HEADER",
    "PARSE_ERROR",
    "PROVIDER_ERROR",
    "RATE_LIMITED",
    "RESOURCE_EXHAUSTED",
    "ResourceLimits",
    "SandboxResult",
    "SessionState",
    "StdinLineReader",
    "StdoutLineWriter",
    "Stream",
    "SubAgent",
    "SubAgentManager",
    "SubAgentSpec",
    "Schedule",
    "SchedulerDaemon",
    "TLSCertificateManager",
    "TOOL_ERROR",
    "TokenManager",
    "TokenScope",
    "build_configured_backend",
    "error_from_code",
    "gateway_config",
    "invalid_params",
    "is_async_generator",
    "memory_to_dict",
    "reminder_to_dict",
    "run_gateway",
    "run_stdio",
    "serialise_error",
    "serve_forever",
    "skill_to_dict",
    "stream_chunks",
    "stream_text",
    "token_manager",
    "tokenise",
    "turn_to_dict",
    "__version__",
]
