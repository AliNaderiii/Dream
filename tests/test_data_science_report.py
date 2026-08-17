"""G6 — report generation: extractable PDF, <= 5 pages, markdown twin."""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("matplotlib")
pypdf = pytest.importorskip("pypdf")

from dream.skills.data_science import REPORT_SECTIONS, DataScienceError  # noqa: E402
from tests._data_science_helpers import load_sales, make_runtime  # noqa: E402


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("report")
    runtime = make_runtime(tmp_path)
    dataset_id = load_sales(runtime, tmp_path)
    # A couple of charts so the report embeds them.
    runtime.create_chart({"type": "bar", "x": "region", "y": "price",
                          "dataset_id": dataset_id})
    runtime.create_chart({"type": "histogram", "x": "price",
                          "dataset_id": dataset_id})
    result = runtime.generate_report(dataset_id, "Sales 2024 Annual Review")
    return runtime, dataset_id, result


def test_report_pdf_exists_with_size(env):
    _, _, result = env
    from pathlib import Path

    path = Path(result["pdf_path"])
    assert path.exists()
    assert result["size_bytes"] == path.stat().st_size > 0


def test_report_title_is_extractable(env):
    _, _, result = env
    reader = pypdf.PdfReader(result["pdf_path"])
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "Sales 2024 Annual Review" in text


def test_report_is_at_most_five_pages(env):
    _, _, result = env
    reader = pypdf.PdfReader(result["pdf_path"])
    assert 1 <= len(reader.pages) <= 5


def test_report_contains_section_headings(env):
    _, _, result = env
    reader = pypdf.PdfReader(result["pdf_path"])
    text = "".join(page.extract_text() or "" for page in reader.pages)
    for heading in ("Abstract", "Data Summary", "Conclusion"):
        assert heading in text


def test_report_embeds_charts(env):
    _, _, result = env
    assert result["charts_embedded"] == 2


def test_report_markdown_twin(env):
    runtime, dataset_id, result = env
    from pathlib import Path

    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert markdown.startswith("# Sales 2024 Annual Review")
    assert "## Charts" in markdown
    assert runtime.read_markdown_report(dataset_id) == markdown


def test_report_custom_sections(env):
    runtime, dataset_id, _ = env
    result = runtime.generate_report(
        dataset_id, "Short Brief", sections=["abstract", "conclusion"]
    )
    assert result["sections"] == ["abstract", "conclusion"]
    reader = pypdf.PdfReader(result["pdf_path"])
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "Short Brief" in text


def test_report_validates_inputs(env):
    runtime, dataset_id, _ = env
    with pytest.raises(DataScienceError, match="title"):
        runtime.generate_report(dataset_id, "  ")
    with pytest.raises(DataScienceError, match="unknown section"):
        runtime.generate_report(dataset_id, "T", sections=["appendix_of_doom"])
    assert len(REPORT_SECTIONS) == 7


def test_report_references_carry_dois(env):
    runtime, dataset_id, _ = env
    markdown = runtime.read_markdown_report(dataset_id)
    # DOI resolution is best-effort/offline: the references section carries
    # the canonical DOIs as text without any network call.
    result = runtime.generate_report(dataset_id, "Ref Check", sections=["references"])
    md = runtime.read_markdown_report(dataset_id)
    assert "doi:" in md
    del markdown, result
