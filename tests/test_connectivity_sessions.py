"""Session registry tests: one Dream per (platform, user), persisted index."""

from __future__ import annotations

import tempfile

from dream.connectivity.sessions import SessionRegistry


class _FakeDream:
    counter = 0

    def __init__(self) -> None:
        _FakeDream.counter += 1
        self.number = _FakeDream.counter


def _registry(tmp_path_factory: tempfile) -> SessionRegistry:
    path = tempfile.mktemp(suffix=".json")
    return SessionRegistry(path, dream_factory=_FakeDream)


def test_get_reuses_the_same_instance():
    _FakeDream.counter = 0
    registry = _registry(tempfile)
    first = registry.get("telegram", "42")
    second = registry.get("telegram", "42")
    other = registry.get("telegram", "43")
    assert first is second
    assert first is not other
    assert _FakeDream.counter == 2


def test_reset_replaces_instance_and_preserves_index():
    _FakeDream.counter = 0
    registry = _registry(tempfile)
    before = registry.get("slack", "U1")
    registry.touch("slack", "U1")
    registry.touch("slack", "U1")
    after = registry.reset("slack", "U1")
    assert before is not after
    stats = registry.stats("slack")
    assert len(stats) == 1
    assert stats[0]["message_count"] == 0  # reset clears the counters


def test_index_persists_across_instances():
    _FakeDream.counter = 0
    path = tempfile.mktemp(suffix=".json")
    first = SessionRegistry(path, dream_factory=_FakeDream)
    first.get("email", "a@b.c")
    first.touch("email", "a@b.c")
    second = SessionRegistry(path, dream_factory=_FakeDream)
    stats = second.stats("email")
    assert len(stats) == 1
    assert stats[0]["user_id"] == "a@b.c"
    assert stats[0]["message_count"] == 1
    # The Dream instance itself is rebuilt (history is in-memory only).
    assert _FakeDream.counter == 1


def test_corrupt_index_file_is_tolerated():
    _FakeDream.counter = 0
    path = tempfile.mktemp(suffix=".json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    registry = SessionRegistry(path, dream_factory=_FakeDream)
    assert registry.stats() == []  # corrupt file loads as an empty index
    assert registry.get("signal", "+1") is not None
    assert len(registry.stats()) == 1
