from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dream.bridge import methods_dataqa
from dream.bridge.errors import INVALID_PARAMS, BridgeError
from dream.dataqa import service as service_module
from dream.dataqa.discovery import discover
from dream.dataqa.models import ExecutionResult
from dream.dataqa.service import DataQAError, DataQAService


def _runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[DataQAService, Path]:
    monkeypatch.setenv("DREAM_WORKSPACE_ROOT", str(tmp_path))
    source = tmp_path / "sales-by-region.csv"
    source.write_text(
        "region,revenue,notes\nNorth,10,ok\nNorth,30,ok\nSouth,20,ok\nSouth,40,ok\n",
        encoding="utf-8",
    )
    return DataQAService(), source


def test_average_by_region_has_evidence_and_validated_chart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, source = _runtime(tmp_path, monkeypatch)
    session = runtime.create_session(source=source.name, query="sales region")
    final = runtime.ask(session["session_id"], "What is the average revenue by region?")[
        "final_answer"
    ]
    assert final["status"] == "ok"
    assert final["evidence"]["rows"] == [
        {"region": "South", "mean_revenue": 30.0},
        {"region": "North", "mean_revenue": 20.0},
    ]
    assert final["chart"]["validated"] is True
    assert final["sandbox"]["network_enabled"] is False
    assert "groupby" in final["generated_code"]
    assert (
        "svg" not in runtime.get_session(session["session_id"])["turns"][0]["final_answer"]["chart"]
    )
    assert runtime.chart(session["session_id"])["chart"]["svg"].startswith("<svg")

    persian = runtime.ask(session["session_id"], "میانگین درآمد به تفکیک منطقه چقدر است؟")[
        "final_answer"
    ]
    assert persian["evidence"]["rows"] == final["evidence"]["rows"]
    assert persian["answer"].startswith("میانگین")


def test_folder_discovery_ranks_relevant_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DREAM_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "unrelated.csv").write_text("planet,mass\nEarth,1\n", encoding="utf-8")
    wanted = tmp_path / "regional-revenue.csv"
    wanted.write_text("region,revenue\nNorth,2\n", encoding="utf-8")
    matches = discover("revenue by region", ".")
    assert Path(matches[0].path) == wanted
    assert matches[0].reasons


def test_persian_semantic_schema_ranking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DREAM_WORKSPACE_ROOT", str(tmp_path))
    wanted = tmp_path / "generic.csv"
    wanted.write_text("region,revenue\nNorth,2\n", encoding="utf-8")
    (tmp_path / "فروش-نامرتبط.csv").write_text("planet,mass\nEarth,1\n", encoding="utf-8")

    result = DataQAService().discover("درآمد به تفکیک منطقه", ".")
    assert result["candidates"][0]["relative_path"] == wanted.name
    assert any("schema matches" in reason for reason in result["candidates"][0]["reasons"])


def test_follow_up_state_and_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, source = _runtime(tmp_path, monkeypatch)
    session_id = runtime.create_session(source=source.name)["session_id"]
    runtime.ask(session_id, "average revenue by region")
    follow_up = runtime.ask(session_id, "What about North?")["final_answer"]
    assert follow_up["status"] == "ok"
    assert follow_up["evidence"]["rows"] == [{"region": "North", "mean_revenue": 20.0}]
    assert runtime.reset(session_id)["reset"] is True
    after_reset = runtime.ask(session_id, "What about North?")["final_answer"]
    assert after_reset["status"] == "insufficient_data"


def test_working_dataframe_filter_composes_until_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, source = _runtime(tmp_path, monkeypatch)
    session_id = runtime.create_session(source=source.name)["session_id"]
    runtime.ask(session_id, "Show North only")
    filtered = runtime.ask(session_id, "average revenue")["final_answer"]
    assert filtered["evidence"]["rows"] == [{"mean_revenue": 20.0}]

    runtime.reset(session_id)
    unfiltered = runtime.ask(session_id, "average revenue")["final_answer"]
    assert unfiltered["evidence"]["rows"] == [{"mean_revenue": 25.0}]


def test_missing_group_is_honest_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, source = _runtime(tmp_path, monkeypatch)
    session_id = runtime.create_session(source=source.name)["session_id"]
    final = runtime.ask(session_id, "average revenue by country")["final_answer"]
    assert final["status"] == "insufficient_data"
    assert "can't determine" in final["answer"]
    assert final["evidence"]["rows"] == []


def test_workspace_confinement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DREAM_WORKSPACE_ROOT", str(tmp_path))
    with pytest.raises(DataQAError, match="workspace"):
        DataQAService().discover("secrets", "/etc/passwd")


def test_bridge_streams_final_answer_and_maps_invalid_params(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, source = _runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(methods_dataqa, "_service", runtime)
    session = methods_dataqa.sessions_create({"source": source.name})

    async def collect() -> tuple[str, dict[str, object]]:
        stream = await methods_dataqa.dataqa_ask(
            {
                "session_id": session["session_id"],
                "question": "average revenue by region",
            }
        )
        chunks = [chunk["token"] async for chunk in stream.chunks]
        return "".join(chunks), stream.final

    streamed, final = asyncio.run(collect())
    assert streamed == final["final_answer"]["answer"]
    assert final["final_answer"]["status"] == "ok"

    with pytest.raises(BridgeError) as raised:
        methods_dataqa.dataqa_discover({"source": "bad\x00path"})
    assert raised.value.code == INVALID_PARAMS


def test_execution_error_is_regrounded_and_retried_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, source = _runtime(tmp_path, monkeypatch)
    session_id = runtime.create_session(source=source.name)["session_id"]
    real_execute = service_module.execute_plan
    calls = 0

    def transient_failure(*args: object, **kwargs: object) -> ExecutionResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ExecutionResult(
                status="error",
                answer_shape="scalar",
                columns=[],
                rows=[],
                rows_considered=0,
                operation="worker",
                error="transient parser failure",
            )
        return real_execute(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service_module, "execute_plan", transient_failure)
    final = runtime.ask(session_id, "average revenue")["final_answer"]
    assert final["status"] == "ok"
    assert calls == 2
    assert "retried once" in final["warnings"][0]


def test_cancelled_execution_preserves_cancelled_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, source = _runtime(tmp_path, monkeypatch)
    session_id = runtime.create_session(source=source.name)["session_id"]

    def cancelled(*args: object, **kwargs: object) -> ExecutionResult:
        return ExecutionResult(
            status="cancelled",
            answer_shape="scalar",
            columns=[],
            rows=[],
            rows_considered=0,
            operation="aggregate",
            error="deadline exceeded",
            warnings=["The operation exceeded its deadline and was terminated."],
        )

    monkeypatch.setattr(service_module, "execute_plan", cancelled)
    final = runtime.ask(session_id, "average revenue")["final_answer"]
    assert final["status"] == "cancelled"
    assert "terminated" in final["warnings"][0]


def test_explicit_chart_breadth_is_grounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DREAM_WORKSPACE_ROOT", str(tmp_path))
    source = tmp_path / "metrics.csv"
    source.write_text(
        "date,revenue,cost\n2024-01-01,-10,3\n2024-02-01,0,2\n2024-03-01,20,6\n2024-04-01,40,9\n",
        encoding="utf-8",
    )
    runtime = DataQAService()
    session_id = runtime.create_session(source=source.name)["session_id"]
    questions = {
        "average revenue by date": "line",
        "histogram distribution of revenue": "histogram",
        "box plot distribution of revenue": "box",
        "relationship between revenue and cost": "scatter",
        "correlation between revenue and cost": "heatmap",
    }
    for question, chart_type in questions.items():
        final = runtime.ask(session_id, question)["final_answer"]
        assert final["status"] == "ok"
        assert final["chart"]["type"] == chart_type
        assert final["chart"]["validated"] is True
        assert "<script" not in final["chart"]["svg"]
