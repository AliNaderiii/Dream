"""Model Context Protocol (MCP) Integration for Dream.

Provides MCP client connections (stdio, SSE, WebSocket), tool discovery, resource
access, and persistent server management.
"""

from .client import MCPClient
from .manager import MCPServerManager
from .models import MCPPrompt, MCPResource, MCPServerConfig, MCPTool
from .transport import InMemoryTransport, MCPTransport, SSETransport, StdioTransport

__all__ = [
    "InMemoryTransport",
    "MCPClient",
    "MCPPrompt",
    "MCPResource",
    "MCPServerConfig",
    "MCPServerManager",
    "MCPTool",
    "MCPTransport",
    "SSETransport",
    "StdioTransport",
]
