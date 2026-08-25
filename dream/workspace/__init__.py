"""Local-first workspace: in-place folder pointers, files, and safe preview."""

from __future__ import annotations

from dream.workspace.errors import WorkspaceError, WorkspaceSecurityError
from dream.workspace.service import WorkspaceService, get_service, reset_service

__all__ = [
    "WorkspaceError",
    "WorkspaceSecurityError",
    "WorkspaceService",
    "get_service",
    "reset_service",
]
