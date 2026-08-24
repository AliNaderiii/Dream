"""A small, schema-driven tool registry with explicit risk tiers.

Tools are ordinary Python functions.  Their callable signatures are the single
source of truth for provider schemas, preventing a hand-maintained schema from
drifting away from the code that ultimately receives model arguments.
"""

from __future__ import annotations

import ast
import inspect
import ipaddress
import json
import logging
import os
import socket
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from dream.memory import normalize_fa
from dream.security.blocklist import scan as _floor_scan
from dream.security.engine import SHELL_COMMAND_TOOLS as _FLOOR_COMMAND_TOOLS

__all__ = [
    "REGISTRY",
    "Tool",
    "_safe_path",
    "anthropic_schemas",
    "calculate",
    "execute",
    "get_datetime",
    "list_notes",
    "apply_skill_proposal",
    "delete_skill",
    "discard_skill_proposal",
    "edit_skill",
    "list_skills",
    "save_skill_bundle",
    "openai_schemas",
    "read_note",
    "read_page",
    "run_shell",
    "save_skill",
    "search_web",
    "send_email",
    "skill_view",
    "tool",
    "use_skill",
    "write_note",
]

RISKS = frozenset({"safe", "guarded", "dangerous"})
WORKSPACE_ROOT = Path(os.environ.get("DREAM_WORKSPACE_ROOT", Path.cwd())).resolve()


@dataclass(frozen=True, slots=True)
class Tool:
    """A registered callable and the schema derived from its signature."""

    name: str
    function: Callable[..., Any]
    description: str
    schema: dict[str, Any]
    risk: str


REGISTRY: dict[str, Tool] = {}
logger = logging.getLogger(__name__)


def _param_descriptions(docstring: str) -> dict[str, str]:
    """Extract reStructuredText ``:param name: text`` descriptions."""
    descriptions: dict[str, str] = {}
    for line in inspect.cleandoc(docstring).splitlines():
        line = line.strip()
        if not line.startswith(":param ") or ":" not in line[7:]:
            continue
        name, description = line[7:].split(":", 1)
        descriptions[name.strip()] = description.strip()
    return descriptions


def _union_json_type(args: tuple[Any, ...]) -> dict[str, Any]:
    """Describe a union, unwrapping ``X | None`` to the schema for ``X``.

    An optional parameter is still the type it wraps: ``list | None`` accepts a
    list, so a model told it is a ``string`` will send the wrong thing.
    """
    members = [arg for arg in args if arg is not type(None)]
    if not members:
        return {"type": "null"}
    if len(members) == 1:
        return _json_type(members[0])
    return {"anyOf": [_json_type(member) for member in members]}


def _json_type(annotation: Any) -> dict[str, Any]:
    """Translate the supported Python annotations to JSON Schema."""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        return _union_json_type(get_args(annotation))
    if origin is Literal:
        values = list(get_args(annotation))
        schema: dict[str, Any] = {"enum": values}
        if values:
            schema["type"] = _json_type(type(values[0]))["type"]
        return schema
    if origin is list or annotation is list:
        return {"type": "array"}
    if origin is dict or annotation is dict:
        return {"type": "object"}
    types = {str: "string", int: "integer", float: "number", bool: "boolean"}
    return {"type": types.get(annotation, "string")}


def tool(*, risk: str = "safe") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a function and derive its input schema from type hints."""
    if risk not in RISKS:
        raise ValueError(f"risk must be one of {sorted(RISKS)}, got {risk!r}")

    def register(function: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(function)
        hints = get_type_hints(function)
        descriptions = _param_descriptions(function.__doc__ or "")
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, parameter in signature.parameters.items():
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                continue
            property_schema = _json_type(hints.get(name, parameter.annotation))
            if name in descriptions:
                property_schema["description"] = descriptions[name]
            properties[name] = property_schema
            if parameter.default is inspect.Parameter.empty:
                required.append(name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        REGISTRY[function.__name__] = Tool(
            name=function.__name__,
            function=function,
            description=inspect.cleandoc(function.__doc__ or "").split("\n\n", 1)[0],
            schema=schema,
            risk=risk,
        )
        return function

    return register


def openai_schemas(registry: Mapping[str, Tool] | None = None) -> list[dict[str, Any]]:
    """Return registered tools in OpenAI's function-tool format.

    ``registry`` narrows the export to a private table. Subagents are granted a
    subset of the tools their parent holds, and the model must not be told
    about capabilities it will be refused, so the schema list and the dispatch
    table have to come from the same mapping.
    """
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.schema},
        }
        for t in (REGISTRY if registry is None else registry).values()
    ]


def anthropic_schemas(registry: Mapping[str, Tool] | None = None) -> list[dict[str, Any]]:
    """Return registered tools in Anthropic's tool format."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema}
        for t in (REGISTRY if registry is None else registry).values()
    ]


# Windows reserved device names: case-insensitive, extension does not release.
# 22 base names; comparison uses the stem before the first dot after Persian
# folding (normalize_fa) so Persian digits folded to Latin are caught.
_RESERVED_DEVICE_NAMES: frozenset[str] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *{f"com{i}" for i in range(1, 10)},
        *{f"lpt{i}" for i in range(1, 10)},
    }
)


def _reserved_stem(name: str) -> str:
    """Return the lower-cased stem before the first dot after folding."""
    folded = normalize_fa(name).lower().strip()
    # Strip trailing dots/spaces as Windows does before lookup.
    folded = folded.rstrip(" .")
    if not folded:
        return ""
    stem = folded.split(".")[0].strip()
    return stem


def _is_reserved_name(name: str) -> bool:
    """Whether *name* is a Windows reserved device name."""
    return _reserved_stem(name) in _RESERVED_DEVICE_NAMES


def _check_reserved_path(rel: str) -> None:
    """Raise ValueError if any path component is a reserved device name."""
    # Check trailing dot/space hazard (Windows collision).
    stripped = rel.strip()
    if stripped.endswith(".") or stripped.endswith(" "):
        raise ValueError(f"path must not end with a trailing dot or space: {rel!r}")
    # Split on both separators to catch every component.
    parts = rel.replace("\\", "/").split("/")
    for part in parts:
        if not part or part in (".", ".."):
            continue
        # Component ending with dot/space is a hazard even if not reserved.
        if part.endswith(".") or part.endswith(" "):
            raise ValueError(f"path component must not end with a trailing dot or space: {rel!r}")
        if _is_reserved_name(part):
            raise ValueError(f"reserved device name is not allowed: {rel!r}")


def _safe_path(rel: str) -> Path:
    """Resolve a relative workspace path, rejecting every escape attempt."""
    _check_reserved_path(rel)
    candidate = Path(rel)
    if candidate.is_absolute():
        raise PermissionError("absolute paths are not permitted")
    path = (WORKSPACE_ROOT / candidate).resolve()
    try:
        path.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise PermissionError("path escapes the workspace root") from exc
    return path


@tool(risk="safe")
def get_datetime(timezone_name: str = "Asia/Tehran") -> str:
    """Return the current Jalali date and local time for an IANA time zone.

    :param timezone_name: IANA zone name, such as ``Asia/Tehran``.
    """
    from dream.jalali import gregorian_to_jalali

    moment = datetime.now(ZoneInfo(timezone_name))
    jy, jm, jd = gregorian_to_jalali(moment.year, moment.month, moment.day)
    digits = str.maketrans(
        "0123456789",
        "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9",
    )
    date = f"{jy:04d}/{jm:02d}/{jd:02d}".translate(digits)
    clock = f"{moment.hour:02d}:{moment.minute:02d}".translate(digits)
    zone = "\u062a\u0647\u0631\u0627\u0646" if timezone_name == "Asia/Tehran" else timezone_name
    return (
        "\u0627\u0645\u0631\u0648\u0632 "
        f"{date}"
        "\u060c \u0633\u0627\u0639\u062a "
        f"{clock}"
        " \u0628\u0647 \u0648\u0642\u062a "
        f"{zone}"
        " \u0627\u0633\u062a."
    )


# Network tools are deliberately small, bounded, and off by default.  The caps
# cover bytes received, not only the decoded final text, so an oversized remote
# response cannot sit in memory before it is rejected or shortened.
NETWORK_TIMEOUT_SECONDS = 10
SEARCH_RESPONSE_CAP = 100_000
PAGE_RESPONSE_CAP = 250_000
PAGE_TEXT_CAP = 200_000
_NETWORK_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})
NETWORK_DISABLED_MESSAGE = (
    "\u0645\u0627\u0644\u06a9 \u062f\u0633\u062a\u0631\u0633\u06cc "
    "\u0634\u0628\u06a9\u0647 \u0631\u0627 \u0641\u0639\u0627\u0644 "
    "\u0646\u06a9\u0631\u062f\u0647 \u0627\u0633\u062a."
)
NETWORK_REFUSAL_MESSAGE = (
    "\u0627\u0645\u06a9\u0627\u0646 \u062f\u0631\u06cc\u0627\u0641\u062a "
    "\u0627\u06cc\u0646\u062a\u0631\u0646\u062a\u06cc \u0646\u06cc\u0633\u062a."
)


class _AddressRefused(ValueError):
    """An untrusted model-selected URL failed Dream's network boundary."""


def _network_enabled() -> bool:
    """Whether the owner explicitly enabled the two network tools."""
    return os.environ.get("DREAM_ALLOW_NETWORK", "").strip().lower() in _NETWORK_ENABLED_VALUES


def _validate_network_url(address: str) -> str:
    """Allow only public HTTP(S) destinations, resolving every hostname now."""
    parsed = urlsplit(address)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise _AddressRefused("unsupported URL")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise _AddressRefused("internal destination is not allowed")
    if parsed.username or parsed.password:
        raise _AddressRefused("credentials in URL are not allowed")
    try:
        literal = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise _AddressRefused("internal destination is not allowed")
        return address
    try:
        candidates = socket.getaddrinfo(
            parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except (OSError, ValueError) as exc:
        raise _AddressRefused("destination could not be resolved") from exc
    if not candidates:
        raise _AddressRefused("destination could not be resolved")
    for candidate in candidates:
        try:
            destination = ipaddress.ip_address(candidate[4][0])
        except ValueError as exc:
            raise _AddressRefused("destination is invalid") from exc
        # is_global excludes private, loopback, link-local, reserved,
        # multicast, and unspecified ranges — all unsuitable for a model URL.
        if not destination.is_global:
            raise _AddressRefused("internal destination is not allowed")
    return address


class _RestrictedRedirectHandler(HTTPRedirectHandler):
    """Reapply URL validation before urllib follows each redirect target."""

    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Request | None:
        del fp, code, msg, headers
        _validate_network_url(newurl)
        return super().redirect_request(req, None, 302, "Found", {}, newurl)


def _default_open_network_request(request: Request, timeout: float) -> Any:
    """Open through the redirect validator rather than urllib's blind default."""
    return build_opener(_RestrictedRedirectHandler()).open(request, timeout=timeout)


# Tests patch this seam; production starts with the standard-library opener.
_open_network_request: Callable[[Request, float], Any] = _default_open_network_request


class _ReadableText(HTMLParser):
    """Dependency-free, conservative conversion of HTML into visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "noscript"}:
            self._ignored_depth += 1
        elif tag.lower() in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def _strip_markup(value: str) -> str:
    parser = _ReadableText()
    parser.feed(value)
    parser.close()
    return parser.text()


def _read_capped(response: Any, cap: int) -> tuple[bytes, bool]:
    """Read at most *cap* bytes plus one marker byte, never an unbounded body."""
    chunks: list[bytes] = []
    remaining = cap + 1
    while remaining:
        chunk = response.read(min(8192, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    body = b"".join(chunks)
    return body[:cap], len(body) > cap


def _fetch(address: str, cap: int) -> tuple[bytes, bool]:
    """Validate and fetch one public URL with hard request and response limits."""
    _validate_network_url(address)
    request = Request(address, headers={"User-Agent": "dream-assistant/0.1.0"})
    with _open_network_request(request, NETWORK_TIMEOUT_SECONDS) as response:
        # A handler validates every redirect before it is followed; geturl is
        # validated again so injected/custom openers cannot bypass the boundary.
        _validate_network_url(response.geturl())
        return _read_capped(response, cap)


def _related_topics(value: object) -> list[tuple[str, str]]:
    """Flatten DuckDuckGo's related-topic groups into at most four safe rows."""
    results: list[tuple[str, str]] = []
    if not isinstance(value, list):
        return results
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("Topics"), list):
            results.extend(_related_topics(item["Topics"]))
        elif isinstance(item, dict):
            title, address = item.get("Text"), item.get("FirstURL")
            if isinstance(title, str) and isinstance(address, str):
                results.append((_strip_markup(title), address))
        if len(results) >= 4:
            break
    return results[:4]


@tool(risk="guarded")
def search_web(query: str) -> str:
    """Search the web for a concise answer and a few related public links.

    :param query: Search terms in the owner's language.
    """
    if not _network_enabled():
        return NETWORK_DISABLED_MESSAGE
    try:
        encoded = urlencode({"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"})
        body, _ = _fetch(f"https://api.duckduckgo.com/?{encoded}", SEARCH_RESPONSE_CAP)
        payload = json.loads(body.decode("utf-8", "replace"))
        answer = _strip_markup(str(payload.get("AbstractText", ""))).strip()
        topics = _related_topics(payload.get("RelatedTopics"))
        if not answer and not topics:
            return NETWORK_REFUSAL_MESSAGE
        lines = [answer] if answer else []
        lines.extend(f"- {title}: {address}" for title, address in topics)
        return "\n".join(lines)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, _AddressRefused):
        return NETWORK_REFUSAL_MESSAGE


@tool(risk="guarded")
def read_page(address: str) -> str:
    """Read a public web page as plain text, with a stated truncation cap.

    :param address: Public HTTP or HTTPS address to read.
    """
    if not _network_enabled():
        return NETWORK_DISABLED_MESSAGE
    try:
        body, response_truncated = _fetch(address, PAGE_RESPONSE_CAP)
        text = _strip_markup(body.decode("utf-8", "replace"))
        text_truncated = len(text) > PAGE_TEXT_CAP
        if text_truncated:
            text = text[:PAGE_TEXT_CAP]
        if not text:
            return NETWORK_REFUSAL_MESSAGE
        if response_truncated or text_truncated:
            return f"{text}\n\n[truncated at {PAGE_TEXT_CAP} characters]"
        return text
    except (OSError, ValueError, UnicodeError, _AddressRefused):
        return NETWORK_REFUSAL_MESSAGE


_ALLOWED_BINARY_OPERATORS: dict[type[ast.operator], Callable[[int | float, int | float], Any]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}
_ALLOWED_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[int | float], Any]] = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}


def _calculate_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY_OPERATORS:
        return _ALLOWED_BINARY_OPERATORS[type(node.op)](
            _calculate_node(node.left), _calculate_node(node.right)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPERATORS:
        return _ALLOWED_UNARY_OPERATORS[type(node.op)](_calculate_node(node.operand))
    raise ValueError("expression contains an unsupported operation")


@tool(risk="safe")
def calculate(expression: str) -> int | float:
    """Evaluate a basic arithmetic expression without executing code.

    :param expression: Arithmetic using numbers, parentheses and allowed operators.
    """
    expression = normalize_fa(expression).translate(str.maketrans({"×": "*", "÷": "/"}))
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("invalid arithmetic expression") from exc
    return _calculate_node(parsed.body)


@tool(risk="safe")
def read_note(filename: str) -> str:
    """Read a UTF-8 text file from the workspace.

    :param filename: Relative path of the note to read.
    """
    return _safe_path(filename).read_text(encoding="utf-8")


@tool(risk="safe")
def list_notes() -> list[str]:
    """List regular files in the workspace, relative to its root."""
    return sorted(
        str(path.relative_to(WORKSPACE_ROOT))
        for path in WORKSPACE_ROOT.rglob("*")
        if path.is_file()
    )


@tool(risk="guarded")
def write_note(filename: str, content: str) -> str:
    """Write UTF-8 text to a workspace file.

    :param filename: Relative path of the note to write.
    :param content: Exact text to store in the note.
    """
    from dream.security.pathsafety import check_write_path

    path = _safe_path(filename)
    # L4 second layer (SEC Stage C): even inside the workspace, sensitive
    # paths (credentials, stores, system dirs) are never writable.
    check_write_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"wrote {path.relative_to(WORKSPACE_ROOT)}"


@tool(risk="guarded")
def save_skill(name: str, description: str, steps: list) -> dict[str, Any]:
    """Save a reusable skill: a named procedure to follow in later requests.

    The skill becomes a plain text file inside ``skills/`` in the workspace
    that the owner can read and correct by hand. The description must say
    when the skill applies; it is what future requests are matched against.

    :param name: Skill name; also the file name, so path characters are refused.
    :param description: When this skill applies, in the owner's words.
    :param steps: Ordered steps the assistant should follow.
    """
    from dream import skills  # deferred: dream.skills imports this module

    cleaned = skills.validate_name(name)
    was_present = (skills._skills_dir() / f"{cleaned}{skills.SKILL_SUFFIX}").exists()
    filename = skills.save_skill(cleaned, description, steps)
    return {"filename": filename, "status": "updated" if was_present else "created"}


@tool(risk="safe")
def use_skill(query: str) -> dict[str, Any]:
    """Find the stored skill that applies to a request and return its steps.

    Reading a skill never runs anything: the steps are text the assistant
    follows using its ordinary tools and their ordinary approvals.

    :param query: The request to match, in any wording.
    """
    from dream import skills  # deferred: dream.skills imports this module

    skill = skills.find_skill(query)
    if skill is None:
        return {"match": None}
    try:
        from dream.skills.store import get_ledger

        with get_ledger() as ledger:
            ledger.log_use(skill.name, "success", duration_ms=0.0, source="use_skill")
    except Exception:
        pass
    return {
        "match": {
            "name": skill.name,
            "description": skill.description,
            "steps": list(skill.steps),
            "filename": skill.filename,
        }
    }


@tool(risk="safe")
def list_skills() -> dict[str, Any]:
    """List every stored skill, plus any file that failed to load."""
    from dream import skills  # deferred: dream.skills imports this module

    loaded, problems = skills.load_skills()
    return {
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "steps": list(skill.steps),
                "filename": skill.filename,
            }
            for skill in loaded
        ],
        "problems": [
            {"filename": problem.filename, "detail": problem.detail} for problem in problems
        ],
    }


@tool(risk="safe")
def skill_view(name: str) -> dict[str, Any]:
    """Load one installed skill's body. Catalog entries never include the body.

    :param name: Skill name or slash name (for example ``ocr-and-documents``).
    """
    from dream import skills  # deferred: dream.skills imports this module

    return skills.view_skill(name)


@tool(risk="guarded")
def edit_skill(name: str, description: str, body: str) -> dict[str, Any]:
    """Create or version a SKILL.md skill. Never silently overwrites history.

    :param name: Hyphen-case skill name (folder name).
    :param description: When this skill applies; at most 60 characters.
    :param body: Markdown instructions. Do not invent commands.
    """
    from dream import skills  # deferred: dream.skills imports this module

    return skills.edit_skill(name, description, body)


@tool(risk="guarded")
def delete_skill(name: str) -> dict[str, Any]:
    """Delete the current file for an installed skill. Version history is kept.

    :param name: Skill name or slash name.
    """
    from dream import skills  # deferred: dream.skills imports this module

    return skills.delete_skill(name)


@tool(risk="guarded")
def save_skill_bundle(
    name: str,
    description: str,
    body: str,
    references: dict | None = None,
) -> dict[str, Any]:
    """Save a knowledge-base skill (SKILL.md plus references/). Merges on re-learn.

    :param name: Hyphen-case skill name.
    :param description: When this skill applies; at most 60 characters.
    :param body: Lean markdown instructions.
    :param references: Optional map of topic name to distilled markdown.
    """
    from dream.skills.learn import install_skill_bundle

    return install_skill_bundle(name, description, body, references)


@tool(risk="guarded")
def apply_skill_proposal(proposal_id: str) -> dict[str, Any]:
    """Apply an approved post-task skill proposal. Denial must not call this.

    :param proposal_id: Identifier from the proposal notice.
    """
    from dream.skills.propose import apply_proposal

    return apply_proposal(proposal_id)


@tool(risk="safe")
def discard_skill_proposal(proposal_id: str) -> dict[str, Any]:
    """Discard a pending skill proposal. Nothing is written.

    :param proposal_id: Identifier from the proposal notice.
    """
    from dream.skills.propose import discard_proposal

    discarded = discard_proposal(proposal_id)
    return {"discarded": discarded, "proposal_id": proposal_id}


@tool(risk="guarded")
def create_reminder(
    date: str, text: str, repeat_days: int | None = None, repeat_months: int | None = None
) -> dict[str, Any]:
    """Create a durable reminder for the owner.

    The reminder fires on the given date and is stored per-owner.

    :param date: Due date as Jalali YYYY-MM-DD (year <1700) or a natural
        Persian phrase. Pure date only; time words cause refusal.
    :param text: Reminder text, what to remind about.
    :param repeat_days: Repeat every N days (optional).
    :param repeat_months: Repeat every N months (optional).
    """
    raise RuntimeError(
        "create_reminder requires a Dream instance; create a Dream first"
    )


@tool(risk="guarded")
def cancel_reminder(text: str, date: str | None = None) -> dict[str, Any]:
    """Cancel one of the owner's reminders, by text and an optional date.

    A row is removed only when the text and date identify exactly one
    active reminder; otherwise the tool refuses and names the candidates
    in Persian, touching nothing.

    :param text: Reminder text as the owner says it; a unique fragment is
        accepted.
    :param date: Optional due date as Jalali YYYY-MM-DD (year <1700) or a
        natural Persian phrase. Pure date only; time words cause refusal.
    """
    raise RuntimeError(
        "cancel_reminder requires a Dream instance; create a Dream first"
    )


@tool(risk="dangerous")
def run_shell(command: str, timeout: int = 30) -> dict[str, Any]:
    """Run a shell command after explicit human approval.

    :param command: Shell command to run.
    :param timeout: Maximum execution time in seconds.
    """
    # ``shell=True`` is the entire point of this tool (pipes, redirection and
    # compound commands). It is gated behind the ``dangerous`` risk tier, which
    # the approval policy refuses to execute without an interactive approver,
    # so the shell is only ever invoked with explicit human consent.
    completed = subprocess.run(  # nosec B602
        command,
        shell=True,
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


@tool(risk="dangerous")
def send_email(to: str, subject: str, body: str) -> dict[str, str]:
    """Describe an email that would be sent; this stub never sends mail.

    :param to: Intended recipient address.
    :param subject: Intended email subject.
    :param body: Intended email body.
    """
    return {
        "status": "dry-run",
        "message": f"Would send email to {to!r} with subject {subject!r}",
        "body": body,
    }


def _failure_payload(error_type: str, message: str) -> dict[str, Any]:
    """Build an error payload that cannot be mistaken for a result.

    The agent feeds this string straight back to the model. A bare
    ``{"error": ...}`` is easy for a small model to skim past and narrate as a
    success, so every failure carries an explicit ``"status": "error"`` and a
    message that starts with ``Tool call failed:``.
    """
    return {"status": "error", "error": {"type": error_type, "message": message}}


def execute(
    name: str,
    arguments: dict[str, Any],
    *,
    approved: bool = False,
    registry: Mapping[str, Tool] | None = None,
) -> str:
    """Run a registered tool and JSON-encode its result or error.

    Dangerous tools remain blocked unless an approval gate explicitly passes
    ``approved=True``. This keeps direct callers fail-closed while allowing the
    agent runtime to enforce a human decision on its execution path.

    ``registry`` dispatches against a private table instead of the process
    global. A tool absent from that table is reported as unknown, which is the
    correct answer for a subagent: the capability does not exist for it.
    """
    registered = (REGISTRY if registry is None else registry).get(name)
    if registered is None:
        return json.dumps(
            _failure_payload("unknown_tool", f"Tool call failed: unknown tool: {name}"),
            ensure_ascii=False,
        )
    # L3 security floor: evaluated BEFORE the approval check and impossible
    # to override with ``approved=True`` — a blocklisted command never runs,
    # no matter who called or what flag they carry.
    if name in _FLOOR_COMMAND_TOOLS:
        floor_match = _floor_scan(str(arguments.get("command", "")))
        if floor_match is not None:
            return json.dumps(
                _failure_payload(
                    "security_floor_blocked",
                    f"Tool call failed: {floor_match.refusal}",
                ),
                ensure_ascii=False,
            )
    if registered.risk == "dangerous" and not approved:
        return json.dumps(
            _failure_payload(
                "approval_required",
                f"Tool call failed: {name} requires human approval and none was given",
            ),
            ensure_ascii=False,
        )
    if registered.risk == "guarded":
        logger.info("executing guarded tool: %s", name)
    try:
        result = registered.function(**arguments)
        return json.dumps({"status": "ok", "result": result}, ensure_ascii=False)
    except Exception as exc:  # Tool boundaries return data, never leak exceptions.
        return json.dumps(
            _failure_payload(
                type(exc).__name__,
                f"Tool call failed: {name}() raised {type(exc).__name__}: {exc}",
            ),
            ensure_ascii=False,
        )
