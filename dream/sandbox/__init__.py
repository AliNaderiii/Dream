"""Isolated Code Interpreter, Data Science Profiler, and Execution Sandbox Subsystem."""

from __future__ import annotations

from dream.sandbox.analyzer import DataScienceAnalyzer
from dream.sandbox.engine import SandboxEngine
from dream.sandbox.executor import SandboxExecutor
from dream.sandbox.slash import handle_sandbox_slash_command
from dream.sandbox.tools import (
    get_global_sandbox_engine,
    get_sandbox_tools,
    reset_global_sandbox_engine,
    sandbox_analyze_dataset,
    sandbox_execute_python,
    sandbox_get_status,
    sandbox_list_artifacts,
    sandbox_reset_session,
)
from dream.sandbox.types import (
    DatasetSummary,
    ExecutionArtifact,
    ExecutionLanguage,
    ExecutionResult,
    ExecutionStatus,
)

# Register toolset if toolset registry is present
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="sandbox",
            description="Isolated Python code execution, dataset analysis, and REPL interpreter.",
            tools=[
                "sandbox_execute_python",
                "sandbox_analyze_dataset",
                "sandbox_reset_session",
                "sandbox_list_artifacts",
                "sandbox_get_status",
            ],
            metadata={"category": "sandbox", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "DataScienceAnalyzer",
    "DatasetSummary",
    "ExecutionArtifact",
    "ExecutionLanguage",
    "ExecutionResult",
    "ExecutionStatus",
    "SandboxEngine",
    "SandboxExecutor",
    "get_global_sandbox_engine",
    "get_sandbox_tools",
    "handle_sandbox_slash_command",
    "reset_global_sandbox_engine",
    "sandbox_analyze_dataset",
    "sandbox_execute_python",
    "sandbox_get_status",
    "sandbox_list_artifacts",
    "sandbox_reset_session",
]
