"""S05: bridge RPC tests for ``commerce.plan``, ``commerce.usage``, ``route.resolve``.

These RPCs are thin, read-only serialisers over ``dream.commerce`` and
``dream.router``. The tests pin the honest-price contract: a paid plan never
carries a numeric IRR price, and an unlimited plan never carries a fabricated
limit.
"""

from __future__ import annotations

import tempfile

from dream.bridge.methods import BridgeMethods
from dream.commerce import PLANS, Ledger
from dream.memory import MemoryStore


def make_methods() -> BridgeMethods:
    return BridgeMethods(
        MemoryStore(":memory:"),
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        default_provider="echo",
    )


def set_plan(monkeypatch, plan: str, ledger: str | None = None) -> None:
    """Point DREAM_PLAN (and optionally DREAM_LEDGER) at a temp path."""
    monkeypatch.setenv("DREAM_PLAN", plan)
    if ledger is None:
        monkeypatch.delenv("DREAM_LEDGER", raising=False)
    else:
        monkeypatch.setenv("DREAM_LEDGER", ledger)


# --------------------------------------------------------------------------- #
# commerce.plan
# --------------------------------------------------------------------------- #


def test_commerce_plan_local_default_is_free_and_unlimited(monkeypatch):
    set_plan(monkeypatch, "local")
    m = make_methods()
    plan = m.commerce_plan({})

    assert plan["plan_id"] == "local"
    assert plan["name_fa"] == "محلی"
    assert plan["name_en"] == "Local"
    assert plan["currency"] == "IRR"
    assert plan["price"] == 0
    assert plan["period"] == "unlimited"
    assert plan["metered"] is False
    assert plan["ledger_attached"] is False
    assert plan["limits"] == {"daily": None, "monthly": None, "yearly": None}


def test_commerce_plan_guest_is_free_metered_daily(monkeypatch):
    ledger = tempfile.mktemp(suffix=".json")
    set_plan(monkeypatch, "guest", ledger)
    m = make_methods()
    plan = m.commerce_plan({})

    assert plan["plan_id"] == "guest"
    assert plan["price"] == 0
    assert plan["period"] == "day"
    assert plan["metered"] is True
    assert plan["ledger_attached"] is True
    assert plan["limits"]["daily"] == 20


def test_commerce_plan_paid_plans_never_carry_a_numeric_price(monkeypatch):
    """The S05 honesty gate: no made-up IRR for any paid plan."""
    paid_plans = [plan for plan in PLANS.values() if plan.price != 0]
    for plan in paid_plans:
        set_plan(monkeypatch, plan.id)
        m = make_methods()
        info = m.commerce_plan({})
        assert info["price"] is None, f"{plan.id} must not invent a price"
        assert info["price_note"] == "TBD after cost measurement"
        assert info["currency"] == "IRR"


def test_commerce_plan_period_matches_quota_window(monkeypatch):
    for plan_id, expected in (
        ("daily", "day"),
        ("individual_monthly", "month"),
        ("individual_yearly", "year"),
        ("team", "month"),
        ("company", "month"),
        ("local", "unlimited"),
    ):
        set_plan(monkeypatch, plan_id)
        m = make_methods()
        assert m.commerce_plan({})["period"] == expected, plan_id


# --------------------------------------------------------------------------- #
# commerce.usage
# --------------------------------------------------------------------------- #


def test_commerce_usage_without_ledger_is_unlimited(monkeypatch):
    set_plan(monkeypatch, "local")
    m = make_methods()
    usage = m.commerce_usage({})

    assert usage["plan_id"] == "local"
    assert usage["window"] is None
    assert usage["used"] == 0
    assert usage["limit"] is None
    assert usage["remaining"] is None
    assert usage["unlimited"] is True


def test_commerce_usage_reads_the_attached_ledger(monkeypatch):
    ledger_path = tempfile.mktemp(suffix=".json")
    set_plan(monkeypatch, "guest", ledger_path)

    ledger = Ledger(path=ledger_path, plan="guest")
    for _ in range(3):
        ledger.consume()

    m = make_methods()
    usage = m.commerce_usage({})
    assert usage["plan_id"] == "guest"
    assert usage["window"] == "day"
    assert usage["used"] == 3
    assert usage["limit"] == 20
    assert usage["remaining"] == 17
    assert usage["unlimited"] is False


# --------------------------------------------------------------------------- #
# route.resolve
# --------------------------------------------------------------------------- #


def test_route_resolve_echo_when_unconfigured(monkeypatch):
    set_plan(monkeypatch, "local")
    for var in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OLLAMA_HOST", "DREAM_BACKEND"):
        monkeypatch.delenv(var, raising=False)
    m = make_methods()
    route = m.route_resolve({})

    assert route["name"] == "echo"
    assert route["leaves_machine"] is False
    assert "no data leaves" in route["sentence_en"]
    assert "خارج نمی" in route["sentence_fa"]


def test_route_resolve_hosted_when_key_configured(monkeypatch):
    set_plan(monkeypatch, "local")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("DREAM_BACKEND", raising=False)
    m = make_methods()
    route = m.route_resolve({})

    assert route["name"] == "hosted"
    assert route["leaves_machine"] is True
    assert "leaves this machine" in route["sentence_en"]


def test_route_resolve_ollama_is_local(monkeypatch):
    set_plan(monkeypatch, "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    monkeypatch.delenv("DREAM_BACKEND", raising=False)
    m = make_methods()
    route = m.route_resolve({})

    assert route["name"] == "ollama"
    assert route["leaves_machine"] is False


def test_route_resolve_aval_when_key_configured(monkeypatch):
    """S09: the existing route.resolve RPC surfaces the new aval route."""
    set_plan(monkeypatch, "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("DREAM_BACKEND", raising=False)
    monkeypatch.delenv("AVALAI_API_KEY", raising=False)
    monkeypatch.setenv("AVALAI_API_KEY", "sk-aval")
    m = make_methods()
    route = m.route_resolve({})

    assert route["name"] == "aval"
    assert route["leaves_machine"] is True
    assert "aval ai" in route["sentence_en"].lower()
    assert "api.avalai.ir" in route["sentence_en"].lower()
    assert "leaves this machine" in route["sentence_en"].lower()
    assert "aval ai" in route["sentence_fa"].lower()


# --------------------------------------------------------------------------- #
# Handler table wiring
# --------------------------------------------------------------------------- #


def test_commerce_and_route_are_registered_in_the_handler_table():
    m = make_methods()
    for method in ("commerce.plan", "commerce.usage", "route.resolve"):
        assert method in m.handlers, method
        assert callable(m.handlers[method])
