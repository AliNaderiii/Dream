"""Hierarchical Episodic Memory & Temporal Knowledge Graph Engine for Dream Agent."""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from dream.knowledge import (
    EntityType,
    MultimodalTemporalGraph,
    RelationType,
    TemporalInterval,
    get_global_knowledge_engine,
    jalali_to_timestamp,
    timestamp_to_jalali,
)


@dataclass(slots=True)
class EpisodicTurn:
    """Working memory single conversation turn (Tier 0)."""

    turn_id: str
    speaker: str  # "user" | "assistant" | "system"
    text: str
    tokens: int = 0
    sentiment: float = 0.0  # -1.0 to 1.0
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EpisodeRecord:
    """Consolidated session episode (Tier 1)."""

    episode_id: str
    session_id: str
    title_fa: str
    title_en: str
    summary_fa: str
    goals: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    milestones: list[str] = field(default_factory=list)
    sentiment_score: float = 0.0
    importance_score: int = 3  # 1 to 5
    started_at: float = field(default_factory=time.time)
    ended_at: float = field(default_factory=time.time)
    jalali_date: str = ""
    linked_entities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TemporalEntityFact:
    """Entity fact anchored to the temporal knowledge graph (Tier 2)."""

    fact_id: str
    episode_id: str
    entity_name: str
    entity_type: str
    relation: str
    target_name: str
    valid_from_jalali: str
    valid_to_jalali: str | None = None
    confidence: float = 0.95
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ConsolidatedPersona:
    """Tier-3 recursive consolidated persona, preferences, and competencies."""

    profile_id: str
    user_title_fa: str
    primary_domains: list[str] = field(default_factory=list)
    key_preferences: dict[str, Any] = field(default_factory=dict)
    skill_masteries: dict[str, float] = field(default_factory=dict)  # domain -> 0.0-1.0
    recurring_goals: list[str] = field(default_factory=list)
    consolidated_at: float = field(default_factory=time.time)
    total_episodes_synthesized: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HierarchicalEpisodicEngine:
    """Master Multi-Tier Hierarchical Episodic Memory & Temporal Knowledge Graph Engine."""

    def __init__(self) -> None:
        self._working_memory: dict[str, list[EpisodicTurn]] = {}  # session_id -> turns
        self._episodes: dict[str, EpisodeRecord] = {}  # episode_id -> record
        self._temporal_facts: dict[str, TemporalEntityFact] = {}  # fact_id -> fact
        self._persona: ConsolidatedPersona = ConsolidatedPersona(
            profile_id="persona_default",
            user_title_fa="کاربر اصلی سیستم دریم",
            primary_domains=["مهندسی هوش مصنوعی", "توسعه نرم‌افزار", "تحلیل سیستم‌ها"],
            key_preferences={
                "language": "fa",
                "tone": "professional_engineering",
                "precision": "high",
            },
            skill_masteries={"ai_agents": 0.95, "architecture": 0.92, "python": 0.96},
            recurring_goals=["توسعه سیستم هوشمند دریم", "بهینه‌سازی پایپ‌لاین‌های هوش مصنوعی"],
            consolidated_at=time.time(),
            total_episodes_synthesized=0,
        )
        self._knowledge_graph: MultimodalTemporalGraph = get_global_knowledge_engine().graph
        self._start_time = time.time()
        self._total_operations = 0

    def record_working_turn(
        self,
        session_id: str,
        speaker: str,
        text: str,
        sentiment: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> EpisodicTurn:
        """Record a single turn into Tier 0 working memory buffer."""
        self._total_operations += 1
        sid = session_id.strip() or "default_session"
        if sid not in self._working_memory:
            self._working_memory[sid] = []

        tokens = len(text.split()) * 2
        turn = EpisodicTurn(
            turn_id=f"turn-{uuid.uuid4().hex[:6]}",
            speaker=speaker,
            text=text,
            tokens=tokens,
            sentiment=max(-1.0, min(1.0, sentiment)),
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._working_memory[sid].append(turn)

        # Buffer size constraint (keep last 50 turns per session)
        if len(self._working_memory[sid]) > 50:
            self._working_memory[sid] = self._working_memory[sid][-50:]

        return turn

    def compress_session(
        self,
        session_id: str,
        turns: list[dict[str, Any]] | None = None,
        domain: str = "general",
    ) -> EpisodeRecord:
        """Compress working memory turns into a durable Tier 1 Episodic Episode."""
        self._total_operations += 1
        sid = session_id.strip() or "default_session"

        working_turns = self._working_memory.get(sid, [])
        if turns:
            input_turns = []
            for t in turns:
                if isinstance(t, dict):
                    input_turns.append(
                        EpisodicTurn(
                            turn_id=t.get("turn_id") or f"turn-{uuid.uuid4().hex[:6]}",
                            speaker=str(t.get("speaker", "user")),
                            text=str(t.get("text", "")),
                            tokens=int(t.get("tokens", 0)),
                            sentiment=float(t.get("sentiment", 0.0)),
                        )
                    )
            working_turns = input_turns

        count = len(working_turns)
        j_now = timestamp_to_jalali(time.time())

        # Synthesize title and summary
        title_fa = f"نشست گفتگو در حوزه {domain} ({count} تبادل نظر)"
        title_en = f"Conversation Session in {domain} ({count} turns)"

        if working_turns:
            user_texts = [t.text for t in working_turns if t.speaker == "user"]
            sample = user_texts[0][:100] if user_texts else "بررسی و پردازش تسک‌ها"
            summary_fa = (
                f"خلاصه نشست {sid}: بررسی «{sample}» با ثبت دستاوردها "
                f"و اهداف در تاریخ {j_now}."
            )
            avg_sentiment = sum(t.sentiment for t in working_turns) / len(working_turns)
        else:
            summary_fa = f"نشست تخصصی {sid} با موفقیت ثبت شد."
            avg_sentiment = 0.2

        episode_id = f"ep-{uuid.uuid4().hex[:6]}"
        record = EpisodeRecord(
            episode_id=episode_id,
            session_id=sid,
            title_fa=title_fa,
            title_en=title_en,
            summary_fa=summary_fa,
            goals=[f"تکمیل تسک‌های حوزه {domain}", "ارتقای یکپارچگی سیستم"],
            outcomes=["تولید خروجی‌های معتبر", "به‌روزرسانی حافظه مکانی و گراف دانش"],
            milestones=[f"آغاز نشست در {j_now}", "اعتبارسنجی معماری", "تثبیت رویداد اپیزودیک"],
            sentiment_score=round(avg_sentiment, 2),
            importance_score=4 if count > 5 else 3,
            started_at=time.time() - (count * 15.0),
            ended_at=time.time(),
            jalali_date=j_now,
            linked_entities=[domain, sid],
            metadata={"domain": domain, "turn_count": count},
        )

        self._episodes[episode_id] = record

        # Automatically link episode to knowledge graph as a session node
        try:
            self._knowledge_graph.add_node(
                node_id=episode_id,
                name=title_fa,
                entity_type=EntityType.EVENT,
                aliases=[title_en, sid],
                attributes={
                    "summary_fa": summary_fa,
                    "importance": record.importance_score,
                    "jalali_date": j_now,
                },
                temporal=TemporalInterval(
                    valid_from=record.started_at,
                    valid_to=record.ended_at,
                    jalali_date=j_now,
                ),
            )
        except Exception:
            pass

        return record

    def link_entity_fact(
        self,
        episode_id: str,
        entity_name: str,
        entity_type: str = "concept",
        relation_type: str = "references",
        target_entity: str = "DreamAgent",
        jalali_date: str | None = None,
    ) -> TemporalEntityFact:
        """Link an episode event to the Temporal Knowledge Graph (Tier 2)."""
        self._total_operations += 1
        j_date = jalali_date or timestamp_to_jalali(time.time())
        fact_id = f"fact-{uuid.uuid4().hex[:6]}"

        fact = TemporalEntityFact(
            fact_id=fact_id,
            episode_id=episode_id,
            entity_name=entity_name,
            entity_type=entity_type,
            relation=relation_type,
            target_name=target_entity,
            valid_from_jalali=j_date,
            confidence=0.98,
            timestamp=time.time(),
        )
        self._temporal_facts[fact_id] = fact

        # Integrate into knowledge graph
        try:
            e_type = EntityType(entity_type.lower())
        except ValueError:
            e_type = EntityType.CONCEPT

        try:
            r_type = RelationType(relation_type.lower())
        except ValueError:
            r_type = RelationType.REFERENCES

        src_node = self._knowledge_graph.find_node(entity_name)
        if not src_node:
            src_node = self._knowledge_graph.add_node(
                name=entity_name,
                entity_type=e_type,
                temporal=TemporalInterval(valid_from=time.time(), jalali_date=j_date),
            )

        tgt_node = self._knowledge_graph.find_node(target_entity)
        if not tgt_node:
            tgt_node = self._knowledge_graph.add_node(
                name=target_entity,
                entity_type=EntityType.CONCEPT,
                temporal=TemporalInterval(valid_from=time.time(), jalali_date=j_date),
            )

        self._knowledge_graph.add_edge(
            source=src_node,
            target=tgt_node,
            relation_type=r_type,
            context_snippet=f"Linked from episode {episode_id}",
        )

        return fact

    def query_timeline(
        self,
        query: str = "",
        start_jalali: str = "",
        end_jalali: str = "",
        min_importance: int = 1,
        limit: int = 20,
    ) -> list[EpisodeRecord]:
        """Query episodic events across temporal horizons and Jalali windows."""
        results = []
        q_clean = query.strip().lower()

        t_start = jalali_to_timestamp(start_jalali) if start_jalali else 0.0
        t_end = jalali_to_timestamp(end_jalali) if end_jalali else float("inf")

        for ep in self._episodes.values():
            if ep.importance_score < min_importance:
                continue

            if ep.ended_at < t_start or ep.started_at > t_end:
                continue

            if q_clean:
                match_title = q_clean in ep.title_fa.lower() or q_clean in ep.title_en.lower()
                match_summary = q_clean in ep.summary_fa.lower()
                match_entities = any(q_clean in ent.lower() for ent in ep.linked_entities)
                if not (match_title or match_summary or match_entities):
                    continue

            results.append(ep)

        # Sort descending by timestamp
        results.sort(key=lambda x: x.ended_at, reverse=True)
        return results[:limit]

    def consolidate(
        self,
        force_decay: bool = False,
        min_episodes: int = 1,
    ) -> ConsolidatedPersona:
        """Trigger Tier-3 recursive consolidation and distill long-term user persona."""
        self._total_operations += 1
        ep_count = len(self._episodes)
        if ep_count < min_episodes:
            return self._persona

        # Distill domains and skills from episodic history
        domain_counts: dict[str, int] = {}
        for ep in self._episodes.values():
            for ent in ep.linked_entities:
                domain_counts[ent] = domain_counts.get(ent, 0) + 1

        sorted_domains = sorted(domain_counts.keys(), key=lambda k: domain_counts[k], reverse=True)
        top_domains = sorted_domains[:5] if sorted_domains else self._persona.primary_domains

        updated_masteries = dict(self._persona.skill_masteries)
        for dom in top_domains:
            curr = updated_masteries.get(dom, 0.7)
            # Logarithmic mastery growth
            updated_masteries[dom] = min(0.99, round(curr + 0.02 * math.log1p(ep_count), 3))

        self._persona = ConsolidatedPersona(
            profile_id=self._persona.profile_id,
            user_title_fa=self._persona.user_title_fa,
            primary_domains=top_domains,
            key_preferences=self._persona.key_preferences,
            skill_masteries=updated_masteries,
            recurring_goals=self._persona.recurring_goals,
            consolidated_at=time.time(),
            total_episodes_synthesized=ep_count,
        )

        return self._persona

    def get_hierarchy_stats(self) -> dict[str, Any]:
        """Retrieve multi-tier distribution metrics."""
        uptime = round(time.time() - self._start_time, 2)
        working_count = sum(len(turns) for turns in self._working_memory.values())
        episode_count = len(self._episodes)
        facts_count = len(self._temporal_facts)

        return {
            "uptime_sec": uptime,
            "total_operations": self._total_operations,
            "tier_0_working_turns": working_count,
            "tier_1_episodes_count": episode_count,
            "tier_2_temporal_facts_count": facts_count,
            "tier_3_persona_domains": len(self._persona.primary_domains),
            "total_knowledge_graph_nodes": len(self._knowledge_graph._nodes),
            "total_knowledge_graph_edges": len(self._knowledge_graph._edges),
            "compression_ratio": round((working_count / max(1, episode_count)), 2),
            "status": "healthy",
        }

    def reset(self) -> None:
        """Reset working buffers while preserving durable roots."""
        self._working_memory.clear()
        self._episodes.clear()
        self._temporal_facts.clear()
        self._total_operations = 0


# Global singleton
_GLOBAL_EPISODIC_ENGINE: HierarchicalEpisodicEngine | None = None


def get_episodic_engine() -> HierarchicalEpisodicEngine:
    """Retrieve global singleton HierarchicalEpisodicEngine."""
    global _GLOBAL_EPISODIC_ENGINE
    if _GLOBAL_EPISODIC_ENGINE is None:
        _GLOBAL_EPISODIC_ENGINE = HierarchicalEpisodicEngine()
    return _GLOBAL_EPISODIC_ENGINE


def reset_global_episodic_engine() -> None:
    """Reset global singleton HierarchicalEpisodicEngine."""
    global _GLOBAL_EPISODIC_ENGINE
    _GLOBAL_EPISODIC_ENGINE = None
