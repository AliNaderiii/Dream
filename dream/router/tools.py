"""LLM tool bindings for Semantic Routing, Prompt Compiler, and Cascading Engine."""

from __future__ import annotations

from typing import Any

from dream.router.engine import RoutingEngine

_GLOBAL_ROUTING_ENGINE: RoutingEngine | None = None


def get_global_routing_engine() -> RoutingEngine:
    """Get or initialize singleton RoutingEngine."""
    global _GLOBAL_ROUTING_ENGINE
    if _GLOBAL_ROUTING_ENGINE is None:
        _GLOBAL_ROUTING_ENGINE = RoutingEngine()
    return _GLOBAL_ROUTING_ENGINE


def reset_global_routing_engine() -> None:
    """Reset singleton RoutingEngine."""
    global _GLOBAL_ROUTING_ENGINE
    _GLOBAL_ROUTING_ENGINE = None


def router_evaluate_query(query: str) -> dict[str, Any]:
    """Evaluate cognitive complexity of user query and return target model tier."""
    engine = get_global_routing_engine()
    decision = engine.router.route_query(query)
    return {"success": True, "decision": decision.to_dict()}


def router_compile_prompt(
    template_name: str = "default_agent",
    variables: dict[str, Any] | None = None,
    user_query: str = "",
) -> dict[str, Any]:
    """Compile token-budgeted prompt template with dynamic variable injection."""
    engine = get_global_routing_engine()
    decision = engine.router.route_query(user_query or "سلام")
    compiled = engine.compiler.compile(
        template_name=template_name,
        target_tier=decision.target_tier,
        user_query=user_query,
        variables=variables or {},
    )
    return {
        "success": True,
        "compiled_prompt": compiled.to_dict(),
        "system_prompt": compiled.system_prompt,
    }


def router_cascade_plan(query: str) -> dict[str, Any]:
    """Generate multi-tier cascading fallback plan and speculative tool sequence."""
    engine = get_global_routing_engine()
    decision, compiled, cascade_plan = engine.route_and_compile(query)
    return {
        "success": True,
        "decision": decision.to_dict(),
        "cascade_plan": cascade_plan,
    }


def router_get_stats() -> dict[str, Any]:
    """Get aggregate statistics on intent distribution and token savings."""
    engine = get_global_routing_engine()
    stats = engine.get_stats()
    return {"success": True, "stats": stats.to_dict()}


def router_export_report() -> dict[str, Any]:
    """Export formatted Markdown summary of routing decisions and token economics."""
    engine = get_global_routing_engine()
    report = engine.format_routing_report()
    return {"success": True, "markdown_report": report}


def router_reset_all() -> dict[str, Any]:
    """Reset router history and metrics."""
    engine = get_global_routing_engine()
    engine.reset()
    return {"success": True, "message": "\u0622\u0645\u0627\u0631 \u0648 \u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."}


def get_router_tools() -> list[Any]:
    """Return router tool functions for agent registration."""
    return [
        router_evaluate_query,
        router_compile_prompt,
        router_cascade_plan,
        router_get_stats,
        router_export_report,
        router_reset_all,
    ]
