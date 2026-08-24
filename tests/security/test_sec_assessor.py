"""Stage B — auxiliary risk assessor discipline (L2, SEC-G-04).

Strict schema, hard timeout (tested against a hanging fake backend),
error isolation, and the deterministic offline pattern rules. No test in
this module touches the network: model access is injected.
"""

from __future__ import annotations

import json
import time

import pytest

from dream.security.assessor import (
    ASSESS_TIMEOUT_SECONDS,
    RISK_LEVELS,
    assess,
    pattern_assess,
)

# -- strict schema ----------------------------------------------------------- #


@pytest.mark.parametrize(
    "reply",
    [
        '{"level": "low", "reason": "listing files"}',
        '{"level": "medium", "reason": "copies files"}',
        '{"level": "high", "reason": "deletes things"}',
        '{"level": "catastrophic", "reason": "formats disks"}',
    ],
)
def test_well_formed_replies_are_accepted(reply: str) -> None:
    assessment = assess("anything", model_call=lambda _p: reply)
    assert assessment.level == json.loads(reply)["level"]
    assert assessment.source == "model"


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        '{"level": "low"}',  # missing reason
        '{"reason": "no level"}',  # missing level
        '{"level": "low", "reason": "x", "extra": 1}',  # extra key
        '{"level": "apocalyptic", "reason": "unknown level"}',
        '{"level": "LOW", "reason": "case matters"}',
        '{"level": "low", "reason": ""}',  # empty reason
        '{"level": "low", "reason": 42}',  # wrong type
        "[1, 2, 3]",
        "null",
    ],
)
def test_schema_violations_deny(reply: str) -> None:
    assessment = assess("anything", model_call=lambda _p: reply)
    assert assessment.verdict == "deny"
    assert assessment.level is None
    assert assessment.source == "schema_violation"


def test_backend_exception_denies() -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("backend exploded")

    assessment = assess("anything", model_call=boom)
    assert assessment.verdict == "deny"
    assert assessment.source == "model_error"


def test_keyboard_interrupt_from_the_backend_denies() -> None:
    def interrupt(_prompt: str) -> str:
        raise KeyboardInterrupt()

    assert assess("anything", model_call=interrupt).source == "model_error"


# -- hard timeout (the hanging fake backend) -------------------------------- #


def test_hanging_backend_hits_the_hard_timeout_and_denies() -> None:
    def hang(_prompt: str) -> str:
        time.sleep(30.0)
        return '{"level": "low", "reason": "never arrives"}'

    started = time.monotonic()
    assessment = assess("anything", model_call=hang, timeout=0.3)
    elapsed = time.monotonic() - started
    assert assessment.verdict == "deny"
    assert assessment.source == "model_timeout"
    assert "timed out" in assessment.reason_en
    assert assessment.reason_fa  # the denial is bilingual
    assert elapsed < 5.0, "the hard timeout must actually interrupt the wait"


def test_timeout_shorter_than_the_reply_is_a_denial() -> None:
    def slow(_prompt: str) -> str:
        time.sleep(0.5)
        return '{"level": "low", "reason": "late but valid"}'

    assert assess("x", model_call=slow, timeout=0.1).verdict == "deny"


def test_reply_faster_than_the_timeout_is_used() -> None:
    def quick(_prompt: str) -> str:
        return '{"level": "low", "reason": "fast"}'

    assert assess("x", model_call=quick, timeout=5.0).level == "low"


# -- offline / echo path: pattern rules only, no network --------------------- #


def test_no_model_call_means_patterns_only() -> None:
    assessment = assess("ls -la")
    assert assessment.source == "pattern"
    assert assessment.level == "low"


def test_pattern_floor_match_is_catastrophic() -> None:
    assessment = pattern_assess("rm -rf /")
    assert assessment.level == "catastrophic"
    assert assessment.verdict == "deny"


@pytest.mark.parametrize(
    ("command", "level"),
    [
        ("cat /etc/hostname", "low"),
        ("ls -la", "low"),
        ("git status", "low"),
        ("grep TODO notes.md", "low"),
        ("echo hello", "low"),
        ("mv a.txt b.txt", "medium"),
        ("pip install requests", "medium"),
        ("git push origin main", "medium"),
        ("mkdir new-folder", "medium"),
        ("sudo apt update", "high"),
        ("rm report.txt", "high"),
        ("shutdown -h now", "high"),
        ("git push --force origin main", "high"),
    ],
)
def test_pattern_rules_classify_the_curated_verbs(command: str, level: str) -> None:
    assert pattern_assess(command).level == level


def test_unknown_verbs_fail_toward_the_human() -> None:
    assessment = pattern_assess("frobnicate --all")
    assert assessment.level == "medium"
    assert assessment.verdict == "prompt"


def test_verdict_mapping_is_pinned() -> None:
    assert assess("ls", model_call=lambda _p: '{"level": "low", "reason": "r"}').verdict == (
        "allow_once"
    )
    assert assess("x", model_call=lambda _p: '{"level": "high", "reason": "r"}').verdict == (
        "prompt"
    )
    assert assess(
        "x", model_call=lambda _p: '{"level": "catastrophic", "reason": "r"}'
    ).verdict == ("deny")


def test_levels_and_timeout_constants_are_stable() -> None:
    assert RISK_LEVELS == ("low", "medium", "high", "catastrophic")
    assert 0.1 < ASSESS_TIMEOUT_SECONDS <= 10.0
