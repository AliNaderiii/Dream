"""Unit tests for the reliability toolkit (tokens, deadlines, budgets, buffers)."""

from __future__ import annotations

import threading
import time

import pytest

from dream.agentmodes.cancel import CancellationToken
from dream.commerce import Ledger, QuotaExceeded
from dream.reliability import (
    MAX_STEP_DELAY_SECONDS,
    MAX_TIMEOUT_SECONDS,
    MAX_WAIT_SECONDS,
    BackpressureError,
    BoundedBuffer,
    BoundedList,
    Budget,
    BudgetExceeded,
    BudgetKind,
    CancelToken,
    Deadline,
    DeadlineExceeded,
    Degradation,
    DegradationLevel,
    ExhaustionAction,
    OperationCancelled,
    OverflowPolicy,
    Watchdog,
    adapt_agentmodes,
    adapt_research_stop,
    attach_ledger,
    clamp_delay,
    clamp_timeout,
    clamp_wait,
    consume_ledger_turn,
)
from dream.reliability.budget import SkipDecision


def test_cancel_token_check_and_throw() -> None:
    token = CancelToken(name="unit")
    assert token.is_cancelled() is False
    token.throw_if_cancelled()
    token.cancel(reason="stop")
    assert token.is_cancelled() is True
    assert token.reason == "stop"
    with pytest.raises(OperationCancelled) as caught:
        token.throw_if_cancelled()
    assert caught.value.reason == "stop"
    assert caught.value.name == "unit"


def test_cancel_token_composes_parent_and_child() -> None:
    parent = CancelToken(name="parent")
    child = parent.child("child")
    parent.cancel(reason="root")
    assert child.is_cancelled() is True
    assert child.reason == "root"


def test_cancel_token_compose_any() -> None:
    a = CancelToken(name="a")
    b = CancelToken(name="b")
    both = CancelToken.compose(a, b, name="both")
    b.cancel(reason="b-fired")
    assert both.is_cancelled() is True
    assert both.reason == "b-fired"


def test_adapt_p4_agentmodes_token_both_directions() -> None:
    p4 = CancellationToken()
    token = adapt_agentmodes(p4, name="p4")
    p4.cancel()
    assert token.is_cancelled() is True

    ours = CancelToken(name="ours")
    other = CancellationToken()
    ours.link_agentmodes(other)
    ours.cancel(reason="from-ours")
    assert other.is_cancelled() is True


def test_adapt_research_stop_event() -> None:
    event = threading.Event()
    token = adapt_research_stop(event)
    event.set()
    assert token.is_cancelled() is True

    event2 = threading.Event()
    token2 = adapt_research_stop(event2)
    token2.cancel(reason="stop")
    assert event2.is_set() is True


def test_wait_is_hard_capped() -> None:
    token = CancelToken(name="cap")
    started = time.monotonic()
    fired = token.wait(timeout=0.12)
    elapsed = time.monotonic() - started
    assert fired is False
    assert elapsed < 0.6
    assert clamp_wait(1e9) == MAX_WAIT_SECONDS
    assert clamp_wait(-3) == 0.0
    assert clamp_wait(None) == MAX_WAIT_SECONDS


def test_public_delay_and_timeout_are_capped() -> None:
    assert clamp_delay(1_000_000_000) == MAX_STEP_DELAY_SECONDS
    assert clamp_delay(-1) == 0.0
    assert clamp_timeout(1e9) == MAX_TIMEOUT_SECONDS
    assert clamp_timeout(float("nan"), default=4.0) == 4.0


def test_deadline_relative_and_child_cannot_outlive_parent() -> None:
    parent = Deadline.after(0.4, owner="engine", step="turn")
    child = parent.child("tool", budget=10.0)
    assert child.remaining() <= parent.remaining() + 0.01
    time.sleep(0.05)
    assert parent.expired() is False
    parent.throw_if_exceeded()


def test_deadline_exceeded_names_owner_and_step() -> None:
    deadline = Deadline.after(0.05, owner="research", step="search")
    time.sleep(0.08)
    with pytest.raises(DeadlineExceeded) as caught:
        deadline.throw_if_exceeded()
    assert caught.value.owner == "research"
    assert caught.value.step == "search"


def test_absolute_deadline_is_capped() -> None:
    far = time.monotonic() + 1e9
    deadline = Deadline.absolute(far, owner="cap", step="wait")
    assert deadline.remaining() <= 600.0 + 0.05


def test_watchdog_reaps_hung_sync_task() -> None:
    def hang() -> None:
        time.sleep(60)

    deadline = Deadline.after(0.15, owner="test", step="hang")
    watchdog = Watchdog(deadline)
    with pytest.raises(DeadlineExceeded) as caught:
        watchdog.run(hang)
    assert watchdog.reaped is True
    assert watchdog.cause is not None
    assert "hang" in watchdog.cause
    assert caught.value.step == "hang"
    assert watchdog.token.is_cancelled() is True


def test_watchdog_returns_when_work_finishes() -> None:
    deadline = Deadline.after(2.0, owner="test", step="ok")
    watchdog = Watchdog(deadline)
    assert watchdog.run(lambda: 7) == 7
    assert watchdog.reaped is False


def test_budget_tokens_fail_with_bilingual_text() -> None:
    budget = Budget(tokens=3, owner="turn", step="reply")
    budget.consume(BudgetKind.TOKENS, 3)
    with pytest.raises(BudgetExceeded) as caught:
        budget.consume("tokens", 1)
    text = caught.value.bilingual()
    assert "Token budget exhausted" in text
    assert "\u0628\u0648\u062f\u062c\u0647\u0654 \u062a\u0648\u06a9\u0646" in text
    assert caught.value.kind is BudgetKind.TOKENS
    assert caught.value.action is ExhaustionAction.FAIL


def test_budget_output_truncates() -> None:
    budget = Budget(output_bytes=8, owner="turn", step="write")
    cut = budget.truncate_text("abcdefghijklmnop")
    assert len(cut.encode("utf-8")) <= 8
    leftover = budget.remaining(BudgetKind.OUTPUT)
    assert leftover == 0


def test_budget_skip_returns_rationale() -> None:
    budget = Budget(tokens=1, owner="turn", step="tool")
    budget.consume(BudgetKind.TOKENS, 1)
    decision = budget.skip_if_exhausted(BudgetKind.TOKENS, rationale="no more tools")
    assert isinstance(decision, SkipDecision)
    text = decision.bilingual()
    assert "skipped" in text
    assert "\u0631\u062f \u0634\u062f" in text


def test_budget_time_exhausts_without_explicit_consume() -> None:
    budget = Budget(time_s=0.05, owner="turn", step="sleep")
    time.sleep(0.08)
    with pytest.raises(BudgetExceeded) as caught:
        budget.check(BudgetKind.TIME)
    assert caught.value.kind is BudgetKind.TIME


def test_ledger_quota_maps_to_budget_exceeded(tmp_path) -> None:
    path = tmp_path / "ledger.json"
    ledger = Ledger(path=path, plan="guest")
    for _ in range(20):
        ledger.consume()
    with pytest.raises(QuotaExceeded):
        ledger.consume()
    with pytest.raises(BudgetExceeded) as caught:
        consume_ledger_turn(ledger)
    assert caught.value.kind is BudgetKind.MONEY
    assert "Money budget exhausted" in caught.value.message_en


def test_attach_ledger_copies_remaining(tmp_path) -> None:
    path = tmp_path / "ledger.json"
    ledger = Ledger(path=path, plan="guest")
    ledger.consume()
    budget = Budget(owner="turn", step="meter")
    attach_ledger(budget, ledger)
    leftover = budget.remaining(BudgetKind.MONEY)
    assert leftover == 19


def test_bounded_buffer_drop_oldest() -> None:
    buf = BoundedBuffer(maxlen=3, policy=OverflowPolicy.DROP_OLDEST)
    for item in range(5):
        buf.put(item)
    assert buf.snapshot() == [2, 3, 4]
    assert len(buf) <= 3
    assert buf.dropped == 2


def test_bounded_buffer_coalesce_same_key() -> None:
    buf = BoundedBuffer(maxlen=4, policy=OverflowPolicy.COALESCE)
    buf.put({"n": 1}, key="progress")
    buf.put({"n": 2}, key="progress")
    buf.put({"n": 3}, key="progress")
    assert buf.snapshot() == [{"n": 3}]
    assert buf.coalesced == 2


def test_bounded_buffer_reject() -> None:
    buf = BoundedBuffer(maxlen=1, policy=OverflowPolicy.REJECT)
    buf.put("a")
    with pytest.raises(BackpressureError):
        buf.put("b")
    assert buf.snapshot() == ["a"]


def test_bounded_list_never_grows_past_maxlen() -> None:
    items = BoundedList(maxlen=2)
    items.extend([1, 2, 3, 4])
    assert list(items) == [3, 4]
    assert len(items) == 2


def test_buffer_maxlen_itself_is_capped() -> None:
    buf = BoundedBuffer(maxlen=1_000_000)
    assert buf.maxlen <= 10_000


def test_degradation_ladder_logs_en_and_fa() -> None:
    ladder = Degradation()
    assert ladder.level is DegradationLevel.FULL
    ladder.step_down("provider timeout")
    assert ladder.level is DegradationLevel.REDUCED
    ladder.step_down("still failing")
    assert ladder.level is DegradationLevel.OFFLINE_ECHO
    ladder.step_down("echo is not enough")
    assert ladder.level is DegradationLevel.HONEST_ERROR
    text = ladder.bilingual()
    assert "honest error" in text
    assert "\u062e\u0637\u0627\u06cc \u0635\u0627\u062f\u0642\u0627\u0646\u0647" in text
    assert len(ladder.history) == 3
    assert ladder.history[0]["reason"] == "provider timeout"


def test_degradation_fail_jumps_to_honest_error() -> None:
    ladder = Degradation()
    ladder.fail("unknown state")
    assert ladder.level is DegradationLevel.HONEST_ERROR
    assert ladder.history[-1]["message_fa"]
