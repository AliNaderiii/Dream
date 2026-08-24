"""Stage D — L8 transport hardening (G-22..G-25).

* reject-before-dispatch: EVERY bridge handler refuses malformed params
  with a BridgeError (or a clean result) — never KeyError/TypeError/
  AttributeError/ValueError leaking out of the boundary;
* bounded, seeded fuzzing over the MP-02 families and the whole handler
  table;
* gateway security-header policy (CSP/HSTS/X-Frame-Options/nosniff);
* token rotation + scope audit + per-token rate limits;
* the legacy desktop window stays quarantined behind an explicit flag.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.gateway_server import (
    CSP_DEFAULT,
    TokenManager,
    TokenRateLimiter,
    TokenScope,
    build_security_headers,
)
from dream.memory import MemoryStore

SEED = 20260824


def _make_methods() -> BridgeMethods:
    store = MemoryStore(":memory:")
    return BridgeMethods(
        store,
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        default_provider="echo",
    )


# -- G-22: reject-before-dispatch property ------------------------------------ #

GARBAGE_PARAMS = [
    None,
    {},
    {"session_id": 123},
    {"session_id": None},
    {"session_id": ["a"]},
    {"name": 5, "arguments": "bad"},
    {"name": "", "arguments": {}},
    {"arguments": [1, 2]},
    {"limit": "big"},
    {"limit": -5},
    {"offset": -1},
    {"query": 42},
    {"content": 3.14},
    {"target": {"nested": ["garbage"]}},
    {"command": ["rm", "-rf", "/"]},
    {"allowed": "yes"},
    {"approval_id": 7},
    {"": ""},
    {"x" * 500: "y" * 500},
]


def _invoke(handler, params):
    """Call one handler, awaiting async handlers exactly as the server does."""
    if inspect.iscoroutinefunction(handler):
        return asyncio.run(handler(params))
    return handler(params)


def test_every_handler_rejects_garbage_before_dispatch() -> None:
    methods = _make_methods()
    failures: list[str] = []
    for name, handler in sorted(methods.handlers.items()):
        for params in GARBAGE_PARAMS:
            try:
                result = _invoke(handler, params)
            except BridgeError:
                continue  # the boundary's own refusal — the contract
            except Exception as exc:  # noqa: BLE001 — the point is to catch all
                failures.append(f"{name}({params!r:.60}) -> {type(exc).__name__}: {exc}")
                continue
            if not isinstance(result, (dict, list, str, bool, int, float)) and result is not None:
                failures.append(f"{name} returned unserialisable {type(result).__name__}")
    assert not failures, "handlers leaked exceptions before dispatch:\n" + "\n".join(failures)


def test_every_handler_result_is_json_serialisable() -> None:
    methods = _make_methods()
    for name, handler in sorted(methods.handlers.items()):
        try:
            result = _invoke(handler, {})
        except BridgeError:
            continue
        except Exception:
            continue  # covered by the property test above
        try:
            json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            pytest.fail(f"{name} returned a non-serialisable result: {exc}")


MP02_FAMILIES = ("memory2.", "skills.", "search.sessions.", "conversation.compact", "nudge.")


def test_mp02_families_reject_wrong_types_individually() -> None:
    methods = _make_methods()
    checked = 0
    for name, handler in methods.handlers.items():
        if not any(name.startswith(prefix) for prefix in MP02_FAMILIES):
            continue
        for params in GARBAGE_PARAMS:
            try:
                _invoke(handler, params)
            except BridgeError:
                checked += 1
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"{name}({params!r:.60}) leaked {type(exc).__name__}: {exc}")
    assert checked > 20, "the MP-02 families must be reachable in this audit"


# -- G-22: bounded, seeded fuzzing --------------------------------------------- #


def _fuzz_value(rng: random.Random, depth: int):
    if depth <= 0:
        return rng.choice([None, True, False, 0, -1, 3.5, "", "x", "س", "😀"])
    kind = rng.randrange(6)
    if kind == 0:
        return rng.choice([None, True, False, 0, -1, 3.5, "", "x" * rng.randrange(1, 40)])
    if kind == 1:
        return "س" * rng.randrange(1, 20) + "\u200b" * rng.randrange(0, 3)
    if kind == 2:
        return rng.randrange(-1000, 1000)
    if kind == 3:
        return [_fuzz_value(rng, depth - 1) for _ in range(rng.randrange(0, 3))]
    if kind == 4:
        return {
            f"k{i}": _fuzz_value(rng, depth - 1) for i in range(rng.randrange(0, 3))
        }
    return rng.choice(["session_id", "name", "query", "limit", "arguments", "target"])


def test_seeded_bridge_fuzzing_finds_no_unhandled_exceptions() -> None:
    methods = _make_methods()
    rng = random.Random(SEED)
    names = sorted(methods.handlers)
    mp02 = [n for n in names if any(n.startswith(p) for p in MP02_FAMILIES)]
    pool = mp02 * 3 + names  # weight the MP-02 families, still cover everything
    failures: list[str] = []
    for _ in range(400):
        name = rng.choice(pool)
        params = _fuzz_value(rng, 3)
        if not isinstance(params, dict):
            params = {"payload": params}
        try:
            _invoke(methods.handlers[name], params)
        except BridgeError:
            continue
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} <- {json.dumps(params, ensure_ascii=False)[:80]}: "
                            f"{type(exc).__name__}")
    assert not failures, "fuzzing escaped the boundary:\n" + "\n".join(failures)


def test_fuzzing_is_deterministic_under_the_seed() -> None:
    a = random.Random(SEED)
    b = random.Random(SEED)
    assert [_fuzz_value(a, 3) for _ in range(50)] == [_fuzz_value(b, 3) for _ in range(50)]


# -- G-23: gateway security headers --------------------------------------------- #


def test_headers_always_carry_frame_denial_and_nosniff_and_csp() -> None:
    headers = build_security_headers(tls_enabled=False)
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Security-Policy"] == CSP_DEFAULT
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in headers  # HSTS only over TLS


def test_hsts_ships_only_over_tls() -> None:
    headers = build_security_headers(tls_enabled=True)
    assert headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_an_existing_csp_wins_over_the_default() -> None:
    headers = build_security_headers(
        tls_enabled=False, existing={"Content-Security-Policy": "default-src 'none'"}
    )
    assert "Content-Security-Policy" not in headers  # middleware must not clobber
    headers_lower = build_security_headers(
        tls_enabled=False, existing={"content-security-policy": "default-src 'none'"}
    )
    assert "Content-Security-Policy" not in headers_lower  # case-insensitive respect


# -- G-24: rotation, scopes, per-token rate limits ------------------------------- #


def test_rotation_invalidates_the_old_token_and_keeps_the_scope(tmp_path) -> None:
    manager = TokenManager(str(tmp_path / "tokens.json"))
    old = manager.create_token(TokenScope.WRITE, "device")
    new = manager.rotate_token(old)
    assert new and new != old
    assert manager.verify_token(old) is None, "the rotated token must die"
    info = manager.verify_token(new, TokenScope.WRITE)
    assert info is not None and info["scope"] == TokenScope.WRITE.value
    assert manager.rotate_token("drm_never_existed") is None


def test_read_scope_still_cannot_write_after_rotation(tmp_path) -> None:
    manager = TokenManager(str(tmp_path / "tokens.json"))
    old = manager.create_token(TokenScope.READ, "reader")
    new = manager.rotate_token(old)
    assert manager.verify_token(new, TokenScope.READ) is not None
    assert manager.verify_token(new, TokenScope.WRITE) is None


def test_token_rate_limiter_enforces_the_per_minute_budget() -> None:
    limiter = TokenRateLimiter(per_minute=3)
    token = "drm_" + "a" * 40
    assert [limiter.check(token, now=1000 + i) for i in range(3)] == [True, True, True]
    assert limiter.check(token, now=1003) is False
    assert limiter.remaining(token, now=1003) == 0
    # the next minute window restores the budget
    assert limiter.check(token, now=1061) is True


def test_rate_limits_are_per_token() -> None:
    limiter = TokenRateLimiter(per_minute=1)
    assert limiter.check("token-a", now=500) is True
    assert limiter.check("token-b", now=500) is True  # a's budget is not b's
    assert limiter.check("token-a", now=501) is False


def test_rate_limiter_rejects_bad_budgets_and_resets() -> None:
    with pytest.raises(ValueError):
        TokenRateLimiter(per_minute=0)
    limiter = TokenRateLimiter(per_minute=2)
    limiter.check("t", now=10)
    limiter.reset()
    assert limiter.remaining("t", now=10) == 2


# -- G-25: the legacy desktop window stays quarantined ----------------------------- #


def test_legacy_desktop_refuses_to_start_without_the_flag(tmp_path) -> None:
    result = subprocess.run(
        [sys.executable, "desktop.py"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(Path(__file__).resolve().parents[2]),
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    assert result.returncode == 2
    assert "quarantined" in result.stderr
    assert "\u0642\u0631\u0646\u0637\u06cc\u0646\u0647" in result.stderr  # bilingual refusal


def test_legacy_flag_is_the_only_way_in(monkeypatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "legacy_desktop_module", str(Path(__file__).resolve().parents[2] / "desktop.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.LEGACY_DESKTOP_FLAG_ENV == "DREAM_ENABLE_LEGACY_DESKTOP"

    monkeypatch.delenv(module.LEGACY_DESKTOP_FLAG_ENV, raising=False)
    assert module._legacy_enabled() is False
    for value in ("1", "true", "YES", "on"):
        monkeypatch.setenv(module.LEGACY_DESKTOP_FLAG_ENV, value)
        assert module._legacy_enabled() is True
    for value in ("0", "no", "off", "", "maybe"):
        monkeypatch.setenv(module.LEGACY_DESKTOP_FLAG_ENV, value)
        assert module._legacy_enabled() is False
