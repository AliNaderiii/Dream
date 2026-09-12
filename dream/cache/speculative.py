"""Speculative tool pre-fetching, execution prediction, and latency minimization."""

from __future__ import annotations

import re
import time
from typing import Any
import uuid

from dream.cache.types import SpeculativePrediction


class SpeculativePrefetcher:
    """Predicts next probable tool invocations and pre-computes results speculatively."""

    def __init__(self) -> None:
        self._predictions: list[SpeculativePrediction] = []
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """Prime standard deterministic tools for speculative pre-fetching."""
        # 1. Datetime / Clock trigger
        self.register_pattern(
            trigger_pattern=r"(\u0633\u0627\u0639\u062a\s+\u0686\u0646\u062f\u0647|\u062a\u0627\u0631\u06cc\u062e\s+\u0627\u0645\u0631\u0648\u0632|what\s+time|current\s+date)",
            tool_name="get_datetime",
            default_args={},
            confidence=0.98,
        )

        # 2. Note listing trigger
        self.register_pattern(
            trigger_pattern=r"(\u0644\u06cc\u0633\u062a\s+\u06cc\u0627\u062f\u062f\u0627\u0634\u062a|\u06cc\u0627\u062f\u062f\u0627\u0634\u062a\u200c\u0647\u0627\u06cc\s+\u0645\u0646|list\s+notes)",
            tool_name="list_notes",
            default_args={},
            confidence=0.95,
        )

        # 3. Calculation trigger
        self.register_pattern(
            trigger_pattern=r"(\u062d\u0633\u0627\u0628\s+\u06a9\u0646|\u0645\u062d\u0627\u0633\u0628\u0647\s+\u06a9\u0646|calculate\s+[\d\.\+\-\*\/]+)",
            tool_name="calculate",
            default_args={"expression": "0"},
            confidence=0.90,
        )

    def register_pattern(
        self,
        trigger_pattern: str,
        tool_name: str,
        default_args: dict[str, Any],
        precomputed_result: Any = None,
        confidence: float = 0.90,
    ) -> SpeculativePrediction:
        """Register a speculative prediction rule for tool execution."""
        pid = f"spec_{uuid.uuid4().hex[:8]}"
        pred = SpeculativePrediction(
            id=pid,
            trigger_pattern=trigger_pattern,
            predicted_tool=tool_name,
            predicted_args=default_args,
            precomputed_result=precomputed_result,
            confidence_score=confidence,
            created_at=time.time(),
        )
        self._predictions.append(pred)
        return pred

    def predict_tool(self, user_input: str) -> SpeculativePrediction | None:
        """Evaluate input against speculative patterns and return highest confidence prediction."""
        best_pred: SpeculativePrediction | None = None
        best_conf = 0.0

        for pred in self._predictions:
            if re.search(pred.trigger_pattern, user_input, re.IGNORECASE):
                if pred.confidence_score > best_conf:
                    best_conf = pred.confidence_score
                    best_pred = pred

        if best_pred is not None:
            best_pred.hit_count += 1
            return best_pred

        return None

    def list_predictions(self) -> list[SpeculativePrediction]:
        """Return all active speculative rules."""
        return list(self._predictions)
