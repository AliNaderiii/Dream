"""Pytest bootstrap: put the repository root on sys.path.

The package exposes ``cli``, ``doctor``, and ``dream`` via the editable
install, but the committed diagnostics live in ``tools/`` and are importable
only from a source checkout.
"""

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# --------------------------------------------------------------------------- #
# TEMPORARY diagnostic (to be removed): surface pytest failures as GitHub
# annotations so the failing test ids are readable through the checks API.
# --------------------------------------------------------------------------- #
def pytest_runtest_logreport(report) -> None:  # noqa: ANN001
    import os

    if os.environ.get("GITHUB_ACTIONS") != "true" or not report.failed:
        return
    text = (report.longreprtext or "").strip().splitlines()
    detail = text[-1] if text else "failed"
    detail = detail.replace("\r", " ").replace("\n", " ").replace("%", "%25")[:900]
    sys.__stdout__.write(f"::error::PROBE {report.nodeid} :: {detail}\n")
    sys.__stdout__.flush()


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001
    import os

    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    sys.__stdout__.write(f"::error::PROBE session_finished exitstatus={exitstatus}\n")
    sys.__stdout__.flush()
