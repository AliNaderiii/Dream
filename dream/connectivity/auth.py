"""Single-use, time-bounded link codes and the linked-user registry.

A user on any platform proves they own the desktop by sending ``/link CODE``;
the desktop UI fetches the code with ``gateway.link_code`` and hands it to the
human. Codes are single-use, expire after :data:`LINK_CODE_TTL_SECONDS`, and
are compared in constant time. Linked identities persist to a JSON file so
surfaces stay authorised across restarts.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from dream.connectivity.models import LinkedUser

LINK_CODE_TTL_SECONDS = 10 * 60
LINK_CODE_LENGTH = 6


@dataclass(slots=True)
class LinkCode:
    """A pending, single-use link code for one platform."""

    code: str
    platform: str
    issued_at: float
    expires_at: float
    user_id: str | None = None
    used: bool = False

    def to_dict(self) -> dict[str, float | str | None]:
        return {
            "platform": self.platform,
            "code": self.code,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "user_id": self.user_id,
        }


class AuthStore:
    """Issues/redeems link codes and persists the linked-user registry."""

    def __init__(
        self,
        path: str,
        *,
        clock: Callable[[], float] | None = None,
        ttl: float = LINK_CODE_TTL_SECONDS,
        code_length: int = LINK_CODE_LENGTH,
    ) -> None:
        self.path = str(path)
        self._clock = clock or time.time
        self._ttl = ttl
        self._code_length = code_length
        self._lock = threading.RLock()
        self._pending: dict[str, LinkCode] = {}
        self._linked: dict[str, dict[str, LinkedUser]] = self._load()

    # -- persistence ----------------------------------------------------- #

    def _load(self) -> dict[str, dict[str, LinkedUser]]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return {}
        linked: dict[str, dict[str, LinkedUser]] = {}
        if not isinstance(raw, dict):
            return linked
        for platform, users in raw.items():
            if not isinstance(users, dict):
                continue
            linked[str(platform)] = {}
            for user_id, row in users.items():
                if isinstance(row, dict):
                    linked[str(platform)][str(user_id)] = LinkedUser(
                        platform=str(platform),
                        user_id=str(user_id),
                        display_name=str(row.get("display_name", "")),
                        linked_at=float(row.get("linked_at", 0.0)),
                    )
        return linked

    def save(self) -> None:
        """Persist the linked registry atomically; best-effort on failure."""
        with self._lock:
            payload = {
                platform: {
                    user_id: user.to_dict() for user_id, user in users.items()
                }
                for platform, users in self._linked.items()
            }
            try:
                directory = os.path.dirname(os.path.abspath(self.path)) or "."
                os.makedirs(directory, exist_ok=True)
                tmp = f"{self.path}.tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                try:
                    os.chmod(tmp, 0o600)
                except OSError:
                    pass
                os.replace(tmp, self.path)
            except OSError:
                pass

    # -- link codes ------------------------------------------------------ #

    def issue(self, platform: str, user_id: str | None = None) -> LinkCode:
        """Create a fresh code for *platform*, replacing any pending one."""
        with self._lock:
            expired = [
                code
                for code in self._pending.values()
                if code.platform == platform and self._expired(code)
            ]
            for code in expired:
                self._pending.pop(code.code, None)
            existing = next(
                (code for code in self._pending.values() if code.platform == platform),
                None,
            )
            if existing is not None and not existing.used:
                return existing
            issued = self._clock()
            code = LinkCode(
                code=f"{secrets.randbelow(10 ** self._code_length):0{self._code_length}d}",
                platform=platform,
                issued_at=issued,
                expires_at=issued + self._ttl,
                user_id=user_id,
            )
            self._pending[code.code] = code
            return code

    def pending(self, platform: str) -> LinkCode | None:
        """The outstanding code for *platform*, or ``None`` when none/expired."""
        with self._lock:
            for code in self._pending.values():
                if code.platform != platform or code.used:
                    continue
                if self._expired(code):
                    self._pending.pop(code.code, None)
                    continue
                return code
            return None

    def redeem(self, platform: str, user_id: str, candidate: str) -> LinkCode | None:
        """Consume one code. Returns the redeemed code or ``None`` on failure.

        Comparison is constant-time and the code is single-use, so replaying
        an intercepted chat message can never link a second identity.
        """
        candidate = str(candidate).strip()
        with self._lock:
            code = self._pending.get(candidate)
            if (
                code is None
                or code.used
                or code.platform != platform
                or self._expired(code)
            ):
                return None
            if not secrets.compare_digest(candidate, code.code):
                return None
            code.used = True
            code.user_id = user_id
            self._pending.pop(candidate, None)
            return code

    def _expired(self, code: LinkCode) -> bool:
        return self._clock() >= code.expires_at

    # -- linked registry ------------------------------------------------- #

    def link(self, platform: str, user_id: str, display_name: str = "") -> LinkedUser:
        """Authorise one chat identity (idempotent)."""
        user_id = str(user_id)
        with self._lock:
            user = self._linked.setdefault(platform, {}).get(user_id)
            if user is None:
                user = LinkedUser(
                    platform=platform,
                    user_id=user_id,
                    display_name=display_name,
                    linked_at=self._clock(),
                )
                self._linked[platform][user_id] = user
            elif display_name:
                user.display_name = display_name
            self.save()
        return user

    def unlink(self, platform: str, user_id: str) -> bool:
        """Revoke one identity's access."""
        with self._lock:
            removed = self._linked.get(platform, {}).pop(str(user_id), None) is not None
            if removed:
                self.save()
        return removed

    def is_linked(self, platform: str, user_id: str) -> bool:
        with self._lock:
            return str(user_id) in self._linked.get(platform, {})

    def linked(self, platform: str | None = None) -> list[LinkedUser]:
        """Linked identities for one platform (or all, when ``None``)."""
        with self._lock:
            rows: list[LinkedUser] = []
            for name, users in self._linked.items():
                if platform is not None and name != platform:
                    continue
                rows.extend(users.values())
            return sorted(rows, key=lambda user: user.linked_at)
