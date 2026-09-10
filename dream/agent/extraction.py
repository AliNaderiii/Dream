"""Background extraction outcome, log/metric recording, and safe message coercion.

The :class:`_ExtractionOutcome` is the carrier between the worker thread
that runs the extraction pass and the turn that reads its result. The
helper functions :func:`_record_extraction_status` and
:func:`_record_store_failure` are the *only* places that increment the
extraction-related metrics and emit the structured logs, so a pass is
never double-counted and a log never carries unsafe metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dream.agent.constants import _LOG_MESSAGE_LIMIT, log
from dream.agent.logging_utils import (
    _EXTRACTION_STATUS_METRIC,
    _EXTRACTION_WARNING_STATUSES,
)
from dream.extraction import (
    STATUS_ABANDONED,
    STATUS_DISABLED,
    STATUS_ERROR,
    STATUS_FACTS_FOUND,
    STATUS_NO_FACTS,
    STATUS_TOO_SHORT,
    STATUS_UNPARSEABLE,
    ExtractionResult,
)
from dream.metrics import (
    METRIC_EXTRACTION_ABANDONED,
    METRIC_EXTRACTION_ERROR,
    METRIC_EXTRACTION_NO_FACTS,
    METRIC_EXTRACTION_PARSE_ERROR,
    METRIC_EXTRACTION_SKIPPED,
    METRIC_EXTRACTION_STORE_ERROR,
    METRIC_EXTRACTION_SUCCESS,
    metrics,
)


def _safe_log_message(raw: str) -> str:
    """Collapse whitespace and truncate an error message for logging.

    Log records and ExtractionResult.raw_text must never carry the full
    extraction prompt, raw model output, user content, credentials, or
    filesystem paths. A whitespace-collapsed, length-capped message keeps
    the diagnostic readable without echoing anything verbose or sensitive
    verbatim.

    Also masks token-like patterns (8+ chars of alphanumerics, hyphens,
    underscores) with ``***`` so API keys and bearer tokens in exception
    messages are not exposed verbatim.
    """
    collapsed = " ".join(raw.split())

    # Mask token-like patterns: 8+ chars of alphanumerics, hyphens, underscores
    collapsed = re.sub(r"[A-Za-z0-9_-]{8,}", "***", collapsed)

    if len(collapsed) <= _LOG_MESSAGE_LIMIT:
        return collapsed
    return collapsed[:_LOG_MESSAGE_LIMIT] + "..."


def _record_extraction_status(result: ExtractionResult) -> None:
    """Increment the metric and emit the log for one finalized extraction pass.

    Called exactly once per turn from the single place that finalizes the turn's
    extraction result (successful completion, abandoned, or a synthetic error),
    so a pass is never double-counted. Only safe metadata is logged.
    """
    metric = _EXTRACTION_STATUS_METRIC.get(result.status)
    if metric is not None:
        metrics.incr(metric)
    if result.status in _EXTRACTION_WARNING_STATUSES:
        log.warning(
            "extraction pass failed",
            extra={"extraction_status": result.status},
        )
    else:
        log.debug(
            "extraction pass completed",
            extra={"extraction_status": result.status, "facts": len(result.facts)},
        )


def _record_store_failure(errors: list[str], exc: Exception) -> None:
    """Record one persistence failure during extraction, visibly and safely.

    Appends a diagnostic for the CLI (as before), increments the store-error
    metric, and emits a redacted warning. Storage failures are never silent,
    but the pass status itself stays ``facts_found`` — extraction succeeded and
    only the write to durable memory failed.
    """
    errors.append(f"{type(exc).__name__}: {exc}")
    metrics.incr(METRIC_EXTRACTION_STORE_ERROR)
    log.warning(
        "extraction store failure",
        extra={
            "extraction_status": "store_error",
            "exception_type": type(exc).__name__,
            "error": _safe_log_message(str(exc)),
        },
    )


@dataclass(slots=True)
class _ExtractionOutcome:
    """Carries the extraction pass result out of its worker thread.

    The worker writes these fields and the turn reads them after the join
    returns, so the happens-before edge of the join makes the read safe.
    """

    result: ExtractionResult | None = None
    errors: list[str] = field(default_factory=list)


__all__ = [
    "METRIC_EXTRACTION_ABANDONED",
    "METRIC_EXTRACTION_ERROR",
    "METRIC_EXTRACTION_NO_FACTS",
    "METRIC_EXTRACTION_PARSE_ERROR",
    "METRIC_EXTRACTION_SKIPPED",
    "METRIC_EXTRACTION_STORE_ERROR",
    "METRIC_EXTRACTION_SUCCESS",
    "STATUS_ABANDONED",
    "STATUS_DISABLED",
    "STATUS_ERROR",
    "STATUS_FACTS_FOUND",
    "STATUS_NO_FACTS",
    "STATUS_TOO_SHORT",
    "STATUS_UNPARSEABLE",
    "_ExtractionOutcome",
    "_EXTRACTION_STATUS_METRIC",
    "_EXTRACTION_WARNING_STATUSES",
    "_record_extraction_status",
    "_record_store_failure",
    "_safe_log_message",
    "metrics",
]
