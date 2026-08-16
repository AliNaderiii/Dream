"""Model serialisation and split_text contract tests (P-07)."""

from __future__ import annotations

import pytest

from dream.connectivity.base import PlatformAdapter, split_text
from dream.connectivity.models import (
    Attachment,
    IncomingMessage,
    LinkedUser,
    MessageLogEntry,
    PlatformStatus,
)


def test_incoming_message_defaults_and_raw_escape_hatch():
    message = IncomingMessage(
        platform="telegram",
        platform_user_id="42",
        platform_channel_id="42",
        text="hello",
        raw={"update_id": 7},
    )
    assert message.attachments == []
    assert message.message_id is None
    assert message.timestamp.tzinfo is not None
    assert message.raw == {"update_id": 7}


def test_attachment_to_dict_never_carries_bytes():
    attachment = Attachment(
        mime_type="image/png", filename="a.png", data=b"\x00\x01\x02", size=3
    )
    payload = attachment.to_dict()
    assert payload["mime_type"] == "image/png"
    assert payload["filename"] == "a.png"
    assert payload["size"] == 3
    assert "data" not in payload
    assert Attachment(url="https://x/y.png").to_dict()["url"] == "https://x/y.png"


def test_platform_status_to_dict_serialises_last_activity():
    status = PlatformStatus(platform="telegram", running=True, connected=True, detail="ok")
    payload = status.to_dict()
    assert payload["platform"] == "telegram"
    assert payload["running"] is True
    assert payload["connected"] is True
    assert payload["error"] is None
    assert status.last_activity is None or payload["last_activity"] is not None


def test_message_log_entry_and_linked_user_wire_shapes():
    entry = MessageLogEntry(
        platform="email", direction="in", user_id="a@b.c", text="hi", attachments=2
    )
    assert entry.to_dict()["direction"] == "in"
    assert entry.to_dict()["attachments"] == 2
    user = LinkedUser(platform="slack", user_id="U1", display_name="Ana", linked_at=1.5)
    assert user.to_dict()["display_name"] == "Ana"


def test_split_text_boundaries_and_limits():
    assert split_text("", 100) == []
    assert split_text("short", 100) == ["short"]
    chunks = split_text("one two three four", 10)
    assert chunks == ["one two", "three four"]
    assert all(len(chunk) <= 10 for chunk in chunks)
    # A single word longer than the limit is hard-split.
    long_word = "a" * 25
    chunks = split_text(long_word, 10)
    assert chunks == ["a" * 10, "a" * 10, "a" * 5]
    with pytest.raises(ValueError):
        split_text("x", 0)


def test_platform_adapter_declares_contract_classvars():
    class Bare(PlatformAdapter):
        async def start(self) -> None: ...
        async def stop(self) -> None: ...
        async def send_message(self, user_id, text, attachments=None) -> None: ...
        async def send_typing_indicator(self, user_id) -> None: ...

    with pytest.raises(TypeError):
        Bare({}, on_message=None)  # type: ignore[arg-type]
