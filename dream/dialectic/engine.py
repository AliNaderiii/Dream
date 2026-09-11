"""Core Dialectic Engine for reflective knowledge graph and mental model synthesis."""

from __future__ import annotations

import time
import unicodedata
import uuid

from dream.dialectic.types import (
    BeliefNode,
    DialecticMemorySnapshot,
    DialecticRelation,
    DialecticStatus,
    DialecticTension,
    RelationType,
)


class DialecticEngine:
    """Manages dialectic user modeling, belief graphs, and self-reflection reconciliation."""

    def __init__(self) -> None:
        self._nodes: dict[str, BeliefNode] = {}
        self._relations: dict[str, DialecticRelation] = {}
        self._tensions: dict[str, DialecticTension] = {}

    def _normalize(self, text: str) -> str:
        """Normalize Persian and English text using NFKC."""
        return unicodedata.normalize("NFKC", text.strip())

    def add_belief(
        self,
        domain: str,
        statement: str,
        confidence: float = 0.8,
        evidence: list[str] | None = None,
    ) -> BeliefNode:
        """Register or update a belief node in the knowledge network."""
        norm_stmt = self._normalize(statement)
        belief_id = f"b_{uuid.uuid4().hex[:6]}"
        node = BeliefNode(
            belief_id=belief_id,
            domain=domain.lower().strip(),
            statement=norm_stmt,
            confidence=max(0.0, min(1.0, confidence)),
            status=DialecticStatus.ACTIVE,
            evidence=evidence or [],
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._nodes[belief_id] = node
        self.detect_tensions()
        return node

    def link_beliefs(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        notes: str = "",
    ) -> DialecticRelation:
        """Create a semantic relation edge between two belief nodes."""
        if source_id not in self._nodes or target_id not in self._nodes:
            raise KeyError("Source or target belief node not found in graph.")

        rel_id = f"r_{uuid.uuid4().hex[:6]}"
        relation = DialecticRelation(
            relation_id=rel_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            notes=notes,
        )
        self._relations[rel_id] = relation
        return relation

    def observe_statement(self, statement: str, domain: str = "general") -> BeliefNode:
        """Observe a factual statement or user preference from conversational turns."""
        norm_stmt = self._normalize(statement)

        # Check if identical statement exists
        for node in self._nodes.values():
            if node.statement.lower() == norm_stmt.lower() and node.domain == domain.lower():
                node.confidence = min(1.0, node.confidence + 0.1)
                node.updated_at = time.time()
                return node

        return self.add_belief(domain=domain, statement=norm_stmt, confidence=0.85)

    def detect_tensions(self) -> list[DialecticTension]:
        """Identify contradictions or dialectic tensions between opposing beliefs."""
        nodes_list = list(self._nodes.values())

        contradiction_pairs = [
            ("concise", "detailed"),
            ("tabs", "spaces"),
            ("morning", "night"),
            ("fast", "deep"),
            ("async", "sync"),
        ]

        for i in range(len(nodes_list)):
            for j in range(i + 1, len(nodes_list)):
                n1 = nodes_list[i]
                n2 = nodes_list[j]

                ten_id = f"t_{n1.belief_id}_{n2.belief_id}"
                if ten_id in self._tensions:
                    continue

                if (
                    n1.status not in (DialecticStatus.ACTIVE, DialecticStatus.CONTRADICTED)
                    or n2.status not in (DialecticStatus.ACTIVE, DialecticStatus.CONTRADICTED)
                ):
                    continue

                for p1, p2 in contradiction_pairs:
                    t1 = p1 in n1.statement.lower() and p2 in n2.statement.lower()
                    t2 = p2 in n1.statement.lower() and p1 in n2.statement.lower()
                    if t1 or t2:
                        desc = f"Contradiction between '{n1.statement}' and '{n2.statement}'"
                        ten = DialecticTension(
                            tension_id=ten_id,
                            belief_ids=[n1.belief_id, n2.belief_id],
                            description=desc,
                        )
                        self._tensions[ten_id] = ten
                        n1.status = DialecticStatus.CONTRADICTED
                        n2.status = DialecticStatus.CONTRADICTED

        return list(self._tensions.values())

    def reconcile_tension(
        self,
        tension_id: str,
        nuanced_statement: str,
    ) -> BeliefNode:
        """Synthesize opposing contradictory beliefs into a unified nuanced higher-order belief."""
        if tension_id not in self._tensions:
            raise KeyError(f"Tension '{tension_id}' not found.")

        tension = self._tensions[tension_id]
        tension.resolved = True
        tension.resolution_notes = nuanced_statement

        # Mark source beliefs as Nuanced
        for b_id in tension.belief_ids:
            if b_id in self._nodes:
                self._nodes[b_id].status = DialecticStatus.NUANCED

        # Create the unified higher-order belief
        domain = "synthesized"
        if tension.belief_ids and tension.belief_ids[0] in self._nodes:
            domain = self._nodes[tension.belief_ids[0]].domain

        ev = [f"Reconciled from tension {tension_id}"]
        nuanced_node = self.add_belief(
            domain=domain,
            statement=nuanced_statement,
            confidence=0.95,
            evidence=ev,
        )

        for b_id in tension.belief_ids:
            if b_id in self._nodes:
                self.link_beliefs(
                    source_id=b_id,
                    target_id=nuanced_node.belief_id,
                    relation_type=RelationType.REFINES,
                    notes=f"Reconciled into nuanced belief {nuanced_node.belief_id}",
                )

        return nuanced_node

    def query_beliefs(self, query: str, limit: int = 5) -> list[BeliefNode]:
        """Search relevant beliefs by keyword or semantic domain."""
        norm_q = self._normalize(query).lower()
        matched = []
        for node in self._nodes.values():
            if norm_q in node.statement.lower() or norm_q in node.domain.lower():
                matched.append(node)
        matched.sort(key=lambda n: n.confidence, reverse=True)
        return matched[:limit]

    def reflect_and_synthesize(self) -> DialecticMemorySnapshot:
        """Perform autonomous self-reflection over beliefs and output structured mental model."""
        self.detect_tensions()
        active_nodes = [
            n for n in self._nodes.values()
            if n.status in (DialecticStatus.ACTIVE, DialecticStatus.NUANCED)
        ]
        active_nodes.sort(key=lambda n: n.confidence, reverse=True)

        unresolved = sum(1 for t in self._tensions.values() if not t.resolved)

        top_statements = [f"- [{n.domain}] {n.statement} (conf: {n.confidence:.2f})"
                          for n in active_nodes[:8]]
        summary_text = (
            "Dialectic Mental Model Summary:\n" + "\n".join(top_statements)
            if top_statements
            else "No active beliefs recorded."
        )

        return DialecticMemorySnapshot(
            nodes_count=len(self._nodes),
            tensions_count=len(self._tensions),
            unresolved_tensions=unresolved,
            top_beliefs=[n.to_dict() for n in active_nodes[:10]],
            synthesized_summary=summary_text,
            timestamp=time.time(),
        )

    def get_snapshot(self) -> DialecticMemorySnapshot:
        """Retrieve current memory snapshot without modifying state."""
        return self.reflect_and_synthesize()

    def reset(self) -> None:
        """Clear all nodes, relations, and tensions."""
        self._nodes.clear()
        self._relations.clear()
        self._tensions.clear()
