"""Tests for the Persian PDF report bridge (``pdf.export_report``)."""

from __future__ import annotations

import asyncio

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.extensions import Registry
from dream.bridge.methods_pdf import HANDLERS, pdf_export_report
from dream.reporting.pdf import ReportError, build_report_pdf, validate_report

SAMPLE_REPORT = {
    "title": "گزارش داده کسب‌وکار — دریم",
    "subtitle": "تولیدشده توسط موتور گزارش هسته دریم",
    "sections": [
        {
            "heading": "خلاصه مدیریتی",
            "paragraphs": ["درآمد کل با رشد ۱۲ درصدی همراه بوده است."],
            "kpis": [
                {"label": "درآمد کل", "value": "۴٫۸ میلیارد تومان"},
                {"label": "حاشیه سود", "value": "۲۳٪"},
            ],
        },
        {
            "heading": "درآمد به تفکیک ناحیه",
            "table": {
                "columns": ["ناحیه", "درآمد (میلیون تومان)"],
                "rows": [["شمال", "۱۲۰"], ["جنوب", "۸۰"]],
            },
        },
    ],
}


def test_pdf_bridge_extension_discovery():
    """pdf.export_report must be auto-registered in the Bridge Registry."""
    handlers = Registry.publish({})
    assert "pdf.export_report" in handlers
    assert handlers["pdf.export_report"] is HANDLERS["pdf.export_report"]


def test_pdf_export_rejects_invalid_params(tmp_path):
    """Structural param errors raise BridgeError before any file is touched."""
    with pytest.raises(BridgeError):
        asyncio.run(pdf_export_report({}))  # missing report
    with pytest.raises(BridgeError):
        asyncio.run(pdf_export_report({"report": "not-an-object"}))
    with pytest.raises(BridgeError):
        asyncio.run(pdf_export_report({"report": SAMPLE_REPORT}))  # no output_path
    with pytest.raises(BridgeError):
        asyncio.run(
            pdf_export_report({"report": SAMPLE_REPORT, "output_path": "report.txt"})
        )  # not .pdf
    with pytest.raises(BridgeError):
        asyncio.run(
            pdf_export_report({"report": SAMPLE_REPORT, "output_path": "\\\\server\\share\\x.pdf"})
        )  # sensitive / network path
    with pytest.raises(BridgeError):
        asyncio.run(
            pdf_export_report(
                {"report": {"sections": []}, "output_path": str(tmp_path / "x.pdf")}
            )
        )  # missing title


def test_pdf_export_writes_a_real_shaped_pdf(tmp_path):
    """A valid report produces a %PDF file with the Vazirmatn subset embedded."""
    target = tmp_path / "report.pdf"

    async def _test():
        return await pdf_export_report(
            {"report": SAMPLE_REPORT, "output_path": str(target)}
        )

    res = asyncio.run(_test())
    assert res["success"] is True
    assert res["pages"] >= 1
    assert res["size_bytes"] > 1_000
    raw = target.read_bytes()
    assert raw[:4] == b"%PDF"
    assert b"/FontFile2" in raw  # the Vazirmatn subset is embedded


def test_pdf_export_creates_missing_parent_dirs(tmp_path):
    """The output directory is created on demand."""
    target = tmp_path / "reports" / "nested" / "report.pdf"

    async def _test():
        return await pdf_export_report(
            {"report": SAMPLE_REPORT, "output_path": str(target)}
        )

    res = asyncio.run(_test())
    assert res["success"] is True
    assert target.is_file()


def test_pdf_export_multi_page_with_tables(tmp_path):
    """Long reports paginate with footers instead of failing."""
    rows = [[f"ردیف {r}", str(r * 100)] for r in range(60)]
    report = {
        "title": "گزارش بلند",
        "sections": [
            {
                "heading": "جزئیات",
                "table": {"columns": ["شرح", "مقدار"], "rows": rows},
            }
        ],
    }
    target = tmp_path / "long.pdf"
    res = asyncio.run(pdf_export_report({"report": report, "output_path": str(target)}))
    assert res["success"] is True
    assert res["pages"] >= 2


def test_report_model_validation_limits():
    """The report model enforces its documented limits."""
    with pytest.raises(ReportError):
        validate_report({"title": ""})
    with pytest.raises(ReportError):
        validate_report({"title": "x", "sections": [{"heading": "h", "paragraphs": ["a"] * 21}]})
    with pytest.raises(ReportError):
        validate_report(
            {
                "title": "x",
                "sections": [
                    {"heading": "h", "table": {"columns": ["a"], "rows": [["1", "2"]]}}
                ],
            }
        )  # row width mismatch
    normalised = validate_report({"title": " گزارش ", "sections": []})
    assert normalised["title"] == " گزارش "  # content preserved verbatim
    with pytest.raises(ReportError):
        build_report_pdf({"title": "x"}, "")  # empty output path
