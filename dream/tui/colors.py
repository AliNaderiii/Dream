"""ANSI color management, terminal capability detection, and text styling."""

from __future__ import annotations

import os
import sys
from typing import TextIO


class ColorManager:
    """Detects terminal capabilities and formats styled text."""

    def __init__(
        self,
        stream: TextIO | None = None,
        force_color: bool = False,
        no_color: bool = False,
    ) -> None:
        self.stream = stream or sys.stdout
        self._force_color = force_color
        self._no_color = no_color or bool(os.environ.get("NO_COLOR", "").strip())
        self._term = os.environ.get("TERM", "").lower()

    @property
    def is_enabled(self) -> bool:
        if self._no_color:
            return False
        if self._force_color:
            return True
        if self._term == "dumb":
            return False
        try:
            return hasattr(self.stream, "isatty") and self.stream.isatty()
        except Exception:
            return False

    def style(self, text: str, code: str) -> str:
        """Wrap text in ANSI escape sequence if terminal supports color."""
        if not self.is_enabled:
            return text
        return f"\x1b[{code}m{text}\x1b[0m"

    def bold(self, text: str) -> str:
        return self.style(text, "1")

    def dim(self, text: str) -> str:
        return self.style(text, "2")

    def italic(self, text: str) -> str:
        return self.style(text, "3")

    def underline(self, text: str) -> str:
        return self.style(text, "4")

    def red(self, text: str) -> str:
        return self.style(text, "31")

    def green(self, text: str) -> str:
        return self.style(text, "32")

    def yellow(self, text: str) -> str:
        return self.style(text, "33")

    def blue(self, text: str) -> str:
        return self.style(text, "34")

    def magenta(self, text: str) -> str:
        return self.style(text, "35")

    def cyan(self, text: str) -> str:
        return self.style(text, "36")

    def white(self, text: str) -> str:
        return self.style(text, "37")

    def render_meter(self, value: int, maximum: int, width: int = 15) -> str:
        """Render a visual gauge bar e.g. [■■■■■□□□□□] (1200/2000)."""
        if maximum <= 0:
            return f"[{'■' * width}] ({value})"
        ratio = min(max(value / maximum, 0.0), 1.0)
        filled = int(round(ratio * width))
        empty = width - filled
        bar = "■" * filled + "□" * empty
        pct = int(ratio * 100)
        if ratio > 0.9:
            colored_bar = self.red(bar)
        elif ratio > 0.7:
            colored_bar = self.yellow(bar)
        else:
            colored_bar = self.green(bar)
        return f"[{colored_bar}] {value}/{maximum} ({pct}%)"


# Default global color manager instance
_DEFAULT_MANAGER = ColorManager()


def style(text: str, code: str, stream: TextIO | None = None) -> str:
    """Convenience functional wrapper matching existing Dream API."""
    mgr = ColorManager(stream) if stream is not None else _DEFAULT_MANAGER
    return mgr.style(text, code)
