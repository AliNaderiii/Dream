"""Metacognitive Evaluator: Real-time self-monitoring and trajectory assessment."""

from __future__ import annotations

import uuid

from dream.reasoning.types import MetacognitiveEvaluation


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
        t_clean = thought_text.strip().lower()
        for prev in history:
            p_clean = prev.lower()
            if t_clean in p_clean or p_clean in t_clean:
                is_repetitive = True
                hallucination_risk = 0.7
                break

        # Suggest next strategic action
        if is_repetitive:
            action = "backtrack"
            critique = "احتمال تکرار یا حلقه منطقی تشخیص داده شد."
        elif depth >= 3 and coherence >= 0.8:
            action = "ready_for_conclusion"
            critique = "عمق استدلال کافی است و آماده نتیجه‌گیری می‌باشد."
        else:
            action = "continue_exploration"
            critique = "استدلال منسجم است. به کاوش شاخه‌ها ادامه دهید."

        return MetacognitiveEvaluation(
            evaluation_id=eid,
            coherence_score=coherence,
            depth_score=depth_score,
            hallucination_risk=hallucination_risk,
            critique_notes=critique,
            suggested_action=action,
        )
