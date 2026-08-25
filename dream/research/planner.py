"""Study planning: topic + sources → research questions, hypotheses, outline.

The planner asks the configured backend for one JSON object and reads it with
the tolerant parser. Two properties matter more than the plan's prose:

* **it always returns a plan.** A refusing, offline, or JSON-mangling backend
  degrades to :func:`fallback_plan`, a deterministic outline derived from the
  discovered schema. EchoBackend therefore produces a real, runnable plan and
  the whole engine stays testable offline.
* **it is bounded.** Section count, question count, and every string are
  clamped before they enter the session, so a runaway generation cannot blow
  up the state file or the report.

:func:`ask_json` is the shared model-call helper used by every LLM step in the
engine: one call, hard timeout, tolerant parse, no retry storm.
"""

from __future__ import annotations

import concurrent.futures
import logging
from typing import Any

from dream.research.errors import ResearchError
from dream.research.prompts import planner_prompt
from dream.research.schemas import (
    MAX_QUESTIONS,
    Plan,
    Section,
    clamp_text,
    new_id,
    parse_json_object,
)

logger = logging.getLogger("dream.research.planner")

__all__ = ["ask_json", "build_plan", "fallback_plan"]

_MODEL_TIMEOUT = 120.0

#: After this many consecutive timeouts the backend is considered unreachable
#: and the engine stops calling it for the rest of the process, running the
#: deterministic path instead. Without this, a wedged provider would cost one
#: full step timeout at *every* step of *every* section.
_TIMEOUT_CIRCUIT = 2
_consecutive_timeouts = 0


def reset_circuit() -> None:
    """Re-arm the provider circuit breaker (tests, and provider re-config)."""
    global _consecutive_timeouts
    _consecutive_timeouts = 0


def ask_json(
    backend: Any,
    prompt: str,
    *,
    system: str = "You are a precise research assistant. Reply with one JSON object.",
    timeout: float = _MODEL_TIMEOUT,
) -> dict[str, Any]:
    """One bounded model call that yields a dict (possibly empty).

    Never raises: a provider error, a timeout, or unparseable output all come
    back as ``{}`` and the caller degrades deterministically. That is what
    keeps a research run from hanging on a flaky provider.
    """
    global _consecutive_timeouts
    if backend is None:
        return {}
    if _consecutive_timeouts >= _TIMEOUT_CIRCUIT:
        return {}
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    # The pool is *not* used as a context manager on purpose: exiting one waits
    # for the worker, which would re-introduce exactly the hang the timeout
    # exists to prevent. A wedged provider thread is abandoned instead.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(backend.chat, messages, None)
        reply = future.result(timeout=timeout)
        _consecutive_timeouts = 0
    except concurrent.futures.TimeoutError:
        _consecutive_timeouts += 1
        future.cancel()
        if _consecutive_timeouts >= _TIMEOUT_CIRCUIT:
            logger.warning(
                "the model timed out %d times in a row; the research engine will "
                "run its deterministic path from here",
                _consecutive_timeouts,
            )
        else:
            logger.warning("model call exceeded %.0fs; degrading to the offline path", timeout)
        return {}
    except Exception as exc:
        logger.warning("model call failed (%s); degrading to the offline path", type(exc).__name__)
        return {}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if isinstance(reply, dict):
        content = reply.get("content")
    else:  # a backend that returns a bare string
        content = reply
    return parse_json_object(content)


def _titles_from_sources(sources: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Deterministic section seeds from what the data actually contains."""
    seeds: list[tuple[str, str]] = [
        ("Data quality and coverage",
         "Establish how complete and trustworthy the available data is before "
         "any claim is drawn from it."),
    ]
    for source in sources[:4]:
        if not source.get("dataset_id"):
            continue
        columns = ", ".join(str(c) for c in (source.get("columns") or [])[:6])
        seeds.append(
            (
                f"Findings from {source.get('name', 'the dataset')}",
                f"Characterise the measures in this source ({columns}) and the "
                "relationships between them.",
            )
        )
    seeds.append(
        ("Anomalies and drivers",
         "Surface spikes, drops, and outliers, and identify what plausibly "
         "drives them."),
    )
    return seeds


def fallback_plan(
    topic: str,
    sources: list[dict[str, Any]],
    *,
    max_sections: int = 6,
) -> Plan:
    """A deterministic plan derived from the discovered schema.

    Used when no model is available or the model's reply is unusable. It is a
    genuine plan — every section is answerable from a registered dataset —
    not a placeholder.
    """
    usable = [s for s in sources if s.get("dataset_id")]
    questions = [
        f"What does the available data show about: {clamp_text(topic, 300)}?",
        "How complete and reliable are the source tables?",
        "Which measures move together, and which stand out as anomalous?",
    ]
    sections = [
        Section(section_id=new_id(), title=title, thesis=thesis, questions=questions[:2])
        for title, thesis in _titles_from_sources(usable)[:max_sections]
    ]
    return Plan(
        objective=clamp_text(topic, 1000),
        questions=questions,
        hypotheses=[
            "The dataset's numeric measures contain at least one relationship "
            "strong enough to report.",
        ],
        methodology=(
            "Each source is ingested through Dream's dataset registry, profiled "
            "in the sandbox, cleaned only where an executed statistic justifies "
            "it, then analysed with descriptive statistics, correlation, and "
            "regression. Every number in the report is produced by an executed "
            "step and checked by the proofreader before publication."
        ),
        sections=sections,
        datasets=[s["dataset_id"] for s in usable],
        source="fallback",
    )


def build_plan(
    backend: Any,
    topic: str,
    sources: list[dict[str, Any]],
    *,
    language: str = "en",
    max_sections: int = 6,
    methodology_doc: str = "",
    timeout: float = _MODEL_TIMEOUT,
) -> Plan:
    """Produce a bounded, dataset-grounded study plan."""
    if not isinstance(topic, str) or not topic.strip():
        raise ResearchError("topic must be a non-empty string")
    usable = [s for s in sources if s.get("dataset_id")]
    if not usable:
        raise ResearchError("no usable data sources were discovered for this topic")

    if backend is None:
        plan = fallback_plan(topic, usable, max_sections=max_sections)
        plan.datasets = [s["dataset_id"] for s in usable]
        return plan

    raw = ask_json(
        backend,
        planner_prompt(
            topic,
            usable,
            language=language,
            max_sections=max_sections,
            methodology_doc=methodology_doc,
        ),
        timeout=timeout,
    )
    sections_raw = raw.get("sections")
    if not isinstance(sections_raw, list) or not sections_raw:
        plan = fallback_plan(topic, usable, max_sections=max_sections)
        plan.datasets = [s["dataset_id"] for s in usable]
        return plan

    sections: list[Section] = []
    for entry in sections_raw[:max_sections]:
        if not isinstance(entry, dict):
            continue
        title = clamp_text(entry.get("title"), 160)
        if not title:
            continue
        sections.append(
            Section(
                section_id=new_id(),
                title=title,
                thesis=clamp_text(entry.get("thesis"), 600),
                questions=[
                    clamp_text(q, 300) for q in (entry.get("questions") or [])[:MAX_QUESTIONS]
                ],
            )
        )
    if not sections:
        return fallback_plan(topic, usable, max_sections=max_sections)

    return Plan(
        objective=clamp_text(raw.get("objective") or topic, 1000),
        questions=[clamp_text(q, 300) for q in (raw.get("questions") or [])[:MAX_QUESTIONS]]
        or [clamp_text(topic, 300)],
        hypotheses=[clamp_text(h, 300) for h in (raw.get("hypotheses") or [])[:MAX_QUESTIONS]],
        methodology=clamp_text(raw.get("methodology"), 2000)
        or fallback_plan(topic, usable).methodology,
        sections=sections,
        datasets=[s["dataset_id"] for s in usable],
        source="model",
    )
