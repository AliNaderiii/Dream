"""Bind policy: loopback by default, LAN only with --lan, WAN refused."""

from __future__ import annotations

import ipaddress

from dream.remotegw.errors import RemoteGwSecurityError

LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 8765


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


def classify_host(host: str) -> str:
    text = (host or "").strip()
    if not text:
        raise RemoteGwSecurityError(
            _bilingual("bind host must be a non-empty address", "نشانی اتصال نباید خالی باشد")
        )
    if text in {"localhost", "::1"}:
        return "loopback"
    try:
        addr = ipaddress.ip_address(text)
    except ValueError as exc:
        raise RemoteGwSecurityError(
            _bilingual(f"invalid bind host: {text}", f"نشانی اتصال نامعتبر: {text}")
        ) from exc
    if addr.is_loopback:
        return "loopback"
    if addr.is_private and not addr.is_unspecified:
        return "lan"
    raise RemoteGwSecurityError(
        _bilingual(
            "WAN / public bind is refused. Use 127.0.0.1 or --lan with a private RFC1918 address.",
            "اتصال به اینترنت عمومی رد شد. از 127.0.0.1 یا --lan با نشانی خصوصی استفاده کنید.",
        )
    )


def resolve_bind(*, lan: bool, host: str | None, port: int | None) -> dict[str, object]:
    """Return a validated bind record. Never returns a public address."""
    listen_port = DEFAULT_PORT if port is None else int(port)
    if not 1024 <= listen_port <= 65535:
        raise RemoteGwSecurityError(
            _bilingual(
                "port must be between 1024 and 65535",
                "پورت باید بین ۱۰۲۴ و ۶۵۵۳۵ باشد",
            )
        )
    if host:
        kind = classify_host(host)
        if kind == "lan" and not lan:
            raise RemoteGwSecurityError(
                _bilingual(
                    "LAN bind requires --lan",
                    "اتصال به شبکهٔ محلی نیاز به --lan دارد",
                )
            )
        return {
            "host": host.strip(),
            "port": listen_port,
            "kind": kind,
            "leaves_machine": kind != "loopback",
        }
    if lan:
        raise RemoteGwSecurityError(
            _bilingual(
                "--lan requires an explicit private host (for example 192.168.1.10)",
                "--lan به یک نشانی خصوصی صریح نیاز دارد (مثلاً 192.168.1.10)",
            )
        )
    return {
        "host": LOOPBACK,
        "port": listen_port,
        "kind": "loopback",
        "leaves_machine": False,
    }
