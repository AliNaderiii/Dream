"""Interactive command-line interface for Dream."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections.abc import Callable
from typing import Any, TextIO

from dream.agent import ApprovalPolicy, Dream, EchoBackend, Turn
from dream.memory import MemoryStore, normalize_fa
from dream.tools import REGISTRY

KNOWN_COMMANDS = (
    "/mem",
    "/mems",
    "/stats",
    "/forget",
    "/dedupe",
    "/pin",
    "/remind",
    "/reminders",
    "/unremind",
    "/skill",
    "/skills",
    "/tools",
    "/plan",
    "/usage",
    "/route",
    "/reset",
    "/learn",
    "/help",
    "/exit",
)

# Aliases: additional spellings accepted by dispatch and the phone.
_COMMAND_ALIASES: dict[str, str] = {
    "/reminder": "/remind",
    "/reminder-list": "/reminders",
    "/reminds": "/reminders",
}

# Help fragments: one per canonical command, single source for both helps.
_HELP_FRAGMENTS: dict[str, str] = {
    "/mem": "/mem QUERY",
    "/mems": "/mems",
    "/stats": "/stats",
    "/forget": "/forget ID",
    "/dedupe": "/dedupe [confirm]",
    "/pin": "/pin ID",
    "/remind": "/remind DATE TEXT [every N days|months]",
    "/reminders": "/reminders",
    "/unremind": "/unremind ID",
    "/skill": "/skill QUERY",
    "/skills": "/skills",
    "/tools": "/tools",
    "/plan": "/plan",
    "/usage": "/usage",
    "/route": "/route",
    "/reset": "/reset",
    "/learn": "/learn SOURCE",
    "/help": "/help",
    "/exit": "/exit",
}

# Phone policy: every KNOWN_COMMAND must have an entry with an explicit
# SECURITY ENGINEER reason. This is the single source for the phone surface;
# adding a new terminal command without a decision here breaks the parity test.
# Six previously-unreachable commands reviewed individually:
#   /dedupe  REFUSED — bulk destructive merge needs large-screen diff review
#   /pin     REFUSED — rare maintenance, keep phone surface minimal
#   /skill   ALLOWED — read-only skill search, needed for visibility
#   /skills  ALLOWED — read-only skill listing, needed for visibility
#   /stats   ALLOWED — read-only aggregate counts, no content
#   /tools   ALLOWED — read-only tool inventory, no execution
# S00 additions, all read-only and therefore phone-safe:
#   /plan    ALLOWED — read-only plan/price display, no billing action
#   /usage   ALLOWED — read-only ledger readout, no mutation
#   /route   ALLOWED — read-only privacy disclosure, no execution
_PHONE_POLICY: dict[str, tuple[bool, str]] = {
    "/mem": (True, "read-only memory search; safe for paired owner"),
    "/mems": (True, "read-only listing; safe"),
    "/stats": (True, "read-only aggregate counts; no content; safe"),
    "/forget": (True, "owner-authenticated archive; already allowed on phone"),
    "/dedupe": (False, "bulk destructive merge needs large-screen diff review; keep terminal-only"),
    "/pin": (False, "rare maintenance pinning; keep phone surface minimal"),
    "/remind": (True, "owner creates reminder; already allowed"),
    "/reminders": (True, "read-only reminder listing; already allowed"),
    "/unremind": (True, "owner deletes own reminder; already allowed"),
    "/skill": (True, "read-only skill search; needed for visibility; safe"),
    "/skills": (True, "read-only skill listing; needed for visibility; safe"),
    "/tools": (True, "read-only tool inventory; no execution; safe"),
    "/plan": (True, "read-only plan and price display; no billing action; safe"),
    "/usage": (True, "read-only ledger readout; no mutation; safe"),
    "/route": (True, "read-only privacy disclosure of the model route; safe"),
    "/reset": (True, "per-chat session reset; safe"),
    "/learn": (
        True,
        "owner turns a source into a skill; writes go through approval; safe",
    ),
    "/help": (True, "help is always allowed"),
    "/exit": (False, "terminal session control; not applicable to phone"),
}

_PHONE_ALLOWED_CANONICAL: frozenset[str] = frozenset(
    cmd for cmd, (allowed, _) in _PHONE_POLICY.items() if allowed
)
_PHONE_REFUSED_CANONICAL: frozenset[str] = frozenset(
    cmd for cmd, (allowed, _) in _PHONE_POLICY.items() if not allowed
)

# Full phone allowlist includes aliases where canonical is allowed.
PHONE_COMMANDS: frozenset[str] = frozenset(
    list(_PHONE_ALLOWED_CANONICAL)
    + [alias for alias, canon in _COMMAND_ALIASES.items() if canon in _PHONE_ALLOWED_CANONICAL]
)


def _build_help(allowed: frozenset[str]) -> str:
    parts = [_HELP_FRAGMENTS[cmd] for cmd in KNOWN_COMMANDS if cmd in allowed]
    base = "  ".join(parts)
    if "/remind" in allowed:
        base = base.replace(
            "/remind DATE TEXT [every N days|months]",
            "/remind DATE TEXT [every N days|months]  (DATE: YYYY-MM-DD or a Persian phrase)",
        )
    return base


PHONE_HELP: str = _build_help(_PHONE_ALLOWED_CANONICAL)
TERMINAL_HELP: str = _build_help(frozenset(KNOWN_COMMANDS))


def _style(text: str, code: str, stream: TextIO) -> str:
    """Colour text only when it will be read in an interactive terminal."""
    return f"\x1b[{code}m{text}\x1b[0m" if stream.isatty() else text


def _closest_command(command: str) -> str | None:
    """Return the closest known command, or ``None`` when nothing is close."""
    matches = difflib.get_close_matches(command, KNOWN_COMMANDS, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _print_memories(store: MemoryStore, output: Callable[[str], None]) -> None:
    memories = store.all()
    if not memories:
        output("No stored memories. Use the conversation to add one.")
        return
    for memory in memories:
        output(
            f"{memory.id}  {memory.kind:<10} importance={memory.importance:.2f}  {memory.content}"
        )


def _format_repeat(repeat_days, repeat_months) -> str:
    """Format repeat interval in Persian with brackets for visual separation.

    Persian uses singular noun after numbers, so "every 3 months" is
    "هر 3 ماه" (not ماه‌ها). Returns empty string for no repeat.
    """
    if repeat_days is not None:
        # هر N روز (every N days)
        return f"(\u0647\u0631 {repeat_days} \u0631\u0648\u0632)"
    if repeat_months is not None:
        # هر N ماه (every N months)
        return f"(\u0647\u0631 {repeat_months} \u0645\u0627\u0647)"
    return ""


# The /remind date slot accepts YYYY-MM-DD (Jalali year < 1700) or a natural
# Persian phrase. The Persian examples are backslash-u escapes:
# فردا / پانزدهم مهر / اول هر ماه.
_REMIND_USAGE = (
    "Unparseable date. Usage: /remind DATE TEXT [repeat] \u2014 DATE as "
    "YYYY-MM-DD (Jalali year <1700) or a Persian phrase like "
    "\u00ab\u0641\u0631\u062f\u0627\u00bb, \u00ab\u067e\u0627\u0646\u0632\u062f\u0647\u0645 "
    "\u0645\u0647\u0631\u00bb, \u00ab\u0627\u0648\u0644 \u0647\u0631 \u0645\u0627\u0647\u00bb"
)


def _parse_natural_date_prefix(argument: str):
    """Try progressively longer leading word-prefixes as a Persian date.

    The date must come first, matching the existing /remind grammar; the
    reminder text is whatever follows. Returns (due_at, rest, error): on
    success error is None; when nothing parses, the ambiguity error from the
    shortest prefix (the most specific, e.g. «مهر» needs a day) is returned
    verbatim, and everything else gets the usage message.
    """
    from dream.reminders import parse_persian_date

    tokens = argument.split()
    last_error = None
    for length in range(min(len(tokens), 6), 0, -1):
        prefix = " ".join(tokens[:length])
        try:
            due_at = parse_persian_date(prefix)
        except ValueError as exc:
            last_error = str(exc)
            continue
        return due_at, " ".join(tokens[length:]), None
    if last_error is not None and last_error.startswith("ambiguous date"):
        return None, None, last_error
    return None, None, _REMIND_USAGE


def _parse_remind_args(argument: str):
    """Parse /remind arguments.

    Returns (due_at, repeat_days, repeat_months, text, error).
    Accepts YYYY-MM-DD (year below 1700 is Jalali) or a natural Persian
    date phrase like «فردا» or «پانزدهم مهر».
    Repeat can appear before or after the text.
    """
    import re

    from dream.memory import normalize_fa
    from dream.reminders import parse_date_to_timestamp

    if not argument.strip():
        return None, None, None, None, _REMIND_USAGE
    # Normalize to fold Persian digits to Latin
    argument = normalize_fa(argument)
    # extract leading date
    m = re.match(r"^\s*(\d{4})\s*[-/.\s]\s*(\d{1,2})\s*[-/.\s]\s*(\d{1,2})\b", argument)
    if m:
        date_str = m.group(0).strip()
        rest = argument[m.end():].strip()
        try:
            due_at = parse_date_to_timestamp(date_str)
        except ValueError as exc:
            return None, None, None, None, (
                f"Invalid date: {exc}. Usage: /remind YYYY-MM-DD TEXT"
            )
    else:
        due_at, rest, error = _parse_natural_date_prefix(argument)
        if error is not None:
            return None, None, None, None, error

    repeat_days = None
    repeat_months = None

    def _consume(match, days=None, months=None):
        """Remove a matched repeat spec from rest and set the interval."""
        nonlocal rest, repeat_days, repeat_months
        repeat_days = days
        repeat_months = months
        rest = (rest[:match.start()] + rest[match.end():]).strip()

    # Ordered list of (pattern, days_value, months_value) tuples.
    # \u0647\u0631 = har, \u0631\u0648\u0632 = rooz, \u0645\u0627\u0647 = mah
    # \u0647\u0641\u062a\u0647 = hafte, \u0633\u0627\u0644 = sal
    _N = r"(\d+)"
    _PERSIAN_PATTERNS = [
        # har N rooz (every N days)
        (rf"\u0647\u0631\s+{_N}\s+\u0631\u0648\u0632", "days"),
        # har rooz (every day = 1 day)
        (r"\u0647\u0631\s+\u0631\u0648\u0632", ("days", 1)),
        # roozane (daily = 1 day)
        (r"\u0631\u0648\u0632\u0627\u0646\u0647", ("days", 1)),
        # har hafte (every week = 7 days)
        (r"\u0647\u0631\s+\u0647\u0641\u062a\u0647", ("days", 7)),
        # haftegi (weekly = 7 days)
        (r"\u0647\u0641\u062a\u06af\u06cc", ("days", 7)),
        # har N mah (every N months)
        (rf"\u0647\u0631\s+{_N}\s+\u0645\u0627\u0647", "months"),
        # harmah (every month, solid = 1 month)
        (r"\u0647\u0631\u0645\u0627\u0647", ("months", 1)),
        # har mah (every month = 1 month)
        (r"\u0647\u0631\s+\u0645\u0627\u0647", ("months", 1)),
        # mahiane (monthly variant = 1 month)
        (r"\u0645\u0627\u0647\u06cc\u0627\u0646\u0647", ("months", 1)),
        # mahane (monthly = 1 month)
        (r"\u0645\u0627\u0647\u0627\u0646\u0647", ("months", 1)),
        # har sal (every year = 12 months)
        (r"\u0647\u0631\s+\u0633\u0627\u0644", ("months", 12)),
        # salane (yearly = 12 months)
        (r"\u0633\u0627\u0644\u0627\u0646\u0647", ("months", 12)),
    ]

    matched = False
    for pattern, spec in _PERSIAN_PATTERNS:
        dm = re.search(pattern, rest)
        if dm:
            if spec == "days":
                _consume(dm, days=int(dm.group(1)))
            elif spec == "months":
                _consume(dm, months=int(dm.group(1)))
            elif isinstance(spec, tuple) and spec[0] == "days":
                _consume(dm, days=spec[1])
            else:
                _consume(dm, months=spec[1])
            matched = True
            break

    # English: every/repeat N days/months
    if not matched:
        dm = re.search(
            r"\b(?:every|repeat)\s+(\d+)\s+(days?|months?)\b",
            rest,
            re.IGNORECASE,
        )
        if dm:
            num = int(dm.group(1))
            unit = dm.group(2).lower()
            if unit.startswith("day"):
                _consume(dm, days=num)
            else:
                _consume(dm, months=num)
            matched = True

    # English: N days/months (only when text remains)
    if not matched:
        dm = re.search(r"\b(\d+)\s+(days?|months?)\b", rest, re.IGNORECASE)
        if dm:
            num = int(dm.group(1))
            unit = dm.group(2).lower()
            before = rest[:dm.start()].strip()
            after = rest[dm.end():].strip()
            if before or after:
                if unit.startswith("day"):
                    _consume(dm, days=num)
                else:
                    _consume(dm, months=num)
                matched = True

    # Flag: --months N, --days N, --repeat-months N, --repeat-days N
    if not matched:
        dm = re.search(r"--(?:repeat[-_]?)?months\s+(\d+)\b", rest, re.IGNORECASE)
        if dm:
            _consume(dm, months=int(dm.group(1)))
            matched = True
    if not matched:
        dm = re.search(r"--(?:repeat[-_]?)?days\s+(\d+)\b", rest, re.IGNORECASE)
        if dm:
            _consume(dm, days=int(dm.group(1)))
            matched = True

    # Reject any remaining -- option (unrecognized flag)
    dm = re.search(r"--\S+", rest)
    if dm:
        unknown = dm.group(0)
        return None, None, None, None, (
            f"Unrecognized option: {unknown}. "
            "Example: /remind 1405-06-01 \u0642\u0633\u0637 \u0648\u0627\u0645 "
            "--months 1"
        )

    if repeat_days == 0 or repeat_months == 0:
        return None, None, None, None, (
            "Repeat must be non-zero. Usage: /remind YYYY-MM-DD TEXT "
            "[every N days|every N months]"
        )
    if repeat_days is not None and repeat_months is not None:
        return None, None, None, None, "Repeat must be either days or months, not both."
    text = rest.strip()
    if not text:
        return None, None, None, None, (
            "Missing text. Usage: /remind YYYY-MM-DD TEXT "
            "[every N days|every N months]"
        )
    return due_at, repeat_days, repeat_months, text, None


# --------------------------------------------------------------------------
# Tool-activity reporting
#
# A model can claim «ذخیره شد» without ever calling remember_fact, or call it
# and misread a failure as success. Turn already records every call's name,
# arguments, and result; printing them to stderr is what makes the CLI honest.
# --------------------------------------------------------------------------

_ARGUMENT_LIMIT = 80
_DETAIL_LIMIT = 120


def _truncate(text: str, limit: int) -> str:
    """Clip text to ``limit`` characters, marking what was dropped."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _stderr_line(line: str) -> None:
    print(line, file=sys.stderr)


def _call_status(result: str) -> tuple[str, str]:
    """Classify a recorded tool result as ok, error, or blocked."""
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        return "error", "unparseable tool result"
    if not isinstance(payload, dict):
        return "ok", ""
    if payload.get("blocked"):
        return "blocked", str(payload.get("reason") or "")
    if payload.get("status") == "error" or "error" in payload:
        error = payload.get("error")
        if isinstance(error, dict):
            return "error", str(error.get("message") or error.get("type") or "")
        return "error", "" if error is None else str(error)
    return "ok", ""


def format_tool_line(name: str, arguments: dict[str, Any], result: str) -> str:
    """Render one recorded tool call as a compact one-line status."""
    rendered = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
    status, detail = _call_status(result)
    line = f"[tool] {name}({_truncate(rendered, _ARGUMENT_LIMIT)}) -> {status}"
    if detail:
        line += f": {_truncate(detail, _DETAIL_LIMIT)}"
    return line


def format_extraction_line(result: Any) -> str:
    """Render one compact status line for the extraction pass."""
    status = getattr(result, "status", "")
    if status == "facts_found":
        count = len(getattr(result, "facts", []))
        return f"[extraction] facts found: {count} fact{'s' if count != 1 else ''}"
    if status == "no_facts":
        return "[extraction] no durable facts"
    if status == "too_short":
        return "[extraction] skipped as too short"
    if status == "disabled":
        return "[extraction] disabled by environment"
    if status == "unparseable":
        return "[extraction] model output unparseable"
    if status == "error":
        detail = getattr(result, "raw_text", "")
        if detail:
            return f"[extraction] backend errored: {_truncate(str(detail), _DETAIL_LIMIT)}"
        return "[extraction] backend errored"
    if status == "abandoned":
        detail = getattr(result, "raw_text", "")
        if detail:
            return f"[extraction] abandoned: {_truncate(str(detail), _DETAIL_LIMIT)}"
        return "[extraction] abandoned: time budget exceeded"
    return f"[extraction] {status}"


def report_turn_activity(turn: Turn, output: Callable[[str], None] | None = None) -> None:
    """Print compact activity lines for tools, extraction, and stored memories.

    Defaults to stderr so the lines never pollute piped stdout output.
    """
    if output is None:
        output = _stderr_line
    for call in turn.tool_calls:
        output(
            format_tool_line(
                str(call.get("name", "")),
                call.get("arguments") or {},
                str(call.get("result", "")),
            )
        )
    injected = getattr(turn, "memories_injected", None)
    if injected is not None and len(injected) < len(turn.memories_used):
        output(
            f"[memory] recalled {len(turn.memories_used)}, injected {len(injected)} (block limit)"
        )
    if getattr(turn, "extraction", None) is not None:
        output(format_extraction_line(turn.extraction))
    if turn.memories_created:
        count = len(turn.memories_created)
        output(f"[memory] stored {count} fact{'s' if count != 1 else ''}")
    for memory in getattr(turn, "memories_superseded", []):
        output(f"[memory] superseded #{memory.id} ({memory.content})")
    for memory in getattr(turn, "memories_merged", []):
        output(f"[memory] merged into #{memory.id} (same fact, said differently)")
    for error in getattr(turn, "memory_errors", []):
        output(f"[memory] store failed: {_truncate(error, _DETAIL_LIMIT)}")


def dispatch_command(
    text: str,
    dream: Dream,
    output: Callable[[str], None] = print,
    quiet: bool = False,
) -> bool:
    """Dispatch one slash command. Return ``False`` when the session should end.

    A leading backslash is accepted as an alias for a leading slash, so
    Windows habits like ``\\mems`` and ``\\exit`` work too.
    """
    command, _, argument = text.partition(" ")
    argument = argument.strip()
    if command.startswith("\\"):
        command = "/" + command[1:]
    store = dream.store
    if command == "/mem":
        if not argument:
            output("Usage: /mem QUERY — provide words to search for.")
        else:
            hits = store.recall(argument, reinforce=False)
            if not hits:
                output("No matching memories found.")
            for memory in hits:
                output(f"[{memory.score:.3f}] {memory.id} {memory.kind}: {memory.content}")
    elif command == "/mems":
        _print_memories(store, output)
    elif command == "/stats":
        output(json.dumps(store.stats(), ensure_ascii=False, sort_keys=True))
    elif command == "/forget":
        try:
            memory_id = int(argument)
        except ValueError:
            output("Usage: /forget ID — ID must be a number.")
        else:
            output(
                "Memory archived." if store.forget(memory_id) else "No active memory has that ID."
            )
    elif command == "/dedupe":
        apply = argument.lower() == "confirm"
        result = store.cleanup_duplicates(dry_run=not apply)
        # Bracketed lines are diagnostics; the command reply itself is not.
        report = (lambda _line: None) if quiet else output
        verb = "would merge" if not apply else "merged"
        ending = "would remain" if not apply else "remain"
        report(
            f"[dedupe] {result['examined']} rows examined, {result['merged']} {verb}, "
            f"{result['remaining']} {ending}"
        )
        for older, newer, old_text, new_text in result["details"]:
            report(f"[dedupe] #{newer} into #{older}")
            report(f"    older: {old_text}")
            report(f"    newer: {new_text}")
        if not apply:
            report("[dedupe] dry run. nothing changed. add the confirm argument to apply.")
    elif command == "/pin":
        try:
            memory_id = int(argument)
        except ValueError:
            output("Usage: /pin ID — ID must be a number.")
        else:
            output("Memory pinned." if store.pin(memory_id) else "No active memory has that ID.")
    elif command in ("/remind", "/reminder"):
        due_at, repeat_days, repeat_months, text, error = _parse_remind_args(argument)
        if error:
            output(error)
        else:
            try:
                rem = store.add_reminder(text, due_at, repeat_days, repeat_months)
                from dream.reminders import format_jalali

                due_str = format_jalali(rem.due_at)
                rep = _format_repeat(rem.repeat_days, rem.repeat_months)
                rep_part = f" {rep}" if rep else ""
                output(f"Reminder #{rem.id} set for {due_str}{rep_part}: {rem.text}")
            except ValueError as exc:
                output(str(exc))
            except Exception as exc:
                output(f"Failed to add reminder: {exc}")
    elif command in ("/reminders", "/reminder-list", "/reminds"):
        include_all = argument.strip().lower() in ("all", "--all", "inactive")
        rems = store.list_reminders(include_inactive=include_all)
        if not rems:
            output("No reminders." if not include_all else "No reminders.")
        else:
            from dream.reminders import format_jalali

            for r in rems:
                due_str = format_jalali(r.due_at)
                rep = _format_repeat(r.repeat_days, r.repeat_months)
                rep_part = f" {rep}" if rep else ""
                status = "" if r.active else " [inactive]"
                output(f"{r.id}  {due_str}{rep_part}  {r.text}{status}")
    elif command == "/unremind":
        try:
            reminder_id = int(argument)
        except ValueError:
            output("Usage: /unremind ID \u2014 ID must be a number.")
        else:
            if store.delete_reminder(reminder_id):
                output(
                    f"Reminder #{reminder_id} deleted permanently. "
                    "This cannot be undone."
                )
            else:
                output(f"No reminder with ID {reminder_id} for this user.")
    elif command == "/skills":
        from dream import skills as skills_module

        loaded, problems = skills_module.load_skills()
        if not loaded and not problems:
            output("No skills yet. The assistant saves them with the save_skill tool.")
        for skill in loaded:
            output(f"{skill.name} — {skill.description} ({skill.filename})")
        for problem in problems:
            output(f"[broken] {problem.filename}: {problem.detail}")
    elif command == "/skill":
        if not argument:
            output("Usage: /skill QUERY — find the skill that applies to a request.")
        else:
            from dream import skills as skills_module

            ranked = skills_module.score_skills(argument, permissive=True)
            if not ranked:
                output("No skill matches that request.")
            else:
                for skill in ranked:
                    output(f"{skill.name} — {skill.description} ({skill.filename})")
                    for index, step in enumerate(skill.steps, start=1):
                        output(f"  {index}. {step}")
    elif command == "/tools":
        for name, registered in sorted(REGISTRY.items()):
            output(f"{name}: {registered.risk}")
    elif command == "/plan":
        from dream.commerce import current_plan_text

        output(current_plan_text())
    elif command == "/usage":
        from dream.commerce import usage_text

        output(usage_text())
    elif command == "/route":
        from dream.router import route_text

        output(route_text())
    elif command == "/reset":
        dream.reset_session()
        output("Session context cleared; long-term memories remain.")
    elif command == "/learn":
        turn = dream.run(text)
        if not quiet:
            report_turn_activity(turn)
        output(turn.reply)
    elif command == "/help":
        output(TERMINAL_HELP)
    elif command == "/exit":
        return False
    else:
        from dream import skills as skills_module

        stack = skills_module.parse_slash_stack(text)
        if stack.invoked:
            turn = dream.run(text)
            if not quiet:
                report_turn_activity(turn)
            output(turn.reply)
            return True
        suggestion = _closest_command(command)
        hint = f" Did you mean {suggestion}?" if suggestion else ""
        output(f"Unknown command: {command}.{hint} Type /help to see available commands.")
    return True


def run_demo(db_path: str = ":memory:", output: Callable[[str], None] = print) -> None:
    """Run an offline, deterministic tour of Dream's core capabilities."""
    with MemoryStore(db_path) as store:
        dream = Dream(store, EchoBackend())
        output("1. Seeding memories across semantic, episodic, and procedural kinds")
        store.remember("I prefer dark coffee", kind="semantic", tags=["coffee"])
        store.remember("Visited Tehran coffee shop today", kind="episodic", tags=["coffee"])
        store.remember(
            "Answer Persian questions in Persian first", kind="procedural", tags=["language"]
        )
        output("2. Hybrid retrieval for 'coffee':")
        for memory in store.recall("coffee"):
            output(f"   relevance={memory.score:.3f}  {memory.content}")
        arabic = "مي‌خواهم كتاب"
        persian = "می‌خواهم کتاب"
        output("3. Normalisation:")
        output(f"   Arabic forms  → {normalize_fa(arabic)}")
        output(f"   Persian forms → {normalize_fa(persian)}")
        output("   This matters because equivalent spellings retrieve the same stored memory.")
        output("4. Agent tool loop:")
        for question in ("What time is it?", "What is 12 × 3?"):
            turn = dream.run(question)
            output(f"   {question} {turn.reply}")

        class DangerousDemoBackend:
            def chat(self, messages, tools=None):
                if messages[-1]["role"] == "tool":
                    return {"content": "The dangerous command was refused.", "tool_calls": []}
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "demo-shell",
                            "name": "run_shell",
                            "arguments": {"command": "echo should-not-run"},
                        }
                    ],
                }

        output("5. Approval gate:")
        dangerous = Dream(store, DangerousDemoBackend(), ApprovalPolicy())
        turn = dangerous.run("Run a shell command")
        output(f"   {turn.tool_calls[0]['result']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dream interactive assistant")
    parser.add_argument("--backend", choices=("echo", "openai", "ollama"), default="echo")
    parser.add_argument("--owner", default="", help="Optional owner name for the session")
    parser.add_argument("--db", default="data/dream.db", help="SQLite database path")
    parser.add_argument(
        "--bridge",
        action="store_true",
        help="Start the JSON-RPC sidecar (stdin/stdout) instead of the interactive CLI",
    )
    parser.add_argument(
        "--demo", action="store_true", help="Run the offline demonstration and exit"
    )
    parser.add_argument("--memories", action="store_true", help="List memories at startup")
    parser.add_argument(
        "--yolo", action="store_true", help="Allow dangerous tools without prompting"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the [tool]/[memory] activity lines on stderr",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Show the active plan, currency, and price, then exit",
    )
    parser.add_argument(
        "--usage",
        action="store_true",
        help="Show ledger usage for the active plan, then exit",
    )
    parser.add_argument(
        "--route",
        action="store_true",
        help="Show the active model route and whether data leaves the machine, then exit",
    )
    parser.add_argument(
        "--council",
        metavar="TOPIC",
        help="Run an offline echo council (proposer → critic → judge) on TOPIC and exit",
    )
    return parser


def run_council_cli(topic: str, output: Callable[[str], None] = print) -> int:
    """Run one echo council to completion and print its three roles + winner.

    The council is opt-in and offline by default (echo members), and it
    respects the active plan's usage ledger exactly like a normal turn: a
    metered plan consumes the council's member turns once, up front.
    ``--demo`` never reaches this function.
    """
    import asyncio

    from dream.council import CouncilSpec, get_council, run_council
    from dream.subagents import SubAgentManager

    async def scenario() -> int:
        manager = SubAgentManager()
        result = run_council(manager, CouncilSpec(prompt=topic))
        if result.refusal is not None:
            # A refused council (quota) returns the ledger's Persian reply.
            output(f"{result.refusal}")
            return 1
        output(f"Council {result.council_id}:")
        await manager.wait_pipeline(result.pipeline_id, timeout=30.0)
        fresh = get_council(manager, result.council_id)
        if fresh is None or fresh.winner is None:
            output("Council did not finish.")
            return 1
        for member in fresh.members:
            excerpt = (member.result or "").replace("\n", " ")
            output(f"  [{member.role}] ({member.provider}) {excerpt[:200]}")
        output(f"  winner: {fresh.winner}")
        output(f"  {fresh.sentence_en}")
        output(f"  {fresh.sentence_fa}")
        return 0

    return asyncio.run(scenario())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        run_demo(args.db)
        return 0
    if args.plan:
        from dream.commerce import current_plan_text

        print(current_plan_text())
        return 0
    if args.usage:
        from dream.commerce import usage_text

        print(usage_text())
        return 0
    if args.route:
        from dream.router import route_text

        print(route_text())
        return 0
    if args.council:
        return run_council_cli(args.council)
    if args.bridge:
        # Start the sidecar instead of the interactive CLI. The bridge runs its
        # own event loop over stdin/stdout; nothing below this branch runs.
        from dream.bridge.server import run_stdio

        return run_stdio()
    policy = ApprovalPolicy()
    if args.yolo:
        policy.auto_approve.add("dangerous")
        policy.always_ask.discard("dangerous")
        print(_style("WARNING: --yolo auto-approves dangerous tools.", "31;1", sys.stdout))
    from dream.agent import build_backend

    try:
        with MemoryStore(args.db) as store:
            dream = Dream(store, build_backend(args.backend), policy)
            # startup due check: find everything due, show it, mark it
            try:
                due = store.check_due_reminders()
            except Exception:
                due = []
            if due and not args.quiet:
                for _r in due:
                    print(f"[reminder] {_r.text}", file=sys.stderr)
            if args.memories:
                _print_memories(store, print)
            owner = f", {args.owner}" if args.owner else ""
            print(_style(f"Dream is ready{owner}. Type /help for commands.", "36", sys.stdout))
            while True:
                try:
                    text = input("> ")
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye.")
                    break
                if not text.strip():
                    continue
                if text.startswith(("/", "\\")):
                    if not dispatch_command(text, dream, output=print, quiet=args.quiet):
                        break
                    continue
                turn = dream.run(text)
                if not args.quiet:
                    report_turn_activity(turn)
                print(turn.reply)
    except OSError as exc:
        print(
            f"Could not open Dream database: {exc}. Try --db PATH with a writable location.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
