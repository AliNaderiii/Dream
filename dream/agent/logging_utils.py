"""Extraction-status metric map and WARNING-level status set.

Kept as a leaf module so backends and prompt strings can be imported
without dragging the metrics singleton along. The two maps here are
the only places that translate an extraction status string into a
metric name and a log level.
"""

from __future__ import annotations

from dream.extraction import (
    STATUS_ABANDONED,
    STATUS_DISABLED,
    STATUS_ERROR,
    STATUS_FACTS_FOUND,
    STATUS_NO_FACTS,
    STATUS_TOO_SHORT,
    STATUS_UNPARSEABLE,
)
from dream.metrics import (
    METRIC_EXTRACTION_ABANDONED,
    METRIC_EXTRACTION_ERROR,
    METRIC_EXTRACTION_NO_FACTS,
    METRIC_EXTRACTION_PARSE_ERROR,
    METRIC_EXTRACTION_SKIPPED,
    METRIC_EXTRACTION_SUCCESS,
)

# Extraction-pass status -> metric name. Every completed pass increments
# exactly one of these from the single call site that finalizes a turn's
# extraction result, so a pass is never double-counted across the background
# worker and the turn that waits on it. ``store_error`` is intentionally absent
# here: storage failures are recorded per fact-write inside the worker against
# ``METRIC_EXTRACTION_STORE_ERROR`` while the pass status stays ``facts_found``
# (extraction itself succeeded; the CLI still surfaces the lost writes).
_EXTRACTION_STATUS_METRIC: dict[str, str] = {
    STATUS_FACTS_FOUND: METRIC_EXTRACTION_SUCCESS,
    STATUS_NO_FACTS: METRIC_EXTRACTION_NO_FACTS,
    STATUS_DISABLED: METRIC_EXTRACTION_SKIPPED,
    STATUS_TOO_SHORT: METRIC_EXTRACTION_SKIPPED,
    STATUS_UNPARSEABLE: METRIC_EXTRACTION_PARSE_ERROR,
    STATUS_ERROR: METRIC_EXTRACTION_ERROR,
    STATUS_ABANDONED: METRIC_EXTRACTION_ABANDONED,
}

# Which extraction statuses are worth a WARNING-level record. Benign or
# expected outcomes (facts found, none found, disabled, too short) stay quiet
# at DEBUG so the default WARNING root level does not spam a terminal.
_EXTRACTION_WARNING_STATUSES: frozenset[str] = frozenset(
    {STATUS_UNPARSEABLE, STATUS_ERROR, STATUS_ABANDONED}
)
