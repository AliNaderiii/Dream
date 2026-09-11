"""Security enforcement, SSRF prevention, and prompt injection quarantine for Web tools."""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlsplit

from dream.security.injection import guard_untrusted, scan_text

logger = logging.getLogger(__name__)

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata",
        "0.0.0.0",
        "::1",
        "::",
        "169.254.169.254",  # AWS/Cloud metadata service
    }
)

_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".corp",
)

_PRIVATE_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


class SSRFSecurityViolation(Exception):
    """Raised when an outbound URL targets private or prohibited network endpoints."""
    pass


def validate_web_url(url: str) -> str:
    """Validate URL scheme, syntax, and block private SSRF destinations.

    Returns normalized URL if safe, raises SSRFSecurityViolation otherwise.
    """
    raw = (url or "").strip()
    if not raw or len(raw) > 2048 or "\\" in raw:
        raise SSRFSecurityViolation(f"Malformed or oversized URL: {url!r}")

    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFSecurityViolation(f"Unsupported scheme '{scheme}'. Only HTTP/HTTPS allowed.")

    hostname = (parts.hostname or "").lower().strip()
    if not hostname:
        raise SSRFSecurityViolation("URL has missing or empty hostname.")

    # 1. Check blocked hostnames and suffixes
    if hostname in _BLOCKED_HOSTS or any(hostname.endswith(sfx) for sfx in _BLOCKED_SUFFIXES):
        raise SSRFSecurityViolation(f"Prohibited internal host target: {hostname}")

    # 2. Check if hostname is a private/loopback IP address
    try:
        ip_addr = ipaddress.ip_address(hostname)
        if any(ip_addr in net for net in _PRIVATE_NETWORKS) or ip_addr.is_loopback:
            raise SSRFSecurityViolation(f"Prohibited private IP destination: {ip_addr}")
    except ValueError:
        # Not a literal IP address; hostname string
        pass

    return raw


def sanitize_extracted_web_text(text: str, source_url: str) -> tuple[str, int]:
    """Scan extracted web content for hostile prompt injection patterns.

    Returns (sanitized_text, injection_findings_count).
    """
    report = scan_text(text)
    if report.clean or not report.findings:
        return text, 0

    count = len(report.findings)
    logger.warning(
        f"Prompt injection pattern detected in web content from {source_url} "
        f"({count} findings)."
    )

    # Quarantine untrusted text
    guarded_text = guard_untrusted(text, source=f"web:{source_url}")
    return guarded_text, count
