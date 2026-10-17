"""Tests for the code-interpreter subsystem — now a fail-closed shell.

MASTER-P0 rewrote this file. It used to assert that ``SandboxExecutor``
``eval``/``exec``'d a program on the host: stateful variables between runs, a
workspace file written by ``open()``, a regex blocklist catching ``rm -rf /``.
Every one of those assertions described the vulnerability, so they are gone.

What remains true and is asserted here:

* the dataset profiler still works — it parses data, it does not execute it;
* ``/data`` and ``/sandbox status|reset`` still answer;
* every ``/code``-shaped entry point now reports ``unavailable`` instead of
  running anything on the host.

The container path is covered by ``tests/test_code_execution_contract.py``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

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
    """The toolset entry is metadata; the tool is *not* in the model registry.

    ``filter_tools`` intersects toolset names with ``dream.tools.base.REGISTRY``,
    so declaring the name here cannot hand a host interpreter to the model.
    """
    ts = get_toolset("sandbox")
    assert ts is not None
    assert "sandbox_execute_python" in ts.tools
    assert "sandbox_reset_session" in ts.tools
    assert "sandbox" in BUILTIN_TOOLSETS

    from dream.tools.base import REGISTRY

    assert "sandbox_execute_python" not in REGISTRY


def test_executor_refuses_host_execution() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = SandboxExecutor(workspace_dir=tmpdir)
        result = executor.execute_python("x = 50\ny = 25\nz = x + y\nprint(z)")

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.exit_code == -1
    assert result.stdout == ""
    assert result.variables_updated == []
    assert "no longer runs code on the host" in result.stderr


def test_executor_refuses_even_a_benign_expression() -> None:
    """No payload is privileged: there is no "safe" subset that runs."""
    executor = SandboxExecutor(workspace_dir="/tmp/dream-p0-refusal")
    for code in ("2 + 2", "math.sqrt(144)", "print('hello')", "import os"):
        result = executor.execute_python(code)
        assert result.status is ExecutionStatus.UNAVAILABLE
        assert result.stdout == ""


def test_the_old_blocklist_is_only_a_classifier_now() -> None:
    executor = SandboxExecutor(workspace_dir="/tmp/dream-p0-classify")
    flagged, pattern = executor.classify("import os; os.system('rm -rf /')")
    assert flagged is True
    assert pattern

    clean, _ = executor.classify("total = sum(range(10))")
    assert clean is False

    # Classification is not execution: nothing ran, and no result is "success".
    assert executor.execute_python("print('x')").status is ExecutionStatus.UNAVAILABLE


def test_data_science_analyzer_tabular_profiling() -> None:
    """Parsing data is not executing it — this surface is unchanged."""
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

    md_report = analyzer.format_summary_markdown(summary)
    assert "Dataset Profile" in md_report


def test_engine_records_the_refusal_and_reports_status() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = SandboxEngine(executor=SandboxExecutor(workspace_dir=tmpdir))
        result = engine.run_code("open('results.txt', 'w').write('nope')")

        assert result.status is ExecutionStatus.UNAVAILABLE
        # Nothing was written, because nothing ran.
        assert not (Path(tmpdir) / "results.txt").exists()

        status = engine.get_status()
        assert status["total_executions"] == 1
        assert status["total_artifacts"] == 0
        assert status["last_execution_status"] == "unavailable"


def test_sandbox_tools_fail_closed_but_analysis_still_works() -> None:
    res_py = sandbox_execute_python("math.sqrt(144)")
    assert res_py["success"] is False
    assert res_py["available"] is False
    assert res_py["result"]["status"] == "unavailable"

    # Dataset analysis is pure parsing: it still returns a real answer.
    json_data = '[{"name": "Ali", "score": 98}, {"name": "Sara", "score": 92}]'
    res_data = sandbox_analyze_dataset(json_data)
    assert res_data["success"] is True
    assert res_data["summary"]["total_rows"] == 2

    res_st = sandbox_get_status()
    assert res_st["success"] is True
    assert res_st["total_executions"] >= 1


def test_slash_commands_report_the_truth() -> None:
    json_data = '[{"name": "Ali", "score": 98}]'

    slash_code = handle_sandbox_slash_command("/code print('Hello Dream Sandbox')")
    assert "Hello Dream Sandbox" not in slash_code
    assert "fail-closed" in slash_code

    slash_data = handle_sandbox_slash_command(f"/data {json_data}")
    assert "Dataset Profile" in slash_data

    slash_status = handle_sandbox_slash_command("/sandbox status")
    assert "وضعیت سندباکس" in slash_status

    slash_reset = handle_sandbox_slash_command("/sandbox reset")
    assert "بازنشانی شد" in slash_reset


def test_no_execution_primitive_remains_in_the_executor_module() -> None:
    import ast

    path = Path(__file__).resolve().parent.parent / "dream" / "sandbox" / "executor.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = {
        getattr(node.func, "id", None)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not ({"eval", "exec", "compile"} & calls)
