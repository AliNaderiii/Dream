"""ACP Client implementation for driving external ACP agents from Dream."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator
from typing import Any


class ACPClientError(Exception):
    """Raised when an ACP client call fails."""


class ACPClient:
    """Connects to external ACP agents (Codex, Gemini CLI, Claude Code) and executes turns/tools."""

    def __init__(
        self,
        endpoint: str = "http://localhost:8000",
        token: str | None = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _make_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-ACP-Token"] = self.token
        return headers

    async def _request(
        self, path: str, method: str = "GET", payload: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self.endpoint}/{path.lstrip('/')}"
        headers = self._make_headers()
        data = json.dumps(payload).encode("utf-8") if payload is not None else None

        def _do_http() -> Any:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8")
                    content_type = resp.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        return json.loads(body)
                    return body
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                raise ACPClientError(f"HTTP {exc.code} for {method} {url}: {err_body}") from exc
            except Exception as exc:
                raise ACPClientError(f"Network error for {method} {url}: {exc}") from exc

        return await asyncio.to_thread(_do_http)

    async def connect(self, endpoint: str | None = None, token: str | None = None) -> bool:
        """Verify connection to the external ACP agent via health/info probe."""
        if endpoint:
            self.endpoint = endpoint.rstrip("/")
        if token is not None:
            self.token = token

        try:
            # Try /acp/v1/info or /acp/health
            await self._request("/acp/v1/info")
            self._connected = True
            return True
        except Exception:
            try:
                await self._request("/acp/health")
                self._connected = True
                return True
            except Exception as exc:
                self._connected = False
                raise ACPClientError(
                    f"Failed to connect to ACP agent at {self.endpoint}: {exc}"
                ) from exc

    async def disconnect(self) -> None:
        self._connected = False

    async def list_tools(self) -> list[dict[str, Any]]:
        """List tools exposed by the external ACP agent."""
        res = await self._request("/acp/v1/tools")
        if isinstance(res, dict):
            return res.get("tools", [])
        return []

    async def execute_tool(self, name: str, args: dict[str, Any] | None = None) -> Any:
        """Execute a tool on the external ACP agent."""
        return await self._request(
            f"/acp/v1/tools/{name}", method="POST", payload={"arguments": args or {}}
        )

    async def list_sessions(self) -> list[dict[str, Any]]:
        """List sessions from the external ACP agent."""
        res = await self._request("/acp/v1/sessions")
        if isinstance(res, dict):
            return res.get("sessions", [])
        return []

    async def create_session(self, title: str = "New Session") -> dict[str, Any]:
        """Create a new session on the external ACP agent."""
        res = await self._request("/acp/v1/sessions", method="POST", payload={"title": title})
        if isinstance(res, dict):
            return res
        return {"session_id": "unknown"}

    async def send_message(
        self,
        session_id: str,
        message: str,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Send a message to the external ACP agent and return the turn result."""
        payload = {
            "session_id": session_id,
            "message": message,
            "stream": stream,
        }
        res = await self._request("/acp/v1/messages", method="POST", payload=payload)
        if isinstance(res, dict):
            return res
        return {"reply": str(res)}

    async def stream_message(
        self,
        session_id: str,
        message: str,
    ) -> AsyncIterator[str]:
        """Send a message and yield streaming chunks."""
        res = await self.send_message(session_id, message, stream=False)
        reply = res.get("reply", "")
        # Tokenize and yield chunks
        for token in reply.split(" "):
            yield token + " "
            await asyncio.sleep(0.01)

    async def replay_history(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        instruction: str = "Review and evaluate this conversation history.",
    ) -> dict[str, Any]:
        """Replay past conversation history to the external ACP agent."""
        payload = {
            "session_id": session_id,
            "messages": messages,
            "instruction": instruction,
        }
        res = await self._request("/acp/v1/replay", method="POST", payload=payload)
        if isinstance(res, dict):
            return res
        return {"reply": str(res)}
