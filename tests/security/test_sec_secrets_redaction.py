"""Stage C — value-scanning secret redaction (L6, SEC-G-17).

The patterns catch the classic key shapes plus JWTs and Dream's own
gateway tokens; the wiring tests prove the message log, provenance trail,
bridge error strings, and log records all pass through the scanner. A key
must never reach disk or the wire.
"""

from __future__ import annotations

import logging

from dream.connectivity.messagelog import MessageLog
from dream.provenance.tracker import ProvenanceTracker
from dream.security.secrets import (
    RedactingFilter,
    install_redaction_filter,
    redact_structure,
    redact_text,
)

# Fixtures are assembled from fragments so the repo's tracked-file secret
# scanner never matches the SOURCE literals, while the runtime values still
# match every redaction shape under test.
SK_KEY = "sk-proj-" + "abcdefghij" * 4
GH_TOKEN = "ghp_" + "abcdefghij" * 3
AWS_KEY = "AKIA" + "0123456789ABCDEF"
SLACK_TOKEN = "xoxb-" + "1234567890-abcdefghij"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
GATEWAY_TOKEN = "drm_" + "0123456789abcdef" * 3
TELEGRAM_TOKEN = "123456789:AAabcdefghij-klmnopqrstuvwxyz012345"
PRIVATE_KEY = "-----BEGIN " + "OPENSSH PRIVATE KEY" + "-----"


def test_every_shape_is_redacted() -> None:
    samples = {
        "openai": f"using {SK_KEY} for chat",
        "github": f"token {GH_TOKEN} here",
        "aws": f"key {AWS_KEY} ok",
        "slack": f"bot {SLACK_TOKEN} up",
        "jwt": f"bearer {JWT} sent",
        "gateway": f"gateway {GATEWAY_TOKEN} saved",
        "telegram": f"bot {TELEGRAM_TOKEN} live",
        "private-key": f"{PRIVATE_KEY} material",
    }
    for name, text in samples.items():
        redacted = redact_text(text)
        assert "[REDACTED:" in redacted, name
        for secret in (
            SK_KEY,
            GH_TOKEN,
            AWS_KEY,
            SLACK_TOKEN,
            JWT,
            GATEWAY_TOKEN,
            TELEGRAM_TOKEN,
            PRIVATE_KEY,
        ):
            assert secret not in redacted, name


def test_benign_text_survives_byte_identical() -> None:
    samples = [
        "the sky is blue",
        "ask about skills and schedules",
        "disk /dev/sda1 is full",
        "eyJ is not a jwt on its own",
        "rm -rf / was blocked by the floor",
        "",
    ]
    for text in samples:
        assert redact_text(text) == text


def test_redact_structure_walks_containers_and_copies() -> None:
    original = {
        "a": [SK_KEY, ("nested", GH_TOKEN)],
        "b": {"c": f"key {AWS_KEY}"},
        "d": 42,
        "e": None,
    }
    redacted = redact_structure(original)
    assert SK_KEY not in str(redacted)
    assert GH_TOKEN not in str(redacted)
    assert AWS_KEY not in str(redacted)
    assert redacted["d"] == 42 and redacted["e"] is None
    # the original stays untouched
    assert SK_KEY in str(original)


def test_message_log_redacts_before_persisting(tmp_path) -> None:
    log = MessageLog(str(tmp_path / "messages.jsonl"))
    entry = log.add("telegram", "in", "u1", f"here is my key {SK_KEY} please save it")
    assert SK_KEY not in entry.text
    assert "[REDACTED:" in entry.text
    reloaded = MessageLog(str(tmp_path / "messages.jsonl"))
    rows = reloaded.entries("telegram")
    assert rows and SK_KEY not in rows[0].text
    assert SK_KEY not in (tmp_path / "messages.jsonl").read_text(encoding="utf-8")


def test_provenance_redacts_payloads_before_sealing(tmp_path) -> None:
    tracker = ProvenanceTracker(str(tmp_path / "prov"))
    record = tracker.record(
        "tool_call",
        "bridge",
        payload={"arguments": {"token": GH_TOKEN}, "result": f"ok {JWT}"},
    )
    serialized = str(record.to_dict())
    assert GH_TOKEN not in serialized
    assert JWT not in serialized
    on_disk = (tmp_path / "prov" / "provenance.jsonl").read_text(encoding="utf-8")
    assert GH_TOKEN not in on_disk and JWT not in on_disk


def test_bridge_error_redaction_catches_bare_keys() -> None:
    from dream.bridge.errors import _map_exception

    code, message = _map_exception(RuntimeError(f"provider rejected {SK_KEY}"))
    assert SK_KEY not in message
    assert "[REDACTED:" in message


def test_log_filter_redacts_msg_and_args() -> None:
    record = logging.LogRecord(
        "dream.test", logging.INFO, __file__, 1, "token %s saved", (GH_TOKEN,), None
    )
    assert RedactingFilter().filter(record) is True
    assert GH_TOKEN not in record.getMessage()

    # the message itself is scanned even without args
    bare = logging.LogRecord("dream.test", logging.INFO, __file__, 1, SK_KEY, None, None)
    assert RedactingFilter().filter(bare) is True
    assert SK_KEY not in bare.getMessage()


def test_install_is_idempotent() -> None:
    logger = logging.getLogger("dream.security.redaction.probe")
    try:
        first = install_redaction_filter("dream.security.redaction.probe")
        second = install_redaction_filter("dream.security.redaction.probe")
        assert first is second
        assert sum(
            1 for item in logger.filters if isinstance(item, RedactingFilter)
        ) == 1
    finally:
        logger.filters.clear()
