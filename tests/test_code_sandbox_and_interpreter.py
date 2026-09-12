"""Unit and integration tests for Code Interpreter, Dataset Analysis & Sandbox."""

from __future__ import annotations

import tempfile

import pytest

from dream.sandbox import (
    DataScienceAnalyzer,
    ExecutionStatus,
    SandboxEngine,
    SandboxExecutor,
    handle_sandbox_slash_command,
    reset_global_sandbox_engine,
    sandbox_analyze_dataset,
    sandbox_execute_python,
    sandbox_get_status,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_sandbox_engine() -> None:
    reset_global_sandbox_engine()
    yield
    reset_global_sandbox_engine()


def test_toolset_includes_sandbox() -> None:
    """Verify sandbox toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("sandbox")
    assert ts is not None
    assert "sandbox_execute_python" in ts.tools
    assert "sandbox_analyze_dataset" in ts.tools
    assert "sandbox_reset_session" in ts.tools
    assert "sandbox" in BUILTIN_TOOLSETS


def test_sandbox_executor_stateful_execution() -> None:
    """Verify execution of expressions, statements, and stateful namespace across turns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = SandboxExecutor(workspace_dir=tmpdir)

        # Turn 1: Define variables
        res1 = executor.execute_python("x = 50\ny = 25\nz = x + y")
        assert res1.status == ExecutionStatus.SUCCESS
        assert res1.exit_code == 0
        assert "z" in res1.variables_updated

        # Turn 2: Reference previously defined variable and evaluate expression
        res2 = executor.execute_python("z * 2")
        assert res2.status == ExecutionStatus.SUCCESS
        assert "150" in res2.stdout.strip()

        # Turn 3: Reset namespace
        executor.reset_namespace()
        res3 = executor.execute_python("z")
        assert res3.status == ExecutionStatus.ERROR
        assert "NameError" in res3.error_message


def test_sandbox_executor_security_blocking() -> None:
    """Verify interception and blocking of destructive host commands."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = SandboxExecutor(workspace_dir=tmpdir)

        # Test rm -rf / blocking
        res_rm = executor.execute_python("import os; os.system('rm -rf /')")
        assert res_rm.status == ExecutionStatus.BLOCKED
        assert res_rm.exit_code == 1

        # Test sensitive path blocking
        res_pass = executor.execute_python("f = open('/etc/passwd')")
        assert res_pass.status == ExecutionStatus.BLOCKED


def test_data_science_analyzer_tabular_profiling() -> None:
    """Verify automated statistical profiling and Markdown table generation."""
    analyzer = DataScienceAnalyzer()

    csv_data = """product,sales,quantity,active
Widget A,120.50,10,true
Widget B,240.00,20,true
Widget C,95.25,5,false
Widget D,,15,true
"""
    summary = analyzer.analyze_tabular_data(csv_data)
    assert summary.total_rows == 4
    assert summary.total_columns == 4
    assert "sales" in summary.column_names
    assert summary.null_counts["sales"] == 1
    assert summary.column_types["quantity"] == "integer"
    assert summary.numeric_stats["quantity"]["mean"] == 12.5
    assert summary.numeric_stats["quantity"]["min"] == 5.0
    assert summary.numeric_stats["quantity"]["max"] == 20.0

    md_report = analyzer.format_summary_markdown(summary)
    assert "Dataset Profile" in md_report
    assert "Widget A" in md_report or "quantity" in md_report


def test_sandbox_engine_and_artifact_generation() -> None:
    """Verify end-to-end sandbox engine and workspace file discovery."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = SandboxExecutor(workspace_dir=tmpdir)
        engine = SandboxEngine(executor=executor)

        # Script that writes a local file in workspace using injected workspace_dir
        code = """
from pathlib import Path
out = Path(workspace_dir) / 'results.txt'
out.write_text('Simulation Complete: 100% accuracy', encoding='utf-8')
"""
        res = engine.run_code(code)
        assert res.status == ExecutionStatus.SUCCESS
        assert len(res.artifacts) >= 1
        assert res.artifacts[0].name == "results.txt"

        status = engine.get_status()
        assert status["total_executions"] == 1
        assert status["total_artifacts"] == 1


def test_sandbox_tools_and_slash_commands() -> None:
    """Verify LLM tool wrappers and /code, /data, /sandbox slash commands."""
    # Tool: execute python
    res_py = sandbox_execute_python("math.sqrt(144)")
    assert res_py["success"] is True
    assert "12.0" in res_py["result"]["stdout"]

    # Tool: analyze dataset
    json_data = '[{"name": "Ali", "score": 98}, {"name": "Sara", "score": 92}]'
    res_data = sandbox_analyze_dataset(json_data)
    assert res_data["success"] is True
    assert res_data["summary"]["total_rows"] == 2

    # Tool: get status
    res_st = sandbox_get_status()
    assert res_st["success"] is True
    assert res_st["total_executions"] >= 1

    # Slash: /code
    slash_code = handle_sandbox_slash_command("/code print('Hello Dream Sandbox')")
    assert "Hello Dream Sandbox" in slash_code

    # Slash: /data
    slash_data = handle_sandbox_slash_command(f"/data {json_data}")
    assert "Dataset Profile" in slash_data

    # Slash: /sandbox status
    slash_status = handle_sandbox_slash_command("/sandbox status")
    assert "وضعیت سندباکس" in slash_status

    # Slash: /sandbox reset
    slash_reset = handle_sandbox_slash_command("/sandbox reset")
    assert "بازنشانی شد" in slash_reset
