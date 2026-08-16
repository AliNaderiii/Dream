"""Transports for Model Context Protocol (MCP) communication: stdio, SSE, and WebSocket."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from .models import MCPServerConfig

MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPTransportError(Exception):
    """Raised when an MCP transport error occurs."""


class MCPTransport(ABC):
    """Abstract base transport for sending JSON-RPC 2.0 messages to an MCP server."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish transport connection and complete MCP initialization."""

    @abstractmethod
    async def close(self) -> None:
        """Close connection and clean up resources."""

    @abstractmethod
    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC request and return its result."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the transport is currently connected and active."""


class StdioTransport(MCPTransport):
    """Transports MCP messages to a child process via standard input and output."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._read_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._process is not None and self._process.returncode is None

    async def connect(self) -> bool:
        if self.is_connected:
            return True

        cmd = self.config.command
        if not cmd:
            raise MCPTransportError(f"No command specified for stdio server {self.config.name}")

        args = [cmd] + list(self.config.args)
        merged_env = dict(os.environ)
        if self.config.env:
            merged_env.update(self.config.env)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=merged_env,
            )
        except Exception as exc:
            raise MCPTransportError(f"Failed to spawn MCP stdio process {args}: {exc}") from exc

        self._connected = True
        self._read_task = asyncio.create_task(self._read_loop())

        # Perform MCP initialize handshake
        try:
            await self.send_request(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                    "clientInfo": {"name": "Dream", "version": "0.1.0"},
                },
            )
            # Send initialized notification
            await self._send_notification("notifications/initialized", {})
            return True
        except Exception as exc:
            await self.close()
            raise MCPTransportError(
                f"Handshake failed with MCP server {self.config.name}: {exc}"
            ) from exc

    async def _read_loop(self) -> None:
        if not self._process or not self._process.stdout:
            return
        try:
            while self._connected and self._process.returncode is None:
                line = await self._process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if not decoded:
                    continue
                try:
                    msg = json.loads(decoded)
                except json.JSONDecodeError:
                    continue

                req_id = msg.get("id")
                if req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        if "error" in msg:
                            err = msg["error"]
                            fut.set_exception(
                                MCPTransportError(
                                    f"MCP error {err.get('code')}: {err.get('message', 'unknown')}"
                                )
                            )
                        else:
                            fut.set_result(msg.get("result"))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            self._connected = False
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(MCPTransportError("MCP stdio process terminated"))
            self._pending.clear()

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if not self.is_connected or not self._process or not self._process.stdin:
            return
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        raw = json.dumps(payload, ensure_ascii=False) + "\n"
        self._process.stdin.write(raw.encode("utf-8"))
        await self._process.stdin.drain()

    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self.is_connected:
            raise MCPTransportError("StdioTransport is not connected")

        async with self._lock:
            req_id = self._next_id
            self._next_id += 1

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[req_id] = fut

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        raw = json.dumps(payload, ensure_ascii=False) + "\n"

        assert self._process and self._process.stdin
        self._process.stdin.write(raw.encode("utf-8"))
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(fut, timeout=30.0)
        except asyncio.TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise MCPTransportError(f"Request {method} (id={req_id}) timed out after 30s") from exc

    async def close(self) -> None:
        self._connected = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None


class SSETransport(MCPTransport):
    """Transports MCP messages to a remote HTTP / SSE endpoint."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._connected = False
        self._next_id = 1
        self._endpoint = config.url or "http://localhost:8000/sse"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        if not self.config.url:
            raise MCPTransportError(f"No URL specified for SSE server {self.config.name}")

        self._connected = True
        try:
            await self.send_request(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}, "resources": {}},
                    "clientInfo": {"name": "Dream", "version": "0.1.0"},
                },
            )
            return True
        except Exception as exc:
            self._connected = False
            raise MCPTransportError(
                f"Failed to connect to SSE MCP server {self.config.url}: {exc}"
            ) from exc

    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        req_id = self._next_id
        self._next_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        data = json.dumps(payload).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.config.headers:
            headers.update(self.config.headers)

        url = self.config.url or self._endpoint
        # If url ends in /sse, route requests to base or /message endpoint if specified
        post_url = url.replace("/sse", "/message") if url.endswith("/sse") else url

        def _do_post() -> Any:
            req = urllib.request.Request(post_url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                raw_resp = resp.read().decode("utf-8")
                return json.loads(raw_resp)

        try:
            res = await asyncio.to_thread(_do_post)
            if "error" in res:
                err = res["error"]
                raise MCPTransportError(f"MCP error {err.get('code')}: {err.get('message')}")
            return res.get("result")
        except Exception as exc:
            raise MCPTransportError(f"HTTP/SSE error for {method}: {exc}") from exc

    async def close(self) -> None:
        self._connected = False


class InMemoryTransport(MCPTransport):
    """Mock/in-memory transport for unit tests and local tools."""

    def __init__(self, config: MCPServerConfig | None = None) -> None:
        self.config = config or MCPServerConfig(id="mock", name="MockServer", type="stdio")
        self._connected = False
        self._tools: dict[str, dict[str, Any]] = {}
        self._resources: dict[str, dict[str, Any]] = {}
        self._prompts: dict[str, dict[str, Any]] = {}

    def register_tool(
        self, name: str, description: str, input_schema: dict[str, Any], handler: Any
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "_handler": handler,
        }

    def register_resource(self, uri: str, name: str, description: str, content: str) -> None:
        self._resources[uri] = {
            "uri": uri,
            "name": name,
            "description": description,
            "mimeType": "text/plain",
            "_content": content,
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def close(self) -> None:
        self._connected = False

    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        if method == "initialize":
            return {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": self.config.name, "version": "1.0"},
            }
        if method == "tools/list":
            return {"tools": [dict(t, _handler=None) for t in self._tools.values()]}
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {})
            if name not in self._tools:
                raise MCPTransportError(f"Tool {name} not found")
            handler = self._tools[name]["_handler"]
            if callable(handler):
                result = handler(**args) if isinstance(args, dict) else handler()
                if asyncio.iscoroutine(result):
                    result = await result
                return {"content": [{"type": "text", "text": str(result)}], "isError": False}
            return {"content": [{"type": "text", "text": str(handler)}], "isError": False}
        if method == "resources/list":
            return {"resources": [dict(r, _content=None) for r in self._resources.values()]}
        if method == "resources/read":
            uri = params.get("uri")
            if uri not in self._resources:
                raise MCPTransportError(f"Resource {uri} not found")
            return {"contents": [{"uri": uri, "text": self._resources[uri]["_content"]}]}
        raise MCPTransportError(f"Unknown MCP method: {method}")
