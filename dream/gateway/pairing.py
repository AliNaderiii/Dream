"""Cryptographically secure, time-bounded pairing manager for multi-platform sessions."""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from dream.gateway.types import PlatformType


@dataclass
class PairingCode:
    """Active pairing code record."""

    code: str
    platform: PlatformType
    user_id: str
    user_name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    is_used: bool = False

    @property
    def is_expired(self) -> bool:
        """Check if code lifetime has elapsed."""
        return datetime.now(timezone.utc) > self.expires_at


class PairingManager:
    """Manages generation, storage, and redemption of pairing codes across platforms."""

    def __init__(self, ttl_minutes: int = 10) -> None:
        self.ttl_minutes = ttl_minutes
        self._lock = threading.RLock()
        self._codes: dict[str, PairingCode] = {}

    def generate_code(
        self,
        platform: PlatformType,
        user_id: str,
        user_name: str,
        prefix: str = "DREAM-",
    ) -> str:
        """Generate a random alphanumeric pairing code for a platform user."""
        with self._lock:
            # Clean up old codes for this user
            self._purge_user_codes(platform, user_id)

            # Generate random 6-character uppercase string
            token = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
            code = f"{prefix}{token}"
            now = datetime.now(timezone.utc)
            record = PairingCode(
                code=code,
                platform=platform,
                user_id=user_id,
                user_name=user_name,
                created_at=now,
                expires_at=now + timedelta(minutes=self.ttl_minutes),
            )
            self._codes[code] = record
            return code

    def verify_and_redeem(
        self,
        code: str,
    ) -> tuple[bool, PairingCode | None, str]:
        """Verify and consume a pairing code, returning (success, code_record, message)."""
        code = code.strip().upper()
        with self._lock:
            record = self._codes.get(code)
            if not record:
                return (
                    False,
                    None,
                    "کد اتصال نامعتبر است یا وجود ندارد. / Invalid pairing code.",
                )

            if record.is_used:
                return (
                    False,
                    record,
                    "این کد اتصال قبلاً استفاده شده است. / Pairing code has already been redeemed.",
                )

            if record.is_expired:
                del self._codes[code]
                return (
                    False,
                    record,
                    "کد اتصال منقضی شده است. لطفاً کد جدیدی دریافت کنید. / Pairing code expired.",
                )

            # Mark as redeemed
            record.is_used = True
            return (
                True,
                record,
                f"اتصال به پلتفرم {record.platform.value} با موفقیت تایید شد! / Paired!",
            )

    def _purge_user_codes(self, platform: PlatformType, user_id: str) -> None:
        """Remove existing codes for the specified user."""
        to_delete = [
            c
            for c, r in self._codes.items()
            if r.platform == platform and r.user_id == user_id or r.is_expired
        ]
        for c in to_delete:
            self._codes.pop(c, None)
