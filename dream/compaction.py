"""Deterministic, provider-neutral conversation context accounting and compaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CHARS_PER_TOKEN = 4
DEFAULT_ECHO_CONTEXT_TOKENS = 16_384
DEFAULT_MODEL_CONTEXT_TOKENS = 8_192
DEFAULT_THRESHOLD = 0.80


@dataclass(frozen=True)
class ContextUsage:
    """Cheap conservative context estimate, with no model or network call."""

    tokens: int
    window: int

    @property
    def ratio(self) -> float:
        return self.tokens / self.window if self.window else 1.0


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate tokens from serialised message content plus role overhead."""
    chars = 0
    for message in messages:
        chars += len(str(message.get("content") or "")) + 12
        chars += len(str(message.get("tool_calls") or ""))
    return max(1, (chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def usage(messages: list[dict[str, Any]], window: int) -> ContextUsage:
    return ContextUsage(estimate_tokens(messages), window)


def deterministic_summary(dropped: list[dict[str, Any]], reason: str) -> str:
    """Return a byte-stable bilingual summary header for offline transports."""
    roles = ",".join(str(item.get("role", "event")) for item in dropped)
    chars = sum(len(str(item.get("content") or "")) for item in dropped)
    # Tool outputs are facts in the conversational record. Keep a bounded,
    # deterministic copy so a later reference remains answerable after its
    # exchange has left the active window.
    tool_results = [str(item.get("content") or "")[:512] for item in dropped if item.get("role") == "tool"]  # noqa: E501
    preserved = " | ".join(tool_results)
    suffix = f" preserved_tool_results={preserved!r}." if preserved else ""
    return (
        "[Context compacted / \u0641\u0634\u0631\u062f\u0647\u200c\u0633\u0627\u0632\u06cc \u0634\u062f] "  # noqa: E501
        f"reason={reason}; dropped_messages={len(dropped)}; dropped_chars={chars}; roles={roles}.{suffix}"  # noqa: E501
    )


def split_for_compaction(history: list[dict[str, Any]], preserve: int = 4) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:  # noqa: E501
    """Keep the active exchange intact and compact only completed older items."""
    if len(history) <= preserve:
        return [], list(history)
    return list(history[:-preserve]), list(history[-preserve:])
