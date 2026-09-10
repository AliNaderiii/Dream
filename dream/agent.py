"""Provider-neutral Dream agent loop with memory and explicit approval gates.

This module is a **facade** over the modular ``dream.agent`` package. Every
public name that older code imported from here continues to be re-exported,
so the refactor that split the 1943-line file into single-responsibility
siblings is invisible to existing callers.

The actual implementation lives in:

* :mod:`dream.agent.constants` — module-level constants and the logger.
* :mod:`dream.agent.env_config` — ``DREAM_*`` environment parsing.
* :mod:`dream.agent.user_agent` — User-Agent override policy.
* :mod:`dream.agent.http_utils` — argument parsing, HTTP error
  description, secret redaction.
* :mod:`dream.agent.tools_wire` — tool-call wire conversion and the
  CLI approval callback.
* :mod:`dream.agent.approval` — :class:`ApprovalPolicy` and the
  per-instance bound tool set.
* :mod:`dream.agent.extraction` — extraction outcome, log/metric recording.
* :mod:`dream.agent.logging_utils` — extraction-status metric map.
* :mod:`dream.agent.reminders` — reminder matching and refusal messages.
* :mod:`dream.agent.prompts` — Persian/English prompt strings and
  the versioned User-Agent.
* :mod:`dream.agent.backends` — :class:`OpenAIBackend`, :class:`OllamaBackend`,
  :class:`EchoBackend` and :func:`build_backend`.
* :mod:`dream.agent.dream` — the :class:`Dream` class and :class:`Turn`.

The ``Dream`` class is the *stable seam*: the public signature, the
:class:`Turn` return type, and the public dataclasses are unchanged.
Internal callers (test fixtures, subagent builder) keep working
through this facade.
"""

from __future__ import annotations

# ``urllib.request`` symbols used to live on this module because the original
# single-file agent imported them here for the HTTP client. Test fixtures and
# monkeypatch-style callers (e.g. ``monkeypatch.setattr("dream.agent.urlopen",
# ...)``) still expect the name to be reachable from the facade, so we
# re-export it explicitly.
from urllib.error import HTTPError, URLError  # noqa: E402
from urllib.request import Request, urlopen  # noqa: E402

# Re-export every public name from the dream.agent package so that
# ``from dream.agent import Dream``, ``from dream.agent import OpenAIBackend``,
# ``from dream.agent import _resolve_user_agent`` and any other historical
# import site continues to work byte-for-byte.
from dream.agent import (
    # Prompts
    _BASE_PROMPT,
    # HTTP utils
    _BEARER,
    # Reminders
    _CANCEL_TIME_HINT,
    _CREATE_TIME_HINT,
    _LANGUAGE_RULE,
    _MEMORIES_CLOSE,
    _MEMORIES_OPEN,
    _MEMORY_USAGE,
    _REMINDER_CANCEL_USAGE,
    _REMINDER_TOOL_USAGE,
    _REMINDER_USAGE,
    _REMINDERS_CLOSE,
    _REMINDERS_OPEN,
    _TIME_WORD,
    # User-Agent
    _USER_AGENT_OWS,
    _USER_AGENT_UNSAFE,
    # Constants
    DEFAULT_EXTRACTION_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MEMORY_BLOCK_CHAR_LIMIT,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    DEFAULT_TEMPERATURE,
    # User-Agent
    DEFAULT_USER_AGENT,
    ERROR_BODY_LIMIT,
    EXTRACTION_TEMPERATURE,
    INSTANCE_BOUND_TOOL_NAMES,
    USER_AGENT_MAX_LENGTH,
    USER_AGENT_PRODUCT,
    # Approval
    ApprovalPolicy,
    # Agent class (stable seam)
    Dream,
    # Backends
    EchoBackend,
    OllamaBackend,
    OpenAIBackend,
    Turn,
    _arguments,
    _cancel_ambiguous_message,
    _cancel_no_date_match_message,
    _cancel_not_found_message,
    _cancelled_message,
    _candidate_summary,
    _candidates_summary,
    _describe_http_error,
    _error_body,
    # Extraction
    _ExtractionOutcome,
    _failure_text,
    # Env config
    _fraction,
    _match_reminders,
    _positive_int,
    _provider_failure_reply,
    _record_extraction_status,
    _record_store_failure,
    _redact,
    _reject_user_agent,
    _relative_age,
    _render_reminder_line,
    _repeat_words,
    _resolve_extraction_timeout,
    _resolve_max_retries,
    _resolve_memory_block_char_limit,
    _resolve_reminder_date,
    _resolve_retry_backoff,
    _resolve_temperature,
    _resolve_user_agent,
    _safe_log_message,
    # Tool wire
    _wire_tool_calls,
    build_backend,
    cli_approver,
    # Logger
    log,
)

__all__ = [
    "Dream",
    "Turn",
    "ApprovalPolicy",
    "INSTANCE_BOUND_TOOL_NAMES",
    "cli_approver",
    "EchoBackend",
    "OllamaBackend",
    "OpenAIBackend",
    "build_backend",
    "DEFAULT_EXTRACTION_TIMEOUT_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MEMORY_BLOCK_CHAR_LIMIT",
    "DEFAULT_RETRY_BACKOFF_SECONDS",
    "DEFAULT_TEMPERATURE",
    "ERROR_BODY_LIMIT",
    "EXTRACTION_TEMPERATURE",
    "USER_AGENT_MAX_LENGTH",
    "USER_AGENT_PRODUCT",
    "log",
    "DEFAULT_USER_AGENT",
    "_ExtractionOutcome",
    "_record_extraction_status",
    "_record_store_failure",
    "_safe_log_message",
    "_fraction",
    "_positive_int",
    "_resolve_extraction_timeout",
    "_resolve_max_retries",
    "_resolve_memory_block_char_limit",
    "_resolve_retry_backoff",
    "_resolve_temperature",
    "_BEARER",
    "_arguments",
    "_describe_http_error",
    "_error_body",
    "_failure_text",
    "_provider_failure_reply",
    "_redact",
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
    "_wire_tool_calls",
    "_USER_AGENT_OWS",
    "_USER_AGENT_UNSAFE",
    "_reject_user_agent",
    "_resolve_user_agent",
    "HTTPError",
    "URLError",
    "Request",
    "urlopen",
]
