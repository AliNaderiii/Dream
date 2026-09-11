"""Comprehensive test suite for Trajectory Recording, Dataset Distillation, and Evals."""

from __future__ import annotations

import json

from dream.agent import Dream, EchoBackend
from dream.distill import (
    AutonomousEvaluator,
    DatasetDistiller,
    DistillFormat,
    EvalTestCase,
    TrajectoryRecorder,
    distill_export_dataset,
    distill_record_trajectory,
    eval_run_benchmark,
    get_distill_tools,
    handle_distill_command,
    handle_eval_command,
    reset_global_distill_state,
    sanitize_trace_text,
)
from dream.memory import MemoryStore
from dream.tools.toolsets import get_toolset


def test_trajectory_recorder_lifecycle_and_scoring(tmp_path):
    """Verify trajectory recording, step tracking, error penalties, and quality scoring."""
    db_file = str(tmp_path / "distill.db")
    with TrajectoryRecorder(db_path=db_file) as recorder:
        sid = recorder.start_trajectory(
            task_prompt="How do I calculate taxes in Iran?",
            tags=["tax", "iran"],
        )
        assert sid.startswith("traj_")

        recorder.add_step(
            session_id=sid,
            role="assistant",
            thought="I should invoke the tax calculation skill",
            tool_name="iran_tax_calc",
            tool_args={"amount": 10000000},
            tool_result='{"status": "ok", "tax": 0}',
        )

        trace = recorder.complete_trajectory(
            session_id=sid,
            final_answer="The tax amount is 0 Rials due to legal exemption.",
            success=True,
            user_rating=5.0,
        )
        assert trace is not None
        assert trace.quality_score >= 0.95

        # List trajectories
        saved = recorder.list_trajectories(min_quality=0.8)
        assert len(saved) == 1
        assert saved[0].session_id == sid
        assert saved[0].tags == ["tax", "iran"]


def test_dataset_distiller_formats_and_sanitization(tmp_path):
    """Verify export to OpenAI, ShareGPT, ChatML, and Alpaca formats with secret redaction."""
    dummy_key = "sk-" + "samplekeyfortest" * 2
    dummy_bearer = "Bearer " + "secrettokenfortest" * 2
    with TrajectoryRecorder() as recorder:
        sid = recorder.start_trajectory(
            task_prompt=f"My secret key is {dummy_key}"
        )
        recorder.add_step(
            session_id=sid,
            role="assistant",
            content=f"Received token {dummy_bearer}",
        )
        trace = recorder.complete_trajectory(
            session_id=sid,
            final_answer="Done processing.",
            success=True,
        )
        assert trace is not None

        # Sanitize check
        redacted = sanitize_trace_text(f"API: {dummy_key}")
        assert "[REDACTED_API_KEY]" in redacted

        # Export OpenAI
        out_openai = tmp_path / "dataset.jsonl"
        res_openai = DatasetDistiller.export_to_file([trace], out_openai, DistillFormat.OPENAI)
        assert res_openai["success"] is True
        assert "[REDACTED_API_KEY]" in out_openai.read_text(encoding="utf-8")

        # Export ShareGPT
        out_sharegpt = tmp_path / "sharegpt.json"
        res_sharegpt = DatasetDistiller.export_to_file(
            [trace], out_sharegpt, DistillFormat.SHAREGPT
        )
        assert res_sharegpt["success"] is True

        # Export ChatML
        out_chatml = tmp_path / "chatml.txt"
        res_chatml = DatasetDistiller.export_to_file([trace], out_chatml, DistillFormat.CHATML)
        assert res_chatml["success"] is True
        assert "<|im_start|>" in out_chatml.read_text(encoding="utf-8")

        # Export Alpaca
        out_alpaca = tmp_path / "alpaca.json"
        res_alpaca = DatasetDistiller.export_to_file([trace], out_alpaca, DistillFormat.ALPACA)
        assert res_alpaca["success"] is True


def test_autonomous_evaluator_benchmark_execution():
    """Verify evaluation battery running against agent and aggregating diagnostics."""
    test_suite = [
        EvalTestCase(
            case_id="echo_test_1",
            category="echo",
            prompt="Hello Echo",
            expected_keywords=["Echo:"],
        ),
        EvalTestCase(
            case_id="echo_test_2",
            category="echo",
            prompt="Another test",
            expected_keywords=["Echo:"],
        ),
    ]

    evaluator = AutonomousEvaluator(test_suite)
    with MemoryStore(":memory:") as store:
        dream = Dream(store, EchoBackend())
        report = evaluator.evaluate(dream)

    assert report.total_tests == 2
    assert report.passed_count == 2
    assert report.pass_rate == 1.0
    assert "echo" in report.category_breakdown


def test_distill_tools_and_slash_commands(tmp_path):
    """Verify LLM agent tools and slash command dispatchers."""
    try:
        # Tool: distill_record_trajectory
        rec_json = distill_record_trajectory(
            task_prompt="Test task",
            final_answer="Test answer",
            quality_score=0.9,
        )
        parsed_rec = json.loads(rec_json)
        assert parsed_rec["status"] == "ok"

        # Tool: distill_export_dataset
        out_file = str(tmp_path / "export_tools.jsonl")
        export_json = distill_export_dataset(output_path=out_file, export_format="openai")
        parsed_exp = json.loads(export_json)
        assert parsed_exp["success"] is True

        # Tool: eval_run_benchmark
        eval_json = eval_run_benchmark()
        parsed_eval = json.loads(eval_json)
        assert parsed_eval["status"] == "ok"

        # Tool registry
        tools_dict = get_distill_tools()
        assert "distill_record_trajectory" in tools_dict
        assert "distill_export_dataset" in tools_dict
        assert "eval_run_benchmark" in tools_dict

        # Slash commands
        out: list[str] = []
        handle_distill_command("/distill stats", output=out.append)
        assert any("Dataset Distillation Engine" in line for line in out)

        out.clear()
        handle_eval_command("/eval run", output=out.append)
        assert any("Benchmark Evaluation Report" in line for line in out)
    finally:
        reset_global_distill_state()


def test_toolsets_includes_distill():
    """Verify distill toolset grouping in BUILTIN_TOOLSETS."""
    distill_ts = get_toolset("distill")
    assert distill_ts is not None
    assert "distill_record_trajectory" in distill_ts.tools
    assert "distill_export_dataset" in distill_ts.tools
    assert "eval_run_benchmark" in distill_ts.tools
