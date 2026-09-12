"""High-level Duplex Engine orchestrating multi-session streaming audio dialogues."""

from __future__ import annotations

import json
from typing import Any

from dream.duplex.session import DuplexSession
from dream.duplex.types import DuplexConfig


class DuplexEngine:
    """Master orchestrator for real-time duplex audio sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, DuplexSession] = {}

    def get_or_create_session(
        self,
        session_id: str = "default-duplex",
        config: DuplexConfig | None = None,
    ) -> DuplexSession:
        """Get an existing duplex session or create a new one."""
        if session_id not in self._sessions:
            cfg = config or DuplexConfig(session_id=session_id)
            self._sessions[session_id] = DuplexSession(cfg)
        return self._sessions[session_id]

    async def close_session(self, session_id: str) -> bool:
        """Close and remove a duplex session."""
        if session_id in self._sessions:
            session = self._sessions.pop(session_id)
            await session.close()
            return True
        return False

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return diagnostic summary of all active sessions."""
        return [session.get_status() for session in self._sessions.values()]

    def export_transcript_markdown(self, session_id: str) -> str:
        """Format session transcript into clean Persian/English Markdown."""
        session = self._sessions.get(session_id)
        if not session:
            return f"❌ نشست صوتی `{session_id}` یافت نشد."

        lines = [
            "# 🎙 گزارش گفتگوی صوتی بلادرنگ (Duplex Audio Transcript)",
            f"- **شناسه نشست**: `{session.session_id}`",
            f"- **وضعیت کنونی**: `{session.state.value}`",
            f"- **تعداد کل نوبت‌ها**: `{len(session.turns)}`",
            f"- **تعداد قطع‌شدن‌ها (Barge-in)**: `{session.metrics.total_interruptions}`",
            f"- **میانگین زمان اولین توکن (TTFT)**: `{session.metrics.avg_ttft_ms:.1f}ms`",
            "",
            "## 📝 مشروح گفتگو:",
            "",
        ]

        if not session.turns:
            lines.append("_هنوز هیچ مکالمه‌ای ثبت نشده است._")
        else:
            for i, turn in enumerate(session.turns, 1):
                speaker_icon = "👤 کاربر" if turn.speaker == "user" else "🤖 دستیار Dream"
                interrupted_tag = " ⚠️ *(حین صحبت قطع شد)*" if turn.interrupted else ""
                emotion_tag = f" `[{turn.emotion_tag}]`" if turn.emotion_tag != "neutral" else ""

                lines.append(
                    f"### {i}. {speaker_icon}{emotion_tag}{interrupted_tag}"
                )
                lines.append(f"> {turn.text}")
                lines.append(
                    f"*مدت صوت: {turn.audio_duration_ms:.0f}ms | تاخیر: {turn.latency_ms:.0f}ms*"
                )
                lines.append("")

        return "\n".join(lines)

    def export_json(self, session_id: str) -> str:
        """Export session data in JSON format."""
        session = self._sessions.get(session_id)
        if not session:
            return json.dumps({"error": f"Session '{session_id}' not found"}, ensure_ascii=False)

        data = {
            "status": session.get_status(),
            "transcript": session.get_transcript(),
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    async def reset_all(self) -> None:
        """Close and purge all active sessions."""
        for session in list(self._sessions.values()):
            await session.close()
        self._sessions.clear()


# Global Singleton
_GLOBAL_DUPLEX_ENGINE: DuplexEngine | None = None


def get_duplex_engine() -> DuplexEngine:
    """Retrieve global singleton instance of DuplexEngine."""
    global _GLOBAL_DUPLEX_ENGINE
    if _GLOBAL_DUPLEX_ENGINE is None:
        _GLOBAL_DUPLEX_ENGINE = DuplexEngine()
    return _GLOBAL_DUPLEX_ENGINE
