"""Agent Client Protocol (ACP) Support for Dream.

Provides bidirectional agent communication: expose Dream as an ACP server, drive
external agents via ACP client, history replay, and ACP provider backends.
"""

from .backend import ACPBackend
from .client import ACPClient, ACPClientError
from .manager import ACPAgentManager
from .models import ACPAgentConfig, ACPMessage, ACPSession
from .server import ACPServer

__all__ = [
    "ACPAgentConfig",
    "ACPBackend",
    "ACPClient",
    "ACPClientError",
    "ACPAgentManager",
    "ACPMessage",
    "ACPServer",
    "ACPSession",
]
