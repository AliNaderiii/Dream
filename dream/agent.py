"""Provider-neutral Dream agent loop with memory and explicit approval gates."""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dream.claims import guard_claims
from dream.extraction import (
    STATUS_ABANDONED,
    STATUS_ERROR,
    ExtractionResult,
    extract_facts,
)
from dream.memory import Memory, MemoryStore, normalize_fa
from dream.normalization import normalize_importance, normalize_kind
from dream.providers import BuiltInMemoryProvider, ProviderManager
from dream.reminders import (
    Reminder,
    format_jalali,
    parse_date_to_timestamp,
    parse_persian_date,
    prompt_reminders,
)
from dream.skills import SkillPromptProvider
from dream.tools import REGISTRY, execute, openai_schemas, tool

# Sampling temperatures. Conversation gets 0.3: calm but not robotic. The
# extraction pass must emit parseable JSON, so it runs colder still; at the
# server default (0.8) a small model wanders — once across a language
# boundary mid-sentence.
DEFAULT_TEMPERATURE = 0.3
EXTRACTION_TEMPERATURE = 0.1

# Eight thousand characters is roughly two thousand tokens, leaving most of a
# small model's 8k-token context window for the conversation and its reply.
DEFAULT_MEMORY_BLOCK_CHAR_LIMIT = 8_000

# Some model providers sit behind Cloudflare, which treats urllib's default
# User-Agent as a bot and answers 403 before the request ever reaches the
# provider. Send our own identifying header instead. Dream is a desktop
# application, not a browser, so this is never a browser-impersonation string.
DEFAULT_USER_AGENT = "dream-assistant/0.1.0"

# Rate-limit retries: a 429 means the provider is alive and answerable, so a
# bounded retry with exponential backoff can succeed. A provider that hangs is
# not retried into the wall clock — the per-request timeout already bounds it.
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0

# The extraction pass runs in the background after the reply is produced. This
# is how long a turn waits for it before the pass is marked abandoned and the
# reply goes out anyway. Five seconds keeps typical extractions reported while
# bounding the damage of a provider that never answers.
DEFAULT_EXTRACTION_TIMEOUT_SECONDS = 5.0


def _resolve_temperature(raw: str | None) -> float:
    """Parse ``DREAM_TEMPERATURE``, falling back to the default on any problem.

    Anything unset, non-numeric, or outside the 0.0 to 2.0 band a sampler
    accepts resolves to the default rather than raising mid-turn.
    """
    if not raw:
        return DEFAULT_TEMPERATURE
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_TEMPERATURE
    if not 0.0 <= value <= 2.0:
        return DEFAULT_TEMPERATURE
    return value


def _resolve_memory_block_char_limit(raw: str | None) -> int:
    """Parse ``DREAM_MEMORY_BLOCK_CHAR_LIMIT`` without risking a failed turn."""
    if not raw:
        return DEFAULT_MEMORY_BLOCK_CHAR_LIMIT
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_MEMORY_BLOCK_CHAR_LIMIT
    if not 1 <= value <= 100_000:
        return DEFAULT_MEMORY_BLOCK_CHAR_LIMIT
    return value


def _resolve_max_retries(raw: str | None) -> int:
    """Parse ``DREAM_MAX_RETRIES``, falling back to the default on any problem."""
    if not raw:
        return DEFAULT_MAX_RETRIES
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_MAX_RETRIES
    if not 0 <= value <= 10:
        return DEFAULT_MAX_RETRIES
    return value


def _resolve_retry_backoff(raw: str | None) -> float:
    """Parse ``DREAM_RETRY_BACKOFF_SECONDS``, falling back safely on bad input."""
    if not raw:
        return DEFAULT_RETRY_BACKOFF_SECONDS
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_RETRY_BACKOFF_SECONDS
    if not 0.0 <= value <= 60.0:
        return DEFAULT_RETRY_BACKOFF_SECONDS
    return value


def _resolve_extraction_timeout(raw: str | None) -> float:
    """Parse ``DREAM_EXTRACTION_TIMEOUT_SECONDS``, falling back safely."""
    if not raw:
        return DEFAULT_EXTRACTION_TIMEOUT_SECONDS
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_EXTRACTION_TIMEOUT_SECONDS
    if not 0.1 <= value <= 60.0:
        return DEFAULT_EXTRACTION_TIMEOUT_SECONDS
    return value


def _resolve_user_agent(raw: str | None) -> str:
    """Parse ``DREAM_USER_AGENT``, falling back to the default on any problem.

    A header value must stay on a single line, so an empty, whitespace-only,
    or line-broken override is a header-injection risk, not a value to pass
    through. Anything unusable resolves to the default rather than raising.
    """
    if not raw:
        return DEFAULT_USER_AGENT
    value = raw.strip()
    if not value:
        return DEFAULT_USER_AGENT
    if "\n" in value or "\r" in value:
        return DEFAULT_USER_AGENT
    return value


class OpenAIBackend:
    """Client for any endpoint implementing OpenAI's chat-completions API."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
    ) -> None:
        self.model = model or os.environ.get("DREAM_MODEL", "")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.temperature = (
            _resolve_temperature(os.environ.get("DREAM_TEMPERATURE"))
            if temperature is None
            else float(temperature)
        )
        self.user_agent = _resolve_user_agent(os.environ.get("DREAM_USER_AGENT"))
        self.max_retries = _resolve_max_retries(os.environ.get("DREAM_MAX_RETRIES"))
        self.retry_backoff_seconds = _resolve_retry_backoff(
            os.environ.get("DREAM_RETRY_BACKOFF_SECONDS")
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Send one chat request, retrying rate limits with backoff.

        Only HTTP 429 is retried: a provider that answers with a rate limit
        is alive and may recover, and each retry sleeps an exponentially
        growing backoff. A provider that hangs is bounded by the per-request
        timeout and reported as a failure rather than retried into the wall
        clock. When every attempt is exhausted the failure message says the
        call was abandoned and how many attempts were made.
        """
        retries = self.max_retries if max_retries is None else max_retries
        for attempt in range(retries + 1):
            status, data = self._attempt_chat(messages, tools)
            if status == 0:
                return data
            rate_limited = status == 429
            if rate_limited and attempt < retries:
                time.sleep(self.retry_backoff_seconds * (2**attempt))
                continue
            return self._failure(status, _failure_text(data, attempt + 1))

    def _attempt_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> tuple[int, Any]:
        """One request attempt: ``(0, response)`` on success, otherwise
        ``(http_status_or_1, failure_detail)``."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:  # nosec B310: configured model endpoint
                data = json.loads(response.read().decode("utf-8"))
            message = data["choices"][0]["message"]
            calls = [
                {
                    "id": call.get("id", ""),
                    "name": call["function"]["name"],
                    "arguments": _arguments(call["function"].get("arguments", {})),
                }
                for call in message.get("tool_calls", [])
            ]
            return 0, {"content": message.get("content"), "tool_calls": calls}
        except HTTPError as exc:
            # The body is where the server says what it rejected; keep it.
            return exc.code, _describe_http_error(exc)
        except (URLError, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
            return 1, f"{type(exc).__name__}: {exc}"

    def _failure(self, status: int, detail: str) -> dict[str, Any]:
        """Report a failed request without ever echoing raw provider detail."""
        safe_detail = _redact(detail, self.api_key)
        print(f"[provider] Model request failed: {safe_detail}", file=sys.stderr)
        return {
            "content": _provider_failure_reply(status, safe_detail),
            "tool_calls": [],
        }


def _failure_text(detail: str, attempts: int) -> str:
    """Describe a failed call, naming abandonment when it was retried.

    A single attempt that failed is just the failure. A call that burned
    several attempts against a rate limit must say so, or the owner cannot
    tell a retried failure from an instantaneous one.
    """
    if attempts > 1:
        return f"{detail} \u2014 abandoned after {attempts} attempts"
    return detail


def _provider_failure_reply(status: int, detail: str) -> str:
    """Return the short chat-facing sentence for a provider failure."""
    if status == 429:
        return (
            "\u0633\u0647\u0645\u06cc\u0647 \u062a\u0645\u0627\u0645 "
            "\u0634\u062f\u0647\u061b \u06cc\u06a9 \u062f\u0642\u06cc\u0642\u0647 "
            "\u062f\u06cc\u06af\u0631 \u062f\u0648\u0628\u0627\u0631\u0647 "
            "\u0628\u067e\u0631\u0633."
        )
    if 400 <= status < 500:
        return (
            "\u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0631\u062f "
            "\u0634\u062f\u061b \u062c\u0632\u0626\u06cc\u0627\u062a "
            "\u0631\u0627 \u062f\u0631 \u062a\u0631\u0645\u06cc\u0646\u0627\u0644 "
            "\u0628\u0628\u06cc\u0646."
        )
    if detail.startswith(("URLError:", "TimeoutError:", "ConnectionError:", "OSError:")):
        return (
            "\u0627\u0644\u0627\u0646 \u0628\u0647 \u0633\u0631\u0648\u06cc\u0633 "
            "\u067e\u0627\u0633\u062e\u200c\u06af\u0648\u06cc\u06cc \u0648\u0635\u0644 "
            "\u0646\u0645\u06cc\u200c\u0634\u0648\u0645\u061b \u0627\u062a\u0635\u0627\u0644 "
            "\u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646."
        )
    return (
        "\u06cc\u06a9 \u062e\u0637\u0627\u06cc "
        "\u063a\u06cc\u0631\u0645\u0646\u062a\u0638\u0631\u0647 "
        "\u0631\u062e \u062f\u0627\u062f\u061b \u062c\u0632\u0626\u06cc\u0627\u062a "
        "\u0631\u0627 \u062f\u0631 \u062a\u0631\u0645\u06cc\u0646\u0627\u0644 "
        "\u0628\u0628\u06cc\u0646."
    )


class OllamaBackend(OpenAIBackend):
    """OpenAI-compatible client pointed at a local Ollama server."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        host = base_url or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        super().__init__(
            model=model or os.environ.get("DREAM_MODEL", "llama3.2"),
            api_key="",
            base_url=f"{host.rstrip('/')}" + "/v1",
        )


class EchoBackend:
    """Offline deterministic backend used for tests and local demos."""

    _MATH = re.compile(r"[0-9۰-۹٠-٩][0-9۰-۹٠-٩\s+\-*/×÷().]*[+\-*/×÷]")

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        del tools
        if messages and messages[-1].get("role") == "tool":
            result = messages[-1].get("content", "")
            return {"content": f"Result: {result}", "tool_calls": []}
        text = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
        lowered = text.lower()
        if any(word in lowered for word in ("time", "date", "ساعت", "زمان")):
            return {
                "content": None,
                "tool_calls": [{"id": "echo-time", "name": "get_datetime", "arguments": {}}],
            }
        if self._MATH.search(text):
            expression = re.sub(r"[^0-9۰-۹٠-٩\s+\-*/×÷().]", "", text).strip()
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "echo-calculate",
                        "name": "calculate",
                        "arguments": {"expression": expression},
                    }
                ],
            }
        return {"content": f"Echo: {text}", "tool_calls": []}


def build_backend(kind: str | None = None) -> OpenAIBackend | OllamaBackend | EchoBackend:
    """Select a backend, defaulting to ``DREAM_BACKEND`` or offline echo."""
    selected = (kind or os.environ.get("DREAM_BACKEND", "echo")).lower()
    if selected == "openai":
        return OpenAIBackend()
    if selected == "ollama":
        return OllamaBackend()
    if selected == "echo":
        return EchoBackend()
    raise ValueError(f"unknown backend: {selected}")


def _arguments(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


ERROR_BODY_LIMIT = 500
_BEARER = re.compile(r"[Bb]earer\s+\S+")


def _error_body(exc: HTTPError, limit: int = ERROR_BODY_LIMIT) -> str:
    """Return an HTTP error's response body, whitespace-collapsed and truncated."""
    try:
        raw = exc.read()
    except (AttributeError, OSError, ValueError):
        return ""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[:limit]} ... (truncated)"


def _describe_http_error(exc: HTTPError) -> str:
    """Describe an HTTP failure, including the explanation the server sent.

    ``str(HTTPError)`` is only ``HTTP Error 400: Bad Request``, which names the
    status and nothing about the cause. The body carries the reason.
    """
    detail = f"HTTP {exc.code} {exc.reason}".strip()
    body = _error_body(exc)
    return f"{detail}: {body}" if body else detail


def _redact(text: str, *secrets: str) -> str:
    """Strip credentials from text before it reaches a user or a log."""
    for secret in secrets:
        if len(secret) >= 4:
            text = text.replace(secret, "***")
    return _BEARER.sub("Bearer ***", text)


def _wire_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Dream's internal tool calls to chat-completions wire format.

    Internally a call is ``{"id", "name", "arguments": {...}}``. The API expects
    ``{"id", "type": "function", "function": {"name", "arguments": "<json>"}}``.
    Replaying the internal shape in history makes every request after the first
    tool call a 400, which is why the first turn works and the second does not.
    """
    wire: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        nested = call.get("function")
        source = nested if isinstance(nested, dict) else call
        wire.append(
            {
                "id": str(call.get("id") or f"call_{index}"),
                "type": "function",
                "function": {
                    "name": str(source.get("name", "")),
                    "arguments": json.dumps(
                        _arguments(source.get("arguments", {})), ensure_ascii=False
                    ),
                },
            }
        )
    return wire


def cli_approver(tool_name: str, arguments: dict[str, Any]) -> bool:
    """Ask on the terminal, treating interrupted input as a denial."""
    try:
        answer = input(f"Allow {tool_name}({json.dumps(arguments, ensure_ascii=False)})? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in {"y", "yes"}


@dataclass(slots=True)
class ApprovalPolicy:
    """Approval rules based exclusively on each registered tool's real risk."""

    auto_approve: set[str] = field(default_factory=lambda: {"safe", "guarded"})
    always_ask: set[str] = field(default_factory=lambda: {"dangerous"})
    ask: Callable[[str, dict[str, Any]], bool] | None = None

    def allows(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        registered = REGISTRY.get(tool_name)
        if registered is None:
            return False, "unknown tool"
        risk = registered.risk
        if risk in self.always_ask:
            if self.ask is None:
                return False, f"{risk} tool denied: no approver configured"
            return (
                (True, f"{risk} tool approved")
                if self.ask(tool_name, arguments)
                else (False, f"{risk} tool denied by approver")
            )
        if risk in self.auto_approve:
            return True, f"{risk} tool auto-approved"
        return False, f"{risk} tool denied by policy"


@dataclass(slots=True)
class _ExtractionOutcome:
    """Carries the extraction pass result out of its worker thread.

    The worker writes these fields and the turn reads them after the join
    returns, so the happens-before edge of the join makes the read safe.
    """

    result: ExtractionResult | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Turn:
    """Observable record of one user turn through the agent loop."""

    reply: str
    tool_calls: list[dict[str, Any]]
    memories_used: list[Memory]
    memories_created: list[Memory]
    elapsed_seconds: float
    extraction: Any = None
    memory_errors: list[str] = field(default_factory=list)
    memories_superseded: list[Memory] = field(default_factory=list)
    memories_merged: list[Memory] = field(default_factory=list)
    memories_injected: list[Memory] | None = None


# ---------------------------------------------------------------------------
# Reminder tool support: shared date resolution, matching, and the Persian
# refusal/confirmation wording every reminder tool answer carries.
# ---------------------------------------------------------------------------

# Gloss: ساعت. A date argument containing the clock-time word is refused in
# both reminder tools; the date is a pure date, never a guessed hour.
_TIME_WORD = "\u0633\u0627\u0639\u062a"

# The create-side clock-time refusal, kept byte-identical to the M15 wording
# its tests pin. Gloss: «عبارت زمان «ساعت» در تاریخ پشتیبانی نمی‌شود؛ تاریخ را
# مثل «فردا» بفرست و ساعت را در متن یادآوری بنویس.»
_CREATE_TIME_HINT = (
    "\u0639\u0628\u0627\u0631\u062a \u0632\u0645\u0627\u0646 "
    "\u00ab\u0633\u0627\u0639\u062a\u00bb \u062f\u0631 "
    "\u062a\u0627\u0631\u06cc\u062e "
    "\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc "
    "\u0646\u0645\u06cc\u0634\u0648\u062f\u061b "
    "\u062a\u0627\u0631\u06cc\u062e \u0631\u0627 "
    "\u0645\u062b\u0644 \u00ab\u0641\u0631\u062f\u0627\u00bb "
    "\u0628\u0641\u0631\u0633\u062a \u0648 "
    "\u0633\u0627\u0639\u062a \u0631\u0627 "
    "\u062f\u0631 \u0645\u062a\u0646 "
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u0628\u0646\u0648\u06cc\u0633."
)

# The cancel-side clock-time refusal. Gloss: «در date ساعت پشتیبانی نمی‌شود؛
# فقط تاریخ را مثل «فردا» یا «1405-05-19» بفرست.»
_CANCEL_TIME_HINT = (
    "\u062f\u0631 date "
    "\u0633\u0627\u0639\u062a "
    "\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc "
    "\u0646\u0645\u06cc\u200c\u0634\u0648\u062f\u061b "
    "\u0641\u0642\u0637 \u062a\u0627\u0631\u06cc\u062e "
    "\u0631\u0627 \u0645\u062b\u0644 "
    "\u00ab\u0641\u0631\u062f\u0627\u00bb \u06cc\u0627 "
    "\u00ab1405-05-19\u00bb "
    "\u0628\u0641\u0631\u0633\u062a."
)


def _resolve_reminder_date(date: str, time_hint: str) -> float:
    """Resolve a shared reminder-tool date argument, refusing clock times.

    Numeric input (``YYYY-MM-DD``; year below 1700 is Jalali) is tried first,
    then a natural Persian phrase; whatever neither parser accepts raises the
    parser's own message, and a clock-time word raises *time_hint*. Neither
    reminder tool ever guesses an hour.
    """
    date_norm = normalize_fa(date).strip()
    if not date_norm:
        raise ValueError(f"unparseable date: {date!r}")
    if _TIME_WORD in date_norm:
        raise ValueError(time_hint)
    try:
        return parse_date_to_timestamp(date_norm)
    except Exception:
        try:
            return parse_persian_date(date_norm)
        except Exception as exc:
            raise ValueError(str(exc)) from exc


def _match_reminders(store: MemoryStore, text: str) -> list:
    # The owner speaks approximately («بیمه» for «تمدید بیمه ماشین»), so when
    # no row equals the said text, rows merely containing it are candidates
    # too. Removing is only allowed when exactly one row fits, and the
    # confirmation always names the full stored text, so a shortened request
    # can be verified against what was removed. Inactive reminders (fired
    # one-offs) never enter matching.
    """Active reminders matching *text*: exact normalized, else substring."""
    query = normalize_fa(text).strip()
    active = store.list_reminders()
    exact = [rem for rem in active if normalize_fa(rem.text).strip() == query]
    if exact:
        return exact
    return [rem for rem in active if query in normalize_fa(rem.text)]


def _repeat_words(reminder: Reminder) -> str:
    # Gloss of the phrasing: «هر روز» / «هر ۳ ماه».
    """The repeat rule in Persian, or "" for a one-off."""
    if reminder.repeat_days is not None:
        if reminder.repeat_days == 1:
            return "\u0647\u0631 \u0631\u0648\u0632"  # هر روز
        return f"\u0647\u0631 {reminder.repeat_days} \u0631\u0648\u0632"  # هر N روز
    if reminder.repeat_months is not None:
        if reminder.repeat_months == 1:
            return "\u0647\u0631 \u0645\u0627\u0647"  # هر ماه
        return f"\u0647\u0631 {reminder.repeat_months} \u0645\u0627\u0647"  # هر N ماه
    return ""


def _candidate_summary(reminder: Reminder) -> str:
    """One candidate for a refusal list: text, Jalali date, repeat rule.

    The owner distinguishes two same-text reminders by the date he said; the
    Jalali date and the repeat rule make each candidate checkable.
    """
    due = format_jalali(reminder.due_at)
    repeat = _repeat_words(reminder)
    if repeat:
        return f"{reminder.text} ({due}\u060c {repeat})"  # ،
    return f"{reminder.text} ({due})"


def _candidates_summary(matches: list) -> str:
    # The separator is the Persian «؛».
    """Join candidate summaries with the Persian semicolon separator."""
    return "\u061b ".join(_candidate_summary(rem) for rem in matches)


def _cancel_not_found_message(text: str) -> str:
    # Gloss: «یادآوری فعالی با متن «{text}» پیدا نشد؛ چیزی لغو نشد.»
    """Refusal when no active reminder fits *text*."""
    return (
        f"\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
        f"\u0641\u0639\u0627\u0644\u06cc "
        f"\u0628\u0627 \u0645\u062a\u0646 \u00ab{text}\u00bb "
        f"\u067e\u06cc\u062f\u0627 \u0646\u0634\u062f\u061b "
        f"\u0686\u06cc\u0632\u06cc \u0644\u063a\u0648 "
        f"\u0646\u0634\u062f."
    )


def _cancel_ambiguous_message(text: str, matches: list) -> str:
    # Gloss: «چند یادآوری با متن «{text}» پیدا شد؛ کدام را لغو کنم؟ ...»
    """Refusal asking the owner to choose between several candidates."""
    return (
        f"\u0686\u0646\u062f \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
        f"\u0628\u0627 \u0645\u062a\u0646 \u00ab{text}\u00bb "
        f"\u067e\u06cc\u062f\u0627 \u0634\u062f\u061b "
        f"\u06a9\u062f\u0627\u0645 \u0631\u0627 \u0644\u063a\u0648 "
        f"\u06a9\u0646\u0645\u061f "
        f"{_candidates_summary(matches)}"
    )


def _cancel_no_date_match_message(text: str, wanted: str, matches: list) -> str:
    # Gloss: «یادآوری فعالی با متن «{text}» برای تاریخ {date} پیدا نشد؛
    # چیزی لغو نشد. موارد موجود: ...»
    """Refusal when the date filter empties the match."""
    return (
        f"\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
        f"\u0641\u0639\u0627\u0644\u06cc "
        f"\u0628\u0627 \u0645\u062a\u0646 \u00ab{text}\u00bb "
        f"\u0628\u0631\u0627\u06cc \u062a\u0627\u0631\u06cc\u062e {wanted} "
        f"\u067e\u06cc\u062f\u0627 \u0646\u0634\u062f\u061b "
        f"\u0686\u06cc\u0632\u06cc \u0644\u063a\u0648 \u0646\u0634\u062f. "
        f"\u0645\u0648\u0627\u0631\u062f "
        f"\u0645\u0648\u062c\u0648\u062f: "
        f"{_candidates_summary(matches)}"
    )


def _cancelled_message(reminder: Reminder) -> str:
    # Gloss: «یادآوری «{text}» برای {due} (تکرار: ...) لغو شد.»
    """The Persian confirmation naming what was removed, in Jalali."""
    due = format_jalali(reminder.due_at)
    repeat = _repeat_words(reminder)
    if repeat:
        return (
            f"\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
            f"\u00ab{reminder.text}\u00bb "
            f"\u0628\u0631\u0627\u06cc {due} "
            f"(\u062a\u06a9\u0631\u0627\u0631: {repeat}) "
            f"\u0644\u063a\u0648 \u0634\u062f."
        )
    return (
        f"\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
        f"\u00ab{reminder.text}\u00bb "
        f"\u0628\u0631\u0627\u06cc {due} \u0644\u063a\u0648 \u0634\u062f."
    )


class Dream:
    """An agent runtime that combines durable memory, tools, and approval."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        backend: OpenAIBackend | OllamaBackend | EchoBackend | None = None,
        approval_policy: ApprovalPolicy | None = None,
        max_iterations: int = 4,
        manager: ProviderManager | None = None,
    ) -> None:
        if manager is not None:
            self.manager = manager
            self.store = None
            for p in manager.providers:
                if isinstance(p, BuiltInMemoryProvider):
                    self.store = p.store
                    break
            if self.store is None and store is not None:
                self.store = store
            # The skills usage line is part of Dream's own behaviour, not of
            # any caller's provider choice; the manager seam carries it
            # either way.
            self.manager.register(SkillPromptProvider())
        else:
            if store is None:
                raise TypeError("Dream requires either a store or a manager")
            self.store = store
            self.manager = ProviderManager()
            self.manager.register(BuiltInMemoryProvider(store))
            self.manager.register(SkillPromptProvider())
        self.backend = backend or build_backend()
        self.approval_policy = approval_policy or ApprovalPolicy()
        self.max_iterations = max_iterations
        self.memory_block_char_limit = _resolve_memory_block_char_limit(
            os.environ.get("DREAM_MEMORY_BLOCK_CHAR_LIMIT")
        )
        self.extraction_timeout_seconds = _resolve_extraction_timeout(
            os.environ.get("DREAM_EXTRACTION_TIMEOUT_SECONDS")
        )
        self.history: list[dict[str, Any]] = []
        self._created: list[Memory] = []
        self._superseded: list[Memory] = []
        self._merged: list[Memory] = []
        self._register_memory_tools()
        self._register_reminder_tools()

    def _register_memory_tools(self) -> None:
        store = self.store
        created = self._created
        superseded = self._superseded
        merged = self._merged

        @tool(risk="guarded")
        def remember_fact(
            content: str, kind: str = "semantic", importance: float = 0.5, tags: list | None = None
        ) -> dict[str, Any]:
            """Store a durable fact in Dream's memory.

            :param content: Fact to remember.
            :param kind: Memory kind — semantic, episodic, or procedural.
            :param importance: Importance from zero to one.
            :param tags: Optional labels for retrieval.
            """
            memory = store.remember(
                content,
                kind=normalize_kind(kind),
                importance=normalize_importance(importance),
                tags=tags or [],
                on_supersede=superseded.append,
                on_merge=merged.append,
            )
            created.append(memory)
            return {
                "id": memory.id,
                "content": memory.content,
                "kind": memory.kind,
                "importance": memory.importance,
            }

        @tool(risk="safe")
        def search_memory(query: str, limit: int = 8) -> list[dict[str, Any]]:
            """Search durable Dream memory.

            :param query: Text to search for.
            :param limit: Maximum matching memories.
            """
            return [
                {"id": m.id, "content": m.content, "kind": m.kind}
                for m in store.recall(query, limit=limit)
            ]

        @tool(risk="guarded")
        def forget_memory(memory_id: int) -> bool:
            """Archive one memory.

            :param memory_id: Identifier of the memory to archive.
            """
            return store.forget(memory_id)

    def _register_reminder_tools(self) -> None:
        store = self.store
        if store is None:
            return

        @tool(risk="guarded")
        def create_reminder(
            date: str, text: str, repeat_days: int | None = None, repeat_months: int | None = None
        ) -> dict[str, Any]:
            """Create a durable reminder for the owner.

            :param date: Due date as Jalali YYYY-MM-DD (year <1700) or a
                natural Persian phrase. Pure date only; time words cause refusal.
            :param text: Reminder text, what to remind about.
            :param repeat_days: Repeat every N days (optional).
            :param repeat_months: Repeat every N months (optional).
            """
            if not text or not text.strip():
                raise ValueError("text must not be empty")
            if repeat_days is not None and repeat_days == 0:
                raise ValueError("repeat must be non-zero")
            if repeat_months is not None and repeat_months == 0:
                raise ValueError("repeat must be non-zero")
            if repeat_days is not None and repeat_months is not None:
                raise ValueError(
                    "repeat must be either days or months, not both"
                )
            due_at = _resolve_reminder_date(date, _CREATE_TIME_HINT)
            rem = store.add_reminder(
                text.strip(), due_at, repeat_days, repeat_months
            )
            return {
                "id": rem.id,
                "due": format_jalali(rem.due_at),
                "text": rem.text,
                "repeat_days": rem.repeat_days,
                "repeat_months": rem.repeat_months,
                "due_at": rem.due_at,
            }

        @tool(risk="guarded")
        def cancel_reminder(text: str, date: str | None = None) -> dict[str, Any]:
            """Cancel one of the owner's reminders, by text and optional date.

            The match runs over the active reminders: an exact text match,
            otherwise a unique substring match, narrowed by the date when one
            is sent. A row is removed only when exactly one row fits; zero or
            several fits refuse with the candidates named in Persian, and no
            row is touched. The removal is the same permanent delete
            ``/unremind`` performs, so the two surfaces stay identical.

            :param text: Reminder text as the owner says it; a unique
                fragment is accepted.
            :param date: Optional due date — Jalali YYYY-MM-DD (year <1700)
                or a natural Persian phrase. Pure date only.
            """
            if not text or not text.strip():
                raise ValueError("text must not be empty")
            matches = _match_reminders(store, text)
            if not matches:
                raise ValueError(_cancel_not_found_message(text.strip()))
            if date is not None and str(date).strip():
                wanted = format_jalali(
                    _resolve_reminder_date(str(date), _CANCEL_TIME_HINT)
                )
                dated = [rem for rem in matches if format_jalali(rem.due_at) == wanted]
                if not dated:
                    raise ValueError(
                        _cancel_no_date_match_message(text.strip(), wanted, matches)
                    )
                matches = dated
            if len(matches) > 1:
                raise ValueError(_cancel_ambiguous_message(text.strip(), matches))
            victim = matches[0]
            # The store cascades reminder deletion to its delivery rows, so a
            # fired reminder deletes cleanly and the child rows go with the
            # parent. No hand cleanup here: that duty belongs under the store,
            # where every caller gets it.
            if not store.delete_reminder(victim.id):
                raise ValueError(_cancel_not_found_message(text.strip()))
            return {
                "id": victim.id,
                "text": victim.text,
                "due": format_jalali(victim.due_at),
                "repeat_days": victim.repeat_days,
                "repeat_months": victim.repeat_months,
                "message": _cancelled_message(victim),
            }

    def reset_session(self) -> None:
        """Discard conversational context without touching durable memory."""
        self.history.clear()

    def _memory_block(self, memories: list[Memory]) -> tuple[str, list[Memory]]:
        """Render complete recalled-memory lines that fit the prompt budget."""
        lines: list[str] = []
        injected: list[Memory] = []
        used = 0
        for memory in sorted(memories, key=lambda memory: memory.score, reverse=True):
            line = f"- [{_relative_age(memory.created_at)}] {memory.content}"
            addition = len(line) + (1 if lines else 0)
            if used + addition > self.memory_block_char_limit:
                break
            lines.append(line)
            injected.append(memory)
            used += addition

        block = f"\n\n{_MEMORIES_OPEN}\n"
        if lines:
            block += "\n".join(lines) + "\n"
        block += _MEMORIES_CLOSE
        return block, injected

    def _reminder_block(
        self, reminders: list[Reminder], query: str, budget: int
    ) -> tuple[str, list[Reminder]]:
        """Render the reminder section of the prompt within *budget* chars.

        Memories are fitted to the shared budget first and this section is
        omitted when nothing qualifies or nothing fits, so reminders can never
        crowd memories out of the prompt.
        """
        if budget <= 0 or not reminders:
            return "", []
        overhead = len("\n\n" + _REMINDERS_OPEN + "\n") + len("\n" + _REMINDERS_CLOSE)
        usable = budget - overhead
        if usable <= 0:
            return "", []
        lines: list[str] = []
        injected: list[Reminder] = []
        used = 0
        for reminder in prompt_reminders(reminders, query):
            line = _render_reminder_line(reminder)
            addition = len(line) + (1 if lines else 0)
            if used + addition > usable:
                break
            lines.append(line)
            injected.append(reminder)
            used += addition
        if not lines:
            return "", []
        block = "\n\n" + _REMINDERS_OPEN + "\n" + "\n".join(lines) + "\n" + _REMINDERS_CLOSE
        return block, injected

    def _system_message(
        self,
        memories: list[Memory],
        memory_block: str | None = None,
        reminder_block: str | None = None,
        query: str = "",
    ) -> dict[str, str]:
        prompt = _BASE_PROMPT + _MEMORY_USAGE + _REMINDER_TOOL_USAGE + _REMINDER_CANCEL_USAGE
        # The M4 contribute_prompt hook, wired for the first time: subsystems
        # (here: skills) add their own usage line to the system prompt.
        skills_block, _ = self.manager.contribute_prompt(
            query, self.memory_block_char_limit
        )
        if skills_block:
            prompt += skills_block
        if memory_block is None:
            memory_block, _ = self._memory_block(memories)
        middle = ""
        if reminder_block:
            middle = _REMINDER_USAGE + reminder_block
        return {"role": "system", "content": prompt + middle + memory_block}

    def run(self, message: str) -> Turn:
        """Run one complete user turn, including any model-requested tools."""
        started = time.monotonic()
        self._created.clear()
        self._superseded.clear()
        self._merged.clear()
        if self.store is not None:
            self.store.log("user", message)
        memories = self.manager.recall(message, limit=8, reinforce=True)
        memory_block, injected_memories = self._memory_block(memories)
        reminder_block, _ = self._reminder_block(
            self.manager.list_reminders(),
            message,
            self.memory_block_char_limit - len(memory_block),
        )
        self.history.append({"role": "user", "content": message})
        calls_made: list[dict[str, Any]] = []
        reply = "I could not produce an answer."

        for _ in range(self.max_iterations):
            messages = [
                self._system_message(memories, memory_block, reminder_block, message),
                *self.history,
            ]
            response = self.backend.chat(messages, tools=openai_schemas())
            calls = response.get("tool_calls", [])
            if not calls:
                reply = response.get("content") or reply
                break
            wire_calls = _wire_tool_calls(calls)
            self.history.append(
                {"role": "assistant", "content": response.get("content"), "tool_calls": wire_calls}
            )
            for call, wire_call in zip(calls, wire_calls, strict=True):
                name = str(call.get("name", ""))
                arguments = _arguments(call.get("arguments", {}))
                allowed, reason = self.approval_policy.allows(name, arguments)
                if allowed:
                    result = execute(name, arguments, approved=REGISTRY[name].risk == "dangerous")
                else:
                    result = json.dumps({"blocked": True, "reason": reason}, ensure_ascii=False)
                calls_made.append(
                    {"name": name, "arguments": arguments, "allowed": allowed, "result": result}
                )
                self.history.append(
                    {"role": "tool", "tool_call_id": wire_call["id"], "content": result}
                )

        self.manager.persist()

        extraction_result, store_errors = self._run_extraction(message)

        # The claim guards run after extraction so the outcome of the turn —
        # the rows it wrote, the memories the model was shown, and whether the
        # extraction pass was abandoned — is complete before any warning is
        # decided. A save-claim reply is only truthful when the write it claims
        # actually happened; an unconfirmed claim gets a Persian warning
        # appended so the owner is never left believing a durable write
        # occurred. A truthful reply passes through byte for byte. The seam is
        # a single call so a mixed sentence never reads two warnings.
        reply = guard_claims(
            reply,
            calls_made,
            list(self._created),
            injected_memories,
            extraction_result.status,
        )
        self.history.append({"role": "assistant", "content": reply})
        if self.store is not None:
            self.store.log("assistant", reply)

        return Turn(
            reply,
            calls_made,
            memories,
            list(self._created),
            time.monotonic() - started,
            extraction=extraction_result,
            memory_errors=store_errors,
            memories_superseded=list(self._superseded),
            memories_merged=list(self._merged),
            memories_injected=list(injected_memories),
        )

    def _extraction_backend(self) -> Any:
        """Return the backend handle for the post-turn extraction pass.

        Extraction must emit parseable JSON, so it samples at a fixed low
        temperature rather than the conversational one. Only the real HTTP
        clients carry sampling; offline and scripted backends ignore
        temperature and are returned unchanged. The real client also gets
        retries disabled: the pass runs inside a wall-clock budget, so it
        must never retry a rate limit into that budget.
        """
        backend = self.backend
        if isinstance(backend, OpenAIBackend):
            colder = copy.copy(backend)
            colder.temperature = EXTRACTION_TEMPERATURE
            colder.max_retries = 0
            return colder
        return backend

    def _extract_in_background(
        self, message: str, outcome: _ExtractionOutcome
    ) -> None:
        """Run the extraction pass and store any facts it finds.

        Runs on a worker thread so the reply is never delayed by it. Every
        exception is contained here: a broken provider, store, or fact must
        never escape into the turn that already produced its reply.
        """
        try:
            result = extract_facts(self._extraction_backend(), message)
        except Exception as exc:  # defensive; extract_facts catches most of these
            result = ExtractionResult(
                facts=[], status=STATUS_ERROR, raw_text=f"{type(exc).__name__}: {exc}"
            )
        errors: list[str] = []
        for fact in result.facts:
            try:
                memory = self.store.remember(
                    fact.content,
                    kind=fact.kind,
                    importance=fact.importance,
                    source="extraction",
                    on_supersede=self._superseded.append,
                    on_merge=self._merged.append,
                )
                if not any(m.id == memory.id for m in self._created):
                    self._created.append(memory)
            except ValueError:
                # The one expected case: an unusable fact (e.g. empty content).
                # Skip it and keep the rest of the batch.
                continue
            except Exception as exc:
                # A store failure (locked database, full disk, ...) must never
                # pass silently: record it so the CLI can print what was lost.
                errors.append(f"{type(exc).__name__}: {exc}")
        outcome.result = result
        outcome.errors = errors

    def _run_extraction(self, message: str) -> tuple[ExtractionResult, list[str]]:
        """Start the extraction pass in the background and wait at most the
        extraction budget for it.

        When the pass finishes within the budget its facts are already in the
        store and are reported on the turn, exactly as before. When it does
        not — the provider hangs — the turn is marked abandoned and the reply
        is returned anyway; the worker keeps running and stores the facts
        when the provider finally answers.
        """
        outcome = _ExtractionOutcome()
        worker = threading.Thread(
            target=self._extract_in_background, args=(message, outcome), daemon=True
        )
        worker.start()
        worker.join(timeout=self.extraction_timeout_seconds)
        if worker.is_alive():
            return (
                ExtractionResult(
                    facts=[],
                    status=STATUS_ABANDONED,
                    raw_text=(
                        "did not finish within "
                        f"{self.extraction_timeout_seconds:.1f}s"
                    ),
                ),
                [],
            )
        result = outcome.result
        if result is None:
            result = ExtractionResult(
                facts=[], status=STATUS_ERROR, raw_text="extraction produced no result"
            )
        return result, outcome.errors


def _relative_age(timestamp: float) -> str:
    days = max(0, int((time.time() - timestamp) // 86400))
    if days == 0:
        return "today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def _render_reminder_line(reminder: Reminder) -> str:
    """Render one reminder for the prompt: text plus its stored Jalali date.

    The date is the owner's own record, so it is explicit on the line and the
    model repeats it instead of guessing. A past due date is flagged with
    «دیر شده» so the model can tell the owner the deadline has passed.
    """
    date = format_jalali(reminder.due_at)
    if reminder.due_at <= time.time():
        return (
            f"- {reminder.text} "
            f"(\u0633\u0631\u0631\u0633\u06cc\u062f {date} \u2014 "
            f"\u062f\u06cc\u0631 \u0634\u062f\u0647)"
        )
    return f"- {reminder.text} (\u0633\u0631\u0631\u0633\u06cc\u062f {date})"


# The language rule is unconditional, so a small model cannot drift away from
# the user's language: reply in the language of the most recent message, reply
# in Persian to Persian input, and never switch to a third language.
_LANGUAGE_RULE = (
    " همیشه به زبان آخرین پیام کاربر پاسخ بده؛ اگر کاربر فارسی نوشت، حتماً فارسی "
    "پاسخ بده؛ هرگز به زبان سومی تغییر نکن."
)

_BASE_PROMPT = (
    "\u062a\u0648 Dream\u060c "
    "\u06cc\u0639\u0646\u06cc \u0631\u0648\u06cc\u0627\u060c "
    "\u0647\u0633\u062a\u06cc\u061b \u0628\u0631\u0627\u06cc "
    "\u06a9\u0627\u0631\u0628\u0631 \u0641\u0627\u0631\u0633\u06cc\u200c\u0632\u0628\u0627\u0646 "
    "\u0646\u0627\u0645\u062a \u0631\u0648\u06cc\u0627 \u0627\u0633\u062a."
    + _LANGUAGE_RULE
    + " \u0627\u06af\u0631 \u0686\u06cc\u0632\u06cc \u0631\u0627 "
    "\u0646\u0645\u06cc\u200c\u062f\u0627\u0646\u06cc\u060c \u0635\u0631\u06cc\u062d "
    "\u0628\u06af\u0648 \u0648 \u062d\u062f\u0633 \u0646\u0632\u0646. "
    "\u0628\u0627 \u0627\u062d\u062a\u0631\u0627\u0645 \u0645\u062e\u0627\u0644\u0641\u062a "
    "\u06a9\u0646\u061b \u0635\u0631\u0641\u0627\u064b \u0628\u0631\u0627\u06cc "
    "\u0645\u0648\u0627\u0641\u0642\u062a \u067e\u0627\u0633\u062e \u0646\u062f\u0647. "
    "\u0628\u0627 \u0641\u0639\u0627\u0644 \u0628\u0648\u062f\u0646 DREAM_ALLOW_NETWORK "
    "\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u06cc \u0628\u0627 search_web "
    "\u062c\u0633\u062a\u062c\u0648 \u0648 \u0628\u0627 read_page "
    "\u0635\u0641\u062d\u0647 \u0628\u062e\u0648\u0627\u0646\u06cc\u061b "
    "\u0627\u06af\u0631 \u062e\u0627\u0645\u0648\u0634 \u0627\u0633\u062a "
    "\u0631\u0648\u0634\u0646 \u0628\u06af\u0648. \u0627\u0632 "
    "\u062e\u0627\u0637\u0631\u0647\u200c\u0647\u0627 \u0637\u0628\u06cc\u0639\u06cc "
    "\u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646\u060c \u0646\u0647 "
    "\u0628\u0647 \u0634\u06a9\u0644 \u0641\u0647\u0631\u0633\u062a."
)

# The extraction pass writes memory automatically now, so the prompt's memory
# job is no longer teaching the model to store — it is telling the model to
# *use* what the store recalls. remember_fact stays registered for facts the
# extraction pass cannot see, and the prompt names it once, on one line.
_MEMORY_USAGE = (
    "\n\nبخش خاطره‌ها در ادامه واقعیت‌هایی است که همین کاربر قبلاً درباره خودش گفته است. "
    "آن‌ها را درست و قطعی بدان؛ به شکل طبیعی در پاسخ به کار ببر، نه به شکل فهرست، و "
    "هرگز اعلام نکن که حافظه را بررسی کرده‌ای. اگر پاسخ سؤال کاربر در همین بخش هست، "
    "مستقیم از همین خاطره‌ها پاسخ بده و از کاربر نخواه دوباره بگوید. اگر واقعیت ماندگار "
    "تازه‌ای شنیدی که هنوز در خاطره‌ها نیست، می‌توانی آن را با ابزار remember_fact ذخیره "
    "کنی؛ ذخیره‌سازی بی‌صدا است."
)

# Reminder tool usage: the model is told it can create a reminder.
_REMINDER_TOOL_USAGE = (
    "\n\n"
    "\u0627\u06af\u0631 \u06a9\u0627\u0631\u0628\u0631 \u062e\u0648\u0627\u0633\u062a "
    "\u0686\u06cc\u0632\u06cc \u0631\u0627 \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u06a9\u0646\u06cc \u2014 \u0645\u062b\u0644 "
    "\u00ab\u0641\u0631\u062f\u0627 \u0628\u0647 \u0645\u0646 "
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u06a9\u0646\u00bb \u06cc\u0627 "
    "\u00ab\u067e\u0627\u0646\u0632\u062f\u0647\u0645 \u0645\u0647\u0631 "
    "\u0642\u0633\u0637 \u0631\u0627 \u06cc\u0627\u062f\u0645 \u0628\u0646\u062f\u0627\u0632\u00bb "
    "\u2014 \u0641\u0642\u0637 \u0628\u0627 \u0627\u0628\u0632\u0627\u0631 "
    "create_reminder \u0628\u0633\u0627\u0632\u061b "
    "\u0647\u0631\u06af\u0632 \u0646\u06af\u0648 \u0633\u0627\u062e\u062a\u0645 "
    "\u062f\u0631 \u062d\u0627\u0644\u06cc \u06a9\u0647 \u0646\u0633\u0627\u062e\u062a\u06cc. "
    "\u067e\u0627\u0631\u0627\u0645\u062a\u0631 date \u062a\u0627\u0631\u06cc\u062e "
    "\u0633\u0631\u0631\u0633\u06cc\u062f \u0627\u0633\u062a: YYYY-MM-DD "
    "(\u0633\u0627\u0644 \u0634\u0645\u0633\u06cc <1700) \u06cc\u0627 "
    "\u0639\u0628\u0627\u0631\u062a \u0641\u0627\u0631\u0633\u06cc "
    "\u0645\u062b\u0644 \u00ab\u0641\u0631\u062f\u0627\u00bb\u060c "
    "\u00ab\u067e\u0627\u0646\u0632\u062f\u0647\u0645 \u0645\u0647\u0631\u00bb\u060c "
    "\u00ab\u0627\u0648\u0644 \u0647\u0631 \u0645\u0627\u0647\u00bb. "
    "\u0627\u06af\u0631 date \u0631\u0627 \u0646\u0641\u0647\u0645\u06cc\u062f\u06cc "
    "\u0647\u0645\u0627\u0646 \u067e\u06cc\u0627\u0645 \u0627\u0628\u0632\u0627\u0631 \u0631\u0627 "
    "\u0628\u0647 \u06a9\u0627\u0631\u0628\u0631 \u0628\u06af\u0648 \u0648 "
    "\u062d\u062f\u0633 \u0646\u0632\u0646. "
    "\u0632\u0645\u0627\u0646 \u00ab\u0633\u0627\u0639\u062a\u00bb "
    "\u062f\u0631 date \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc "
    "\u0646\u0645\u06cc\u0634\u0648\u062f\u061b \u0633\u0627\u0639\u062a \u0631\u0627 "
    "\u062f\u0631 \u0645\u062a\u0646 \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u0628\u0646\u0648\u06cc\u0633. "
    "\u0628\u0639\u062f \u0627\u0632 \u0645\u0648\u0641\u0642\u06cc\u062a "
    "\u062a\u0627\u0631\u06cc\u062e \u0634\u0645\u0633\u06cc \u0648 "
    "\u0645\u062a\u0646 \u0630\u062e\u06cc\u0631\u0647\u0634\u062f\u0647 \u0631\u0627 "
    "\u062f\u0631 \u067e\u0627\u0633\u062e \u062a\u06a9\u0631\u0627\u0631 "
    "\u06a9\u0646 \u062a\u0627 \u06a9\u0627\u0631\u0628\u0631 "
    "\u0628\u062a\u0648\u0627\u0646\u062f \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646\u062f."
)

# Reminder cancellation usage: taking a reminder back is cancel_reminder's
# job, never a claim without the call. The model passes the owner's text (and
# the date, when the owner gives one); when the tool reports several rows it
# relays the list and asks for the date instead of choosing — the data
# integrity floor — and after success it repeats the cancelled text and
# Jalali date so the owner can verify the removal. Gloss (plain spelling):
# «اگر کاربر خواست یادآوری‌ای را لغو یا حذف کند — مثل «یادآوری قسط وام را لغو
# کن» — فقط با ابزار cancel_reminder لغو کن؛ هرگز نگو لغو کردم در حالی که
# نکردی. پارامتر text متن یادآوری است؛ اگر کاربر تاریخ گفت، آن تاریخ را مثل
# «1405-05-19» یا «فردا» در پارامتر date بفرست. اگر ابزار گفت چند یادآوری
# پیدا شد، فهرستش را به کاربر بگو و تاریخش را بپرس؛ خودت انتخاب نکن. بعد از
# موفقیت، متن و تاریخ شمسی یادآوریِ لغوشده را عیناً از پاسخ ابزار تکرار کن.»
_REMINDER_CANCEL_USAGE = (
    "\n\n"
    "\u0627\u06af\u0631 \u06a9\u0627\u0631\u0628\u0631 \u062e\u0648\u0627\u0633\u062a "
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc\u200c\u0627\u06cc \u0631\u0627 "
    "\u0644\u063a\u0648 \u06cc\u0627 \u062d\u0630\u0641 \u06a9\u0646\u062f "
    "\u2014 \u0645\u062b\u0644 "
    "\u00ab\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u0642\u0633\u0637 \u0648\u0627\u0645 \u0631\u0627 "
    "\u0644\u063a\u0648 \u06a9\u0646\u00bb \u2014 "
    "\u0641\u0642\u0637 \u0628\u0627 \u0627\u0628\u0632\u0627\u0631 "
    "cancel_reminder \u0644\u063a\u0648 \u06a9\u0646\u061b "
    "\u0647\u0631\u06af\u0632 \u0646\u06af\u0648 \u0644\u063a\u0648 "
    "\u06a9\u0631\u062f\u0645 \u062f\u0631 \u062d\u0627\u0644\u06cc "
    "\u06a9\u0647 \u0646\u06a9\u0631\u062f\u06cc. "
    "\u067e\u0627\u0631\u0627\u0645\u062a\u0631 text "
    "\u0645\u062a\u0646 \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u0627\u0633\u062a\u061b \u0627\u06af\u0631 \u06a9\u0627\u0631\u0628\u0631 "
    "\u062a\u0627\u0631\u06cc\u062e \u06af\u0641\u062a\u060c "
    "\u0622\u0646 \u062a\u0627\u0631\u06cc\u062e \u0631\u0627 "
    "\u0645\u062b\u0644 \u00ab1405-05-19\u00bb \u06cc\u0627 "
    "\u00ab\u0641\u0631\u062f\u0627\u00bb \u062f\u0631 "
    "\u067e\u0627\u0631\u0627\u0645\u062a\u0631 date "
    "\u0628\u0641\u0631\u0633\u062a. "
    "\u0627\u06af\u0631 \u0627\u0628\u0632\u0627\u0631 \u06af\u0641\u062a "
    "\u0686\u0646\u062f \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u067e\u06cc\u062f\u0627 \u0634\u062f\u060c "
    "\u0641\u0647\u0631\u0633\u062a\u0634 \u0631\u0627 \u0628\u0647 "
    "\u06a9\u0627\u0631\u0628\u0631 \u0628\u06af\u0648 \u0648 "
    "\u062a\u0627\u0631\u06cc\u062e\u0634 \u0631\u0627 "
    "\u0628\u067e\u0631\u0633\u061b \u062e\u0648\u062f\u062a "
    "\u0627\u0646\u062a\u062e\u0627\u0628 \u0646\u06a9\u0646. "
    "\u0628\u0639\u062f \u0627\u0632 \u0645\u0648\u0641\u0642\u06cc\u062a\u060c "
    "\u0645\u062a\u0646 \u0648 \u062a\u0627\u0631\u06cc\u062e "
    "\u0634\u0645\u0633\u06cc \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc\u0650 "
    "\u0644\u063a\u0648\u0634\u062f\u0647 \u0631\u0627 "
    "\u0639\u06cc\u0646\u0627\u064b \u0627\u0632 \u067e\u0627\u0633\u062e "
    "\u0627\u0628\u0632\u0627\u0631 \u062a\u06a9\u0631\u0627\u0631 \u06a9\u0646."
)

# The block markers stay bracketed so the block is scannable, but the words
# are Persian: an English header inside a Persian prompt invites the model to
# drift languages right where it must answer in Persian.
_MEMORIES_OPEN = "[خاطره‌های بازیابی‌شده — زمینه خصوصی]"
_MEMORIES_CLOSE = "[پایان خاطره‌ها]"

# Scheduled reminders get their own labelled section, placed between the usage
# instructions and the memory section, so the model answers with the owner's
# stored date rather than general knowledge. The section is omitted entirely
# when nothing is relevant or due, so a turn that has nothing to do with
# reminders sends byte-for-byte the same prompt as before this feature.
#
# New Persian strings are written as backslash-u escapes, matching the
# convention in tests/test_extraction_prompt.py and dream/memory.py.
_REMINDERS_OPEN = "[\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc\u0647\u0627]"
_REMINDERS_CLOSE = (
    "[\u067e\u0627\u06cc\u0627\u0646 \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc\u0647\u0627]"
)

# «بخش یادآوریها کارهایی است که کاربر با تاریخ مشخص برای خودش ثبت کرده. اگر
# سؤال کاربر درباره یکی از همین کارهاست، تاریخ ثبت‌شده را از همین بخش بگو و حدس
# نزن. یادآوری‌ای که سررسیدش گذشته یا نزدیک است مهم‌تر است و باید در پاسخ دیده
# شود.»
_REMINDER_USAGE = (
    "\n\n"
    "\u0628\u062e\u0634 \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc\u0647\u0627 "
    "\u06a9\u0627\u0631\u0647\u0627\u06cc\u06cc \u0627\u0633\u062a \u06a9\u0647 "
    "\u06a9\u0627\u0631\u0628\u0631 \u0628\u0627 \u062a\u0627\u0631\u06cc\u062e "
    "\u0645\u0634\u062e\u0635 \u0628\u0631\u0627\u06cc \u062e\u0648\u062f\u0634 "
    "\u062b\u0628\u062a \u06a9\u0631\u062f\u0647. "
    "\u0627\u06af\u0631 \u0633\u0624\u0627\u0644 \u06a9\u0627\u0631\u0628\u0631 "
    "\u062f\u0631\u0628\u0627\u0631\u0647 \u06cc\u06a9\u06cc \u0627\u0632 "
    "\u0647\u0645\u06cc\u0646 \u06a9\u0627\u0631\u0647\u0627\u0633\u062a\u060c "
    "\u062a\u0627\u0631\u06cc\u062e \u062b\u0628\u062a\u200c\u0634\u062f\u0647 "
    "\u0631\u0627 \u0627\u0632 \u0647\u0645\u06cc\u0646 \u0628\u062e\u0634 "
    "\u0628\u06af\u0648 \u0648 \u062d\u062f\u0633 \u0646\u0632\u0646. "
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc\u200c\u0627\u06cc \u06a9\u0647 "
    "\u0633\u0631\u0631\u0633\u06cc\u062f\u0634 \u06af\u0630\u0634\u062a\u0647 "
    "\u06cc\u0627 \u0646\u0632\u062f\u06cc\u06a9 \u0627\u0633\u062a "
    "\u0645\u0647\u0645\u200c\u062a\u0631 \u0627\u0633\u062a \u0648 \u0628\u0627\u06cc\u062f "
    "\u062f\u0631 \u067e\u0627\u0633\u062e \u062f\u06cc\u062f\u0647 \u0634\u0648\u062f."
)
