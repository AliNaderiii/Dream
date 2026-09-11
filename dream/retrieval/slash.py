"""Slash command handlers for Knowledge Graph Memory and Hybrid Retrieval."""

from __future__ import annotations

from collections.abc import Callable

from dream.retrieval.engine import UnifiedRetrievalEngine
from dream.retrieval.tools import get_global_retrieval_engine
from dream.tui.colors import ColorManager


def handle_graph_command(
    cmd_text: str,
    engine: UnifiedRetrievalEngine | None = None,
    output: Callable[[str], None] = print,
    colors: ColorManager | None = None,
) -> bool:
    """Handle `/graph` slash command (inspect, query entity, or find paths)."""
    cm = colors or ColorManager()
    eng = engine or get_global_retrieval_engine()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "show"

    if subcmd in ("show", "list", "view"):
        ascii_view = eng.graph.export_ascii_graph()
        output(cm.cyan(ascii_view))
        return True

    if subcmd in ("entity", "node", "query") and len(parts) > 2:
        name = parts[2]
        entity = eng.graph.find_entity(name)
        if not entity:
            output(cm.yellow(f"Entity '{name}' not found in knowledge graph."))
            return True
        output(cm.bold(f"Node: [{entity.entity_type}] {entity.name}"))
        if entity.description:
            output(f"  Description: {entity.description}")
        if entity.aliases:
            output(f"  Aliases: {', '.join(entity.aliases)}")
        neighbors = eng.graph.query_neighbors(entity.name, max_hops=2)
        if neighbors:
            output(cm.dim("  Connections:"))
            for n in neighbors:
                output(f"    • ({n['source']}) ──[{n['relation']}]──> ({n['target']})")
        return True

    if subcmd in ("path", "link") and len(parts) > 3:
        src, tgt = parts[2], parts[3]
        path = eng.graph.find_path(src, tgt)
        if not path:
            output(cm.yellow(f"No semantic path found between '{src}' and '{tgt}'."))
            return True
        output(cm.bold(f"Path between {src} and {tgt}:"))
        output("  " + " ".join(path))
        return True

    # Usage help
    output(cm.bold("Usage / راهنمای دستور /graph:"))
    output("  /graph                  - نمایش گراف دانش متنی / Show ASCII graph")
    output("  /graph entity <name>    - جستجوی یک گره / Inspect entity node")
    output("  /graph path <src> <tgt> - یافتن کوتاهترین مسیر / Find shortest path")
    return True


def handle_retrieve_command(
    cmd_text: str,
    engine: UnifiedRetrievalEngine | None = None,
    output: Callable[[str], None] = print,
    colors: ColorManager | None = None,
) -> bool:
    """Handle `/retrieve` slash command (test hybrid search with scoring breakdown)."""
    cm = colors or ColorManager()
    eng = engine or get_global_retrieval_engine()
    parts = cmd_text.strip().split(maxsplit=1)
    if len(parts) < 2:
        output(cm.yellow("Usage: /retrieve <search query>"))
        return True

    query = parts[1]
    results = eng.search(query, top_k=5)
    if not results:
        output(cm.dim(f"No matching documents found for query: '{query}'"))
        return True

    output(cm.bold(f"Hybrid Retrieval Results for '{query}' (Found {len(results)}):"))
    for idx, r in enumerate(results, 1):
        b = r.breakdown
        score_str = (
            f"Final: {r.score:.4f} [BM25: {b.sparse_bm25_score:.2f} (# {b.sparse_bm25_rank}) | "
            f"Dense: {b.dense_vector_score:.2f} (# {b.dense_vector_rank}) | "
            f"Decay: {b.temporal_multiplier:.2f}]"
        )
        output(f"  {idx}. {cm.green(r.content)}")
        output(f"     {cm.dim(score_str)}")
        if r.graph_context:
            output(f"     {cm.cyan('Graph Links:')} {'; '.join(r.graph_context[:2])}")

    return True
