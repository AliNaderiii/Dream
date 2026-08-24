"""Stage B — approval engine v2: modes, contexts, opt-ins (L2, SEC-G-04..06).

The evaluation order is the contract: floor → context → mode. ``manual``
is the default and reproduces the pre-SEC behaviour byte for byte; ``off``
exists only as an explicit opt-in; cron and single-query contexts default
to deny.
"""

from __future__ import annotations

import pytest

from dream.security.assessor import Assessment
from dream.security.engine import SecurityEngine
from dream.security.history import ApprovalHistory


def _engine(mode: str = "manual", **kwargs) -> SecurityEngine:
    return SecurityEngine(mode, history=ApprovalHistory(":memory:"), **kwargs)


# -- modes ------------------------------------------------------------------ #


def test_default_mode_is_manual() -> None:
    assert _engine().mode == "manual"


def test_manual_without_approver_denies_with_the_legacy_reason() -> None:
    decision = _engine().evaluate_dangerous("run_shell", {"command": "echo hi"})
    assert not decision.allowed
    assert decision.reason == "dangerous tool denied: no approver configured"


def test_manual_approver_denial_keeps_the_legacy_reason() -> None:
    decision = _engine().evaluate_dangerous(
        "run_shell", {"command": "echo hi"}, ask=lambda *_: False
    )
    assert not decision.allowed
    assert decision.reason == "dangerous tool denied by approver"


def test_manual_approver_yes_keeps_the_legacy_reason() -> None:
    decision = _engine().evaluate_dangerous(
        "run_shell", {"command": "echo hi"}, ask=lambda *_: True
    )
    assert decision.allowed
    assert decision.reason == "dangerous tool approved"


def test_off_mode_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="explicit opt-in"):
        SecurityEngine("off")


def test_off_mode_allows_what_the_floor_misses_and_says_so() -> None:
    decision = _engine("off", off_opt_in=True).evaluate_dangerous(
        "run_shell", {"command": "echo hi"}
    )
    assert decision.allowed
    assert "approval engine is OFF" in decision.reason


def test_invalid_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        SecurityEngine("yolo")


def test_invalid_context_modes_are_rejected() -> None:
    with pytest.raises(ValueError):
        SecurityEngine("manual", cron_mode="allow")
    with pytest.raises(ValueError):
        SecurityEngine("manual", single_query_mode="prompt")


# -- contexts (cron / single-query default deny) ----------------------------- #


def test_cron_context_denies_dangerous_by_default() -> None:
    decision = _engine().evaluate_dangerous(
        "run_shell", {"command": "echo hi"}, context="cron"
    )
    assert not decision.allowed
    assert decision.stage == "context"
    assert "cron mode denies" in decision.reason


def test_single_query_context_denies_dangerous_by_default() -> None:
    decision = _engine().evaluate_dangerous(
        "run_shell", {"command": "echo hi"}, context="single_query"
    )
    assert not decision.allowed
    assert "single-query mode denies" in decision.reason


def test_cron_denial_is_bilingual() -> None:
    decision = _engine().evaluate_dangerous(
        "run_shell", {"command": "echo hi"}, context="cron"
    )
    assert "\u067e\u06cc\u0634\u200c\u0641\u0631\u0636" in decision.reason


def test_cron_denial_applies_even_in_off_mode() -> None:
    decision = _engine("off", off_opt_in=True).evaluate_dangerous(
        "run_shell", {"command": "echo hi"}, context="cron"
    )
    assert not decision.allowed


def test_cron_auto_mode_runs_after_the_floor() -> None:
    engine = _engine(cron_mode="auto")
    assert engine.evaluate_dangerous(
        "run_shell", {"command": "echo hi"}, context="cron"
    ).allowed
    assert not engine.evaluate_dangerous(
        "run_shell", {"command": "rm -rf /"}, context="cron"
    ).allowed


# -- smart mode (assessor-ordered decisions) -------------------------------- #


class _FixedModel:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.reply


def test_smart_low_auto_approves_once_and_logs() -> None:
    model = _FixedModel('{"level": "low", "reason": "read-only listing"}')
    engine = _engine("smart", model_call=model)
    decision = engine.evaluate_dangerous("run_shell", {"command": "ls -la"})
    assert decision.allowed
    assert decision.stage == "assessor"
    assert "low risk" in decision.reason
    rows = engine.history.entries()
    assert rows[0]["verdict"] == "approved_auto_low"


def test_smart_high_prompts_the_human() -> None:
    model = _FixedModel('{"level": "high", "reason": "deletes files"}')
    engine = _engine("smart", model_call=model)
    asked: list[str] = []
    decision = engine.evaluate_dangerous(
        "run_shell", {"command": "rm x.txt"}, ask=lambda name, _args: asked.append(name) or True
    )
    assert decision.allowed
    assert decision.stage == "approval"
    assert asked == ["run_shell"]


def test_smart_catastrophic_denies_without_prompting() -> None:
    model = _FixedModel('{"level": "catastrophic", "reason": "destroys the disk"}')
    engine = _engine("smart", model_call=model)
    asked: list[str] = []
    decision = engine.evaluate_dangerous(
        "run_shell", {"command": "custom-destruct"}, ask=lambda *_: asked.append("x") or True
    )
    assert not decision.allowed
    assert decision.stage == "assessor"
    assert asked == []  # the human is never offered a catastrophic choice


def test_smart_timeout_denies() -> None:
    import time

    def hang(_prompt: str) -> str:
        time.sleep(5.0)
        return '{"level": "low", "reason": "too late"}'

    engine = _engine("smart", model_call=hang, assess_timeout=0.2)
    decision = engine.evaluate_dangerous("run_shell", {"command": "anything"})
    assert not decision.allowed
    assert "timed out" in decision.reason


# -- status + history -------------------------------------------------------- #


def test_status_reports_the_engine_state() -> None:
    engine = _engine("off", off_opt_in=True, cron_mode="deny")
    status = engine.status()
    assert status["mode"] == "off"
    assert status["off_active"] is True
    assert status["floor"] == "always-on"
    assert status["cron_mode"] == "deny"
    assert status["history_available"] is True


def test_every_decision_lands_in_the_history() -> None:
    engine = _engine()
    engine.evaluate_dangerous("run_shell", {"command": "rm -rf /"})
    engine.evaluate_dangerous("run_shell", {"command": "echo hi"})
    engine.evaluate_dangerous("run_shell", {"command": "echo hi"}, ask=lambda *_: True)
    verdicts = [row["verdict"] for row in engine.history.entries()]
    assert verdicts == ["approved_human", "denied_no_approver", "floor_blocked"]


def test_engine_survives_a_corrupt_history_store(tmp_path) -> None:
    broken = tmp_path / "approvals.db"
    broken.write_bytes(b"this is not a sqlite database, just noise")
    engine = SecurityEngine("manual", history_path=str(broken))
    assert engine.history_broken
    # Protection keeps working even when the audit trail cannot be read.
    assert not engine.evaluate_dangerous("run_shell", {"command": "rm -rf /"}).allowed
    assert engine.evaluate_dangerous(
        "run_shell", {"command": "echo hi"}, ask=lambda *_: True
    ).allowed


def test_default_engine_validates_the_environment(monkeypatch, tmp_path) -> None:
    import dream.security.engine as engine_module

    monkeypatch.setenv("DREAM_APPROVAL_DB", str(tmp_path / "approvals.db"))
    engine_module.reset_default_engine(None)
    monkeypatch.setenv(engine_module.MODE_ENV, "off")
    assert engine_module.default_engine().mode == "manual"  # off needs opt-in
    engine_module.reset_default_engine(None)
    monkeypatch.setenv(engine_module.MODE_ENV, "off")
    monkeypatch.setenv(engine_module.OFF_OPT_IN_ENV, "1")
    assert engine_module.default_engine().mode == "off"
    engine_module.reset_default_engine(None)
    monkeypatch.setenv(engine_module.MODE_ENV, "bogus")
    assert engine_module.default_engine().mode == "manual"
    engine_module.reset_default_engine(None)


def test_assessment_type_is_exposed_for_tooling() -> None:
    assessment = Assessment(
        level="low", verdict="allow_once", reason_en="r", reason_fa="f", source="pattern"
    )
    assert assessment.level == "low"
