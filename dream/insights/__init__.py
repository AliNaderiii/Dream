"""Dream Insights & Behavior Analytics Subsystem."""

from .analyzer import InsightsAnalyzer
from .slash import handle_insights_command
from .types import (
    CostEstimate,
    SessionInsightReport,
    TokenBreakdown,
    ToolUsageStats,
)

__all__ = [
    "CostEstimate",
    "InsightsAnalyzer",
    "SessionInsightReport",
    "TokenBreakdown",
    "ToolUsageStats",
    "handle_insights_command",
]
