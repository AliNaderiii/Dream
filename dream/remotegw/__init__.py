"""Local-first remote gateway: loopback JSON-RPC with scoped tokens."""

from dream.remotegw.bind import resolve_bind
from dream.remotegw.errors import RemoteGwError, RemoteGwSecurityError
from dream.remotegw.service import RemoteGwService, get_service, reset_service

__all__ = [
    "RemoteGwError",
    "RemoteGwSecurityError",
    "RemoteGwService",
    "get_service",
    "reset_service",
    "resolve_bind",
]
