"""Errors for the local-first workspace layer."""

from __future__ import annotations


class WorkspaceError(Exception):
    """Expected workspace failure (bad params, missing root, refused path)."""


class WorkspaceSecurityError(WorkspaceError):
    """Path traversal, symlink escape, or other boundary refusal."""
