"""Space: a bounded local work surface for specialized agents."""

from dream.space.catalog import list_roles
from dream.space.errors import SpaceError, SpaceSecurityError
from dream.space.service import SpaceService, get_service, reset_service
from dream.space.store import reset_store

__all__ = [
    "SpaceError",
    "SpaceSecurityError",
    "SpaceService",
    "get_service",
    "list_roles",
    "reset_service",
    "reset_store",
]
