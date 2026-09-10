"""Agent runtime internals.

This package holds the modular pieces of the Dream agent loop, decomposed
along single-responsibility lines. The public surface lives in
:mod:`dream.agent` (the facade): every name the rest of the codebase or
third-party callers import is re-exported from there unchanged. The modules
inside this package are private implementation details and may evolve
without notice; tests that need to exercise internal helpers continue to
reach them through the facade.

Layout
------

- :mod:`dream.agent.constants` — module-level constants (sampling,
  retry, extraction, log limits) and the structured logger.
- :mod:`dream.agent.env_config` — ``DREAM_*`` environment parsing
  helpers. Pure functions; no side effects beyond logging a rejection.
- :mod:`dream.agent.user_agent` — User-Agent override policy and the
  regexes that gate it.
- :mod:`dream.agent.http_utils` — argument parsing, HTTP error
  description, body truncation, secret redaction.
- :mod:`dream.agent.tools_wire` — chat-completions tool-call wire
  conversion and the CLI approval callback.
- :mod:`dream.agent.approval` — :class:`ApprovalPolicy` and the
  ``INSTANCE_BOUND_TOOL_NAMES`` set.
- :mod:`dream.agent.extraction` — :class:`_ExtractionOutcome` and the
  status / store-failure recording helpers.
- :mod:`dream.agent.reminders` — reminder matching, Persian refusal
  messages, and the prompt-render line for one reminder.
- :mod:`dream.agent.prompts` — Persian and English prompt strings plus
  the system-prompt builder. Strings only; no runtime imports.
- :mod:`dream.agent.backends` — LLM backends: OpenAI-compatible HTTP
  client, Ollama, the deterministic Echo, and the factory.
- :mod:`dream.agent.dream` — the :class:`Dream` agent class, the
  conversation loop, memory/ledger accounting, and turn execution.
- :mod:`dream.agent.logging_utils` — extraction-status metric map and
  WARNING-level status set. Kept separate so backends and prompts do
  not import the metrics singleton.

Stable seam
-----------

The :class:`Dream` class is the *stable seam* of this refactor: the
class signature, the public methods, and the public dataclasses are
unchanged, so every existing caller (CLI, bridge, subagent builder,
test suite) keeps working without modification. Internally the class
delegates to the sibling modules below, so a future change in, say,
how tool calls are dispatched touches one sibling rather than a single
1943-line file.
"""

from __future__ import annotations

# ``urllib.request`` symbols and ``interruptible_sleep`` are re-exported on
# this facade so test fixtures can monkeypatch ``dream.agent.urlopen`` (and
# the sleep helper) and the backend uses the same callable the test patched.
# Without this, the backend holds its own local import of ``urlopen`` and
# monkeypatching the facade has no effect on the HTTP code path. Defining
# the names *first* (before the sibling imports) keeps them reachable as
# attributes of the partially-initialised package during a circular import.
from urllib.error import HTTPError, URLError  # noqa: F401
from urllib.request import Request, urlopen  # noqa: F401

from dream.agent.approval import INSTANCE_BOUND_TOOL_NAMES, ApprovalPolicy
from dream.agent.backends import (
    EchoBackend,
    OllamaBackend,
    OpenAIBackend,
    build_backend,
)
from dream.agent.constants import (
    _LOG_MESSAGE_LIMIT,
    DEFAULT_EXTRACTION_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MEMORY_BLOCK_CHAR_LIMIT,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    DEFAULT_TEMPERATURE,
    ERROR_BODY_LIMIT,
    EXTRACTION_TEMPERATURE,
    USER_AGENT_MAX_LENGTH,
    USER_AGENT_PRODUCT,
    log,
)
from dream.agent.dream import Dream, Turn
from dream.agent.env_config import (
    _fraction,
    _positive_int,
    _resolve_extraction_timeout,
    _resolve_max_retries,
    _resolve_memory_block_char_limit,
    _resolve_retry_backoff,
    _resolve_temperature,
)
from dream.agent.extraction import (
    _ExtractionOutcome,
    _record_extraction_status,
    _record_store_failure,
    _safe_log_message,
)
from dream.agent.http_utils import (
    _BEARER,
    _arguments,
    _describe_http_error,
    _error_body,
    _failure_text,
    _provider_failure_reply,
    _redact,
)
from dream.agent.prompts import (
    _BASE_PROMPT,
    _LANGUAGE_RULE,
    _MEMORIES_CLOSE,
    _MEMORIES_OPEN,
    _MEMORY_USAGE,
    _REMINDER_CANCEL_USAGE,
    _REMINDER_TOOL_USAGE,
    _REMINDER_USAGE,
    _REMINDERS_CLOSE,
    _REMINDERS_OPEN,
    DEFAULT_USER_AGENT,
)
from dream.agent.prompts import (
    USER_AGENT_MAX_LENGTH as _USER_AGENT_MAX_LENGTH_FROM_PROMPTS,  # noqa: F401
)
from dream.agent.reminders import (
    _CANCEL_TIME_HINT,
    _CREATE_TIME_HINT,
    _TIME_WORD,
    _cancel_ambiguous_message,
    _cancel_no_date_match_message,
    _cancel_not_found_message,
    _cancelled_message,
    _candidate_summary,
    _candidates_summary,
    _match_reminders,
    _relative_age,
    _render_reminder_line,
    _repeat_words,
    _resolve_reminder_date,
)
from dream.agent.tools_wire import _wire_tool_calls, cli_approver
from dream.agent.user_agent import (
    _USER_AGENT_OWS,
    _USER_AGENT_UNSAFE,
    _reject_user_agent,
    _resolve_user_agent,
)
from dream.reliability.sleep import interruptible_sleep  # noqa: F401

__all__ = [
    # Agent class (stable seam)
    "Dream",
    "Turn",
    # Approval
    "ApprovalPolicy",
    "INSTANCE_BOUND_TOOL_NAMES",
    "cli_approver",
    # Backends
    "EchoBackend",
    "OllamaBackend",
    "OpenAIBackend",
    "build_backend",
    # Constants
    "_LOG_MESSAGE_LIMIT",
    "DEFAULT_EXTRACTION_TIMEOUT_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MEMORY_BLOCK_CHAR_LIMIT",
    "DEFAULT_RETRY_BACKOFF_SECONDS",
    "DEFAULT_TEMPERATURE",
    "ERROR_BODY_LIMIT",
    "EXTRACTION_TEMPERATURE",
    "USER_AGENT_MAX_LENGTH",
    "USER_AGENT_PRODUCT",
    # Logger
    "log",
    # User-Agent
    "DEFAULT_USER_AGENT",
    # Extraction
    "_ExtractionOutcome",
    "_record_extraction_status",
    "_record_store_failure",
    "_safe_log_message",
    # Env config
    "_fraction",
    "_positive_int",
    "_resolve_extraction_timeout",
    "_resolve_max_retries",
    "_resolve_memory_block_char_limit",
    "_resolve_retry_backoff",
    "_resolve_temperature",
    # HTTP utils
    "_BEARER",
    "_arguments",
    "_describe_http_error",
    "_error_body",
    "_failure_text",
    "_provider_failure_reply",
    "_redact",
    # Prompts
    "_BASE_PROMPT",
    "_LANGUAGE_RULE",
    "_MEMORIES_CLOSE",
    "_MEMORIES_OPEN",
    "_MEMORY_USAGE",
    "_REMINDERS_CLOSE",
    "_REMINDERS_OPEN",
    "_REMINDER_CANCEL_USAGE",
    "_REMINDER_TOOL_USAGE",
    "_REMINDER_USAGE",
    # Reminders
    "_CANCEL_TIME_HINT",
    "_CREATE_TIME_HINT",
    "_TIME_WORD",
    "_candidate_summary",
    "_candidates_summary",
    "_cancel_ambiguous_message",
    "_cancel_not_found_message",
    "_cancel_no_date_match_message",
    "_cancelled_message",
    "_match_reminders",
    "_relative_age",
    "_render_reminder_line",
    "_repeat_words",
    "_resolve_reminder_date",
    # Tool wire
    "_wire_tool_calls",
    # User-Agent
    "_USER_AGENT_OWS",
    "_USER_AGENT_UNSAFE",
    "_reject_user_agent",
    "_resolve_user_agent",
    # urllib symbols re-exported for backward compatibility
    "HTTPError",
    "URLError",
    "Request",
    "urlopen",
    "interruptible_sleep",
]
