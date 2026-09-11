"""Model Context Protocol (MCP) Integration for Dream.

Provides MCP client connections (stdio, SSE, WebSocket), tool discovery, resource
access, dynamic tool registry synchronization, and persistent server management.
"""

from .client import MCPClient
from .manager import MCPServerManager
from .models import MCPPrompt, MCPResource, MCPServerConfig, MCPTool
from .slash import handle_mcp_command
from .sync import sync_mcp_tools_to_registry
from .tools import (
    get_mcp_manager,
    mcp_call_tool,
    mcp_list_servers,
    mcp_list_tools,
    mcp_read_resource,
    mcp_reload,
    reset_mcp_manager,
)
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
    "get_mcp_manager",
    "handle_mcp_command",
    "mcp_call_tool",
    "mcp_list_servers",
    "mcp_list_tools",
    "mcp_read_resource",
    "mcp_reload",
    "reset_mcp_manager",
    "sync_mcp_tools_to_registry",
]
