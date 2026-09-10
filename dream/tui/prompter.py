"""Interactive prompt reader with multiline support and autocomplete hints."""

from __future__ import annotations

import difflib

from dream.tui.colors import ColorManager


class TerminalPrompter:
    """Handles terminal user inputs, multiline lines, and command matching."""

    def __init__(self, colors: ColorManager | None = None) -> None:
        self.colors = colors or ColorManager()

    def get_prompt_symbol(self, multiline: bool = False) -> str:
        if multiline:
            return self.colors.dim("... ")
        return self.colors.cyan("dream> ")

    def read_input(self, known_commands: tuple[str, ...] = ()) -> str | None:
        """Read a single line or multiline block from stdin."""
        try:
            first_line = input(self.get_prompt_symbol(multiline=False))
        except (EOFError, KeyboardInterrupt):
            return None

        # Multiline continuation check (line ending in backslash)
        if first_line.endswith("\\"):
            lines = [first_line[:-1]]
            while True:
                try:
                    cont = input(self.get_prompt_symbol(multiline=True))
                except (EOFError, KeyboardInterrupt):
                    break
                if cont.endswith("\\"):
                    lines.append(cont[:-1])
                else:
                    lines.append(cont)
                    break
            return "\n".join(lines)

        return first_line

    def suggest_command(self, query: str, known_commands: tuple[str, ...]) -> str | None:
        """Fuzzy match slash command."""
        matches = difflib.get_close_matches(query, known_commands, n=1, cutoff=0.55)
        return matches[0] if matches else None
