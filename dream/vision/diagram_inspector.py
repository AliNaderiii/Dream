"""Diagram, Flowchart, and Persian Text Overlay Visual Inspector."""

from __future__ import annotations

import re
from typing import Any


class DiagramInspector:
    """Inspects diagrams, Mermaid charts, SVG layouts, and Persian visual overlays."""

    def inspect_mermaid_source(self, mermaid_code: str) -> dict[str, Any]:
        """Analyze structural validity, node count, and direction of Mermaid diagram code."""
        lines = [line.strip() for line in mermaid_code.strip().splitlines() if line.strip()]
        if not lines:
            return {"valid": False, "error": "کد Mermaid خالی است."}

        first_line = lines[0].lower()
        diagram_type = "unknown"
        for dt in ["graph", "flowchart", "sequencediagram", "classdiagram", "erdiagram", "mindmap"]:
            if dt in first_line:
                diagram_type = dt
                break

        nodes: set[str] = set()
        edges: list[tuple[str, str]] = []

        # Simple regex for node connections: A --> B, A --- B, A -.-> B
        edge_pattern = re.compile(
            r"([A-Za-z0-9_\u0600-\u06FF]+)\s*[-.=]+>\s*([A-Za-z0-9_\u0600-\u06FF]+)"
        )

        for line in lines[1:]:
            matches = edge_pattern.findall(line)
            for src, dst in matches:
                nodes.add(src)
                nodes.add(dst)
                edges.append((src, dst))

        persian_nodes = [n for n in nodes if re.search(r"[\u0600-\u06FF]", n)]

        return {
            "valid": True,
            "diagram_type": diagram_type,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes": list(nodes),
            "edges_count": len(edges),
            "has_persian_text": len(persian_nodes) > 0,
            "persian_nodes_count": len(persian_nodes),
            "summary_fa": (
                f"نمودار از نوع `{diagram_type}` با {len(nodes)} گره و "
                f"{len(edges)} اتصال شناسایی شد."
            ),
        }

    def inspect_svg_elements(self, svg_content: str) -> dict[str, Any]:
        """Inspect SVG elements (rectangles, circles, text, paths) for visual structure."""
        if "<svg" not in svg_content:
            return {"valid": False, "error": "محتوای ورودی فاقد ساختار معتبر SVG است."}

        rect_count = len(re.findall(r"<rect\b", svg_content, re.IGNORECASE))
        circle_count = len(re.findall(r"<circle\b", svg_content, re.IGNORECASE))
        path_count = len(re.findall(r"<path\b", svg_content, re.IGNORECASE))
        text_count = len(re.findall(r"<text\b", svg_content, re.IGNORECASE))

        has_persian = bool(re.search(r"[\u0600-\u06FF]", svg_content))

        return {
            "valid": True,
            "element_counts": {
                "rectangles": rect_count,
                "circles": circle_count,
                "paths": path_count,
                "text_labels": text_count,
            },
            "has_persian_text": has_persian,
            "total_visual_elements": rect_count + circle_count + path_count + text_count,
            "summary_fa": (
                f"فایل SVG شامل {rect_count} مستطیل، {circle_count} دایره و "
                f"{text_count} برچسب متنی است."
            ),
        }
