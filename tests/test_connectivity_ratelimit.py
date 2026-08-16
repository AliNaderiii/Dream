"""Rate limiter tests: the {platform, user_id, minute} gate counter."""

from __future__ import annotations

from dream.connectivity.ratelimit import RateLimiter


def test_default_limit_and_burst():
    limiter = RateLimiter(default_per_minute=3)
    decisions = [limiter.check("telegram", "user-1", now=100.0) for _ in range(5)]
    assert [decision.allowed for decision in decisions] == [True, True, True, False, False]
    assert decisions[3].used == 4
    assert decisions[3].limit == 3
    assert decisions[3].retry_after_seconds > 0


def test_users_and_platforms_are_isolated():
    limiter = RateLimiter(default_per_minute=1)
    assert limiter.check("telegram", "u1", now=100.0).allowed
    assert limiter.check("telegram", "u2", now=100.0).allowed
    assert limiter.check("slack", "u1", now=100.0).allowed
    assert not limiter.check("telegram", "u1", now=100.0).allowed


def test_window_rolls_over_per_minute():
    limiter = RateLimiter(default_per_minute=1)
    assert limiter.check("email", "a@b.c", now=59.9).allowed
    # 60.0 is a fresh minute: the window rolled over and the slot is free...
    assert limiter.check("email", "a@b.c", now=60.0).allowed
    # ...but a second message inside that same new minute is over the limit.
    assert not limiter.check("email", "a@b.c", now=60.1).allowed


def test_per_platform_configuration():
    limiter = RateLimiter(default_per_minute=5)
    limiter.configure("discord", 2)
    assert limiter.limit_for("discord") == 2
    assert limiter.limit_for("telegram") == 5
    decisions = [limiter.check("discord", "u", now=1.0) for _ in range(3)]
    assert decisions[-1].allowed is False
    limiter.configure("discord", None)
    assert limiter.limit_for("discord") == 5


def test_reset_and_remaining():
    limiter = RateLimiter(default_per_minute=2)
    limiter.check("whatsapp", "u", now=0.0)
    assert limiter.remaining("whatsapp", "u", now=1.0) == 1
    limiter.reset("whatsapp")
    assert limiter.remaining("whatsapp", "u", now=1.0) == 2
    assert limiter.to_dict()["default"] == 2
