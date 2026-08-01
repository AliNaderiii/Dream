"""Provider-neutral Dream agent loop with memory and explicit approval gates."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dream.extraction import extract_facts
from dream.memory import Memory, MemoryStore
from dream.normalization import normalize_importance, normalize_kind
from dream.tools import REGISTRY, execute, openai_schemas, tool


class OpenAIBackend:
    """Client for any endpoint implementing OpenAI's chat-completions API."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model or os.environ.get("DREAM_MODEL", "")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
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
            return {"content": message.get("content"), "tool_calls": calls}
        except HTTPError as exc:
            # The body is where the server says what it rejected; keep it.
            return self._failure(_describe_http_error(exc))
        except (URLError, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
            return self._failure(f"{type(exc).__name__}: {exc}")

    def _failure(self, detail: str) -> dict[str, Any]:
        """Report a failed request without ever echoing the credential."""
        return {
            "content": f"Model request failed: {_redact(detail, self.api_key)}",
            "tool_calls": [],
        }


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
class Turn:
    """Observable record of one user turn through the agent loop."""

    reply: str
    tool_calls: list[dict[str, Any]]
    memories_used: list[Memory]
    memories_created: list[Memory]
    elapsed_seconds: float
    extraction: Any = None


class Dream:
    """An agent runtime that combines durable memory, tools, and approval."""

    def __init__(
        self,
        store: MemoryStore,
        backend: OpenAIBackend | OllamaBackend | EchoBackend | None = None,
        approval_policy: ApprovalPolicy | None = None,
        max_iterations: int = 4,
    ) -> None:
        self.store = store
        self.backend = backend or build_backend()
        self.approval_policy = approval_policy or ApprovalPolicy()
        self.max_iterations = max_iterations
        self.history: list[dict[str, Any]] = []
        self._created: list[Memory] = []
        self._register_memory_tools()

    def _register_memory_tools(self) -> None:
        store = self.store
        created = self._created

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

    def reset_session(self) -> None:
        """Discard conversational context without touching durable memory."""
        self.history.clear()

    def _system_message(self, memories: list[Memory]) -> dict[str, str]:
        prompt = _BASE_PROMPT + _MEMORY_POLICY + _MEMORY_EXAMPLE
        if memories:
            lines = [
                f"- [{_relative_age(memory.created_at)}] {memory.content}" for memory in memories
            ]
            prompt += (
                "\n\n[RECALLED MEMORIES — PRIVATE CONTEXT]\n"
                + "\n".join(lines)
                + "\n[END MEMORIES]"
            )
        return {"role": "system", "content": prompt}

    def run(self, message: str) -> Turn:
        """Run one complete user turn, including any model-requested tools."""
        started = time.monotonic()
        self._created.clear()
        self.store.log("user", message)
        memories = self.store.recall(message, reinforce=True)
        self.history.append({"role": "user", "content": message})
        calls_made: list[dict[str, Any]] = []
        reply = "I could not produce an answer."

        for _ in range(self.max_iterations):
            messages = [self._system_message(memories), *self.history]
            response = self.backend.chat(messages, tools=openai_schemas())
            calls = response.get("tool_calls", [])
            if not calls:
                reply = response.get("content") or reply
                self.history.append({"role": "assistant", "content": reply})
                self.store.log("assistant", reply)
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
        else:
            self.history.append({"role": "assistant", "content": reply})
            self.store.log("assistant", reply)

        extraction_result = extract_facts(self.backend, message)
        for fact in getattr(extraction_result, "facts", []):
            try:
                memory = self.store.remember(
                    fact.content,
                    kind=fact.kind,
                    importance=fact.importance,
                    source="extraction",
                )
                if not any(m.id == memory.id for m in self._created):
                    self._created.append(memory)
            except (ValueError, Exception):
                continue

        return Turn(
            reply,
            calls_made,
            memories,
            list(self._created),
            time.monotonic() - started,
            extraction=extraction_result,
        )


def _relative_age(timestamp: float) -> str:
    days = max(0, int((time.time() - timestamp) // 86400))
    if days == 0:
        return "today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


# The language rule is unconditional, so a small model cannot drift away from
# the user's language: reply in the language of the most recent message, reply
# in Persian to Persian input, and never switch to a third language.
_LANGUAGE_RULE = (
    " همیشه به زبان آخرین پیام کاربر پاسخ بده؛ اگر کاربر فارسی نوشت، حتماً فارسی "
    "پاسخ بده؛ هرگز به زبان سومی تغییر نکن."
)

_BASE_PROMPT = (
    "تو Dream هستی: دقیق، آرام و مستقیم."
    + _LANGUAGE_RULE
    + " اگر چیزی را نمی‌دانی، صریح بگو و حدس نزن. با احترام مخالفت کن؛ "
    "صرفاً برای موافقت پاسخ نده. از خاطره‌ها طبیعی استفاده کن، نه به شکل فهرست."
)

# The memory policy tells the model *when* to call remember_fact. Without it a
# small model treats the registered tool as decoration and never stores
# anything, leaving the session with zero persistent memory.
_MEMORY_POLICY = (
    "\n\nسیاست حافظه:\n"
    "- وقتی کاربر یک واقعیت ماندگار درباره خودش می‌گوید — نام، شغل، پروژه‌ها، "
    "ترجیحات، محدودیت‌ها یا تصمیمی که گرفته — ابزار remember_fact را فراخوانی کن.\n"
    "- حرف‌های گذرای گفتگو، سلام‌ها و سؤال‌ها را ذخیره نکن.\n"
    "- در هر فراخوانی فقط یک واقعیت مستقل ذخیره کن، طوری نوشته شود که ماه‌ها بعد "
    "بدون گفتگوی اطرافش معنا بدهد.\n"
    "- kind را آگاهانه انتخاب کن: semantic برای واقعیت‌ها و ترجیحات ماندگار، "
    "episodic برای رویدادهای تاریخ‌دار، procedural برای دستورالعمل‌های رفتاری.\n"
    "- importance را بر اساس مرکزی بودن واقعیت تنظیم کن، نه تازگی آن.\n"
    "- ذخیره‌سازی بی‌صدا است؛ آن را اعلام نکن و اجازه نپرس؛ فقط طبیعی به کاربر پاسخ بده."
)

# Small local models follow a demonstrated pattern far more reliably than a
# described one, so the policy ends with one compact worked example.
_MEMORY_EXAMPLE = (
    "\n\nمثال:\n"
    "کاربر: «من علی هستم و روی پروژه‌ای به نام Dream کار می‌کنم.»\n"
    "این پیام دو واقعیت ماندگار دارد؛ هر کدام را جداگانه ذخیره کن:\n"
    'remember_fact(content="کاربر علی نام دارد", kind="semantic", importance=0.9)\n'
    'remember_fact(content="کاربر روی پروژه‌ای به نام Dream کار می‌کند", '
    'kind="semantic", importance=0.9)\n'
    "سپس بدون اعلام ذخیره‌سازی، عادی پاسخ بده: «سلام علی! چطور می‌توانم کمک کنم؟»"
)
