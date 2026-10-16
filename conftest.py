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
