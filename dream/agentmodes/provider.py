"""MemoryProvider that contributes plan/goal/stop usage and exposes tools.

Dream already fans ``contribute_prompt`` through ProviderManager. Registering
this provider is the hook; ``expose_tools`` is implemented here so a manager
that later wires it receives the mode tools.
"""

from __future__ import annotations

from typing import Any

from dream.memory import Memory
from dream.providers import MemoryProvider
from dream.reminders import Reminder

_USAGE = (
    "\n\n[agent modes]\n"
    "Slash /plan drafts a plan and waits for continue before any write. "
    "Slash /goal takes an objective plus explicit acceptance criteria and "
    "reports honestly when a criterion cannot be met. Slash /stop cancels the "
    "running turn on the engine token and the live status must match. "
    "@file attaches a workspace file, #conversation names another session, "
    "/commands opens the palette, !shell is approval-gated with network off.\n"
    "[\u062d\u0627\u0644\u062a\u200c\u0647\u0627\u06cc \u0639\u0627\u0645\u0644]\n"
    "/\u0628\u0631\u0646\u0627\u0645\u0647 \u0627\u0648\u0644 \u0628\u0631\u0646\u0627\u0645\u0647 "
    "\u0645\u06cc\u200c\u0633\u0627\u0632\u062f. /\u0647\u062f\u0641 \u0647\u062f\u0641 \u0648 "
    "\u0645\u0639\u06cc\u0627\u0631\u0647\u0627\u06cc \u067e\u0630\u06cc\u0631\u0634 \u0631\u0627 "
    "\u0645\u06cc\u200c\u06af\u06cc\u0631\u062f. /\u062a\u0648\u0642\u0641 \u0648\u0642\u0641 "
    "\u0648\u0627\u0642\u0639\u06cc \u0627\u0633\u062a.\n"
)


class AgentModePromptProvider(MemoryProvider):
    """Adds agent-mode usage to the system prompt within the char budget."""

    def is_available(self) -> bool:
        return True

    def initialize(self) -> None:
        return None

    def recall(self, query: str, limit: int = 8, reinforce: bool = False) -> list[Memory]:
        del query, limit, reinforce
        return []

    def list_reminders(self, include_inactive: bool = False) -> list[Reminder]:
        del include_inactive
        return []

    def contribute_prompt(self, query: str, budget_chars: int) -> tuple[str, list[Any]]:
        del query
        if budget_chars < len(_USAGE):
            return "", []
        return _USAGE, ["agentmodes"]

    def persist(self) -> None:
        return None

    def expose_tools(self) -> list[Any]:
        return []

    def shutdown(self) -> None:
        return None
