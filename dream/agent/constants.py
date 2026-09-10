"""Module-level constants and the structured logger for the agent runtime.

The values here are the *baseline* defaults read by sibling modules when no
override is supplied. Anything read from the environment goes through
:mod:`dream.agent.env_config` so a malformed override never reaches the rest
of the system.

The structured logger is named ``dream.agent`` so test fixtures and
production code can both attach handlers to it without changing the
spelling. The logger is intentionally module-level (not a class attribute)
because every other module imports it; that is the only dependency
this module has on its siblings.
"""

from __future__ import annotations

import logging

# Sampling temperatures. Conversation gets 0.3: calm but not robotic. The
# extraction pass must emit parseable JSON, so it runs colder still; at the
# server default (0.8) a small model wanders — once across a language
# boundary mid-sentence.
DEFAULT_TEMPERATURE: float = 0.3
EXTRACTION_TEMPERATURE: float = 0.1

# Eight thousand characters is roughly two thousand tokens, leaving most of a
# small model's 8k-token context window for the conversation and its reply.
DEFAULT_MEMORY_BLOCK_CHAR_LIMIT: int = 8_000

# Rate-limit retries: a 429 means the provider is alive and answerable, so a
# bounded retry with exponential backoff can succeed. A provider that hangs is
# not retried into the wall clock — the per-request timeout already bounds it.
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_BACKOFF_SECONDS: float = 1.0

# The extraction pass runs in the background after the reply is produced. This
# is how long a turn waits for it before the pass is marked abandoned and the
# reply goes out anyway. Five seconds keeps typical extractions reported while
# bounding the damage of a provider that never answers.
DEFAULT_EXTRACTION_TIMEOUT_SECONDS: float = 5.0

# Cap and collapse free-form exception messages before they can reach a log,
# so a verbose or multiline provider/store message cannot bloat or leak.
_LOG_MESSAGE_LIMIT: int = 200

# HTTP error body limit for the error description pipeline: a small window
# keeps the diagnostic readable, anything longer is truncated with a
# trailing marker so the operator can tell.
ERROR_BODY_LIMIT: int = 500

# The structured logger used by the agent and its background extraction worker.
# Extraction log records carry only safe metadata (status, exception class, a
# short redacted message) — never the extraction prompt, raw model output, full
# user content, API credentials, or filesystem/database paths.
log = logging.getLogger("dream.agent")

# The longest ``DREAM_USER_AGENT`` override that is forwarded. Real product
# tokens are a few dozen characters; anything past this is either a mistake
# or an attempt to smuggle bulk data into a request line, and header fields
# past a few hundred bytes start tripping edge proxies (431) anyway.
USER_AGENT_MAX_LENGTH: int = 200

# Product token used in the versioned User-Agent header. RFC 9110
# ``product/version`` shape. The version is filled in by :mod:`dream.agent.prompts`
# at import time so the header can never drift behind a release.
USER_AGENT_PRODUCT: str = "dream-assistant"
