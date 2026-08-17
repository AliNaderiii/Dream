"""G5 — every chart type renders to non-empty files under the size quota."""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("matplotlib")

from dream.skills.data_science import CHART_QUOTA_BYTES, DataScienceError  # noqa: E402
from tests._data_science_helpers import load_sales, make_runtime  # noqa: E402


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("charts")
    runtime = make_runtime(tmp_path)
    dataset_id = load_sales(runtime, tmp_path)
    return runtime, dataset_id


SPECS = [
    {"type": "line", "x": "invoice_date", "y": "price"},
    {"type": "bar", "x": "region", "y": "price"},
    {"type": "scatter", "x": "price", "y": "quantity"},
    {"type": "histogram", "x": "price"},
    {"type": "box", "x": "region", "y": "price"},
    {"type": "heatmap"},
    {"type": "pie", "x": "region"},
    {"type": "area", "x": "invoice_date", "y": "quantity"},
    {"type": "bubble", "x": "price", "y": "quantity", "size_by": "quantity"},
]


@pytest.mark.parametrize("spec", SPECS, ids=[s["type"] for s in SPECS])
def test_every_chart_type_renders_all_formats(env, spec):
    runtime, dataset_id = env
    result = runtime.create_chart({**spec, "dataset_id": dataset_id})
    assert set(result["files"]) == {"png", "svg", "pdf", "html"}
    from pathlib import Path

    for ext, path in result["files"].items():
        size = Path(path).stat().st_size
        assert size > 0, f"{spec['type']}.{ext} is empty"
        assert size <= CHART_QUOTA_BYTES, f"{spec['type']}.{ext} exceeds quota"
    assert result["chart_id"] in result["files"]["png"]


def test_chart_html_embeds_plotly_payload(env):
    runtime, dataset_id = env
    result = runtime.create_chart(
        {"type": "bar", "x": "region", "y": "price", "dataset_id": dataset_id}
    )
    from pathlib import Path

    html = Path(result["files"]["html"]).read_text(encoding="utf-8")
    assert "Plotly.newPlot" in html
    assert '"type": "bar"' in html


def test_chart_theme_and_custom_palette(env):
    runtime, dataset_id = env
    result = runtime.create_chart(
        {
            "type": "bar",
            "x": "region",
            "y": "price",
            "dataset_id": dataset_id,
            "theme": "dark",
            "palette": "custom",
            "colors": ["#FF0000", "#00FF00", "#0000FF"],
            "title": "Revenue by region",
        }
    )
    assert result["spec"]["theme"] == "dark"
    assert result["spec"]["colors"] == ["#FF0000", "#00FF00", "#0000FF"]


def test_unknown_style_falls_back_gracefully(env):
    # 'seaborn' maps to the seaborn-v0_8 style; if the matplotlib build lacks
    # it, the script falls back to default rather than crashing.
    runtime, dataset_id = env
    result = runtime.create_chart(
        {"type": "histogram", "x": "price", "dataset_id": dataset_id, "theme": "seaborn"}
    )
    assert result["sizes"]["png"] > 0


def test_chart_rejects_dataset_escape(env):
    runtime, _ = env
    with pytest.raises(DataScienceError):
        runtime.create_chart({"type": "bar", "x": "region", "y": "price",
                              "dataset_id": "../../../etc"})


def test_chart_rejects_absent_column(env):
    runtime, dataset_id = env
    with pytest.raises(DataScienceError, match="not in the dataset schema"):
        runtime.create_chart({"type": "bar", "x": "ghost", "y": "price",
                              "dataset_id": dataset_id})


def test_auto_chart_returns_ranked_specs(env):
    runtime, dataset_id = env
    out = runtime.auto_chart(dataset_id, max_charts=5)
    charts = out["charts"]
    assert 1 <= len(charts) <= 5
    scores = [c["score"] for c in charts]
    assert scores == sorted(scores, reverse=True)
    for chart in charts:
        assert chart["dataset_id"] == dataset_id
        assert chart["type"] in {
            "line", "bar", "scatter", "histogram", "box", "heatmap", "pie", "area", "bubble",
        }


def test_auto_chart_suggestions_are_renderable(env):
    runtime, dataset_id = env
    top = runtime.auto_chart(dataset_id, max_charts=1)["charts"][0]
    spec = {k: v for k, v in top.items() if k not in ("score", "reason")}
    result = runtime.create_chart(spec)
    assert result["sizes"]["png"] > 0
