"""Interactive slash command handler for Speech, Voice, and Emotion Engine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.speech.tools import (
    speech_list_voices,
    speech_text_to_speech,
)


def handle_speech_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/speech` or `/voice` slash commands in REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    parts = cmd_text.strip().split(maxsplit=2)
    subcmd = parts[1].lower() if len(parts) > 1 else "voices"

    if subcmd in ("voices", "list", "ls"):
        res = speech_list_voices()
        title = (
            "\U0001f399\ufe0f "
            "\u0635\u062f\u0627\u0647\u0627\u06cc "
            "\u0641\u0639\u0627\u0644 "
            "(Voice Personas):"
        )
        output(cm.bold(title))
        for v in res.get("voices", []):
            output(
                f"  \u2022 {cm.bold(v['voice_id'])}: {v['name']} "
                f"({v['language']}) [{cm.cyan(v['default_emotion'])}] - {v['description']}"
            )
        return True

    if subcmd in ("tts", "say", "speak"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0645\u062a\u0646 \u0631\u0627 "
                "\u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        text = parts[2]
        res = speech_text_to_speech(text=text)
        if res.get("success"):
            succ = (
                f"\u2713 \u0635\u0648\u062a "
                f"\u062a\u0648\u0644\u06cc\u062f "
                f"\u0634\u062f: {res.get('audio_path')} "
                f"({res.get('duration_seconds')}s)"
            )
            output(cm.green(succ))
        else:
            fail = f"\u2717 \u062e\u0637\u0627: {res.get('error')}"
            output(cm.red(fail))
        return True

    # Help
    h_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /speech:"
    )
    output(cm.bold(h_title))
    output(
        "  /speech voices                      - "
        "\u0641\u0647\u0631\u0633\u062a \u0635\u062f\u0627\u0647\u0627 / List voices"
    )
    output(
        "  /speech tts <text>                  - "
        "\u062a\u0628\u062f\u06cc\u0644 \u0645\u062a\u0646 / Text to speech"
    )
    return True
