"""Dream Command-Line Interface (CLI) package."""

from __future__ import annotations

from dream.cli.args import build_parser
from dream.cli.commands import (
    _COMMAND_ALIASES,
    _HELP_FRAGMENTS,
    _PHONE_ALLOWED_CANONICAL,
    _PHONE_POLICY,
    _PHONE_REFUSED_CANONICAL,
    KNOWN_COMMANDS,
    PHONE_COMMANDS,
    PHONE_HELP,
    TERMINAL_HELP,
    _closest_command,
    _format_repeat,
    _parse_natural_date_prefix,
    _parse_remind_args,
    _print_memories,
    dispatch_command,
)
from dream.cli.runner import run_cli, run_council_cli, run_demo

__all__ = [
    "KNOWN_COMMANDS",
    "PHONE_COMMANDS",
    "PHONE_HELP",
    "TERMINAL_HELP",
    "_COMMAND_ALIASES",
    "_HELP_FRAGMENTS",
    "_PHONE_ALLOWED_CANONICAL",
    "_PHONE_POLICY",
    "_PHONE_REFUSED_CANONICAL",
    "_closest_command",
    "_format_repeat",
    "_parse_natural_date_prefix",
    "_parse_remind_args",
    "_print_memories",
    "build_parser",
    "dispatch_command",
    "run_cli",
    "run_council_cli",
    "run_demo",
]
