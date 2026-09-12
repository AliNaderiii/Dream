"""Adaptive Semantic Router, Dynamic Prompt Compiler, and Model Cascading Engine Subsystem."""

from __future__ import annotations

from dream.router.backend import (
    AVAL_BASE_URLS,
    OFFICIAL_BASE_URLS,
    Route,
    _AVAL,
    _BYOK,
    _ECHO,
    _HOSTED,
    _OLLAMA,
    _ROUTE_BACKEND,
    build_router_backend,
    resolve_route,
    route_text,
)
from dream.router.cascade import ModelCascader
from dream.router.compiler import PromptCompiler
from dream.router.engine import RoutingEngine
from dream.router.semantic import SemanticRouter
from dream.router.slash import handle_router_slash_command
from dream.router.tools import (
    get_global_routing_engine,
    get_router_tools,
    reset_global_routing_engine,
    router_cascade_plan,
    router_compile_prompt,
    router_evaluate_query,
    router_export_report,
    router_get_stats,
    router_reset_all,
)
from dream.router.types import (
    CompiledPrompt,
    IntentComplexity,
    ModelTier,
    PromptSection,
    RouterStats,
    RoutingDecision,
)

# Auto-register router toolset
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="router",
            description="Adaptive semantic routing, prompt compilation, and cascading execution.",
            tools=[
                "router_evaluate_query",
                "router_compile_prompt",
                "router_cascade_plan",
                "router_get_stats",
                "router_export_report",
                "router_reset_all",
            ],
            metadata={"category": "router", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "AVAL_BASE_URLS",
    "CompiledPrompt",
    "IntentComplexity",
    "ModelCascader",
    "ModelTier",
    "OFFICIAL_BASE_URLS",
    "PromptCompiler",
    "PromptSection",
    "Route",
    "RouterStats",
    "RoutingDecision",
    "RoutingEngine",
    "SemanticRouter",
    "_AVAL",
    "_BYOK",
    "_ECHO",
    "_HOSTED",
    "_OLLAMA",
    "_ROUTE_BACKEND",
    "build_router_backend",
    "get_global_routing_engine",
    "get_router_tools",
    "handle_router_slash_command",
    "reset_global_routing_engine",
    "resolve_route",
    "route_text",
    "router_cascade_plan",
    "router_compile_prompt",
    "router_evaluate_query",
    "router_export_report",
    "router_get_stats",
    "router_reset_all",
]
