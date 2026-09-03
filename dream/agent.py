"""Provider-neutral Dream agent loop with memory and explicit approval gates."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dream.claims import guard_claims
from dream.commerce import Ledger, LedgerError, QuotaExceeded, ledger_attached
from dream.compaction import (
    DEFAULT_ECHO_CONTEXT_TOKENS,
    DEFAULT_MODEL_CONTEXT_TOKENS,
    DEFAULT_THRESHOLD,
    deterministic_summary,
    split_for_compaction,
    usage,
)
from dream.extraction import (
    STATUS_ABANDONED,
    STATUS_DISABLED,
    STATUS_ERROR,
    STATUS_FACTS_FOUND,
    STATUS_NO_FACTS,
    STATUS_TOO_SHORT,
    STATUS_UNPARSEABLE,
    ExtractionResult,
    extract_facts,
)
from dream.memory import Memory, MemoryStore, normalize_fa
from dream.memory_stores import (
    BOUNDED_MEMORY_USAGE,
    NOTES_LABEL,
    PROFILE_LABEL,
    TARGET_MEMORY,
    TARGET_USER,
    BoundedMemory,
    BoundedSnapshot,
)
from dream.metrics import (
    METRIC_EXTRACTION_ABANDONED,
    METRIC_EXTRACTION_ERROR,
    METRIC_EXTRACTION_NO_FACTS,
    METRIC_EXTRACTION_PARSE_ERROR,
    METRIC_EXTRACTION_SKIPPED,
    METRIC_EXTRACTION_STORE_ERROR,
    METRIC_EXTRACTION_SUCCESS,
    metrics,
)
from dream.normalization import normalize_importance, normalize_kind
from dream.providers import BuiltInMemoryProvider, ProviderManager
from dream.reliability.sleep import interruptible_sleep
from dream.reminders import (
    Reminder,
    format_jalali,
    parse_date_to_timestamp,
    parse_persian_date,
    prompt_reminders,
)
from dream.skills import SkillPromptProvider, apply_slash_invocation, render_skill_catalog
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

# The structured logger used by the agent and its background extraction worker.
# Extraction log records carry only safe metadata (status, exception class, a
# short redacted message) — never the extraction prompt, raw model output, full
# user content, API credentials, or filesystem/database paths.
log = logging.getLogger("dream.agent")

# Extraction-pass status -> metric name. Every completed pass increments
# exactly one of these from the single call site that finalizes a turn's
# extraction result, so a pass is never double-counted across the background
# worker and the turn that waits on it. ``store_error`` is intentionally absent
# here: storage failures are recorded per fact-write inside the worker against
# ``METRIC_EXTRACTION_STORE_ERROR`` while the pass status stays ``facts_found``
# (extraction itself succeeded; the CLI still surfaces the lost writes).
_EXTRACTION_STATUS_METRIC: dict[str, str] = {
    STATUS_FACTS_FOUND: METRIC_EXTRACTION_SUCCESS,
    STATUS_NO_FACTS: METRIC_EXTRACTION_NO_FACTS,
    STATUS_DISABLED: METRIC_EXTRACTION_SKIPPED,
    STATUS_TOO_SHORT: METRIC_EXTRACTION_SKIPPED,
    STATUS_UNPARSEABLE: METRIC_EXTRACTION_PARSE_ERROR,
    STATUS_ERROR: METRIC_EXTRACTION_ERROR,
    STATUS_ABANDONED: METRIC_EXTRACTION_ABANDONED,
}

# Which extraction statuses are worth a WARNING-level record. Benign or
# expected outcomes (facts found, none found, disabled, too short) stay quiet
# at DEBUG so the default WARNING root level does not spam a terminal.
_EXTRACTION_WARNING_STATUSES: frozenset[str] = frozenset(
    {STATUS_UNPARSEABLE, STATUS_ERROR, STATUS_ABANDONED}
)

# Cap and collapse free-form exception messages before they can reach a log,
# so a verbose or multiline provider/store message cannot bloat or leak.
_LOG_MESSAGE_LIMIT = 200


def _safe_log_message(raw: str) -> str:
    """Collapse whitespace and truncate an error message for logging.

    Log records and ExtractionResult.raw_text must never carry the full
    extraction prompt, raw model output, user content, credentials, or
    filesystem paths. A whitespace-collapsed, length-capped message keeps
    the diagnostic readable without echoing anything verbose or sensitive
    verbatim.

    Also masks token-like patterns (8+ chars of alphanumerics, hyphens,
    underscores) with ``***`` so API keys and bearer tokens in exception
    messages are not exposed verbatim.
    """
    import re
    collapsed = " ".join(raw.split())

    # Mask token-like patterns: 8+ chars of alphanumerics, hyphens, underscores
    collapsed = re.sub(r"[A-Za-z0-9_-]{8,}", "***", collapsed)

    if len(collapsed) <= _LOG_MESSAGE_LIMIT:
        return collapsed
    return collapsed[:_LOG_MESSAGE_LIMIT] + "..."


def _record_extraction_status(result: ExtractionResult) -> None:
    """Increment the metric and emit the log for one finalized extraction pass.

    Called exactly once per turn from the single place that finalizes the turn's
    extraction result (successful completion, abandoned, or a synthetic error),
    so a pass is never double-counted. Only safe metadata is logged.
    """
    metric = _EXTRACTION_STATUS_METRIC.get(result.status)
    if metric is not None:
        metrics.incr(metric)
    if result.status in _EXTRACTION_WARNING_STATUSES:
        log.warning(
            "extraction pass failed",
            extra={"extraction_status": result.status},
        )
    else:
        log.debug(
            "extraction pass completed",
            extra={"extraction_status": result.status, "facts": len(result.facts)},
        )


def _record_store_failure(errors: list[str], exc: Exception) -> None:
    """Record one persistence failure during extraction, visibly and safely.

    Appends a diagnostic for the CLI (as before), increments the store-error
    metric, and emits a redacted warning. Storage failures are never silent,
    but the pass status itself stays ``facts_found`` — extraction succeeded and
    only the write to durable memory failed.
    """
    errors.append(f"{type(exc).__name__}: {exc}")
    metrics.incr(METRIC_EXTRACTION_STORE_ERROR)
    log.warning(
        "extraction store failure",
        extra={
            "extraction_status": "store_error",
            "exception_type": type(exc).__name__,
            "error": _safe_log_message(str(exc)),
        },
    )


# Tools Dream registers as per-instance closures bound to the owning
# agent's stores (memory, reminders, bounded stores). A child agent rebinds
# the memory/reminder names to its own ephemeral store in its own
# ``__init__``; the bounded-store names only exist when a parent attached
# ``BoundedMemory``, so a child can never rebind them. The subagent builder
# uses this set to refuse grants that would hand a child a parent-bound
# closure verbatim (MEM Stage A: agent_notes/user_profile must never reach
# a parent's bounded stores from inside a subagent).
INSTANCE_BOUND_TOOL_NAMES = frozenset(
    {
        "remember_fact",
        "search_memory",
        "forget_memory",
        "create_reminder",
        "cancel_reminder",
        "agent_notes",
        "user_profile",
    }
)


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


def _positive_int(raw: str | None, default: int, minimum: int = 1, maximum: int = 1_000_000) -> int:
    """Parse a bounded positive integer environment setting safely."""
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        return default
    return value if minimum <= value <= maximum else default


def _fraction(raw: str | None, default: float) -> float:
    """Parse a safe compaction threshold between zero and one."""
    try:
        value = float(raw or default)
    except (TypeError, ValueError):
        return default
    return value if 0.1 <= value < 1.0 else default


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
        reasoning_effort: str | None = None,
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
        self.reasoning_effort = (
            reasoning_effort if reasoning_effort in {"low", "medium", "high"} else None
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
                # The OpenAIBackend call is synchronous and has no cancellation
                # token today; the helper is still used so future callers can
                # wire one without re-introducing blocking time.sleep.
                interruptible_sleep(self.retry_backoff_seconds * (2**attempt))
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
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
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
    if selected in ("aval", "avalai"):
        # Aval AI is an OpenAI-compatible endpoint (see ``dream/router.py``
        # and the Aval section of ``.env.example``). The base URL and key come
        # from the same environment names the router reads: ``OPENAI_BASE_URL``
        # wins, the documented Aval host is the fallback, and the key is
        # ``OPENAI_API_KEY`` or the Aval-specific ``AVALAI_API_KEY``.
        return OpenAIBackend(
            base_url=os.environ.get("OPENAI_BASE_URL") or "https://api.avalai.ir/v1",
            api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("AVALAI_API_KEY"),
        )
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
    """Approval rules based exclusively on each registered tool's real risk.

    Evaluation order is a contract (SEC Stage B): the L3 security floor runs
    BEFORE any approval logic and cannot be overridden by modes, autonomous
    contexts, approvers, or auto-approve (``--yolo``-style) grants.
    """

    auto_approve: set[str] = field(default_factory=lambda: {"safe", "guarded"})
    always_ask: set[str] = field(default_factory=lambda: {"dangerous"})
    ask: Callable[[str, dict[str, Any]], bool] | None = None
    registry: Mapping[str, Any] | None = None
    """Private tool table to resolve risk from; ``None`` uses the global one.

    A subagent dispatches against its own grant, so its policy must judge risk
    from the same mapping. Reading the global registry here would let a name
    the subagent was never granted resolve to a real risk tier.
    """
    context: str = "interactive"
    """Execution context for autonomous runs: ``interactive``, ``cron`` or
    ``single_query``. Autonomous contexts deny dangerous tools by default."""
    security: Any = None
    """SecurityEngine to evaluate dangerous calls; ``None`` uses the
    process-wide default engine."""
    scope: str = "admin"
    """SEC Stage E (G-01): the linked user's permission scope —
    ``chat_only | safe_tools | guarded_tools | admin``. Tools above the
    scope's ceiling are refused; the floor still precedes the gate."""
    attempt_limiter: Callable[[str, dict[str, Any]], bool] | None = None
    """SEC Stage E (G-02): optional per-user approval-attempt throttle.
    Called for dangerous tools that passed floor and scope; ``False``
    refuses with a rate-limit denial."""

    #: The risk ceiling each scope may reach (G-01). Class-level constant —
    #: not a dataclass field.
    _SCOPE_CEILING = {
        "chat_only": frozenset(),
        "safe_tools": frozenset({"safe"}),
        "guarded_tools": frozenset({"safe", "guarded"}),
        "admin": frozenset({"safe", "guarded", "dangerous"}),
    }

    def allows(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        from dream.security.engine import default_engine

        registered = (REGISTRY if self.registry is None else self.registry).get(tool_name)
        if registered is None:
            return False, "unknown tool"
        risk = registered.risk
        engine = self.security if self.security is not None else default_engine()
        ceiling = self._SCOPE_CEILING.get(self.scope, frozenset())
        if risk == "dangerous":
            # Contract: the L3 floor precedes EVERY approval-layer gate —
            # scope, throttles, contexts and modes alike.
            refusal = engine.floor_check(tool_name, arguments)
            if refusal is not None:
                return False, refusal
            if "dangerous" not in ceiling:
                return (
                    False,
                    f"dangerous tool denied: scope {self.scope!r} does not allow it",
                )
            if self.attempt_limiter is not None and not self.attempt_limiter(
                tool_name, arguments
            ):
                return False, "dangerous tool denied: too many approval attempts"
            if risk in self.always_ask or self.context != "interactive":
                # Floor -> autonomous-context gate -> mode, in that order,
                # all inside the engine; nothing below can override the floor.
                decision = engine.evaluate_dangerous(
                    tool_name, arguments, context=self.context, ask=self.ask
                )
                return decision.allowed, decision.reason
            return True, "dangerous tool auto-approved"
        if risk not in ceiling:
            return False, f"{risk} tool denied: scope {self.scope!r} does not allow it"
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
        bounded: BoundedMemory | None = None,
        demo: bool = False,
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
        self.demo = bool(demo)
        # The usage ledger hook: attached only when DREAM_PLAN is not local
        # or DREAM_LEDGER is set, so the unlimited local plan runs with no
        # ledger file at all. Metered plans fail closed on a corrupt ledger.
        # A misconfigured ledger (unknown plan name) must not crash the agent
        # at construction: the Persian refusal is held and returned by run().
        self.ledger: Ledger | None = None
        self._ledger_refusal: str | None = None
        try:
            self.ledger = Ledger.from_env() if ledger_attached() else None
        except LedgerError as exc:
            self._ledger_refusal = str(exc)
        self.memory_block_char_limit = _resolve_memory_block_char_limit(
            os.environ.get("DREAM_MEMORY_BLOCK_CHAR_LIMIT")
        )
        self.extraction_timeout_seconds = _resolve_extraction_timeout(
            os.environ.get("DREAM_EXTRACTION_TIMEOUT_SECONDS")
        )
        self.history: list[dict[str, Any]] = []
        # Stage E: accounting is local and deterministic. Echo defaults generously
        # so ordinary offline turns never compact unless explicitly configured.
        default_window = (
            DEFAULT_ECHO_CONTEXT_TOKENS if isinstance(self.backend, EchoBackend) else DEFAULT_MODEL_CONTEXT_TOKENS  # noqa: E501
        )
        self.context_tokens = _positive_int(os.environ.get("DREAM_CONTEXT_TOKENS"), default_window)
        self.compaction_threshold = _fraction(os.environ.get("DREAM_COMPACTION_THRESHOLD"), DEFAULT_THRESHOLD)  # noqa: E501
        self.compaction_keep_messages = _positive_int(os.environ.get("DREAM_COMPACTION_KEEP_MESSAGES"), 4, 2, 100)  # noqa: E501
        self._compaction_summary = ""
        self._turn_count = 0
        self.nudge_every_turns = _positive_int(os.environ.get("DREAM_MEMORY_NUDGE_EVERY_TURNS"), 8, 1, 10_000)  # noqa: E501
        self.nudges_enabled = os.environ.get("DREAM_MEMORY_NUDGES", "1").lower() not in {"0", "false", "off", "no"}  # noqa: E501
        self._nudge_sent = False
        self._created: list[Memory] = []
        self._superseded: list[Memory] = []
        self._merged: list[Memory] = []
        # The dual bounded stores (MEM Stage A): agent notes + user profile.
        # Attachment is explicit so existing embedders see no new files; the
        # snapshots are frozen for the session at construction time.
        self.bounded = bounded
        self._bounded_snapshots: dict[str, BoundedSnapshot] | None = None
        self._bounded_prompt: str | None = None
        self._refresh_bounded_snapshots()
        self._register_memory_tools()
        self._register_reminder_tools()
        self._register_bounded_memory_tools()

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
        """Discard conversational context without touching durable memory.

        Starting a new conversational session also takes a fresh frozen
        snapshot of the bounded stores: the previous session's snapshot was
        frozen for that session's lifetime, and the new one must reflect
        everything the tools wrote since.
        """
        self.history.clear()
        self._compaction_summary = ""
        self._turn_count = 0
        self._nudge_sent = False
        self._refresh_bounded_snapshots()

    def _refresh_bounded_snapshots(self) -> None:
        """Freeze the bounded-store snapshots and render their prompt block.

        Called once at construction (session start) and again by
        :meth:`reset_session`. Between those points the block is a constant
        string: writes made through the tools land in the stores and in the
        tools' own result payloads, never retroactively in the running
        session's prompt.
        """
        if self.bounded is None:
            self._bounded_snapshots = None
            self._bounded_prompt = None
            return
        snapshots = self.bounded.snapshots()
        self._bounded_snapshots = snapshots
        sections = [BOUNDED_MEMORY_USAGE]
        for label, snapshot in (
            (NOTES_LABEL, snapshots[TARGET_MEMORY]),
            (PROFILE_LABEL, snapshots[TARGET_USER]),
        ):
            section = f"\n\n[{label}]\n{snapshot.header}"
            if snapshot.text:
                section += f"\n{snapshot.text}"
            sections.append(section)
        self._bounded_prompt = "".join(sections)

    def _register_bounded_memory_tools(self) -> None:
        """Register the two bounded-store edit tools (MEM Stage A).

        The action surface is exactly add / replace / remove; there is no
        read action because the frozen snapshot is already in the system
        prompt and every mutation returns the fresh store state. The risk
        tier is ``guarded`` — local, reversible writes, logged on execution —
        matching ``remember_fact``.
        """
        if self.bounded is None:
            return
        bounded = self.bounded

        def _bounded_result(target: str, action: str, snapshot: BoundedSnapshot):
            return {
                "target": target,
                "action": action,
                "header": snapshot.header,
                "used_chars": snapshot.used_chars,
                "capacity": snapshot.capacity,
                "entries": len(snapshot.entries),
                "content": snapshot.text,
            }

        def _apply(
            store, target: str, action: str, text: str, old: str, new: str
        ):
            if action == "add":
                return _bounded_result(target, action, store.add(text))
            if action == "replace":
                return _bounded_result(target, action, store.replace(old, new))
            if action == "remove":
                return _bounded_result(target, action, store.remove(old))
            raise ValueError(f"action must be add, replace, or remove, got {action!r}")

        @tool(risk="guarded")
        def agent_notes(
            action: Literal["add", "replace", "remove"],
            text: str = "",
            old: str = "",
            new: str = "",
        ) -> dict[str, Any]:
            """Edit the agent's durable notes store (bounded, §-separated).

            The store is character-bounded; when it is full the tool returns
            an error instead of truncating — consolidate near-duplicate
            entries with replace, or drop stale ones with remove, then retry
            in the same turn.

            :param action: add appends an entry; replace swaps the unique
                entry containing old for new; remove deletes the unique entry
                containing old.
            :param text: Entry text, for action add.
            :param old: Substring identifying one entry, for replace/remove.
            :param new: Replacement entry text, for action replace.
            """
            return _apply(bounded.notes, TARGET_MEMORY, action, text, old, new)

        @tool(risk="guarded")
        def user_profile(
            action: Literal["add", "replace", "remove"],
            text: str = "",
            old: str = "",
            new: str = "",
        ) -> dict[str, Any]:
            """Edit the durable user-profile store (bounded, §-separated).

            Holds durable facts about the user: preferences, constraints,
            identity details worth remembering across sessions. The store is
            character-bounded; on overflow the tool errors — consolidate with
            replace or remove, then retry in the same turn.

            :param action: add appends an entry; replace swaps the unique
                entry containing old for new; remove deletes the unique entry
                containing old.
            :param text: Entry text, for action add.
            :param old: Substring identifying one entry, for replace/remove.
            :param new: Replacement entry text, for action replace.
            """
            return _apply(bounded.profile, TARGET_USER, action, text, old, new)

    @property
    def ledger_attached(self) -> bool:
        """True when this agent meters turns against a usage ledger.

        False for the default local plan: ``Dream(store, EchoBackend())``
        carries no meter and needs no ledger file. It is also true when the
        ledger is misconfigured, because a broken meter still gates the turn
        (fail-closed) rather than disappearing.
        """
        return self.ledger is not None or self._ledger_refusal is not None

    def _ledger_block(self) -> str | None:
        """Consume one turn on the attached ledger; return a Persian refusal.

        Returns ``None`` when the turn may proceed. Raises nothing: every
        ledger refusal (quota exhausted, corrupt file, unknown plan) becomes
        the turn's reply so the caller always receives a ``Turn``.
        """
        if self._ledger_refusal is not None:
            return self._ledger_refusal
        if self.ledger is None:
            return None
        try:
            self.ledger.consume()
        except (QuotaExceeded, LedgerError) as exc:
            return str(exc)
        return None

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
        # Stage C catalog: name + description only, own budget, never a body.
        catalog_block, _ = render_skill_catalog()
        if catalog_block:
            prompt += catalog_block
        # The frozen bounded-store snapshots (MEM Stage A) ride with the
        # system prompt as a constant per-session block, after the usage
        # sentences and before the per-turn reminder/recalled-memory sections.
        if self._bounded_prompt is not None:
            prompt += self._bounded_prompt
        if self._compaction_summary:
            prompt += "\n\n" + self._compaction_summary
        if self._nudge_due():
            prompt += (
                "\n\nMemory nudge / "
                "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
                "\u062d\u0627\u0641\u0638\u0647: "
                "Persist only durable preferences or facts through the bounded memory tools; "
                "\u0641\u0642\u0637 "
                "\u062f\u0627\u0646\u0633\u062a\u0647\u200c\u0647\u0627\u06cc "
                "\u0645\u0627\u0646\u062f\u06af\u0627\u0631 \u0631\u0627 "
                "\u0630\u062e\u06cc\u0631\u0647 \u06a9\u0646."
            )
        if memory_block is None:
            memory_block, _ = self._memory_block(memories)
        middle = ""
        if reminder_block:
            middle = _REMINDER_USAGE + reminder_block
        return {"role": "system", "content": prompt + middle + memory_block}

    def context_usage(self) -> dict[str, float | int]:
        """Expose local accounting for transcripts, tests, and bridge clients."""
        current = usage(self.history, self.context_tokens)
        return {"tokens": current.tokens, "window": current.window, "ratio": current.ratio}

    def _nudge_due(self) -> bool:
        return self.nudges_enabled and not self.demo and not self._nudge_sent and self._turn_count >= self.nudge_every_turns  # noqa: E501

    def compact(self, reason: str = "threshold") -> dict[str, Any]:
        """Compact only at a turn boundary; retain the active recent exchange."""
        model_history = [item for item in self.history if item.get("role") in {"user", "assistant", "tool"}]  # noqa: E501
        before = usage(model_history, self.context_tokens)
        dropped, kept = split_for_compaction(model_history, self.compaction_keep_messages)
        if not dropped:
            return {"compacted": False, "before_tokens": before.tokens, "after_tokens": before.tokens}  # noqa: E501
        summary = deterministic_summary(dropped, reason)
        self._compaction_summary = (self._compaction_summary + "\n" + summary).strip()
        prior_events = [item for item in self.history if item.get("kind") == "compaction"]
        self.history = prior_events + kept
        after = usage(kept, self.context_tokens)
        event = {
            "kind": "compaction", "timestamp": time.time(), "reason": reason,
            "before_tokens": before.tokens, "after_tokens": after.tokens,
            "preserved_messages": len(kept), "summary": summary,
        }
        self.history.insert(0, event)
        return {"compacted": True, **event}

    def _compact_if_needed(self) -> None:
        estimate = usage(self.history, self.context_tokens)
        if estimate.ratio >= self.compaction_threshold:
            self.compact("threshold")

    def run(self, message: str) -> Turn:
        """Run one complete user turn, including any model-requested tools."""
        self._compact_if_needed()
        # Metering gate: a turn is consumed (and possibly refused) before any
        # backend call, memory write, or journal entry. The refusal is a
        # normal Turn whose reply is the Persian quota/corruption sentence, so
        # every caller gets a reply and no code path grants a free turn on a
        # broken meter.
        ledger_block = self._ledger_block()
        if ledger_block is not None:
            return Turn(ledger_block, [], [], [], 0.0)
        started = time.monotonic()
        self._created.clear()
        self._superseded.clear()
        self._merged.clear()
        if self.store is not None:
            self.store.log("user", message)
        original_message = message
        stripped = message.lstrip()
        if stripped.lower() == "/compress":
            outcome = self.compact("explicit")
            reply = "Context compacted." if outcome["compacted"] else "Nothing eligible for compaction."  # noqa: E501
            self.history.append({"role": "assistant", "content": reply})
            return Turn(reply, [], [], [], time.monotonic() - started)
        if stripped.startswith("\\"):
            stripped = "/" + stripped[1:]
        if stripped.lower().startswith("/learn"):
            from dream.skills.learn import LearnError, prepare_learn_turn

            try:
                message = prepare_learn_turn(message, history=self.history)
            except LearnError as exc:
                return Turn(str(exc), [], [], [], time.monotonic() - started)
        # Slash stacking: leading skill tokens load bodies into the user turn.
        model_message, slash_stack = apply_slash_invocation(message)
        if slash_stack.invoked:
            try:
                from dream.skills.store import get_ledger

                with get_ledger() as ledger:
                    for skill in slash_stack.skills:
                        ledger.log_use(skill.name, "invoked", duration_ms=0.0, source="slash")
            except Exception:
                pass
        memories = self.manager.recall(message, limit=8, reinforce=True)
        memory_block, injected_memories = self._memory_block(memories)
        reminder_block, _ = self._reminder_block(
            self.manager.list_reminders(),
            message,
            self.memory_block_char_limit - len(memory_block),
        )
        self.history.append({"role": "user", "content": model_message})
        # A second boundary before dispatch ensures a small configured window
        # is never sent an already-overflowing transcript. The just-added user
        # message remains active; no in-flight tool exchange exists yet.
        self._compact_if_needed()
        calls_made: list[dict[str, Any]] = []
        reply = "I could not produce an answer."

        for _ in range(self.max_iterations):
            messages = [
                self._system_message(memories, memory_block, reminder_block, message),
                *(item for item in self.history if item.get("role") in {"user", "assistant", "tool"}),  # noqa: E501
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
        from dream.skills.propose import format_proposal_notice, maybe_propose

        proposal = maybe_propose(original_message, calls_made, demo=self.demo)
        if proposal is not None:
            reply = reply + format_proposal_notice(proposal)
        self.history.append({"role": "assistant", "content": reply})
        if self.store is not None:
            self.store.log("assistant", reply)
        if self._nudge_due():
            self._nudge_sent = True
        self._turn_count += 1

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

        Runs on a worker thread so the reply is never delayed by it. A broken
        provider or fact must never escape into the turn that already produced
        its reply: extract_facts returns a typed ExtractionResult for every
        failure class it knows, and the two bounded catches below only guard
        the unexpected. Cancellation and system exits are always re-raised —
        they are never flattened into a fake result.
        """
        try:
            result = extract_facts(self._extraction_backend(), message)
        except (KeyboardInterrupt, SystemExit):
            raise
        # Redact raw_text after extract_facts returns (extract_facts may have
        # set raw_text directly; this ensures sensitive data is always bounded).
        result.raw_text = _safe_log_message(result.raw_text)
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
                log.debug("extraction store rejected an unusable fact")
                continue
            except (KeyboardInterrupt, SystemExit):
                raise
            except sqlite3.Error as exc:
                # A real storage failure (locked database, full disk, broken
                # constraint, ...). Never silent: record it for the CLI, count
                # it, and log it redacted.
                _record_store_failure(errors, exc)
        outcome.result = result
        outcome.errors = errors

    def _run_extraction(self, message: str) -> tuple[ExtractionResult, list[str]]:
        """Start the extraction pass in the background and wait at most the
        extraction budget for it.

        When the pass finishes within the budget its facts are already in the
        store and are reported on the turn, exactly as before. When it does
        not — the provider hangs — the turn is marked abandoned and the reply
        is returned anyway; the worker keeps running and stores the facts
        when the provider finally answers. The finalized status is recorded
        (metric + structured log) exactly once per turn.
        """
        outcome = _ExtractionOutcome()
        worker = threading.Thread(
            target=self._extract_in_background, args=(message, outcome), daemon=True
        )
        worker.start()
        worker.join(timeout=self.extraction_timeout_seconds)
        if worker.is_alive():
            result = ExtractionResult(
                facts=[],
                status=STATUS_ABANDONED,
                raw_text=(
                    "did not finish within "
                    f"{self.extraction_timeout_seconds:.1f}s"
                ),
            )
            errors: list[str] = []
        else:
            result = outcome.result
            if result is None:
                result = ExtractionResult(
                    facts=[], status=STATUS_ERROR, raw_text="extraction produced no result"
                )
            errors = outcome.errors
        _record_extraction_status(result)
        return result, errors


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
