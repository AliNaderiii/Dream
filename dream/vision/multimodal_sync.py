"""Multi-Modal Audio-Visual Stream Synchronization for Simultaneous Hearing and Seeing."""

from __future__ import annotations

import time
from typing import Any

from dream.duplex.engine import get_duplex_engine
from dream.vision.stream_engine import get_visual_stream_engine


class MultiModalStreamSynchronizer:
    """Binds active voice conversation turns with contemporaneous visual screen/camera frames."""

    def __init__(self) -> None:
        self._duplex_engine = get_duplex_engine()
        self._vision_engine = get_visual_stream_engine()

    def get_unified_multimodal_context(
        self,
        duplex_session_id: str = "default-duplex",
        visual_stream_id: str = "screen-primary",
    ) -> dict[str, Any]:
        """Produce unified multi-modal context with audio turns and visual scene."""
        session = self._duplex_engine.get_or_create_session(duplex_session_id)
        visual_ctx = self._vision_engine.query_recent_visual_context(visual_stream_id)

        last_turn_text = (
            session.turns[-1].text if session.turns else "گفتگویی هنوز انجام نشده."
        )
        return {
            "timestamp": time.time(),
            "duplex_session_id": duplex_session_id,
            "visual_stream_id": visual_stream_id,
            "duplex_state": session.state.value,
            "last_dialogue_turn": last_turn_text,
            "visual_context": visual_ctx,
            "multimodal_reasoning_prompt": (
                f"کاربر گفت: '{last_turn_text}' | "
                f"اطلاعات روی صفحه نمایش: {visual_ctx.get('visible_texts', [])}"
            ),
        }


_GLOBAL_SYNC: MultiModalStreamSynchronizer | None = None


def get_multimodal_synchronizer() -> MultiModalStreamSynchronizer:
    """Retrieve singleton MultiModalStreamSynchronizer."""
    global _GLOBAL_SYNC
    if _GLOBAL_SYNC is None:
        _GLOBAL_SYNC = MultiModalStreamSynchronizer()
    return _GLOBAL_SYNC
