"""Standalone HTML preview renderer with Persian typography and zero external dependencies."""

from __future__ import annotations

import html
import json
from typing import Any

from dream.canvas.types import ArtifactType, CanvasArtifact


class CanvasRenderer:
    """Renders visual artifacts into safe, standalone HTML packages."""

    @staticmethod
    def render_to_standalone_html(
        artifact: CanvasArtifact,
        theme: str = "dark",
    ) -> str:
        """Generate a complete, self-contained HTML page for the artifact."""
        bg_color = "#0f172a" if theme == "dark" else "#f8fafc"
        text_color = "#f1f5f9" if theme == "dark" else "#0f172a"
        card_bg = "#1e293b" if theme == "dark" else "#ffffff"
        border_color = "#334155" if theme == "dark" else "#e2e8f0"
        header_bg = "#0284c7"

        # Determine rendered body based on type
        body_content = ""
        is_rtl = any("\u0600" <= c <= "\u06ff" for c in artifact.content) or any(
            "\u0600" <= c <= "\u06ff" for c in artifact.title
        )
        dir_attr = 'dir="rtl"' if is_rtl else 'dir="ltr"'

        escaped_title = html.escape(artifact.title)
        escaped_content = html.escape(artifact.content)

        if artifact.artifact_type == ArtifactType.HTML:
            body_content = f"""
            <div class="preview-box">
                {artifact.content}
            </div>
            """
        elif artifact.artifact_type == ArtifactType.SVG:
            body_content = f"""
            <div class="svg-container" style="display: flex; justify-content: center; padding: 24px;">
                {artifact.content}
            </div>
            """
        elif artifact.artifact_type == ArtifactType.MERMAID:
            body_content = f"""
            <div class="mermaid-diagram">
                <pre class="code-block" style="background:#000; color:#38bdf8; padding:16px; border-radius:8px;"><code>{escaped_content}</code></pre>
                <div style="font-size: 13px; color: #94a3b8; margin-top: 8px;">
                    \U0001f4ca \u0646\u0645\u0648\u062f\u0627\u0631 Mermaid (Rendered via Engine)
                </div>
            </div>
            """
        elif artifact.artifact_type == ArtifactType.CSV:
            # Simple tabular rendering for CSV
            lines = [line for line in artifact.content.strip().splitlines() if line]
            table_html = "<table style='width:100%; border-collapse:collapse;'>"
            if lines:
                headers = [h.strip() for h in lines[0].split(",")]
                table_html += (
                    "<thead><tr style='background:rgba(56,189,248,0.15); font-weight:bold;'>"
                )
                for h in headers:
                    table_html += f"<th style='padding:8px; border:1px solid {border_color}; text-align:inherit;'>{html.escape(h)}</th>"
                table_html += "</tr></thead><tbody>"

                for row in lines[1:]:
                    table_html += "<tr>"
                    for cell in row.split(","):
                        table_html += f"<td style='padding:8px; border:1px solid {border_color};'>{html.escape(cell.strip())}</td>"
                    table_html += "</tr>"
                table_html += "</tbody></table>"
            body_content = table_html
        else:
            # Code or generic text
            lang_label = (
                artifact.language
                if artifact.language
                else artifact.artifact_type.value
            )
            body_content = f"""
            <div class="code-container">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px; font-size:12px; color:#94a3b8;">
                    <span>\u0632\u0628\u0627\u0646: {lang_label}</span>
                    <span>\u0646\u0633\u062e\u0647 {artifact.version}</span>
                </div>
                <pre class="code-block" style="background:#030712; color:#e2e8f0; padding:16px; border-radius:8px; overflow-x:auto; font-family:Consolas, Monaco, monospace; font-size:13px; line-height:1.5;"><code>{escaped_content}</code></pre>
            </div>
            """

        page = f"""<!DOCTYPE html>
<html lang="fa" {dir_attr}>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escaped_title} - Dream Artifact Studio</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Vazirmatn", Tahoma, sans-serif;
            background-color: {bg_color};
            color: {text_color};
            margin: 0;
            padding: 24px;
            box-sizing: border-box;
        }}
        .artifact-card {{
            max-width: 900px;
            margin: 0 auto;
            background-color: {card_bg};
            border: 1px solid {border_color};
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            overflow: hidden;
        }}
        .artifact-header {{
            background: linear-gradient(135deg, {header_bg}, #4f46e5);
            color: white;
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .artifact-title {{
            font-size: 18px;
            font-weight: 700;
            margin: 0;
        }}
        .artifact-badge {{
            background: rgba(255, 255, 255, 0.2);
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }}
        .artifact-body {{
            padding: 20px;
        }}
        .artifact-footer {{
            border-top: 1px solid {border_color};
            padding: 12px 20px;
            font-size: 12px;
            color: #94a3b8;
            display: flex;
            justify-content: space-between;
        }}
    </style>
</head>
<body>
    <div class="artifact-card">
        <div class="artifact-header">
            <h1 class="artifact-title">{escaped_title}</h1>
            <span class="artifact-badge">{artifact.artifact_type.value.upper()} (v{artifact.version})</span>
        </div>
        <div class="artifact-body">
            {body_content}
        </div>
        <div class="artifact-footer">
            <span>\u0634\u0646\u0627\u0633\u0647 \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a: {artifact.id}</span>
            <span>Dream Visual Artifact Studio \u2022 v{artifact.version}</span>
        </div>
    </div>
</body>
</html>"""
        return page

    @staticmethod
    def render_to_markdown_bundle(artifacts: list[CanvasArtifact]) -> str:
        """Compile multiple artifacts into a structured Markdown document."""
        lines = [
            "# \U0001f3a8 \u0628\u0633\u062a\u0647 \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627\u06cc \u0628\u0648\u0645 \u062a\u0639\u0627\u0645\u0644\u06cc Dream",
            f"- \u062a\u0639\u062f\u0627\u062f \u06a9\u0644 \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627: {len(artifacts)}",
            "",
        ]

        for i, art in enumerate(artifacts, 1):
            lines.append(f"## {i}. {art.title} (`{art.id}`)")
            lines.append(f"- **\u0646\u0648\u0639:** `{art.artifact_type.value}` | **\u0646\u0633\u062e\u0647:** `v{art.version}`")
            if art.description_fa:
                lines.append(f"- **\u062a\u0648\u0636\u06cc\u062d\u0627\u062a:** {art.description_fa}")
            lines.append("")
            lang = art.language or art.artifact_type.value
            lines.append(f"```{lang}\n{art.content}\n```")
            lines.append("")

        return "\n".join(lines)
