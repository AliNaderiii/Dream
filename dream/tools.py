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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from dream.memory import normalize_fa

__all__ = [
    "REGISTRY",
    "Tool",
    "_safe_path",
    "anthropic_schemas",
    "calculate",
    "execute",
    "get_datetime",
    "list_notes",
    "list_skills",
    "openai_schemas",
    "read_note",
    "run_shell",
    "save_skill",
    "send_email",
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


def openai_schemas() -> list[dict[str, Any]]:
    """Return registered tools in OpenAI's function-tool format."""
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.schema},
        }
        for t in REGISTRY.values()
    ]


def anthropic_schemas() -> list[dict[str, Any]]:
    """Return registered tools in Anthropic's tool format."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema}
        for t in REGISTRY.values()
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
    path = _safe_path(filename)
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
    completed = subprocess.run(
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


# ---------------------------------------------------------------------------
# Network tools. Reaching the network is not a safe act: both tools are
# guarded, off unless DREAM_ALLOW_NETWORK is on, and every address the model
# invents is checked before a byte is read. Tests inject fetch_bytes and
# resolve_host so the suite never touches the live network.
# ---------------------------------------------------------------------------

NETWORK_TIMEOUT_SECONDS = 10.0
NETWORK_MAX_BYTES = 2_000_000
PAGE_TEXT_CHAR_LIMIT = 200_000
NETWORK_MAX_REDIRECTS = 5
_SEARCH_HOST = "api.duckduckgo.com"
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
    }
)
_BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".intranet")

# Gloss: «دسترسی به شبکه فعال نیست.»
NETWORK_DISABLED_MESSAGE = (
    "\u062f\u0633\u062a\u0631\u0633\u06cc \u0628\u0647 "
    "\u0634\u0628\u06a9\u0647 \u0641\u0639\u0627\u0644 \u0646\u06cc\u0633\u062a."
)
# Gloss: «این نشانی مجاز نیست.»
REFUSED_ADDRESS_MESSAGE = (
    "\u0627\u06cc\u0646 \u0646\u0634\u0627\u0646\u06cc "
    "\u0645\u062c\u0627\u0632 \u0646\u06cc\u0633\u062a."
)
# Gloss: «نشانی داخلی یا خصوصی پذیرفته نمی‌شود.»
PRIVATE_ADDRESS_MESSAGE = (
    "\u0646\u0634\u0627\u0646\u06cc \u062f\u0627\u062e\u0644\u06cc \u06cc\u0627 "
    "\u062e\u0635\u0648\u0635\u06cc \u067e\u0630\u06cc\u0631\u0641\u062a\u0647 "
    "\u0646\u0645\u06cc\u200c\u0634\u0648\u062f."
)
# Gloss: «تغییر مسیر به نشانی غیرمجاز رد شد.»
REDIRECT_REFUSED_MESSAGE = (
    "\u062a\u063a\u06cc\u06cc\u0631 \u0645\u0633\u06cc\u0631 \u0628\u0647 "
    "\u0646\u0634\u0627\u0646\u06cc \u063a\u06cc\u0631\u0645\u062c\u0627\u0632 "
    "\u0631\u062f \u0634\u062f."
)
# Gloss: «درخواست به شبکه زمانش تمام شد.»
TIMEOUT_MESSAGE = (
    "\u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0628\u0647 "
    "\u0634\u0628\u06a9\u0647 \u0632\u0645\u0627\u0646\u0634 \u062a\u0645\u0627\u0645 "
    "\u0634\u062f."
)
# Gloss: «متن کوتاه شد.»
TRUNCATED_MESSAGE = (
    "\u0645\u062a\u0646 \u06a9\u0648\u062a\u0627\u0647 \u0634\u062f."
)
# Gloss: «خواندن صفحه ممکن نشد.»
FETCH_FAILED_MESSAGE = (
    "\u062e\u0648\u0627\u0646\u062f\u0646 \u0635\u0641\u062d\u0647 "
    "\u0645\u0645\u06a9\u0646 \u0646\u0634\u062f."
)

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def network_access_enabled() -> bool:
    """Whether the owner has turned the network tools on."""
    raw = os.environ.get("DREAM_ALLOW_NETWORK", "") or ""
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _refusal(message: str) -> dict[str, Any]:
    return {"refused": True, "message": message}


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_blocked_ip(ip.ipv4_mapped)
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    return ip in _CGNAT


def resolve_host(host: str) -> list[str]:
    """Resolve a hostname. Tests replace this so DNS is never touched."""
    infos = socket.getaddrinfo(host, None)
    addresses: list[str] = []
    for info in infos:
        packed = info[4]
        if packed:
            addresses.append(str(packed[0]))
    return addresses


def _host_is_blocked_name(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    if lowered in _BLOCKED_HOSTS:
        return True
    return any(lowered.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES)


def _refuse_url(url: str) -> str | None:
    """Return a Persian refusal for a forbidden address, or None if allowed."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return REFUSED_ADDRESS_MESSAGE
    if parsed.username is not None or parsed.password is not None:
        return REFUSED_ADDRESS_MESSAGE
    host = parsed.hostname
    if not host:
        return REFUSED_ADDRESS_MESSAGE
    if _host_is_blocked_name(host):
        return PRIVATE_ADDRESS_MESSAGE
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_blocked_ip(ip):
            return PRIVATE_ADDRESS_MESSAGE
        return None
    try:
        addresses = resolve_host(host)
    except OSError:
        return REFUSED_ADDRESS_MESSAGE
    if not addresses:
        return REFUSED_ADDRESS_MESSAGE
    for address in addresses:
        try:
            resolved = ipaddress.ip_address(address)
        except ValueError:
            return REFUSED_ADDRESS_MESSAGE
        if _is_blocked_ip(resolved):
            return PRIVATE_ADDRESS_MESSAGE
    return None


def _read_capped(stream: Any, max_bytes: int) -> bytes:
    """Read at most *max_bytes* from *stream*, stopping while reading."""
    chunks: list[bytes] = []
    remaining = max_bytes
    while remaining > 0:
        chunk = stream.read(min(8192, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class _NoRedirectHandler(HTTPRedirectHandler):
    """Leave 3xx responses in place so the caller can inspect Location."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        del req, fp, code, msg, headers, newurl
        return None


def _urllib_fetch_bytes(url: str, *, timeout: float, max_bytes: int) -> dict[str, Any]:
    """One GET. Does not follow redirects. Caps the body while reading."""
    request = Request(
        url,
        headers={"User-Agent": "dream-assistant/0.1.0"},
        method="GET",
    )
    opener = build_opener(_NoRedirectHandler)
    try:
        with opener.open(request, timeout=timeout) as response:  # nosec B310: checked URL
            body = _read_capped(response, max_bytes=max_bytes)
            headers = {str(key): str(value) for key, value in response.headers.items()}
            status = int(getattr(response, "status", 200) or 200)
            return {"status": status, "headers": headers, "body": body, "url": url}
    except HTTPError as exc:
        headers = {}
        if exc.headers is not None:
            headers = {str(key): str(value) for key, value in exc.headers.items()}
        return {"status": int(exc.code), "headers": headers, "body": b"", "url": url}
    except TimeoutError:
        raise
    except URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise TimeoutError(str(reason)) from exc
        raise


fetch_bytes = _urllib_fetch_bytes


def _header(headers: dict[str, str], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return ""


def _network_get(url: str) -> dict[str, Any]:
    """Validate, fetch, and refuse a redirect that lands on a blocked host."""
    if not network_access_enabled():
        return _refusal(NETWORK_DISABLED_MESSAGE)
    current = url
    hops = 0
    while True:
        blocked = _refuse_url(current)
        if blocked:
            return _refusal(blocked)
        try:
            response = fetch_bytes(
                current,
                timeout=NETWORK_TIMEOUT_SECONDS,
                max_bytes=NETWORK_MAX_BYTES,
            )
        except TimeoutError:
            return _refusal(TIMEOUT_MESSAGE)
        except Exception:
            return _refusal(FETCH_FAILED_MESSAGE)
        status = int(response.get("status") or 0)
        if status in _REDIRECT_STATUSES:
            location = _header(response.get("headers") or {}, "Location")
            if not location:
                return _refusal(REFUSED_ADDRESS_MESSAGE)
            destination = urljoin(current, location)
            dest_blocked = _refuse_url(destination)
            if dest_blocked:
                return _refusal(REDIRECT_REFUSED_MESSAGE)
            hops += 1
            if hops > NETWORK_MAX_REDIRECTS:
                return _refusal(FETCH_FAILED_MESSAGE)
            current = destination
            continue
        if not (200 <= status < 300):
            return _refusal(FETCH_FAILED_MESSAGE)
        return response


class _HTMLTextExtractor(HTMLParser):
    _SKIP = frozenset({"script", "style", "noscript", "template"})
    _BREAK = frozenset(
        {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self._SKIP:
            self._skip += 1
        if tag in self._BREAK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        if tag in self._BREAK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def _strip_markup(raw: str) -> str:
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(raw)
        extractor.close()
    except Exception:
        return " ".join(raw.split())
    return extractor.text()


def _search_endpoint(query: str) -> str:
    return "https://{}/?{}".format(
        _SEARCH_HOST,
        urlencode({"q": query, "format": "json", "no_html": "1", "no_redirect": "1"}),
    )


def _topic_items(items: Any) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    if not isinstance(items, list):
        return results
    for item in items:
        if not isinstance(item, dict):
            continue
        nested = item.get("Topics")
        if isinstance(nested, list):
            results.extend(_topic_items(nested))
            continue
        url = item.get("FirstURL")
        title = item.get("Text") or url
        if isinstance(url, str) and url.startswith("http") and isinstance(title, str):
            results.append({"title": _strip_markup(title), "url": url})
    return results


@tool(risk="guarded")
def search_web(query: str) -> dict[str, Any]:
    """Search the public web for a short answer and a few results.

    Uses the key-free instant-answer endpoint. The bot-challenged HTML
    search page is never requested.

    :param query: What to search for.
    """
    if not network_access_enabled():
        return _refusal(NETWORK_DISABLED_MESSAGE)
    if not query or not str(query).strip():
        return _refusal(REFUSED_ADDRESS_MESSAGE)
    response = _network_get(_search_endpoint(str(query).strip()))
    if response.get("refused"):
        return response
    body = response.get("body") or b""
    text = body.decode("utf-8", "replace")
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return {
            "refused": False,
            "answer": _strip_markup(text)[:PAGE_TEXT_CHAR_LIMIT],
            "results": [],
        }
    if not isinstance(payload, dict):
        return {"refused": False, "answer": "", "results": []}
    answer = payload.get("AbstractText") or payload.get("Abstract") or ""
    if not isinstance(answer, str):
        answer = ""
    answer = _strip_markup(answer)
    results = _topic_items(payload.get("Results"))
    results.extend(_topic_items(payload.get("RelatedTopics")))
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in results:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        unique.append(item)
        if len(unique) >= 5:
            break
    return {"refused": False, "answer": answer, "results": unique}


@tool(risk="guarded")
def read_page(url: str) -> dict[str, Any]:
    """Read one web page as plain text, with markup removed.

    :param url: Address of the page to read.
    """
    if not network_access_enabled():
        return _refusal(NETWORK_DISABLED_MESSAGE)
    if not url or not str(url).strip():
        return _refusal(REFUSED_ADDRESS_MESSAGE)
    response = _network_get(str(url).strip())
    if response.get("refused"):
        return response
    body = response.get("body") or b""
    raw = body.decode("utf-8", "replace")
    text = _strip_markup(raw)
    truncated = len(text) > PAGE_TEXT_CHAR_LIMIT
    if truncated:
        text = text[:PAGE_TEXT_CHAR_LIMIT]
    result: dict[str, Any] = {"refused": False, "text": text, "truncated": truncated}
    if truncated:
        result["message"] = TRUNCATED_MESSAGE
    return result


def _failure_payload(error_type: str, message: str) -> dict[str, Any]:
    """Build an error payload that cannot be mistaken for a result.

    The agent feeds this string straight back to the model. A bare
    ``{"error": ...}`` is easy for a small model to skim past and narrate as a
    success, so every failure carries an explicit ``"status": "error"`` and a
    message that starts with ``Tool call failed:``.
    """
    return {"status": "error", "error": {"type": error_type, "message": message}}


def execute(name: str, arguments: dict[str, Any], *, approved: bool = False) -> str:
    """Run a registered tool and JSON-encode its result or error.

    Dangerous tools remain blocked unless an approval gate explicitly passes
    ``approved=True``. This keeps direct callers fail-closed while allowing the
    agent runtime to enforce a human decision on its execution path.
    """
    registered = REGISTRY.get(name)
    if registered is None:
        return json.dumps(
            _failure_payload("unknown_tool", f"Tool call failed: unknown tool: {name}"),
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
