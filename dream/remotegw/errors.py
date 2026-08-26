"""Remote-gateway errors. Fail closed; bilingual when they leave the kernel."""

from __future__ import annotations


class RemoteGwError(ValueError):
    """Owner-facing remote-gateway failure."""


class RemoteGwSecurityError(RemoteGwError):
    """Bind, token, or scope refusal."""
