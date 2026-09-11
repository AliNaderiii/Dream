"""Knowledge Graph Memory: Entity-Relation-Entity graph with multi-hop retrieval."""

from __future__ import annotations

import collections
import json
import re
import sqlite3
import time
import uuid
from typing import Any

from dream.retrieval.types import Entity, Relation


class KnowledgeGraphStore:
    """Relational and in-memory knowledge graph for semantic associative linking."""

    def __init__(self, db_path: str | None = None, user_id: str = "default") -> None:
        self.user_id = user_id
        self._db_path = db_path or ":memory:"
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        """Initialize relational entity-relation schema."""
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kg_entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    aliases_json TEXT DEFAULT '[]',
                    attributes_json TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    user_id TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kg_relations (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    context TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    user_id TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES kg_entities (id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES kg_entities (id) ON DELETE CASCADE
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_entities_name ON kg_entities (name, user_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_relations_src ON kg_relations "
                "(source_id, user_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_relations_tgt ON kg_relations "
                "(target_id, user_id)"
            )

    def add_entity(
        self,
        name: str,
        entity_type: str = "concept",
        description: str = "",
        aliases: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
        entity_id: str | None = None,
    ) -> Entity:
        """Insert or update an entity node in the graph."""
        clean_name = name.strip()
        existing = self.find_entity(clean_name)
        now = time.time()
        aliases_list = aliases or []
        attrs = attributes or {}

        if existing:
            # Update existing entity
            merged_aliases = list(set(existing.aliases + aliases_list))
            merged_attrs = {**existing.attributes, **attrs}
            desc = description if description else existing.description
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE kg_entities
                    SET entity_type = ?, description = ?, aliases_json = ?, attributes_json = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        entity_type or existing.entity_type,
                        desc,
                        json.dumps(merged_aliases, ensure_ascii=False),
                        json.dumps(merged_attrs, ensure_ascii=False),
                        existing.id,
                        self.user_id,
                    ),
                )
            return Entity(
                id=existing.id,
                name=existing.name,
                entity_type=entity_type or existing.entity_type,
                description=desc,
                aliases=merged_aliases,
                attributes=merged_attrs,
                created_at=existing.created_at,
                user_id=self.user_id,
            )

        new_id = entity_id or f"ent_{uuid.uuid4().hex[:10]}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO kg_entities (
                    id, name, entity_type, description, aliases_json,
                    attributes_json, created_at, user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    clean_name,
                    entity_type,
                    description,
                    json.dumps(aliases_list, ensure_ascii=False),
                    json.dumps(attrs, ensure_ascii=False),
                    now,
                    self.user_id,
                ),
            )
        return Entity(
            id=new_id,
            name=clean_name,
            entity_type=entity_type,
            description=description,
            aliases=aliases_list,
            attributes=attrs,
            created_at=now,
            user_id=self.user_id,
        )

    def find_entity(self, name_or_alias: str) -> Entity | None:
        """Find entity by exact name or match in aliases."""
        term = name_or_alias.strip().lower()
        rows = self._conn.execute(
            "SELECT * FROM kg_entities WHERE user_id = ?",
            (self.user_id,),
        ).fetchall()
        for row in rows:
            aliases = json.loads(row["aliases_json"] or "[]")
            if row["name"].lower() == term or any(a.lower() == term for a in aliases):
                return Entity(
                    id=row["id"],
                    name=row["name"],
                    entity_type=row["entity_type"],
                    description=row["description"],
                    aliases=aliases,
                    attributes=json.loads(row["attributes_json"] or "{}"),
                    created_at=row["created_at"],
                    user_id=row["user_id"],
                )
        return None

    def get_entity_by_id(self, entity_id: str) -> Entity | None:
        """Fetch entity by unique ID."""
        row = self._conn.execute(
            "SELECT * FROM kg_entities WHERE id = ? AND user_id = ?",
            (entity_id, self.user_id),
        ).fetchone()
        if not row:
            return None
        return Entity(
            id=row["id"],
            name=row["name"],
            entity_type=row["entity_type"],
            description=row["description"],
            aliases=json.loads(row["aliases_json"] or "[]"),
            attributes=json.loads(row["attributes_json"] or "{}"),
            created_at=row["created_at"],
            user_id=row["user_id"],
        )

    def add_relation(
        self,
        source: str | Entity,
        target: str | Entity,
        relation_type: str,
        weight: float = 1.0,
        context: str = "",
        rel_id: str | None = None,
    ) -> Relation:
        """Create a directed relation between two entities."""
        src_ent = (
            source
            if isinstance(source, Entity)
            else (self.find_entity(source) or self.add_entity(source))
        )
        tgt_ent = (
            target
            if isinstance(target, Entity)
            else (self.find_entity(target) or self.add_entity(target))
        )

        # Check existing edge
        existing = self._conn.execute(
            """
            SELECT * FROM kg_relations
            WHERE source_id = ? AND target_id = ? AND relation_type = ? AND user_id = ?
            """,
            (src_ent.id, tgt_ent.id, relation_type, self.user_id),
        ).fetchone()

        now = time.time()
        if existing:
            new_weight = max(existing["weight"], weight)
            with self._conn:
                self._conn.execute(
                    "UPDATE kg_relations SET weight = ?, context = ? WHERE id = ?",
                    (new_weight, context or existing["context"], existing["id"]),
                )
            return Relation(
                id=existing["id"],
                source_id=src_ent.id,
                target_id=tgt_ent.id,
                relation_type=relation_type,
                weight=new_weight,
                context=context or existing["context"],
                created_at=existing["created_at"],
                user_id=self.user_id,
            )

        new_rel_id = rel_id or f"rel_{uuid.uuid4().hex[:10]}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO kg_relations (
                    id, source_id, target_id, relation_type, weight,
                    context, created_at, user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_rel_id,
                    src_ent.id,
                    tgt_ent.id,
                    relation_type,
                    weight,
                    context,
                    now,
                    self.user_id,
                ),
            )
        return Relation(
            id=new_rel_id,
            source_id=src_ent.id,
            target_id=tgt_ent.id,
            relation_type=relation_type,
            weight=weight,
            context=context,
            created_at=now,
            user_id=self.user_id,
        )

    def extract_triples_from_text(self, text: str) -> list[tuple[str, str, str]]:
        """Extract entity-relation-entity triples via bilingual patterns."""
        triples: list[tuple[str, str, str]] = []

        # English patterns: "X uses Y", "X prefers Y", "X builds Y", "X works at Y"
        patterns_en = [
            (r"([A-Za-z0-9_\-]+)\s+(?:uses|is using)\s+([A-Za-z0-9_\-]+)", "uses"),
            (r"([A-Za-z0-9_\-]+)\s+(?:prefers|likes)\s+([A-Za-z0-9_\-]+)", "prefers"),
            (r"([A-Za-z0-9_\-]+)\s+(?:builds|develops|created)\s+([A-Za-z0-9_\-]+)", "builds"),
            (r"([A-Za-z0-9_\-]+)\s+(?:works at|works for)\s+([A-Za-z0-9_\-]+)", "works_at"),
            (r"([A-Za-z0-9_\-]+)\s+(?:is a|is an)\s+([A-Za-z0-9_\-]+)", "is_a"),
            (r"([A-Za-z0-9_\-]+)\s+(?:depends on)\s+([A-Za-z0-9_\-]+)", "depends_on"),
        ]

        # Persian patterns: "X با Y کار می‌کند", "X علاقه دارد به Y", "X سازنده Y است"
        patterns_fa = [
            (r"([\w]+)\s+(?:از|با)\s+([\w]+)\s+(?:استفاده می‌کند|کار می‌کند)", "uses"),
            (r"([\w]+)\s+به\s+([\w]+)\s+(?:علاقه دارد|ترجیح می‌دهد)", "prefers"),
            (r"([\w]+)\s+(?:سازنده|توسعه‌دهنده)\s+([\w]+)\s+(?:است|هست)", "builds"),
            (r"([\w]+)\s+در\s+([\w]+)\s+(?:کار می‌کند|شاغل است)", "works_at"),
        ]

        for pat, rel in patterns_en + patterns_fa:
            for match in re.finditer(pat, text, flags=re.IGNORECASE):
                src = match.group(1).strip()
                tgt = match.group(2).strip()
                if src and tgt and src.lower() != tgt.lower():
                    triples.append((src, rel, tgt))
        return triples

    def query_neighbors(
        self,
        entity_name: str,
        max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        """Multi-hop breadth-first graph traversal from root entity."""
        root = self.find_entity(entity_name)
        if not root:
            return []

        visited_nodes: set[str] = {root.id}
        queue: collections.deque[tuple[str, int]] = collections.deque([(root.id, 0)])
        paths: list[dict[str, Any]] = []

        while queue:
            current_id, hop = queue.popleft()
            if hop >= max_hops:
                continue

            # Outgoing edges
            rows_out = self._conn.execute(
                """
                SELECT r.*, e.name as target_name, e.entity_type as target_type
                FROM kg_relations r
                JOIN kg_entities e ON e.id = r.target_id
                WHERE r.source_id = ? AND r.user_id = ?
                """,
                (current_id, self.user_id),
            ).fetchall()

            curr_ent = self.get_entity_by_id(current_id)
            curr_name = curr_ent.name if curr_ent else current_id

            for row in rows_out:
                tgt_id = row["target_id"]
                paths.append(
                    {
                        "source": curr_name,
                        "relation": row["relation_type"],
                        "target": row["target_name"],
                        "hop": hop + 1,
                        "weight": row["weight"],
                        "context": row["context"],
                    }
                )
                if tgt_id not in visited_nodes:
                    visited_nodes.add(tgt_id)
                    queue.append((tgt_id, hop + 1))

        return paths

    def find_path(
        self,
        source_name: str,
        target_name: str,
        max_depth: int = 3,
    ) -> list[str] | None:
        """Find shortest relationship path between two entities."""
        src = self.find_entity(source_name)
        tgt = self.find_entity(target_name)
        if not src or not tgt:
            return None
        if src.id == tgt.id:
            return [src.name]

        queue: collections.deque[tuple[str, list[str]]] = collections.deque([(src.id, [src.name])])
        visited: set[str] = {src.id}

        while queue:
            curr_id, path = queue.popleft()
            if len(path) > max_depth + 1:
                continue

            rows = self._conn.execute(
                """
                SELECT r.relation_type, e.id as target_id, e.name as target_name
                FROM kg_relations r
                JOIN kg_entities e ON e.id = r.target_id
                WHERE r.source_id = ? AND r.user_id = ?
                """,
                (curr_id, self.user_id),
            ).fetchall()

            for row in rows:
                t_id = row["target_id"]
                step = f"--[{row['relation_type']}]--> {row['target_name']}"
                new_path = path + [step]
                if t_id == tgt.id:
                    return new_path
                if t_id not in visited:
                    visited.add(t_id)
                    queue.append((t_id, new_path))
        return None

    def export_ascii_graph(self) -> str:
        """Render knowledge graph as ASCII tree/table."""
        entities = self._conn.execute(
            "SELECT * FROM kg_entities WHERE user_id = ? ORDER BY name",
            (self.user_id,),
        ).fetchall()
        if not entities:
            return "Knowledge Graph is currently empty."

        lines = [f"📊 Knowledge Graph Memory ({len(entities)} Entities):"]
        for ent in entities:
            lines.append(f"  • Node: [{ent['entity_type']}] {ent['name']}")
            relations = self._conn.execute(
                """
                SELECT r.relation_type, e.name as target_name, r.weight
                FROM kg_relations r
                JOIN kg_entities e ON e.id = r.target_id
                WHERE r.source_id = ? AND r.user_id = ?
                """,
                (ent["id"], self.user_id),
            ).fetchall()
            for r in relations:
                edge_label = f"({r['relation_type']})"
                tgt = r["target_name"]
                w = r["weight"]
                lines.append(f"      └── {edge_label} ──> {tgt} [w={w:.1f}]")
        return "\n".join(lines)
