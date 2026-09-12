"""Study planning: topic + sources -> research questions, hypotheses, outline."""

from __future__ import annotations

import concurrent.futures
import logging
import re
import uuid
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
from dream.research.types import ResearchPlan, ResearchStatus

logger = logging.getLogger("dream.research.planner")

__all__ = [
    "ResearchPlanner",
    "ask_json",
    "build_plan",
    "fallback_plan",
    "reset_circuit",
]

_MODEL_TIMEOUT = 120.0
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
    """One bounded model call that yields a dict (possibly empty)."""
    global _consecutive_timeouts
    if backend is None:
        return {}
    if _consecutive_timeouts >= _TIMEOUT_CIRCUIT:
        return {}
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
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
    else:
        content = reply
    return parse_json_object(content)


def _titles_from_sources(sources: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Deterministic section seeds from what the data actually contains."""
    seeds: list[tuple[str, str]] = [
        (
            "Data quality and coverage",
            "Establish how complete and trustworthy the available data is before "
            "any claim is drawn from it.",
        ),
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
        (
            "Anomalies and drivers",
            "Surface spikes, drops, and outliers, and identify what plausibly drives them.",
        ),
    )
    return seeds


def fallback_plan(
    topic: str,
    sources: list[dict[str, Any]],
    *,
    max_sections: int = 6,
) -> Plan:
    """A deterministic plan derived from the discovered schema."""
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


class ResearchPlanner:
    """Generates structured investigation plans and query permutations for research topics."""

    def create_plan(
        self,
        topic: str,
        target_depth: int = 2,
        max_sources: int = 15,
        focus_areas: list[str] | None = None,
    ) -> ResearchPlan:
        """Analyze topic and decompose into sub-questions, hypotheses, and queries."""
        session_id = f"res_{uuid.uuid4().hex[:8]}"

        hypotheses = self._generate_hypotheses(topic, focus_areas)
        sub_questions = self._generate_sub_questions(topic, focus_areas)

        return ResearchPlan(
            session_id=session_id,
            topic=topic,
            hypotheses=hypotheses,
            sub_questions=sub_questions,
            target_depth=target_depth,
            max_sources=max_sources,
            status=ResearchStatus.PLANNING,
            metadata={
                "focus_areas": focus_areas or [],
                "search_queries": self.generate_search_queries(topic, sub_questions),
            },
        )

    def generate_search_queries(
        self,
        topic: str,
        sub_questions: list[str],
    ) -> list[dict[str, str]]:
        """Generate bilingual targeted queries (Persian and English) with search modifiers."""
        queries: list[dict[str, str]] = []

        # Base overview queries
        queries.append({
            "language": "fa",
            "query": f"{topic} تحلیل جامع و گزارش فنی",
            "intent": "overview",
        })
        queries.append({
            "language": "en",
            "query": f"{topic} comprehensive architecture analysis benchmark",
            "intent": "overview",
        })

        for q in sub_questions[:5]:
            clean_q = re.sub(r"[^\w\s\u0600-\u06FF]", "", q).strip()
            if any("\u0600" <= c <= "\u06FF" for c in clean_q):
                queries.append({
                    "language": "fa",
                    "query": f"{topic} {clean_q}",
                    "intent": "deep_dive",
                })
            else:
                queries.append({
                    "language": "en",
                    "query": f"{topic} {clean_q}",
                    "intent": "deep_dive",
                })

        return queries

    def _generate_hypotheses(
        self,
        topic: str,
        focus_areas: list[str] | None = None,
    ) -> list[str]:
        """Formulate working hypotheses for verification."""
        hypos = [
            f"بررسی تاثیرگذاری و کارایی کلیدی '{topic}'",
            "شناسایی چالش‌ها و محدودیت‌های فنی و عملیاتی",
            f"مقایسه رویکردهای پیشرو در حوزه '{topic}'",
        ]
        if focus_areas:
            for fa in focus_areas:
                hypos.append(f"تحلیل تخصصی در بخش {fa}")
        return hypos

    def _generate_sub_questions(
        self,
        topic: str,
        focus_areas: list[str] | None = None,
    ) -> list[str]:
        """Formulate core research inquiries."""
        questions = [
            f"مفاهیم پایه و معماری اصلی '{topic}' چیست؟",
            "آخرین دستاوردها و نتایج بنچ‌مارک چگونه ارزیابی می‌شوند؟",
            "بهترین الگوهای پیاده‌سازی و ملاحظات امنیتی کدامند؟",
        ]
        if focus_areas:
            for fa in focus_areas:
                questions.append(f"چگونه می‌توان {fa} را در '{topic}' بهینه کرد؟")
        return questions
