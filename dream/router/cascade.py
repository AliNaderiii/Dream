"""Model Cascader: Multi-tier fallback execution policies and escalation triggers."""

from __future__ import annotations

from typing import Any

from dream.router.types import ModelTier, RoutingDecision


class ModelCascader:
    """Orchestrates tiered escalation policies across Fast, Standard, and Heavy models."""

    def get_cascade_plan(self, decision: RoutingDecision) -> dict[str, Any]:
        """Generate full execution and escalation pipeline based on routing decision."""
        primary_tier = decision.target_tier

        escalation_path: list[ModelTier] = []
        if primary_tier == ModelTier.FAST_EDGE:
            escalation_path = [
                ModelTier.FAST_EDGE,
                ModelTier.STANDARD_CHAT,
                ModelTier.REASONING_HEAVY,
            ]
        elif primary_tier == ModelTier.STANDARD_CHAT:
            escalation_path = [ModelTier.STANDARD_CHAT, ModelTier.REASONING_HEAVY]
        else:
            escalation_path = [ModelTier.REASONING_HEAVY]

        return {
            "primary_tier": primary_tier.value,
            "escalation_chain": [t.value for t in escalation_path],
            "speculative_tools": decision.predicted_tools,
            "escalation_triggers": [
                "tool_dispatch_failure",
                "model_hallucination_detected",
                "token_budget_overflow",
                "confidence_drop_below_0.75",
            ],
            "estimated_token_saving": decision.estimated_tokens_saved,
        }

    def evaluate_escalation(
        self,
        current_tier: ModelTier,
        confidence: float,
        had_tool_error: bool = False,
    ) -> tuple[bool, ModelTier | None]:
        """Determine if current turn must escalate to higher model tier."""
        if current_tier == ModelTier.REASONING_HEAVY:
            return False, None

        if had_tool_error or confidence < 0.70:
            next_tier = (
                ModelTier.STANDARD_CHAT
                if current_tier == ModelTier.FAST_EDGE
                else ModelTier.REASONING_HEAVY
            )
            return True, next_tier

        return False, None
