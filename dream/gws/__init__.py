"""Google Workspace connectors: owner OAuth, read-only APIs, fail-closed."""

from __future__ import annotations

from dream.gws.service import GoogleWorkspaceService, get_service, reset_service

__all__ = ["GoogleWorkspaceService", "get_service", "reset_service"]
