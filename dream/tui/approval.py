"""Interactive terminal approval dialog for guarded and dangerous actions."""

from __future__ import annotations

from typing import Any

from dream.tui.colors import ColorManager


class TerminalApprovalPrompt:
    """Prompts the user interactively in TUI for authorization of guarded actions."""

    def __init__(self, colors: ColorManager | None = None) -> None:
        self.colors = colors or ColorManager()

    def request_approval(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: str = "guarded",
    ) -> bool:
        """Display authorization prompt and read user decision."""
        cm = self.colors
        badge = (
            cm.red("[DANGEROUS ACTION]")
            if risk_level == "dangerous"
            else cm.yellow("[GUARDED ACTION]")
        )

        prompt_box = [
            f"\n{badge} {cm.bold('مجوز اجرای ابزار / Tool Execution Approval Required')}",
            cm.dim("─" * 60),
            f"  • {cm.bold('ابزار / Tool:')}      {cm.cyan(tool_name)}",
            f"  • {cm.bold('سطح ریسک / Risk:')} {cm.bold(risk_level.upper())}",
            f"  • {cm.bold('پارامترها / Args:')}  {arguments}",
            cm.dim("─" * 60),
            (
                f"  {cm.green('[y] Allow Once (تأیید)')}  |  "
                f"{cm.red('[n] Deny (رد)')}  |  {cm.dim('[a] Always Allow')}"
            ),
        ]

        print("\n".join(prompt_box))
        try:
            choice = input(cm.yellow("انتخاب شما / Choice [y/n/a] (default: n): ")).strip().lower()
            if choice in ("y", "yes", "a", "always"):
                print(cm.green("✓ مجوز صادر شد. / Approved.\n"))
                return True
            print(cm.red("✗ درخواست لغو شد. / Denied.\n"))
            return False
        except (EOFError, KeyboardInterrupt):
            print(cm.red("\n✗ عملیات متوقف شد. / Cancelled.\n"))
            return False
