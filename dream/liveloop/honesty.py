"""Honest route snapshot: never pretend echo is a hosted model."""

from __future__ import annotations

from typing import Any


def snapshot(
    *,
    bar_provider: str | None = None,
    pane_provider: str | None = None,
    pane_model: str | None = None,
) -> dict[str, Any]:
    bar = (bar_provider or "echo").strip() or "echo"
    pane = (pane_provider or "").strip() or None
    model = (pane_model or "").strip() or None
    echo_bar = bar.lower() in {"echo", "echo (offline)"}
    mismatch = bool(pane and pane.lower() not in {bar.lower(), "echo"} and echo_bar)
    return {
        "bar_provider": bar,
        "pane_provider": pane,
        "pane_model": model,
        "echo_bar": echo_bar,
        "mismatch": mismatch,
        "honest": not mismatch,
        "note_en": (
            "The status bar follows Settings → active provider. "
            "A chat pane can use another model. This bar is not the pane."
            if mismatch
            else "Status bar and the declared pane agree, or no pane was declared."
        ),
        "note_fa": (
            "نوار وضعیت از ارائه‌دهندهٔ تنظیمات پیروی می‌کند. "
            "پنل چت می‌تواند مدل دیگری باشد. این نوار همان پنل نیست."
            if mismatch
            else "نوار وضعیت و پنل اعلام‌شده هم‌خوان‌اند، یا پنلی اعلام نشده."
        ),
    }
