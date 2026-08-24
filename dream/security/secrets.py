"""Value-scanning secret redaction (L6, SEC-G-17).

Dream already keeps platform tokens out of wire replies by construction;
this module closes the residue paths: logs, the message log, provenance
records, and error strings. A key-shaped value crossing any of those
boundaries is replaced by ``[REDACTED:<shape>]`` before it lands.

The patterns are deliberately broad — a false positive in a log is an
annoyance, a false negative is a leak. Scanned shapes mirror the repo
commit scanner (tests/test_security_secrets.py) plus JWTs and Dream's own
gateway-token prefix.
"""

from __future__ import annotations

import logging
import re
from typing import Any

__all__ = [
    "RedactingFilter",
    "install_redaction_filter",
    "redact_structure",
    "redact_text",
]

#: (shape name, pattern). Order matters only for overlapping shapes.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key-block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("openai-key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("github-fine", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:AA[0-9A-Za-z_-]{33}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")),
    ("dream-gateway-token", re.compile(r"\bdrm_[a-f0-9]{40,}")),
)


def redact_text(text: str) -> str:
    """Replace every secret-shaped span in *text* with a shape marker."""
    if not isinstance(text, str) or not text:
        return text
    for name, pattern in SECRET_PATTERNS:
        text = pattern.sub(f"[REDACTED:{name}]", text)
    return text


def redact_structure(value: Any) -> Any:
    """Recursively redact strings inside dicts/lists; other types pass through.

    Returns a redacted COPY — callers keep their originals untouched, so a
    redaction pass can never mutate live state.
    """
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: redact_structure(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact_structure(item) for item in value)
    return value


class RedactingFilter(logging.Filter):
    """Log filter that scrubs secret shapes from every record it passes."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_structure(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_structure(item) for item in record.args)
        return True


def install_redaction_filter(logger_name: str | None = None) -> RedactingFilter:
    """Attach a :class:`RedactingFilter` to one logger (idempotent)."""
    target = logging.getLogger(logger_name)
    for existing in target.filters:
        if isinstance(existing, RedactingFilter):
            return existing
    added = RedactingFilter()
    target.addFilter(added)
    return added
