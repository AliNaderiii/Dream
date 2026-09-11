"""Metacognitive Evaluator: Real-time self-monitoring and reasoning trajectory assessment."""

from __future__ import annotations

import time
from typing import Any
import uuid

from dream.reasoning.types import MetacognitiveEvaluation, ThoughtNode


class MetacognitiveEvaluator:
    """Evaluates coherence, depth, and risk across reasoning trajectories."""

    def evaluate_thought_step(
        self,
        thought_text: str,
        depth: int,
        context_history: list[str] | None = None,
    ) -> MetacognitiveEvaluation:
        """Perform self-reflective critique on a single reasoning step."""
        eid = f"eval-{uuid.uuid4().hex[:6]}"
        history = context_history or []

        # Coherence score based on length and clarity
        length = len(thought_text.strip())
        coherence = 0.9 if length >= 30 else (0.6 if length >= 10 else 0.3)

        # Depth score based on tree level
        depth_score = min(1.0, 0.4 + (depth * 0.2))

        # Check for circular reasoning in history
        hallucination_risk = 0.1
        is_repetitive = False
        for prev in history:
            if thought_text.strip().lower() in prev.lower() or prev.lower() in thought_text.strip().lower():
                is_repetitive = True
                hallucination_risk = 0.7
                break

        # Suggest next strategic action
        if is_repetitive:
            action = "backtrack"
            critique = "\u0627\u062d\u062a\u0645\u0627\u0644 \u062a\u06a9\u0631\u0627\u0631 \u06cc\u0627 \u062d\u0644\u0642\u0647 \u0645\u0646\u0637\u0642\u06cc \u062a\u0634\u062e\u06cc\u0635 \u062f\u0627\u062f\u0647 \u0634\u062f."
        elif depth >= 3 and coherence >= 0.8:
            action = "ready_for_conclusion"
            critique = "\u0639\u0645\u0642 \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u06a9\u0627\u0641\u06cc \u0627\u0633\u062a \u0648 \u0622\u0645\u0627\u062f\u0647 \u0646\u062a\u06cc\u062c\u0647\u200c\u06af\u06cc\u0631\u06cc \u0645\u06cc\u200c\u0628\u0627\u0634\u062f."
        else:
            action = "continue_exploration"
            critique = "\u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0645\u0646\u0633\u062c\u0645 \u0627\u0633\u062a. \u0628\u0647 \u06a9\u0627\u0648\u0634 \u0634\u0627\u062e\u0647\u200c\u0647\u0627 \u0627\u062f\u0627\u0645\u0647 \u062f\u0647\u06cc\u062f."

        return MetacognitiveEvaluation(
            evaluation_id=eid,
            coherence_score=coherence,
            depth_score=depth_score,
            hallucination_risk=hallucination_risk,
            critique_notes=critique,
            suggested_action=action,
        )
