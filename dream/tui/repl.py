"""Interactive REPL session manager for Dream Assistant v2.0."""

from __future__ import annotations

from collections.abc import Callable

from dream.agent import Dream
from dream.memory import MemoryStore
from dream.tui.banner import render_banner
from dream.tui.colors import ColorManager
from dream.tui.formatters import report_turn_activity
from dream.tui.prompter import TerminalPrompter


class InteractiveSession:
    """Manages the interactive terminal loop, slash commands, and telemetry."""

    def __init__(
        self,
        dream: Dream,
        store: MemoryStore,
        owner: str = "",
        quiet: bool = False,
        colors: ColorManager | None = None,
        output: Callable[[str], None] = print,
    ) -> None:
        self.dream = dream
        self.store = store
        self.owner = owner
        self.quiet = quiet
        self.colors = colors or ColorManager()
        self.output = output
        self.prompter = TerminalPrompter(self.colors)
        self.turn_count = 0

    def start(self, show_banner: bool = True) -> None:
        """Start the interactive REPL loop."""
        if show_banner:
            model_name = getattr(self.dream.backend, "model", "default")
            backend_type = self.dream.backend.__class__.__name__
            banner_text = render_banner(
                owner=self.owner,
                model=model_name,
                backend_info=backend_type,
                context_files_count=4,
                colors=self.colors,
            )
            self.output(banner_text)

        # Check due reminders at startup
        try:
            due = self.store.check_due_reminders()
            if due and not self.quiet:
                for r in due:
                    self.output(self.colors.yellow(f"[⏰ Reminder] {r.text}"))
        except Exception:
            pass

        while True:
            raw_input = self.prompter.read_input()
            if raw_input is None:
                self.output("\n" + self.colors.dim("Session terminated. Goodbye! / خدانگهدار"))
                break

            text = raw_input.strip()
            if not text:
                continue

            # Command routing
            if text.startswith(("/", "\\")):
                from dream.cli.commands import dispatch_command

                should_continue = dispatch_command(
                    text,
                    self.dream,
                    output=self.output,
                    quiet=self.quiet,
                    colors=self.colors,
                )
                if not should_continue:
                    break
                continue

            # Execute normal agent turn
            self.turn_count += 1
            try:
                turn = self.dream.run(text)
                if not self.quiet:
                    report_turn_activity(turn, output=self.output, colors=self.colors)
                self.output(turn.reply)
            except Exception as exc:
                self.output(self.colors.red(f"Error during agent turn: {exc}"))
