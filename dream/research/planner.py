"""Decomposes research topics into hypotheses, multi-lingual queries, and structured investigation plans."""

from __future__ import annotations

import re
import uuid

from dream.research.types import ResearchPlan, ResearchStatus


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
            "query": f"{topic} \u062a\u062d\u0644\u06cc\u0644 \u062c\u0627\u0645\u0639 \u0648 \u06af\u0632\u0627\u0631\u0634 \u0641\u0646\u06cc",
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
            f"\u0628\u0631\u0631\u0633\u06cc \u062a\u0627\u062b\u06cc\u0631\u06af\u0630\u0627\u0631\u06cc \u0648 \u06a9\u0627\u0631\u0627\u06cc\u06cc \u06a9\u0644\u06cc\u062f\u06cc '{topic}'",
            f"\u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u0686\u0627\u0644\u0634\u200c\u0647\u0627 \u0648 \u0645\u062d\u062f\u0648\u062f\u06cc\u062a\u200c\u0647\u0627\u06cc \u0641\u0646\u06cc \u0648 \u0639\u0645\u0644\u06cc\u0627\u062a\u06cc",
            f"\u0645\u0642\u0627\u06cc\u0633\u0647 \u0631\u0648\u06cc\u06a9\u0631\u062f\u0647\u0627\u06cc \u067e\u06cc\u0634\u0631\u0648 \u062f\u0631 \u062d\u0648\u0632\u0647 '{topic}'",
        ]
        if focus_areas:
            for fa in focus_areas:
                hypos.append(f"\u062a\u062d\u0644\u06cc\u0644 \u062a\u062e\u0635\u0635\u06cc \u062f\u0631 \u0628\u062e\u0634 {fa}")
        return hypos

    def _generate_sub_questions(
        self,
        topic: str,
        focus_areas: list[str] | None = None,
    ) -> list[str]:
        """Formulate core research inquiries."""
        questions = [
            f"\u0645\u0641\u0627\u0647\u06cc\u0645 \u067e\u0627\u06cc\u0647 \u0648 \u0645\u0639\u0645\u0627\u0631\u06cc \u0627\u0635\u0644\u06cc '{topic}' \u0686\u06cc\u0633\u062a\u061f",
            f"\u0622\u062e\u0631\u06cc\u0646 \u062f\u0633\u062a\u0627\u0648\u0631\u062f\u0647\u0627 \u0648 \u0646\u062a\u0627\u06cc\u062c \u0628\u0646\u0686\u200c\u0645\u0627\u0631\u06a9 \u0686\u06af\u0648\u0646\u0647 \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u0645\u06cc\u200c\u0634\u0648\u0646\u062f\u061f",
            f"\u0628\u0647\u062a\u0631\u06cc\u0646 \u0627\u0644\u06af\u0648\u0647\u0627\u06cc \u067e\u06cc\u0627\u062f\u0647\u200c\u0633\u0627\u0632\u06cc \u0648 \u0645\u0644\u0627\u062d\u0638\u0627\u062a \u0627\u0645\u0646\u06cc\u062a\u06cc \u06a9\u062f\u0627\u0645\u0646\u062f\u061f",
        ]
        if focus_areas:
            for fa in focus_areas:
                questions.append(
                    f"\u0686\u06af\u0648\u0646\u0647 \u0645\u06cc\u200c\u062a\u0648\u0627\u0646 {fa} \u0631\u0627 \u062f\u0631 '{topic}' \u0628\u0647\u06cc\u0646\u0647 \u06a9\u0631\u062f\u061f"
                )
        return questions
