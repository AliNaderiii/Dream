"""Bilingual ASCII banner and terminal status telemetry header."""

from __future__ import annotations

from typing import Any

from dream.tui.colors import ColorManager

_BANNER_ART = r"""
  ____                               
 |  _ \ _ __ ___  __ _ _ __ ___  
 | | | | '__/ _ \/ _` | '_ ` _ \ 
 | |_| | | |  __/ (_| | | | | | |
 |____/|_|  \___|\__,_|_| |_| |_|
"""

DREAM_VERSION = "2.0.0"


def render_banner(
    owner: str = "",
    model: str = "echo",
    backend_info: str = "EchoBackend",
    context_files_count: int = 4,
    colors: ColorManager | None = None,
) -> str:
    """Render the startup banner with telemetry info and bilingual greeting."""
    cm = colors or ColorManager()
    lines: list[str] = []

    # Styled ASCII art
    art_colored = cm.cyan(_BANNER_ART.strip("\n"))
    lines.append(art_colored)

    # Title & Version
    title = f"Dream Assistant v{DREAM_VERSION} — Next-Gen Agent Engine"
    lines.append(cm.bold(title))
    lines.append(cm.dim("=" * len(title)))

    # Status Telemetry Card
    owner_str = owner if owner else "Local Owner"
    lines.append(f"  {cm.dim('•')} {cm.bold('Owner:')}          {owner_str}")
    lines.append(
        f"  {cm.dim('•')} {cm.bold('Backend / Model:')} {cm.green(model)} ({backend_info})"
    )
    lines.append(
        f"  {cm.dim('•')} {cm.bold('Context Memory:')} "
        f"{context_files_count} Tier-4 Files (SOUL, USER, MEMORY, AGENTS)"
    )
    lines.append(f"  {cm.dim('•')} {cm.bold('Security Floor:')} L1-L5 Multi-Layer Guard Active")

    # Bilingual Quick Start
    lines.append("")
    lines.append(
        f"  {cm.yellow('💡 راهنما:')} دستورات با {cm.cyan('/help')} | خروج با {cm.dim('/exit')}"
    )
    lines.append("")
    return "\n".join(lines)


def render_status_bar(telemetry: dict[str, Any], colors: ColorManager | None = None) -> str:
    """Render a one-line live status bar for the prompt footer."""
    cm = colors or ColorManager()
    model = telemetry.get("model", "default")
    turns = telemetry.get("turns", 0)
    memory_tokens = telemetry.get("memory_tokens", 0)
    return cm.dim(f"[{model} | Turns: {turns} | Context: {memory_tokens} chars]")
