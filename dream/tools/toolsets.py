"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
    "research": Toolset(
        name="research",
        description=(
            "Autonomous multi-step deep research, evidence collection, "
            "and multi-source intelligence synthesis"
        ),
        tools=(
            "research_plan_investigation",
            "research_add_source",
            "research_synthesize_report",
            "research_run_autonomous",
            "research_export_report",
            "research_get_status",
            "research_list_sessions",
        ),
    ),
    "cache": Toolset(
        name="cache",
        description=(
            "Semantic caching, speculative pre-fetching, and token economics optimization"
        ),
        tools=(
            "cache_lookup_query",
            "cache_store_entry",
            "cache_predict_tool",
            "cache_get_economics",
            "cache_clear",
            "cache_warmup",
        ),
    ),
    "sandbox": Toolset(
        name="sandbox",
        description=(
            "Isolated Python code execution, dataset analysis, and REPL interpreter"
        ),
        tools=(
            "sandbox_execute_python",
            "sandbox_analyze_dataset",
            "sandbox_reset_session",
            "sandbox_list_artifacts",
            "sandbox_get_status",
        ),
    ),
    "canvas": Toolset(
        name="canvas",
        description=(
            "Interactive visual artifacts, diagrams, standalone previews, and versioning"
        ),
        tools=(
            "canvas_create_artifact",
            "canvas_update_artifact",
            "canvas_get_artifact",
            "canvas_list_artifacts",
            "canvas_diff_versions",
            "canvas_render_preview",
            "canvas_export_bundle",
            "canvas_reset_session",
            "canvas_get_status",
        ),
    ),
    "debate": Toolset(
        name="debate",
        description=(
            "Multi-agent debate rounds, Delphi consensus evaluation, and fact verification"
        ),
        tools=(
            "debate_create_session",
            "debate_add_turn",
            "debate_run_autonomous",
            "debate_verify_statement",
            "debate_reach_consensus",
            "debate_list_sessions",
            "debate_reset_all",
        ),
    ),
    "reasoning": Toolset(
        name="reasoning",
        description=(
            "Tree-of-Thought exploration, strategy branching, and metacognitive self-evaluation"
        ),
        tools=(
            "reasoning_create_thought_tree",
            "reasoning_expand_node",
            "reasoning_evaluate_node",
            "reasoning_solve_goal",
            "reasoning_get_best_path",
            "reasoning_get_status",
            "reasoning_reset_all",
        ),
    ),
    "healing": Toolset(
        name="healing",
        description=(
            "Autonomous error diagnosis, self-healing recovery, telemetry, and chaos testing"
        ),
        tools=(
            "healing_diagnose_failure",
            "healing_run_chaos_test",
            "telemetry_get_health_metrics",
            "telemetry_export_report",
            "telemetry_export_spans",
            "telemetry_reset_all",
        ),
    ),
    "router": Toolset(
        name="router",
        description=(
            "Adaptive semantic routing, prompt compilation, and cascading execution"
        ),
        tools=(
            "router_evaluate_query",
            "router_compile_prompt",
            "router_cascade_plan",
            "router_get_stats",
            "router_export_report",
            "router_reset_all",
        ),
    ),
    "consolidation": Toolset(
        name="consolidation",
        description=(
            "Autonomous sleep-phase memory consolidation, Ebbinghaus decay, "
            "entropy pruning, and contradiction resolution"
        ),
        tools=(
            "consolidation_add_memory",
            "consolidation_run_cycle",
            "consolidation_distill_session",
            "consolidation_get_stats",
            "consolidation_export_report",
            "consolidation_reset_all",
        ),
    ),
    "isolation": Toolset(
        name="isolation",
        description=(
            "Kernel-level micro-isolation, Seccomp syscall filtering, and WASM virtualization"
        ),
        tools=(
            "sandbox_isolate_execute",
            "sandbox_wasm_execute",
            "sandbox_get_isolation_status",
            "sandbox_export_security_report",
            "sandbox_reset_isolation",
        ),
    ),
    "migration": Toolset(
        name="migration",
        description=(
            "Universal migration toolkit from Hermes Agent, OpenClaw, and markdown workspaces"
        ),
        tools=(
            "migration_analyze_source",
            "migration_execute",
            "migration_get_status",
            "migration_export_report",
            "migration_reset",
        ),
    ),
    "evals": Toolset(
        name="evals",
        description=(
            "Comprehensive agent benchmarking, tool calling accuracy, and Persian fluency evals"
        ),
        tools=(
            "evals_run_suite",
            "evals_list_suites",
            "evals_compare_baseline",
            "evals_export_report",
            "evals_get_status",
            "evals_reset",
        ),
    ),
    "evolution": Toolset(
        name="evolution",
        description=(
            "Autonomous self-evolution, heuristic policy distillation, and strategy Elo arena"
        ),
        tools=(
            "evolution_distill_heuristics",
            "evolution_run_tournament",
            "evolution_get_leaderboard",
            "evolution_export_policy",
            "evolution_get_status",
            "evolution_reset",
        ),
    ),
    "workflow": Toolset(
        name="workflow",
        description=(
            "Long-horizon workflow orchestration, persistent saga state machine, and auto-rollback"
        ),
        tools=(
            "workflow_create_plan",
            "workflow_execute_step",
            "workflow_approve_step",
            "workflow_rollback",
            "workflow_get_status",
            "workflow_export_diagram",
            "workflow_reset",
        ),
    ),
    "refactor": Toolset(
        name="refactor",
        description=(
            "Code intelligence, AST structural symbol indexing, and deterministic patch synthesis"
        ),
        tools=(
            "refactor_index_symbols",
            "refactor_find_symbol",
            "refactor_generate_patch",
            "refactor_apply_patch",
            "refactor_rollback_patch",
            "refactor_get_status",
            "refactor_reset",
        ),
    ),
    "duplex": Toolset(
        name="duplex",
        description=(
            "Real-time bi-directional streaming audio duplex agent, VAD, and barge-in interruption"
        ),
        tools=(
            "duplex_start_session",
            "duplex_push_audio_frame",
            "duplex_inject_interruption",
            "duplex_get_session_metrics",
            "duplex_export_transcript",
            "duplex_reset_session",
        ),
    ),
    "rbac": Toolset(
        name="rbac",
        description=(
            "Enterprise multi-tenant role-based access control, token quotas, and audit logging"
        ),
        tools=(
            "rbac_create_tenant",
            "rbac_create_user",
            "rbac_verify_access",
            "rbac_record_usage",
            "rbac_get_quota_status",
            "rbac_export_audit_log",
        ),
    ),
    "reactive": Toolset(
        name="reactive",
        description=(
            "Autonomous event-driven reactive engine, pub-sub event bus, and webhook verification"
        ),
        tools=(
            "reactive_register_rule",
            "reactive_ingest_event",
            "reactive_verify_webhook",
            "reactive_list_rules",
            "reactive_get_metrics",
        ),
    ),
    "dashboard": Toolset(
        name="dashboard",
        description=(
            "Unified web dashboard, real-time agent control tower, and visual metrics studio"
        ),
        tools=(
            "dashboard_get_overview",
            "dashboard_get_subsystem_telemetry",
            "dashboard_render_html",
            "dashboard_export_metrics",
            "dashboard_get_alerts",
        ),
    ),
    "vision": Toolset(
        name="vision",
        description=(
            "Multi-modal vision perception, video stream decomposition, and UI element grounding"
        ),
        tools=(
            "vision_analyze_image",
            "vision_decompose_video",
            "vision_ground_ui_elements",
            "vision_inspect_diagram",
            "vision_diff_visual_states",
        ),
    ),
    "federation": Toolset(
        name="federation",
        description=(
            "Multi-agent neural mesh federation, epidemic gossip, and distributed consensus"
        ),
        tools=(
            "federation_register_peer",
            "federation_broadcast_gossip",
            "federation_delegate_task",
            "federation_get_topology",
            "federation_trigger_election",
        ),
    ),
    "synthetic": Toolset(
        name="synthetic",
        description=(
            "Autonomous synthetic dataset generation, DPO preference distillation, and curation"
        ),
        tools=(
            "synthetic_generate_samples",
            "synthetic_curate_and_filter",
            "synthetic_export_dataset",
            "synthetic_get_batch_status",
        ),
    ),
    "kernel": Toolset(
        name="kernel",
        description=(
            "Dream kernel lifecycle management, lazy loading registry, and runtime hot reload"
        ),
        tools=(
            "kernel_get_status",
            "kernel_trigger_hot_reload",
            "kernel_list_subsystems",
            "kernel_get_memory_profile",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        names = source.keys()
        allowed_names.update(names)

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
