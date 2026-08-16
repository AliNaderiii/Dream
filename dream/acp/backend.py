"""ACP Backend provider adapter allowing external ACP agents to serve as Dream model backends."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from .client import ACPClient
from .models import ACPAgentConfig


class ACPBackend:
    """Model backend provider that routes chat requests to an external ACP agent."""

    def __init__(
        self,
        endpoint: str | None = None,
        token: str | None = None,
        agent_config: ACPAgentConfig | None = None,
        session_id: str = "dream_acp_provider",
    ) -> None:
        if agent_config:
            self.endpoint = agent_config.endpoint
            self.token = agent_config.token
            self.name = agent_config.name
        else:
            self.endpoint = endpoint or os.environ.get(
                "DREAM_ACP_ENDPOINT", "http://localhost:8000"
            )
            self.token = token or os.environ.get("DREAM_ACP_TOKEN")
            self.name = "ACP Agent"

        self.session_id = session_id
        self._client = ACPClient(endpoint=self.endpoint, token=self.token)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Synchronous chat interface called by Dream's agent loop."""
        del tools  # ACP agents handle their own tools natively
        # Extract last user message or system/user summary
        last_message = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_message = m.get("content", "")
                break
        if not last_message and messages:
            last_message = messages[-1].get("content", "")

        async def _call() -> dict[str, Any]:
            res = await self._client.send_message(self.session_id, last_message)
            return {
                "content": res.get("reply", ""),
                "tool_calls": res.get("tool_calls", []),
            }

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In nested event loop (e.g. in thread executor), run in new loop or thread
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, _call()).result()
            else:
                return loop.run_until_complete(_call())
        except Exception:
            return asyncio.run(_call())
