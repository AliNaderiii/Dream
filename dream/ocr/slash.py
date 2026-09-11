"""Interactive slash command handler for Document OCR and Receipt Parsing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.ocr.tools import ocr_extract_document


def handle_ocr_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/ocr` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    parts = cmd_text.strip().split(maxsplit=2)
    subcmd = parts[1].lower() if len(parts) > 1 else "help"

    if subcmd in ("scan", "extract", "read"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0645\u0633\u06cc\u0631 \u0641\u0627\u06cc\u0644 "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        path = parts[2]
        res = ocr_extract_document(path)
        if res.get("success"):
            title = (
                "\U0001f4c4 "
                "\u0646\u062a\u06cc\u062c\u0647 "
                "\u0627\u0633\u062a\u062e\u0631\u0627\u062c OCR:"
            )
            output(cm.bold(title))
            output(f"  \u2022 \u0641\u0627\u06cc\u0644: {res.get('file_path')}")
            fields = res.get("extracted_fields", {})
            if fields:
                f_hdr = (
                    "\u0641\u06cc\u0644\u062f\u0647\u0627\u06cc "
                    "\u06a9\u0644\u06cc\u062f\u06cc:"
                )
                output(f"  {cm.cyan(f_hdr)}")
                for k, v in fields.items():
                    output(f"    - {k}: {v}")
        else:
            fail = f"\u2717 \u062e\u0637\u0627: {res.get('error')}"
            output(cm.red(fail))
        return True

    # Help
    h_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /ocr:"
    )
    output(cm.bold(h_title))
    output(
        "  /ocr scan <file_path>               - "
        "\u0627\u0633\u062a\u062e\u0631\u0627\u062c \u0645\u062a\u0646 \u0648 "
        "\u0627\u0637\u0644\u0627\u0639\u0627\u062a \u0633\u0646\u062f / Scan document"
    )
    return True
