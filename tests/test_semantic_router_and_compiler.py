"""Unit and integration tests for Semantic Router, Dynamic Prompt Compiler & Cascading Engine."""

from __future__ import annotations

import pytest

from dream.router import (
    IntentComplexity,
    ModelCascader,
    ModelTier,
    PromptCompiler,
    RoutingEngine,
    SemanticRouter,
    get_router_tools,
    handle_router_slash_command,
    reset_global_routing_engine,
    router_cascade_plan,
    router_compile_prompt,
    router_evaluate_query,
    router_export_report,
    router_get_stats,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_router_engine() -> None:
    reset_global_routing_engine()
    yield
    reset_global_routing_engine()


def test_toolset_includes_router() -> None:
    """Verify router toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("router")
    assert ts is not None
    assert "router_evaluate_query" in ts.tools
    assert "router_compile_prompt" in ts.tools
    assert "router_cascade_plan" in ts.tools
    assert "router" in BUILTIN_TOOLSETS


def test_semantic_router_intent_classification() -> None:
    """Verify semantic router accurately classifies queries into intents and model tiers."""
    router = SemanticRouter()

    # Direct Answer
    d_direct = router.route_query("سلام، حال شما چطوره؟")
    assert d_direct.intent == IntentComplexity.DIRECT_ANSWER
    assert d_direct.target_tier == ModelTier.FAST_EDGE
    assert d_direct.estimated_tokens_saved == 1250

    # Simple Tool
    d_tool = router.route_query("ساعت و تاریخ امروز چند است؟")
    assert d_tool.intent == IntentComplexity.SIMPLE_TOOL
    assert d_tool.target_tier == ModelTier.FAST_EDGE
    assert "get_datetime" in d_tool.predicted_tools

    # Code Execution
    d_code = router.route_query("یک اسکریپت پایتون برای مرتب‌سازی آرایه بنویس")
    assert d_code.intent == IntentComplexity.CODE_EXECUTION
    assert d_code.target_tier == ModelTier.STANDARD_CHAT
    assert "sandbox_execute_python" in d_code.predicted_tools

    # Reasoning Chain
    d_reason = router.route_query("استدلال و اثبات کن که آیا هوش مصنوعی عمومی ممکن است؟")
    assert d_reason.intent == IntentComplexity.REASONING_CHAIN
    assert d_reason.target_tier == ModelTier.REASONING_HEAVY

    # Deep Research
    d_deep = router.route_query("یک تحقیق جامع و بررسی عمیق از بازار تراشه‌های هوش مصنوعی ارائه بده")
    assert d_deep.intent == IntentComplexity.DEEP_RESEARCH
    assert d_deep.target_tier == ModelTier.REASONING_HEAVY


def test_semantic_router_custom_rule() -> None:
    """Verify custom routing regex rules take priority."""
    router = SemanticRouter()
    router.add_route_rule(
        pattern=r"^\/admin_deep",
        intent=IntentComplexity.DEEP_RESEARCH,
        target_tier=ModelTier.REASONING_HEAVY,
        priority=100,
    )

    decision = router.route_query("/admin_deep analyze server logs")
    assert decision.intent == IntentComplexity.DEEP_RESEARCH
    assert decision.target_tier == ModelTier.REASONING_HEAVY
    assert "custom_pattern:^\\/admin_deep" in decision.matched_rules


def test_prompt_compiler_token_budgeting() -> None:
    """Verify dynamic prompt assembly obeys token limits and drops lower priority sections."""
    compiler = PromptCompiler()

    # Small budget drops non-mandatory sections
    compiled_small = compiler.compile(
        template_name="default_agent",
        target_tier=ModelTier.FAST_EDGE,
        user_query="Hello",
        max_budget_tokens=50,
    )
    assert "soul_core" in compiled_small.included_sections
    assert "persian_excellence" in compiled_small.included_sections
    assert "extended_dialectic" in compiled_small.dropped_sections

    # Variable injection
    compiled_vars = compiler.compile(
        template_name="default_agent",
        target_tier=ModelTier.STANDARD_CHAT,
        user_query="تست",
        variables={"jalali_date": "1405/06/20", "user_profile": "AI Researcher"},
        max_budget_tokens=4000,
    )
    assert "1405/06/20" in compiled_vars.system_prompt
    assert "AI Researcher" in compiled_vars.system_prompt


def test_model_cascader_and_escalation() -> None:
    """Verify cascading pipeline and escalation evaluation."""
    cascader = ModelCascader()
    router = SemanticRouter()

    dec_fast = router.route_query("سلام")
    plan = cascader.get_cascade_plan(dec_fast)
    assert plan["primary_tier"] == "fast_edge"
    assert "standard_chat" in plan["escalation_chain"]
    assert "reasoning_heavy" in plan["escalation_chain"]

    # Escalation on tool failure
    must_esc, next_tier = cascader.evaluate_escalation(
        current_tier=ModelTier.FAST_EDGE,
        confidence=0.85,
        had_tool_error=True,
    )
    assert must_esc is True
    assert next_tier == ModelTier.STANDARD_CHAT

    # No escalation on normal high confidence
    no_esc, _ = cascader.evaluate_escalation(
        current_tier=ModelTier.STANDARD_CHAT,
        confidence=0.95,
        had_tool_error=False,
    )
    assert no_esc is False


def test_routing_engine_and_stats() -> None:
    """Verify routing coordinator records history and calculates token savings."""
    engine = RoutingEngine()

    engine.route_and_compile("سلام")
    engine.route_and_compile("کد پایتون بنویس")
    engine.route_and_compile("ساعت چند است؟")

    stats = engine.get_stats()
    assert stats.total_routed == 3
    assert stats.direct_answers == 1
    assert stats.code_executions == 1
    assert stats.simple_tools == 1
    assert stats.total_tokens_saved > 0
    assert stats.average_latency_ms >= 0.0


def test_router_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /route, /cascade, /router slash commands."""
    tools = get_router_tools()
    assert len(tools) >= 5

    # Tool: evaluate query
    res_eval = router_evaluate_query("یک الگوریتم یادگیری عمیق به زبان پایتون")
    assert res_eval["success"] is True
    assert res_eval["decision"]["intent"] == "code_execution"

    # Tool: compile prompt
    res_comp = router_compile_prompt(variables={"jalali_date": "1405/01/01"})
    assert res_comp["success"] is True
    assert "1401" in res_comp["system_prompt"] or "1405" in res_comp["system_prompt"]

    # Tool: cascade plan
    res_casc = router_cascade_plan("تحقیق جامع پیرامون پردازنده‌های عصبی")
    assert res_casc["success"] is True
    assert res_casc["decision"]["target_tier"] == "reasoning_heavy"

    # Tool: get stats
    res_stats = router_get_stats()
    assert res_stats["success"] is True

    # Tool: export report
    res_rep = router_export_report()
    assert res_rep["success"] is True
    assert "Semantic Router & Cascading" in res_rep["markdown_report"]

    # Slash: /route
    slash_r = handle_router_slash_command("/route ساعت چنده؟")
    assert "نتیجه مسیریابی معنایی" in slash_r

    # Slash: /cascade
    slash_c = handle_router_slash_command("/cascade بنویس کد")
    assert "پلان آبشار مدل‌ها" in slash_c

    # Slash: /router stats
    slash_s = handle_router_slash_command("/router stats")
    assert "Semantic Router & Cascading" in slash_s

    # Slash: /router reset
    slash_reset = handle_router_slash_command("/router reset")
    assert "بازنشانی شد" in slash_reset
