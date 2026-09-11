"""Agent Client Protocol (ACP) Support for Dream.

Provides bidirectional agent communication: expose Dream as an ACP server, drive
external agents via ACP client, history replay, IDE diff tools, and ACP provider backends.
"""

from .backend import ACPBackend
from .client import ACPClient, ACPClientError
from .manager import ACPAgentManager
from .models import ACPAgentConfig, ACPMessage, ACPSession
from .server import ACPServer
from .slash import handle_acp_command
from .tools import (
    acp_apply_diff,
    acp_call_agent,
    acp_get_session_status,
    acp_list_agents,
    acp_read_diagnostics,
    get_acp_tools,
    get_global_acp_manager,
    get_global_acp_server,
    reset_global_acp,
)

__all__ = [
    "ACPAgentConfig",
    "ACPAgentManager",
    "ACPBackend",
    "ACPClient",
    "ACPClientError",
    "ACPMessage",
    "ACPServer",
    "ACPSession",
    "acp_apply_diff",
    "acp_call_agent",
    "acp_get_session_status",
    "acp_list_agents",
    "acp_read_diagnostics",
    "get_acp_tools",
    "get_global_acp_manager",
    "get_global_acp_server",
    "handle_acp_command",
    "reset_global_acp",
]

try:
    from dream.tools import toolsets

    if hasattr(toolsets, "register_toolset") and "acp" not in toolsets.BUILTIN_TOOLSETS:
        toolsets.register_toolset(
            "acp",
            [
                "acp_apply_diff",
                "acp_read_diagnostics",
                "acp_get_session_status",
                "acp_list_agents",
                "acp_call_agent",
            ],
            description="Agent Client Protocol (ACP) IDE integration and diff tools",
        )
except Exception:
    pass
