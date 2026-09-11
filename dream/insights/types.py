"""Data models and type definitions for Dream Session Insights and Analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TokenBreakdown:
    """Token consumption categorization across conversation roles."""

    prompt_tokens: int
    completion_tokens: int
    tool_tokens: int
    system_tokens: int
    total_tokens: int

    @property
    def tool_percentage(self) -> float:
        return (self.tool_tokens / self.total_tokens * 100) if self.total_tokens else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "tool_tokens": self.tool_tokens,
            "system_tokens": self.system_tokens,
            "total_tokens": self.total_tokens,
            "tool_percentage": round(self.tool_percentage, 2),
        }


@dataclass
class CostEstimate:
    """Estimated financial cost of session usage in USD and Iranian Toman (IRR)."""

    usd_cost: float
    toman_cost: float
    exchange_rate_toman: float = 60_000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "usd_cost": round(self.usd_cost, 4),
            "toman_cost": round(self.toman_cost, 0),
            "exchange_rate_toman": self.exchange_rate_toman,
        }


@dataclass
class ToolUsageStats:
    """Frequency and error metrics for a specific tool."""

    name: str
    call_count: int
    error_count: int = 0
    total_chars_generated: int = 0

    @property
    def success_rate(self) -> float:
        if not self.call_count:
            return 100.0
        return (self.call_count - self.error_count) / self.call_count * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "call_count": self.call_count,
            "error_count": self.error_count,
            "success_rate": round(self.success_rate, 2),
            "total_chars_generated": self.total_chars_generated,
        }


@dataclass
class SessionInsightReport:
    """Comprehensive analytical report of session activity and optimization tips."""

    message_count: int
    turn_count: int
    tokens: TokenBreakdown
    cost: CostEstimate
    tools: list[ToolUsageStats] = field(default_factory=list)
    top_topics: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_count": self.message_count,
            "turn_count": self.turn_count,
            "tokens": self.tokens.to_dict(),
            "cost": self.cost.to_dict(),
            "tools": [t.to_dict() for t in self.tools],
            "top_topics": self.top_topics,
            "recommendations": self.recommendations,
            "generated_at": self.generated_at.isoformat(),
        }
