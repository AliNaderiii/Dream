"""Persian PDF report builder (v4.6).

Renders structured report content into a real PDF file with correct Persian
typography: joined glyphs and bidi via HarfBuzz text shaping (fpdf2 +
uharfbuzz) and the bundled Vazirmatn font (SIL OFL 1.1 — see fonts/OFL.txt).

Report model (all strings UTF-8, Persian or otherwise)::

    {
      "title": str,                  # 1..200 chars
      "subtitle": str,               # optional, <= 300 chars
      "sections": [                  # 0..50 items
        {
          "heading": str,            # 1..200 chars
          "paragraphs": [str],       # optional, <= 20 items, each <= 4000
          "kpis": [{"label": str, "value": str}],   # optional, <= 12
          "table": {"columns": [str], "rows": [[str]]},  # optional
        },
      ],
    }

Tables are rendered right-to-left: the column and row cell orders are
reversed so the first column appears on the right, matching Persian reading
direction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_REGULAR = FONT_DIR / "Vazirmatn-Regular.ttf"
FONT_BOLD = FONT_DIR / "Vazirmatn-Bold.ttf"

BOLD_FACE = FontFace(emphasis="BOLD")

MAX_TITLE = 200
MAX_SUBTITLE = 300
MAX_SECTIONS = 50
MAX_PARAGRAPHS = 20
MAX_PARAGRAPH = 4_000
MAX_KPIS = 12
MAX_KPI_TEXT = 200
MAX_COLUMNS = 8
MAX_ROWS = 200
MAX_CELL = 500


class ReportError(ValueError):
    """Raised when the report model is invalid or fonts are unavailable."""


def _string(value: Any, name: str, *, limit: int, required: bool = False) -> str:
    if value is None:
        if required:
            raise ReportError(f"{name} must be a non-empty string")
        return ""
    if not isinstance(value, str):
        raise ReportError(f"{name} must be a string")
    if len(value) > limit:
        raise ReportError(f"{name} must be at most {limit} characters")
    if required and not value.strip():
        raise ReportError(f"{name} must be a non-empty string")
    return value


def validate_report(report: Any) -> dict[str, Any]:
    """Validate and normalise the report model. Raises :class:`ReportError`."""
    if not isinstance(report, dict):
        raise ReportError("report must be an object")
    title = _string(report.get("title"), "title", limit=MAX_TITLE, required=True)
    subtitle = _string(report.get("subtitle"), "subtitle", limit=MAX_SUBTITLE)
    raw_sections = report.get("sections", [])
    if raw_sections is None:
        raw_sections = []
    if not isinstance(raw_sections, list) or len(raw_sections) > MAX_SECTIONS:
        raise ReportError(f"sections must be a list of at most {MAX_SECTIONS} items")
    sections: list[dict[str, Any]] = []
    for index, section in enumerate(raw_sections):
        if not isinstance(section, dict):
            raise ReportError(f"sections[{index}] must be an object")
        heading = _string(
            section.get("heading"), f"sections[{index}].heading", limit=MAX_TITLE, required=True
        )
        paragraphs_raw = section.get("paragraphs") or []
        if not isinstance(paragraphs_raw, list) or len(paragraphs_raw) > MAX_PARAGRAPHS:
            raise ReportError(
                f"sections[{index}].paragraphs must be a list of at most {MAX_PARAGRAPHS} items"
            )
        paragraphs = [
            _string(p, f"sections[{index}].paragraphs[{j}]", limit=MAX_PARAGRAPH)
            for j, p in enumerate(paragraphs_raw)
        ]
        kpis_raw = section.get("kpis") or []
        if not isinstance(kpis_raw, list) or len(kpis_raw) > MAX_KPIS:
            raise ReportError(
                f"sections[{index}].kpis must be a list of at most {MAX_KPIS} items"
            )
        kpis: list[dict[str, str]] = []
        for k, kpi in enumerate(kpis_raw):
            if not isinstance(kpi, dict):
                raise ReportError(f"sections[{index}].kpis[{k}] must be an object")
            kpis.append(
                {
                    "label": _string(
                        kpi.get("label"),
                        f"sections[{index}].kpis[{k}].label",
                        limit=MAX_KPI_TEXT,
                        required=True,
                    ),
                    "value": _string(
                        kpi.get("value"),
                        f"sections[{index}].kpis[{k}].value",
                        limit=MAX_KPI_TEXT,
                    ),
                }
            )
        table_raw = section.get("table")
        table = None
        if table_raw is not None:
            if not isinstance(table_raw, dict):
                raise ReportError(f"sections[{index}].table must be an object")
            columns_raw = table_raw.get("columns")
            if not isinstance(columns_raw, list) or not 1 <= len(columns_raw) <= MAX_COLUMNS:
                raise ReportError(
                    f"sections[{index}].table.columns must be a list of 1..{MAX_COLUMNS} items"
                )
            columns = [
                _string(c, f"sections[{index}].table.columns[{j}]", limit=MAX_CELL, required=True)
                for j, c in enumerate(columns_raw)
            ]
            rows_raw = table_raw.get("rows") or []
            if not isinstance(rows_raw, list) or len(rows_raw) > MAX_ROWS:
                raise ReportError(
                    f"sections[{index}].table.rows must be a list of at most {MAX_ROWS} rows"
                )
            rows: list[list[str]] = []
            for r, row in enumerate(rows_raw):
                if not isinstance(row, list) or len(row) != len(columns):
                    raise ReportError(
                        f"sections[{index}].table.rows[{r}] must have {len(columns)} cells"
                    )
                rows.append(
                    [
                        _string(
                            cell,
                            f"sections[{index}].table.rows[{r}][{c}]",
                            limit=MAX_CELL,
                        )
                        for c, cell in enumerate(row)
                    ]
                )
            table = {"columns": columns, "rows": rows}
        sections.append(
            {
                "heading": heading,
                "paragraphs": paragraphs,
                "kpis": kpis,
                "table": table,
            }
        )
    return {"title": title, "subtitle": subtitle, "sections": sections}


class _ReportPDF(FPDF):
    """A4 portrait report with a page-number footer in Persian."""

    def footer(self) -> None:
        self.set_y(-15)
        self.set_x(self.l_margin)
        self.set_font("Vazirmatn", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"صفحه {self.page_no()} از {{nb}}", align="C")
        self.set_text_color(0, 0, 0)


def _rtl_multicell(
    pdf: _ReportPDF,
    text: str,
    *,
    size: int,
    bold: bool = False,
    align: str = "R",
    color: tuple[int, int, int] = (0, 0, 0),
    line_height: float | None = None,
) -> None:
    """Render one RTL text block. Resets x first: with RTL shaping fpdf2
    leaves the cursor at the right edge after each cell, which would starve
    the next zero-width cell of horizontal space."""
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Vazirmatn", "B" if bold else "", size=size)
    pdf.set_text_color(*color)
    height = line_height if line_height is not None else size * 0.55
    pdf.multi_cell(0, height, text, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)


def build_report_pdf(report: dict[str, Any], output_path: str) -> dict[str, Any]:
    """Validate *report*, render it to a Persian PDF at *output_path*.

    Returns ``{"file_path", "pages", "size_bytes"}``. Raises
    :class:`ReportError` on invalid input and ``OSError`` on write failures.
    """
    if not isinstance(output_path, str) or not output_path.strip():
        raise ReportError("output_path must be a non-empty string")
    if not FONT_REGULAR.is_file() or not FONT_BOLD.is_file():
        raise ReportError("Vazirmatn font files are missing from the package")

    model = validate_report(report)

    pdf = _ReportPDF(format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("Vazirmatn", "", str(FONT_REGULAR))
    pdf.add_font("Vazirmatn", "B", str(FONT_BOLD))
    # Persian typography: HarfBuzz shaping with explicit RTL/Arabic script run
    # direction — joined letterforms and correct bidi inside every cell.
    pdf.set_text_shaping(use_shaping_engine=True, direction="rtl", script="arab", language="fa")
    pdf.set_margins(left=12, top=14, right=12)
    pdf.add_page()

    _rtl_multicell(pdf, model["title"], size=18, bold=True, align="C")
    if model["subtitle"]:
        _rtl_multicell(pdf, model["subtitle"], size=10, align="C", color=(110, 110, 110))
    pdf.ln(4)

    for section in model["sections"]:
        _rtl_multicell(pdf, section["heading"], size=13, bold=True)
        for paragraph in section["paragraphs"]:
            _rtl_multicell(pdf, paragraph, size=11, line_height=7.5)
        if section["kpis"]:
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Vazirmatn", size=10)
            with pdf.table(
                col_widths=(pdf.epw * 0.35, pdf.epw * 0.65),
                text_align=("R", "R"),
                line_height=7,
                padding=1.5,
            ) as table:
                for kpi in section["kpis"]:
                    row = table.row()
                    row.cell(kpi["label"], style=BOLD_FACE)
                    row.cell(kpi["value"])
        if section["table"]:
            columns = section["table"]["columns"]
            rows = section["table"]["rows"]
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Vazirmatn", size=10)
            column_width = pdf.epw / len(columns)
            with pdf.table(
                col_widths=tuple(column_width for _ in columns),
                text_align=("R",) * len(columns),
                line_height=7,
                padding=1.5,
            ) as table:
                head = table.row()
                for column in reversed(columns):
                    head.cell(column, style=BOLD_FACE)
                for row in rows:
                    cells = table.row()
                    for cell in reversed(row):
                        cells.cell(cell)
        pdf.ln(4)

    pdf.output(output_path)
    return {
        "file_path": str(Path(output_path)),
        "pages": pdf.page,
        "size_bytes": Path(output_path).stat().st_size,
    }
