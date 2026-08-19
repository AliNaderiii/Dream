"""M23 Defect One — the settings example may only name variables the code reads.

Evidence justifying these tests:
- The shipped example documented provider variable names the code never looks
  at. With the documented names the key arrives empty and the request goes to
  the default vendor host, producing an authorisation failure that names the
  wrong service. The defect is in the repository, not in the owner's setup.
- This module reads the settings example file, extracts every variable name
  (including commented-out example lines, which are exactly the lines a person
  uncomments), and asserts each one appears in product source that reads
  settings via ``os.environ``.

The scan covers every product ``*.py`` in the repository (root modules,
``dream/``, ``tools/``) and deliberately excludes ``tests/`` and ``conftest``:
a test setting a variable is not the code reading it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"

# An assignment line: NAME=value, optionally commented out with '#'.
_NAME_LINE = re.compile(r"^\s*(?:#\s*)?([A-Z][A-Z0-9_]*)=")
# A read: os.environ.get("NAME" ... or os.environ["NAME"].
_ENV_READ = re.compile(
    r"os\.environ\s*(?:\.\s*get\s*\(|\[\s*)\s*[\"']([A-Z][A-Z0-9_]*)[\"']"
)


def example_variable_names(example_text: str) -> list[str]:
    """Every variable assignment in the example file, commented out or not."""
    names = []
    for raw in example_text.splitlines():
        match = _NAME_LINE.match(raw)
        if match:
            names.append(match.group(1))
    return names


def names_read_by_code() -> set[str]:
    """Every variable name product code reads from the environment."""
    read: set[str] = set()
    for path in sorted(ROOT.rglob("*.py")):
        parts = path.parts
        if ".venv" in parts or "tests" in parts or path.name == "conftest.py":
            continue
        source = path.read_text(encoding="utf-8")
        read.update(_ENV_READ.findall(source))
    return read


def unknown_example_names(example_text: str, read_names: set[str]) -> list[str]:
    """Names documented in the example but never read by product code."""
    return sorted(set(example_variable_names(example_text)) - read_names)


def test_extraction_finds_active_and_commented_assignments():
    text = (
        "DREAM_BACKEND=echo\n"
        "# DREAM_MODEL=x\n"
        "# a prose comment that is not an assignment\n"
        "\n"
        "DREAM_DB=data/x.db\n"
        "# --- section header, also not an assignment ---\n"
    )
    assert example_variable_names(text) == ["DREAM_BACKEND", "DREAM_MODEL", "DREAM_DB"]


def test_read_scan_finds_known_product_variables():
    # Self-defence: the scan must see the names the code provably reads today.
    read = names_read_by_code()
    for known in (
        "DREAM_BACKEND",
        "DREAM_TEMPERATURE",
        "DREAM_DB",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "DREAM_MODEL",
        "OLLAMA_HOST",
        "AVALAI_API_KEY",
    ):
        assert known in read, f"code reads {known} but the scan missed it"


def test_example_only_names_variables_the_code_reads():
    read = names_read_by_code()
    unknown = unknown_example_names(EXAMPLE.read_text(encoding="utf-8"), read)
    assert unknown == [], (
        ".env.example documents variables the code never reads: "
        f"{unknown}. Every name in the example must be a name the code reads."
    )


def test_example_still_documents_backend_selection_and_db():
    # The fix must repair names, not delete the file's purpose.
    names = example_variable_names(EXAMPLE.read_text(encoding="utf-8"))
    assert "DREAM_BACKEND" in names
    assert "DREAM_DB" in names


def test_synthetic_unknown_name_is_flagged():
    # Break pin: a name the code never reads must be caught by the check.
    read = names_read_by_code()
    bogus = "# DREAM_NOT_A_REAL_VARIABLE=1\n"
    assert unknown_example_names(bogus, read) == ["DREAM_NOT_A_REAL_VARIABLE"]
