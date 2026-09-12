"""Unit and integration tests for Multi-Agent Debate & Fact-Checking Subsystem."""

from __future__ import annotations

import pytest

from dream.debate import (
    DebateEngine,
    DebateRole,
    DebateStatus,
    FactChecker,
    VerificationStatus,
    debate_list_sessions,
    debate_run_autonomous,
    debate_verify_statement,
    handle_debate_slash_command,
    reset_global_debate_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_debate_engine() -> None:
    reset_global_debate_engine()
    yield
    reset_global_debate_engine()


def test_toolset_includes_debate() -> None:
    """Verify debate toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("debate")
    assert ts is not None
    assert "debate_create_session" in ts.tools
    assert "debate_verify_statement" in ts.tools
    assert "debate_run_autonomous" in ts.tools
    assert "debate" in BUILTIN_TOOLSETS


def test_factchecker_fallacy_detection_and_claims() -> None:
    """Verify statement extraction and logical fallacy identification."""
    checker = FactChecker()

    statement_fallacy = "همه می‌دانند که یا باید این سیستم اجرا شود یا نابودی کامل حتمی است!"
    fallacies = checker.detect_fallacies(statement_fallacy)
    assert len(fallacies) >= 2

    test_stmt = (
        "زبان پایتون سرعت اجرای بالایی در محاسبات عددی دارد. "
        "این موضوع در مقالات معتبر اثبات شده است."
    )
    claims = checker.extract_claims(test_stmt)
    assert len(claims) >= 1
    assert claims[0].verification_status == VerificationStatus.UNVERIFIED


def test_factchecker_evidence_verification() -> None:
    """Verify evidence matching and contradiction detection."""
    checker = FactChecker()
    claim = checker.extract_claims("زمین به دور خورشید گردش می‌کند.")[0]

    # Positive evidence verification
    verified_claim = checker.verify_claim_against_evidence(
        claim,
        evidence="بر اساس قوانین کپلر، زمین در یک مدار بیضوی به دور خورشید گردش می‌کند.",
    )
    assert verified_claim.verification_status in (
        VerificationStatus.VERIFIED,
        VerificationStatus.PARTIAL,
    )
    assert verified_claim.confidence_score >= 0.5

    # Contradiction verification
    contradicted_claim = checker.verify_claim_against_evidence(
        claim,
        evidence="این ادعا کاملاً غلط و نادرست است و زمین به دور خورشید گردش نمی‌کند.",
    )
    assert contradicted_claim.verification_status == VerificationStatus.CONTRADICTED


def test_delphi_moderator_and_consensus_computation() -> None:
    """Verify multi-round moderation and Delphi consensus scoring."""
    engine = DebateEngine()
    session = engine.create_debate(topic="مهاجرت به معماری میکروسرویس")

    # Turn 1
    engine.add_argument(
        debate_id=session.debate_id,
        role=DebateRole.PROPONENT,
        speaker_name="Architect Pro",
        argument="معماری میکروسرویس قابلیت مقیاس‌پذیری مستقل تیم‌ها را افزایش می‌دهد.",
        evidence="میکروسرویس قابلیت مقیاس‌پذیری و استقلال تیم‌ها را فراهم می‌آورد.",
    )

    # Turn 2
    engine.add_argument(
        debate_id=session.debate_id,
        role=DebateRole.OPPONENT,
        speaker_name="Architect Skeptic",
        argument="پیچیدگی شبکه و هزینه نگهداری در معماری توزیع‌شده افزایش می‌یابد.",
        evidence="پیچیدگی شبکه و هزینه نگهداری سرویس‌های توزیع‌شده بالا است.",
    )

    status, score, summary = engine.moderator.evaluate_consensus(session)
    assert score > 0.4
    assert "Delphi Consensus Report" in summary
    assert len(session.turns) == 2


def test_debate_engine_autonomous_rounds() -> None:
    """Verify autonomous debate rounds and session lifecycle."""
    engine = DebateEngine()
    p_arg = "ابزارهای هوش مصنوعی بهره‌وری توسعه‌دهندگان را به میزان چشمگیری افزایش می‌دهند."
    o_arg = "کدهای تولیدشده توسط هوش مصنوعی ممکن است دارای باگ‌های امنیتی باشند."
    evi = "هوش مصنوعی بهره‌وری توسعه‌دهندگان را افزایش می‌دهد اما ممکن است باگ امنیتی داشته باشد."

    session, summary = engine.run_autonomous_debate(
        topic="استفاده از هوش مصنوعی در کدنویسی",
        proponent_arg=p_arg,
        opponent_arg=o_arg,
        evidence=evi,
    )

    assert session.status in (DebateStatus.CONVERGED, DebateStatus.IN_PROGRESS)
    assert session.confidence_score > 0.0
    assert len(session.turns) == 2
    assert "Delphi Consensus Report" in summary


def test_debate_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /debate & /verify slash commands."""
    # Tool: verify statement
    res_v = debate_verify_statement(
        statement="سرعت نور در خلا حدود ۳۰۰ هزار کیلومتر بر ثانیه است.",
        evidence="سرعت نور در خلا دقیقاً ۲۹۹,۷۹۲ کیلومتر بر ثانیه اندازه‌گیری شده است.",
    )
    assert res_v["success"] is True
    assert res_v["confidence"] >= 0.4

    # Tool: autonomous debate
    res_deb = debate_run_autonomous(
        topic="تحلیل کارایی زبان Rust در مقایسه با C++",
        proponent_arg="زبان Rust با سیستم Borrow Checker امنیت حافظه را تضمین می‌کند.",
        opponent_arg="زمان کامپایل در Rust در پروژه‌های بزرگ نسبت به C++ طولانی‌تر است.",
    )
    assert res_deb["success"] is True
    assert "session" in res_deb

    # Tool: list
    res_list = debate_list_sessions()
    assert res_list["success"] is True
    assert len(res_list["debates"]) >= 1

    # Slash: /verify
    slash_v = handle_debate_slash_command("/verify زمین مسطح است چون همه می‌دانند!")
    assert "نتیجه ارزیابی" in slash_v
    assert "مغالطه" in slash_v

    # Slash: /debate list
    slash_list = handle_debate_slash_command("/debate list")
    assert "فهرست نشست‌های مناظره" in slash_list

    # Slash: /debate reset
    slash_reset = handle_debate_slash_command("/debate reset")
    assert "پاکسازی شد" in slash_reset
