"""Manager for external ACP agent configurations and agent routing."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

from .client import ACPClient
from .models import ACPAgentConfig


class ACPAgentManager:
    """Manages configurations and active clients for external ACP agents."""

    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = config_path or os.environ.get(
            "DREAM_ACP_AGENTS_PATH", "data/acp_agents.json"
        )
        self._lock = threading.RLock()
        self._agents: dict[str, ACPAgentConfig] = {}
        self._clients: dict[str, ACPClient] = {}
        self._load_configs()
        self._ensure_defaults()

    def _load_configs(self) -> None:
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "id" in item:
                            cfg = ACPAgentConfig.from_dict(item)
                            self._agents[cfg.id] = cfg
        except Exception:
            pass

    def _ensure_defaults(self) -> None:
        """Seed presets for well-known ACP agents if none exist."""
        if not self._agents:
            defaults = [
                ACPAgentConfig(
                    id="claude_code",
                    name="Claude Code (ACP)",
                    endpoint="http://localhost:8001",
                    label="Claude Code",
                    description="Anthropic Claude Code agent via local ACP bridge",
                ),
                ACPAgentConfig(
                    id="codex_acp",
                    name="Codex (ACP)",
                    endpoint="http://localhost:8002",
                    label="OpenAI Codex",
                    description="OpenAI Codex programming agent via ACP",
                ),
                ACPAgentConfig(
                    id="gemini_cli",
                    name="Gemini CLI (ACP)",
                    endpoint="http://localhost:8003",
                    label="Gemini CLI",
                    description="Google Gemini CLI assistant via ACP",
                ),
            ]
            for d in defaults:
                self._agents[d.id] = d
            self._save_configs()

    def _save_configs(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                data = [a.to_full_dict() for a in self._agents.values()]
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def add_agent(
        self,
        name: str,
        endpoint: str,
        *,
        token: str | None = None,
        label: str = "",
        description: str = "",
        model: str | None = None,
        enabled: bool = True,
        agent_id: str | None = None,
    ) -> ACPAgentConfig:
        """Add and persist a new external ACP agent."""
        aid = agent_id or f"acp_{uuid.uuid4().hex[:12]}"
        cfg = ACPAgentConfig(
            id=aid,
            name=name,
            endpoint=endpoint,
            token=token,
            label=label or name,
            description=description,
            model=model,
            enabled=enabled,
        )
        with self._lock:
            self._agents[aid] = cfg
            self._save_configs()
        return cfg

    def remove_agent(self, agent_id: str) -> bool:
        """Remove a configured ACP agent."""
        with self._lock:
            cfg = self._agents.pop(agent_id, None)
            self._clients.pop(agent_id, None)
            self._save_configs()
        return cfg is not None

    def get_client(self, agent_id: str) -> ACPClient | None:
        """Get or create an ACPClient for the specified agent."""
        with self._lock:
            cfg = self._agents.get(agent_id)
            if not cfg:
                return None
            if agent_id in self._clients:
                return self._clients[agent_id]
            client = ACPClient(endpoint=cfg.endpoint, token=cfg.token)
            self._clients[agent_id] = client
            return client

    async def test_agent(self, agent_id_or_config: str | ACPAgentConfig) -> dict[str, Any]:
        """Test connection to an external ACP agent."""
        started = time.monotonic()
        if isinstance(agent_id_or_config, str):
            cfg = self._agents.get(agent_id_or_config)
            if not cfg:
                return {"ok": False, "error": f"Agent {agent_id_or_config} not found"}
        else:
            cfg = agent_id_or_config

        client = ACPClient(endpoint=cfg.endpoint, token=cfg.token)
        try:
            connected = await client.connect()
            tools = await client.list_tools()
            latency_ms = round((time.monotonic() - started) * 1000, 2)
            return {
                "ok": connected,
                "agent_id": cfg.id,
                "name": cfg.name,
                "endpoint": cfg.endpoint,
                "tools_count": len(tools),
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            return {
                "ok": False,
                "agent_id": cfg.id,
                "name": cfg.name,
                "error": str(exc),
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
            }

    def list_agents(self) -> list[dict[str, Any]]:
        """List all configured external ACP agents."""
        with self._lock:
            return [a.to_dict() for a in self._agents.values()]
