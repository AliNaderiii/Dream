"""Per-platform connectivity configuration with secret redaction.

One JSON file (``data/connectivity.json`` by default) holds the config dict
for every platform. The file is local to the machine and is written with
0600 permissions; every public read path (:meth:`ConnectivityConfig.public`,
the ``gateway.status`` / ``gateway.platforms`` RPCs) redacts values whose key
name marks them as secrets before they leave this module.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from typing import Any

from dream.connectivity.platforms import PLATFORM_CATALOG

#: Key names treated as secrets. A key whose *name* matches any of these
#: tokens (or contains one) has its value masked in public views.
SECRET_KEY_TOKENS = ("token", "secret", "password", "key", "credential")

#: How masked secrets render in public config views.
REDACTED_VALUE = "••••••••"


def _is_secret_key(key: str) -> bool:
    """Whether a config key name marks its value as a secret."""
    lowered = str(key).lower()
    return any(token in lowered for token in SECRET_KEY_TOKENS)


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy *config*, masking every secret-keyed value."""
    redacted: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, dict):
            redacted[key] = redact_config(value)
        elif _is_secret_key(key):
            redacted[key] = REDACTED_VALUE if value else ""
        else:
            redacted[key] = copy.deepcopy(value)
    return redacted


def _clean_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Reject non-string config keys so redaction can never miss a secret."""
    return {str(key): value for key, value in raw.items() if str(key)}


class ConnectivityConfig:
    """Thread-safe per-platform config store backed by one JSON file."""

    def __init__(self, path: str) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._config: dict[str, dict[str, Any]] = self._load()

    # -- persistence ----------------------------------------------------- #

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        config: dict[str, dict[str, Any]] = {}
        for platform, values in raw.items():
            if isinstance(values, dict):
                config[str(platform)] = _clean_keys(values)
        return config

    def save(self) -> None:
        """Atomically persist the config file; best-effort on read-only dirs."""
        with self._lock:
            directory = os.path.dirname(os.path.abspath(self.path)) or "."
            try:
                os.makedirs(directory, exist_ok=True)
                tmp = f"{self.path}.tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(self._config, handle, ensure_ascii=False, indent=2)
                try:
                    os.chmod(tmp, 0o600)
                except OSError:
                    pass
                os.replace(tmp, self.path)
            except OSError:
                # Persistence is best-effort; in-memory state still serves.
                pass

    # -- accessors -------------------------------------------------------- #

    def get(self, platform: str) -> dict[str, Any]:
        """The live (unredacted) config dict for *platform* — internal use."""
        with self._lock:
            return dict(self._config.get(platform, {}))

    def all(self) -> dict[str, dict[str, Any]]:
        """Every platform's live config, keyed by platform name."""
        with self._lock:
            return {key: dict(value) for key, value in self._config.items()}

    def set(self, platform: str, values: dict[str, Any]) -> dict[str, Any]:
        """Merge *values* into one platform's config and persist.

        A ``None`` value deletes the key; an empty ``token``/``secret`` value
        keeps the previously stored secret (so "leave unchanged" saves work).
        """
        platform = str(platform)
        cleaned = _clean_keys(values)
        with self._lock:
            merged = dict(self._config.get(platform, {}))
            for key, value in cleaned.items():
                if value is None:
                    merged.pop(key, None)
                elif value == "" and _is_secret_key(key) and key in merged:
                    continue  # blank secret → keep the stored one
                else:
                    merged[key] = value
            self._config[platform] = merged
            self.save()
        return redact_config(merged)

    def enabled(self, platform: str) -> bool:
        """Whether the platform's adapter should run."""
        with self._lock:
            return bool(self._config.get(platform, {}).get("enabled", False))

    def configured(self, platform: str) -> bool:
        """Whether every required field for *platform* has a value.

        Platforms outside the catalog (custom/test adapters) have no required
        fields, so they count as configured whenever their config exists.
        """
        catalog = PLATFORM_CATALOG.get(platform)
        if catalog is None:
            return bool(self._config.get(platform, {}))
        with self._lock:
            values = self._config.get(platform, {})
        return all(str(values.get(field["key"]) or "").strip() for field in catalog["fields"]
                   if field.get("required"))

    def rate_limit_per_minute(self, platform: str) -> int:
        """The per-platform gateway allowance (default 20)."""
        with self._lock:
            raw = self._config.get(platform, {}).get("rate_limit_per_minute", 20)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return 20
        return value if value >= 1 else 20

    def public(self, platform: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        """Config in UI-safe shape: secrets redacted, plus ``configured``.

        With no *platform*, returns the redacted dict keyed by platform; with
        one, returns that platform's redacted dict.
        """
        with self._lock:
            raw = (
                {platform: self._config.get(platform, {})}
                if platform is not None
                else self._config
            )
        public: dict[str, Any] = {}
        for name, values in raw.items():
            redacted = redact_config(values)
            redacted["enabled"] = bool(values.get("enabled", False))
            redacted["configured"] = self.configured(name)
            redacted["secret_fields"] = [
                field["key"]
                for field in PLATFORM_CATALOG.get(name, {}).get("fields", [])
                if field.get("secret") or field.get("type") == "secret"
            ]
            public[name] = redacted
        if platform is not None:
            return public.get(platform, {})
        return public
