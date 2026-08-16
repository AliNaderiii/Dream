"""ACP Server implementation exposing Dream as an Agent Client Protocol agent."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any

from dream.agent import ApprovalPolicy, Dream
from dream.memory import MemoryStore
from dream.tools import REGISTRY, execute

from .models import ACPSession

DEFAULT_ACP_TOKEN = os.environ.get("DREAM_ACP_TOKEN", "")


class ACPServer:
    """Exposes Dream capabilities and conversational turns over Agent Client Protocol (ACP)."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        token: str | None = None,
        dream_instance: Dream | None = None,
    ) -> None:
        self.store = store or MemoryStore(os.environ.get("DREAM_DB", "data/dream.db"))
        self.token = token if token is not None else DEFAULT_ACP_TOKEN
        self._dream = dream_instance or Dream(self.store, approval_policy=ApprovalPolicy())
        self._sessions: dict[str, ACPSession] = {}
        self._session_dreams: dict[str, Dream] = {}

    def _authenticate(self, headers: dict[str, str]) -> bool:
        """Validate Bearer or X-ACP-Token against configured token."""
        if not self.token:
            return True  # No token required if not configured

        auth = headers.get("authorization") or headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            bearer = auth[7:].strip()
            if bearer == self.token:
                return True

        custom_tok = headers.get("x-acp-token") or headers.get("X-ACP-Token") or ""
        return custom_tok.strip() == self.token

    def _get_or_create_session_dream(self, session_id: str) -> Dream:
        if session_id in self._session_dreams:
            return self._session_dreams[session_id]
        d = Dream(self.store, approval_policy=ApprovalPolicy())
        self._session_dreams[session_id] = d
        return d

    async def handle_request(
        self,
        path: str,
        method: str,
        headers: dict[str, str],
        body: str | dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        """Dispatch an ACP request and return (status_code, response_headers, response_body)."""
        if not self._authenticate(headers):
            return 401, {"Content-Type": "application/json"}, {"error": "Unauthorized", "code": 401}

        parsed_body: dict[str, Any] = {}
        if isinstance(body, str) and body.strip():
            try:
                parsed_body = json.loads(body)
            except Exception:
                return (
                    400,
                    {"Content-Type": "application/json"},
                    {"error": "Invalid JSON body", "code": 400},
                )
        elif isinstance(body, dict):
            parsed_body = body

        clean_path = path.rstrip("/")
        m = method.upper()

        # Health / Info endpoints
        if (
            clean_path in ("/acp/v1/info", "/acp/v1/health", "/acp/info", "/acp/health")
            and m == "GET"
        ):
            return (
                200,
                {"Content-Type": "application/json"},
                {
                    "name": "Dream Assistant",
                    "version": "0.1.0",
                    "protocol": "acp/1.0",
                    "capabilities": {
                        "chat": True,
                        "streaming": True,
                        "tools": True,
                        "sessions": True,
                        "replay": True,
                    },
                },
            )

        # List tools
        if clean_path in ("/acp/tools", "/acp/v1/tools") and m == "GET":
            tools = [
                {
                    "name": name,
                    "risk": reg.risk,
                    "description": reg.description,
                    "schema": reg.schema,
                }
                for name, reg in sorted(REGISTRY.items())
            ]
            return 200, {"Content-Type": "application/json"}, {"tools": tools}

        # Execute tool
        if (
            clean_path.startswith("/acp/tools/") or clean_path.startswith("/acp/v1/tools/")
        ) and m == "POST":
            tool_name = clean_path.split("/")[-1]
            if tool_name not in REGISTRY:
                return (
                    404,
                    {"Content-Type": "application/json"},
                    {"error": f"Tool {tool_name} not found"},
                )
            args = parsed_body.get("arguments", parsed_body)
            try:
                raw = execute(tool_name, args if isinstance(args, dict) else {}, approved=True)
                try:
                    result = json.loads(raw)
                except Exception:
                    result = {"status": "ok", "result": raw}
                return 200, {"Content-Type": "application/json"}, result
            except Exception as exc:
                return 500, {"Content-Type": "application/json"}, {"error": str(exc)}

        # Sessions: list / create
        if clean_path in ("/acp/sessions", "/acp/v1/sessions"):
            if m == "GET":
                sess_list = [s.to_dict() for s in self._sessions.values()]
                return 200, {"Content-Type": "application/json"}, {"sessions": sess_list}
            if m == "POST":
                sid = parsed_body.get("session_id") or f"acp_sess_{uuid.uuid4().hex[:16]}"
                title = str(parsed_body.get("title") or "New ACP Session")
                session = ACPSession(id=sid, title=title)
                self._sessions[sid] = session
                return 201, {"Content-Type": "application/json"}, session.to_dict()

        # Session detail
        if (
            clean_path.startswith("/acp/sessions/") or clean_path.startswith("/acp/v1/sessions/")
        ) and m == "GET":
            sid = clean_path.split("/")[-1]
            session = self._sessions.get(sid)
            if not session:
                return (
                    404,
                    {"Content-Type": "application/json"},
                    {"error": f"Session {sid} not found"},
                )
            return (
                200,
                {"Content-Type": "application/json"},
                {
                    **session.to_dict(),
                    "messages": session.messages,
                },
            )

        # Replay conversation history
        if clean_path in ("/acp/replay", "/acp/v1/replay") and m == "POST":
            sid = parsed_body.get("session_id") or f"acp_sess_{uuid.uuid4().hex[:16]}"
            messages = parsed_body.get("messages", [])
            instruction = (
                parsed_body.get("instruction") or "Review and summarize this conversation."
            )

            session = self._sessions.setdefault(sid, ACPSession(id=sid, title="Replayed Session"))
            dream = self._get_or_create_session_dream(sid)

            # Seed history
            for msg in messages:
                if isinstance(msg, dict):
                    dream.history.append(
                        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                    )
                    session.messages.append(msg)

            # Run turn on instruction
            turn = await asyncio.to_thread(dream.run, instruction)
            reply = turn.reply
            session.messages.append(
                {"role": "user", "content": instruction, "timestamp": time.time()}
            )
            session.messages.append(
                {"role": "assistant", "content": reply, "timestamp": time.time()}
            )

            return (
                200,
                {"Content-Type": "application/json"},
                {
                    "session_id": sid,
                    "reply": reply,
                    "tool_calls": getattr(turn, "tool_calls", []),
                    "elapsed_seconds": getattr(turn, "elapsed_seconds", 0.0),
                },
            )

        # Chat / Messages: run agent turn
        if clean_path in ("/acp/chat", "/acp/v1/messages") and m == "POST":
            message = parsed_body.get("message") or parsed_body.get("content")
            if not message or not isinstance(message, str):
                return (
                    400,
                    {"Content-Type": "application/json"},
                    {"error": "Missing message content"},
                )

            sid = parsed_body.get("session_id") or "default"
            session = self._sessions.setdefault(sid, ACPSession(id=sid, title="ACP Chat"))
            dream = self._get_or_create_session_dream(sid)

            turn = await asyncio.to_thread(dream.run, message)
            reply = turn.reply
            session.messages.append({"role": "user", "content": message, "timestamp": time.time()})
            session.messages.append(
                {"role": "assistant", "content": reply, "timestamp": time.time()}
            )
            session.updated_at = time.time()

            stream_mode = bool(parsed_body.get("stream", False))
            if stream_mode:
                # Return Server-Sent Events stream format
                msg_payload = json.dumps({"role": "assistant", "content": reply})
                tool_calls_payload = getattr(turn, "tool_calls", [])
                done_payload = json.dumps({"reply": reply, "tool_calls": tool_calls_payload})
                sse_lines = [
                    f"event: message\ndata: {msg_payload}\n\n",
                    f"event: done\ndata: {done_payload}\n\n",
                ]
                return 200, {"Content-Type": "text/event-stream"}, "".join(sse_lines)

            return (
                200,
                {"Content-Type": "application/json"},
                {
                    "session_id": sid,
                    "reply": reply,
                    "tool_calls": getattr(turn, "tool_calls", []),
                    "elapsed_seconds": getattr(turn, "elapsed_seconds", 0.0),
                },
            )

        return (
            404,
            {"Content-Type": "application/json"},
            {"error": f"Endpoint not found: {method} {path}"},
        )
