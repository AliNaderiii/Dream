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
    "CODE_NAMES",
    "CONTEXT_OVERFLOW",
    "ERRORS",
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "ListLineReader",
    "METHOD_NOT_FOUND",
    "MemoryLineWriter",
    "PROTOCOL_HEADER",
    "PARSE_ERROR",
    "PROVIDER_ERROR",
    "RATE_LIMITED",
    "RESOURCE_EXHAUSTED",
    "SessionState",
    "StdinLineReader",
    "StdoutLineWriter",
    "Stream",
    "SubAgent",
    "SubAgentManager",
    "SubAgentSpec",
    "Schedule",
    "SchedulerDaemon",
    "TOOL_ERROR",
    "build_configured_backend",
    "error_from_code",
    "invalid_params",
    "is_async_generator",
    "memory_to_dict",
    "reminder_to_dict",
    "run_stdio",
    "serialise_error",
    "serve_forever",
    "skill_to_dict",
    "stream_chunks",
    "stream_text",
    "tokenise",
    "turn_to_dict",
    "__version__",
]
