#!/usr/bin/env python3
"""Phase 33: Multi-Modal Interactive Canvas & Visual Artifact Studio Subsystem.

Applies all modules for Phase 33:
- dream/canvas/types.py
- dream/canvas/versioning.py
- dream/canvas/renderer.py
- dream/canvas/engine.py
- dream/canvas/tools.py
- dream/canvas/slash.py
- dream/canvas/__init__.py
- dream/tools/toolsets.py (registered canvas toolset)
- tests/test_canvas_and_artifacts.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

FILES: dict[str, str] = {
    "dream/canvas/types.py": r'''"""Domain models and data structures for Interactive Canvas and Visual Artifact Studio."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class ArtifactType(str, Enum):
    """Supported artifact formats and interactive components."""

    CODE = "code"
    MARKDOWN = "markdown"
    HTML = "html"
    SVG = "svg"
    MERMAID = "mermaid"
    JSON = "json"
    CSV = "csv"
    REACT_JSX = "react_jsx"
    DIAGRAM = "diagram"


class CanvasExportFormat(str, Enum):
    """Output bundle formats for canvas sessions."""

    HTML_STANDALONE = "html"
    MARKDOWN_BUNDLE = "markdown"
    JSON = "json"


@dataclass(slots=True)
class ArtifactVersion:
    """Historical snapshot of an artifact at a point in time."""

    version_number: int
    content: str
    diff_summary: str = ""
    timestamp: float = field(default_factory=time.time)
    author: str = "assistant"

    def to_dict(self) -> dict[str, Any]:
        """Serialize artifact version to dictionary."""
        return {
            "version_number": self.version_number,
            "content": self.content,
            "diff_summary": self.diff_summary,
            "timestamp": round(self.timestamp, 2),
            "author": self.author,
        }


@dataclass(slots=True)
class CanvasArtifact:
    """Core artifact entity representing code, documentation, or interactive UI."""

    id: str
    title: str
    artifact_type: ArtifactType
    content: str
    language: str = ""
    version: int = 1
    versions: list[ArtifactVersion] = field(default_factory=list)
    description_fa: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize canvas artifact to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "artifact_type": self.artifact_type.value,
            "content": self.content,
            "language": self.language,
            "version": self.version,
            "versions_count": len(self.versions),
            "description_fa": self.description_fa,
            "metadata": self.metadata,
            "created_at": round(self.created_at, 2),
            "updated_at": round(self.updated_at, 2),
        }


@dataclass(slots=True)
class CanvasSession:
    """Container holding active artifacts and visual studio state."""

    session_id: str
    name: str = "default_canvas"
    artifacts: dict[str, CanvasArtifact] = field(default_factory=dict)
    active_artifact_id: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize canvas session to dictionary."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "total_artifacts": len(self.artifacts),
            "active_artifact_id": self.active_artifact_id,
            "created_at": round(self.created_at, 2),
            "updated_at": round(self.updated_at, 2),
        }
''',
    "dream/canvas/versioning.py": r'''"""Artifact version control, differential computation, and branching."""

from __future__ import annotations

import difflib
import time
from typing import Any
import uuid

from dream.canvas.types import ArtifactVersion, CanvasArtifact


class ArtifactVersionManager:
    """Manages version evolution, diff calculation, and history rollbacks."""

    @staticmethod
    def compute_diff(old_content: str, new_content: str) -> str:
        """Calculate unified line-by-line diff between two text versions."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="v_previous",
            tofile="v_current",
            lineterm="",
        )
        return "".join(diff)

    def record_update(
        self,
        artifact: CanvasArtifact,
        new_content: str,
        diff_summary: str = "",
        author: str = "assistant",
    ) -> CanvasArtifact:
        """Append current state to version history and apply new content."""
        if not artifact.versions:
            # Seed version 1 snapshot
            artifact.versions.append(
                ArtifactVersion(
                    version_number=artifact.version,
                    content=artifact.content,
                    diff_summary="\u0646\u0633\u062e\u0647 \u0627\u0648\u0644\u06cc\u0647",
                    timestamp=artifact.created_at,
                    author=author,
                )
            )

        new_version_num = artifact.version + 1
        calculated_diff = diff_summary or f"Update to v{new_version_num}"

        new_snapshot = ArtifactVersion(
            version_number=new_version_num,
            content=new_content,
            diff_summary=calculated_diff,
            timestamp=time.time(),
            author=author,
        )

        artifact.versions.append(new_snapshot)
        artifact.content = new_content
        artifact.version = new_version_num
        artifact.updated_at = time.time()
        return artifact

    def revert_to_version(
        self,
        artifact: CanvasArtifact,
        target_version: int,
    ) -> CanvasArtifact:
        """Rollback artifact content to a previous version and record rollback."""
        matched = next((v for v in artifact.versions if v.version_number == target_version), None)
        if not matched:
            raise ValueError(f"Version {target_version} does not exist in artifact history.")

        return self.record_update(
            artifact=artifact,
            new_content=matched.content,
            diff_summary=f"\u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc \u0628\u0647 \u0646\u0633\u062e\u0647 {target_version}",
        )

    def fork_artifact(
        self,
        artifact: CanvasArtifact,
        new_title: str | None = None,
    ) -> CanvasArtifact:
        """Create an independent fork/branch of an existing artifact."""
        fork_id = f"art-{uuid.uuid4().hex[:8]}"
        title = new_title or f"{artifact.title} (\u0627\u0646\u0634\u0639\u0627\u0628)"
        now = time.time()
        initial_v = ArtifactVersion(
            version_number=1,
            content=artifact.content,
            diff_summary=f"\u0627\u0646\u0634\u0639\u0627\u0628 \u0627\u0632 {artifact.id} (v{artifact.version})",
            timestamp=now,
        )
        return CanvasArtifact(
            id=fork_id,
            title=title,
            artifact_type=artifact.artifact_type,
            content=artifact.content,
            language=artifact.language,
            version=1,
            versions=[initial_v],
            description_fa=artifact.description_fa,
            metadata=dict(artifact.metadata),
            created_at=now,
            updated_at=now,
        )
''',
    "dream/canvas/renderer.py": r'''"""Standalone HTML preview renderer with Persian typography and zero external dependencies."""

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
''',
    "dream/canvas/engine.py": r'''"""Core coordinator for Canvas Artifact Studio, session tracking, and rendering."""

from __future__ import annotations

import json
import time
from typing import Any
import uuid

from dream.canvas.renderer import CanvasRenderer
from dream.canvas.types import (
    ArtifactType,
    ArtifactVersion,
    CanvasArtifact,
    CanvasExportFormat,
    CanvasSession,
)
from dream.canvas.versioning import ArtifactVersionManager


class CanvasEngine:
    """Coordinates active canvas artifacts, multi-version tracking, and visual exports."""

    def __init__(
        self,
        session_id: str | None = None,
        version_manager: ArtifactVersionManager | None = None,
        renderer: CanvasRenderer | None = None,
    ) -> None:
        self.session_id = session_id or f"canvas-{uuid.uuid4().hex[:6]}"
        self.version_manager = version_manager or ArtifactVersionManager()
        self.renderer = renderer or CanvasRenderer()
        self.session = CanvasSession(session_id=self.session_id)

    def create_artifact(
        self,
        title: str,
        artifact_type: str | ArtifactType,
        content: str,
        language: str = "",
        description_fa: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CanvasArtifact:
        """Create a new canvas artifact and set as active."""
        if isinstance(artifact_type, str):
            try:
                art_enum = ArtifactType(artifact_type.lower())
            except ValueError:
                art_enum = ArtifactType.CODE
        else:
            art_enum = artifact_type

        art_id = f"art-{uuid.uuid4().hex[:6]}"
        now = time.time()
        initial_v = ArtifactVersion(
            version_number=1,
            content=content,
            diff_summary="\u0646\u0633\u062e\u0647 \u0627\u0648\u0644\u06cc\u0647",
            timestamp=now,
        )

        artifact = CanvasArtifact(
            id=art_id,
            title=title,
            artifact_type=art_enum,
            content=content,
            language=language or ("python" if art_enum == ArtifactType.CODE else ""),
            version=1,
            versions=[initial_v],
            description_fa=description_fa,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

        self.session.artifacts[art_id] = artifact
        self.session.active_artifact_id = art_id
        self.session.updated_at = now
        return artifact

    def update_artifact(
        self,
        artifact_id: str,
        content: str,
        diff_summary: str = "",
    ) -> CanvasArtifact:
        """Update artifact content, appending a new version to its history."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found in canvas session.")

        updated = self.version_manager.record_update(
            artifact=art,
            new_content=content,
            diff_summary=diff_summary,
        )
        self.session.active_artifact_id = artifact_id
        self.session.updated_at = time.time()
        return updated

    def get_artifact(
        self,
        artifact_id: str,
        version: int | None = None,
    ) -> CanvasArtifact | None:
        """Retrieve artifact by ID, optionally scoped to a specific historical version."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            return None

        if version is not None and version != art.version:
            matched_v = next((v for v in art.versions if v.version_number == version), None)
            if matched_v:
                # Return snapshot clone
                return CanvasArtifact(
                    id=art.id,
                    title=f"{art.title} (v{version})",
                    artifact_type=art.artifact_type,
                    content=matched_v.content,
                    language=art.language,
                    version=matched_v.version_number,
                    versions=list(art.versions),
                    description_fa=art.description_fa,
                    metadata=dict(art.metadata),
                    created_at=art.created_at,
                    updated_at=matched_v.timestamp,
                )
        return art

    def list_artifacts(self) -> list[CanvasArtifact]:
        """List all artifacts currently managed in the session."""
        return list(self.session.artifacts.values())

    def delete_artifact(self, artifact_id: str) -> bool:
        """Remove an artifact from the session."""
        if artifact_id in self.session.artifacts:
            del self.session.artifacts[artifact_id]
            if self.session.active_artifact_id == artifact_id:
                self.session.active_artifact_id = (
                    next(iter(self.session.artifacts.keys()), None)
                    if self.session.artifacts
                    else None
                )
            return True
        return False

    def fork_artifact(
        self,
        artifact_id: str,
        new_title: str | None = None,
    ) -> CanvasArtifact:
        """Branch an existing artifact into a new independent version tree."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found.")

        forked = self.version_manager.fork_artifact(art, new_title=new_title)
        self.session.artifacts[forked.id] = forked
        self.session.active_artifact_id = forked.id
        return forked

    def revert_artifact(
        self,
        artifact_id: str,
        target_version: int,
    ) -> CanvasArtifact:
        """Rollback artifact to an earlier version."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found.")

        reverted = self.version_manager.revert_to_version(art, target_version)
        self.session.updated_at = time.time()
        return reverted

    def diff_artifact_versions(
        self,
        artifact_id: str,
        v_from: int | None = None,
        v_to: int | None = None,
    ) -> str:
        """Calculate line-by-line diff between two versions of an artifact."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found.")

        v_from_num = v_from if v_from is not None else (art.version - 1 if art.version > 1 else 1)
        v_to_num = v_to if v_to is not None else art.version

        c_from = next((v.content for v in art.versions if v.version_number == v_from_num), "")
        c_to = next((v.content for v in art.versions if v.version_number == v_to_num), art.content)

        return self.version_manager.compute_diff(c_from, c_to)

    def render_preview(
        self,
        artifact_id: str,
        theme: str = "dark",
    ) -> str:
        """Render single artifact as standalone HTML."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found.")
        return self.renderer.render_to_standalone_html(art, theme=theme)

    def export_bundle(self, format_type: str = "html") -> str:
        """Export all session artifacts as Markdown or JSON."""
        artifacts = list(self.session.artifacts.values())
        if format_type.lower() == "json":
            return json.dumps(
                {
                    "session": self.session.to_dict(),
                    "artifacts": [a.to_dict() for a in artifacts],
                },
                ensure_ascii=False,
                indent=2,
            )
        return self.renderer.render_to_markdown_bundle(artifacts)

    def reset(self) -> None:
        """Clear all session artifacts."""
        self.session.artifacts.clear()
        self.session.active_artifact_id = None
        self.session.updated_at = time.time()

    def get_status(self) -> dict[str, Any]:
        """Return operational summary of canvas session."""
        return {
            "session_id": self.session.session_id,
            "total_artifacts": len(self.session.artifacts),
            "active_artifact_id": self.session.active_artifact_id,
            "artifacts_summary": [
                {
                    "id": a.id,
                    "title": a.title,
                    "type": a.artifact_type.value,
                    "version": a.version,
                }
                for a in self.session.artifacts.values()
            ],
        }
''',
    "dream/canvas/tools.py": r'''"""LLM tool bindings for Interactive Canvas & Visual Artifact Studio."""

from __future__ import annotations

from typing import Any

from dream.canvas.engine import CanvasEngine

_GLOBAL_CANVAS_ENGINE: CanvasEngine | None = None


def get_global_canvas_engine() -> CanvasEngine:
    """Get or initialize singleton CanvasEngine."""
    global _GLOBAL_CANVAS_ENGINE
    if _GLOBAL_CANVAS_ENGINE is None:
        _GLOBAL_CANVAS_ENGINE = CanvasEngine()
    return _GLOBAL_CANVAS_ENGINE


def reset_global_canvas_engine() -> None:
    """Reset singleton CanvasEngine."""
    global _GLOBAL_CANVAS_ENGINE
    _GLOBAL_CANVAS_ENGINE = None


def canvas_create_artifact(
    title: str,
    artifact_type: str,
    content: str,
    language: str = "",
    description_fa: str = "",
) -> dict[str, Any]:
    """Create a new interactive visual artifact (code, HTML, SVG, Mermaid diagram, markdown)."""
    engine = get_global_canvas_engine()
    try:
        art = engine.create_artifact(
            title=title,
            artifact_type=artifact_type,
            content=content,
            language=language,
            description_fa=description_fa,
        )
        return {
            "success": True,
            "artifact": art.to_dict(),
            "message": f"\u0622\u0631\u062a\u06cc\u0641\u06a9\u062a '{art.title}' ({art.id}) \u0627\u06cc\u062c\u0627\u062f \u0634\u062f.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def canvas_update_artifact(
    artifact_id: str,
    content: str,
    diff_summary: str = "",
) -> dict[str, Any]:
    """Update artifact with new content, saving the old version into revision history."""
    engine = get_global_canvas_engine()
    try:
        updated = engine.update_artifact(
            artifact_id=artifact_id,
            content=content,
            diff_summary=diff_summary,
        )
        return {
            "success": True,
            "artifact": updated.to_dict(),
            "message": f"\u0622\u0631\u062a\u06cc\u0641\u06a9\u062a '{updated.title}' \u0628\u0647 \u0646\u0633\u062e\u0647 v{updated.version} \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u0634\u062f.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def canvas_get_artifact(
    artifact_id: str,
    version: int | None = None,
) -> dict[str, Any]:
    """Retrieve artifact content and metadata, optionally for a specific version."""
    engine = get_global_canvas_engine()
    art = engine.get_artifact(artifact_id, version=version)
    if not art:
        return {"success": False, "error": f"Artifact '{artifact_id}' not found."}
    return {"success": True, "artifact": art.to_dict()}


def canvas_list_artifacts() -> dict[str, Any]:
    """List all artifacts in the current canvas session."""
    engine = get_global_canvas_engine()
    artifacts = engine.list_artifacts()
    return {"success": True, "artifacts": [a.to_dict() for a in artifacts]}


def canvas_diff_versions(
    artifact_id: str,
    v_from: int | None = None,
    v_to: int | None = None,
) -> dict[str, Any]:
    """Inspect line-by-line differences between two versions of an artifact."""
    engine = get_global_canvas_engine()
    try:
        diff_str = engine.diff_artifact_versions(artifact_id, v_from=v_from, v_to=v_to)
        return {"success": True, "diff": diff_str}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def canvas_render_preview(
    artifact_id: str,
    theme: str = "dark",
) -> dict[str, Any]:
    """Render standalone HTML preview for an artifact."""
    engine = get_global_canvas_engine()
    try:
        html_page = engine.render_preview(artifact_id, theme=theme)
        return {"success": True, "html": html_page}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def canvas_export_bundle(
    format_type: str = "markdown",
) -> dict[str, Any]:
    """Export all artifacts in the canvas as a markdown bundle or JSON."""
    engine = get_global_canvas_engine()
    try:
        bundle = engine.export_bundle(format_type=format_type)
        return {"success": True, "format": format_type, "bundle": bundle}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def canvas_reset_session() -> dict[str, Any]:
    """Reset canvas session and delete all artifacts."""
    engine = get_global_canvas_engine()
    engine.reset()
    return {"success": True, "message": "\u0628\u0648\u0645 \u062a\u0639\u0627\u0645\u0644\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."}


def canvas_get_status() -> dict[str, Any]:
    """Get status and metrics of the current canvas session."""
    engine = get_global_canvas_engine()
    return {"success": True, **engine.get_status()}


def get_canvas_tools() -> list[Any]:
    """Return canvas tool functions for agent registration."""
    return [
        canvas_create_artifact,
        canvas_update_artifact,
        canvas_get_artifact,
        canvas_list_artifacts,
        canvas_diff_versions,
        canvas_render_preview,
        canvas_export_bundle,
        canvas_reset_session,
        canvas_get_status,
    ]
''',
    "dream/canvas/slash.py": r'''"""CLI and slash command handlers for Interactive Canvas & Visual Artifact Studio."""

from __future__ import annotations

from typing import Any

from dream.canvas.tools import (
    canvas_create_artifact,
    canvas_diff_versions,
    canvas_export_bundle,
    canvas_get_artifact,
    canvas_get_status,
    canvas_list_artifacts,
    canvas_reset_session,
    canvas_update_artifact,
)


def handle_canvas_slash_command(command_str: str) -> str:
    """Handle /canvas slash commands for REPL and CLI interface.

    Usage:
        /canvas list
        /canvas create <type> <title> <code>
        /canvas update <artifact_id> <code>
        /canvas view <artifact_id>
        /canvas diff <artifact_id> <v1> <v2>
        /canvas export [markdown|json]
        /canvas reset
        /canvas status
    """
    cmd = command_str.strip()
    if not cmd.startswith("/canvas"):
        return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."

    parts = cmd.split(maxsplit=2)
    if len(parts) == 1:
        # Default help
        return (
            "\U0001f3a8 \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u0628\u0648\u0645 \u062a\u0639\u0627\u0645\u0644\u06cc (Canvas):\n"
            "  /canvas list                              \u0641\u0647\u0631\u0633\u062a \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627\n"
            "  /canvas create <type> <title> <code>      \u0627\u06cc\u062c\u0627\u062f \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a \u062c\u062f\u06cc\u062f\n"
            "  /canvas view <id>                         \u0645\u0634\u0627\u0647\u062f\u0647 \u0645\u062d\u062a\u0648\u0627\n"
            "  /canvas export [markdown|json]            \u062e\u0631\u0648\u062c\u06cc \u06a9\u0644 \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627\n"
            "  /canvas status                            \u0648\u0636\u0639\u06cc\u062a \u0628\u0648\u0645\n"
            "  /canvas reset                             \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0628\u0648\u0645"
        )

    subcmd = parts[1].lower()
    args_str = parts[2] if len(parts) > 2 else ""

    if subcmd == "list":
        res = canvas_list_artifacts()
        artifacts = res.get("artifacts", [])
        if not artifacts:
            return "\U0001f4dc \u0647\u06cc\u0686 \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u06cc \u062f\u0631 \u0628\u0648\u0645 \u0641\u0639\u0644\u06cc \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f."
        lines = ["\U0001f3a8 \u0641\u0647\u0631\u0633\u062a \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627\u06cc \u0628\u0648\u0645:"]
        for a in artifacts:
            lines.append(f"- `{a['id']}`: **{a['title']}** ({a['artifact_type']}, v{a['version']})")
        return "\n".join(lines)

    if subcmd == "view":
        art_id = args_str.strip()
        if not art_id:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0634\u0646\u0627\u0633\u0647 \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = canvas_get_artifact(art_id)
        if not res.get("success"):
            return f"\u274c {res.get('error')}"
        art = res["artifact"]
        return f"### \U0001f4cb {art['title']} (`{art['id']}` - v{art['version']})\n```{art['language'] or art['artifact_type']}\n{art['content']}\n```"

    if subcmd == "export":
        fmt = args_str.strip() or "markdown"
        res = canvas_export_bundle(format_type=fmt)
        if res.get("success"):
            return res.get("bundle", "")
        return f"\u274c {res.get('error')}"

    if subcmd == "status":
        st = canvas_get_status()
        return (
            f"\U0001f4df \u0648\u0636\u0639\u06cc\u062a \u0628\u0648\u0645 \u062a\u0639\u0627\u0645\u0644\u06cc:\n"
            f"- \u0634\u0646\u0627\u0633\u0647 \u0646\u0634\u0633\u062a: {st.get('session_id')}\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a\u200c\u0647\u0627: {st.get('total_artifacts')}\n"
            f"- \u0622\u0631\u062a\u06cc\u0641\u06a9\u062a \u0641\u0639\u0627\u0644: {st.get('active_artifact_id') or '\u0647\u06cc\u0686'}"
        )

    if subcmd == "reset":
        canvas_reset_session()
        return "\u2705 \u0628\u0648\u0645 \u062a\u0639\u0627\u0645\u0644\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

    return "\u274c \u0632\u06cc\u0631\u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a. \u0628\u0631\u0627\u06cc \u0631\u0627\u0647\u0646\u0645\u0627 `/canvas` \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
''',
    "dream/canvas/__init__.py": r'''"""Multi-Modal Interactive Canvas & Visual Artifact Studio Subsystem."""

from __future__ import annotations

from dream.canvas.engine import CanvasEngine
from dream.canvas.renderer import CanvasRenderer
from dream.canvas.slash import handle_canvas_slash_command
from dream.canvas.tools import (
    canvas_create_artifact,
    canvas_diff_versions,
    canvas_export_bundle,
    canvas_get_artifact,
    canvas_get_status,
    canvas_list_artifacts,
    canvas_render_preview,
    canvas_reset_session,
    canvas_update_artifact,
    get_canvas_tools,
    get_global_canvas_engine,
    reset_global_canvas_engine,
)
from dream.canvas.types import (
    ArtifactType,
    ArtifactVersion,
    CanvasArtifact,
    CanvasExportFormat,
    CanvasSession,
)
from dream.canvas.versioning import ArtifactVersionManager

# Auto-register canvas toolset in toolset registry
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="canvas",
            description="Interactive visual artifacts, diagrams, standalone previews, and versioning.",
            tools=[
                "canvas_create_artifact",
                "canvas_update_artifact",
                "canvas_get_artifact",
                "canvas_list_artifacts",
                "canvas_diff_versions",
                "canvas_render_preview",
                "canvas_export_bundle",
                "canvas_reset_session",
                "canvas_get_status",
            ],
            metadata={"category": "canvas", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "ArtifactType",
    "ArtifactVersion",
    "ArtifactVersionManager",
    "CanvasArtifact",
    "CanvasEngine",
    "CanvasExportFormat",
    "CanvasRenderer",
    "CanvasSession",
    "canvas_create_artifact",
    "canvas_diff_versions",
    "canvas_export_bundle",
    "canvas_get_artifact",
    "canvas_get_status",
    "canvas_list_artifacts",
    "canvas_render_preview",
    "canvas_reset_session",
    "canvas_update_artifact",
    "get_canvas_tools",
    "get_global_canvas_engine",
    "handle_canvas_slash_command",
    "reset_global_canvas_engine",
]
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
    "research": Toolset(
        name="research",
        description=(
            "Autonomous multi-step deep research, evidence collection, "
            "and multi-source intelligence synthesis"
        ),
        tools=(
            "research_plan_investigation",
            "research_add_source",
            "research_synthesize_report",
            "research_run_autonomous",
            "research_export_report",
            "research_get_status",
            "research_list_sessions",
        ),
    ),
    "cache": Toolset(
        name="cache",
        description=(
            "Semantic caching, speculative pre-fetching, and token economics optimization"
        ),
        tools=(
            "cache_lookup_query",
            "cache_store_entry",
            "cache_predict_tool",
            "cache_get_economics",
            "cache_clear",
            "cache_warmup",
        ),
    ),
    "sandbox": Toolset(
        name="sandbox",
        description=(
            "Isolated Python code execution, dataset analysis, and REPL interpreter"
        ),
        tools=(
            "sandbox_execute_python",
            "sandbox_analyze_dataset",
            "sandbox_reset_session",
            "sandbox_list_artifacts",
            "sandbox_get_status",
        ),
    ),
    "canvas": Toolset(
        name="canvas",
        description=(
            "Interactive visual artifacts, diagrams, standalone previews, and versioning"
        ),
        tools=(
            "canvas_create_artifact",
            "canvas_update_artifact",
            "canvas_get_artifact",
            "canvas_list_artifacts",
            "canvas_diff_versions",
            "canvas_render_preview",
            "canvas_export_bundle",
            "canvas_reset_session",
            "canvas_get_status",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        allowed_names.update(source.keys())

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_canvas_and_artifacts.py": r'''"""Unit and integration tests for Multi-Modal Interactive Canvas & Visual Artifact Studio."""

from __future__ import annotations

import pytest

from dream.canvas import (
    ArtifactType,
    ArtifactVersionManager,
    CanvasArtifact,
    CanvasEngine,
    CanvasRenderer,
    canvas_create_artifact,
    canvas_diff_versions,
    canvas_export_bundle,
    canvas_get_artifact,
    canvas_get_status,
    canvas_list_artifacts,
    canvas_render_preview,
    canvas_reset_session,
    canvas_update_artifact,
    handle_canvas_slash_command,
    reset_global_canvas_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_canvas_engine() -> None:
    reset_global_canvas_engine()
    yield
    reset_global_canvas_engine()


def test_toolset_includes_canvas() -> None:
    """Verify canvas toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("canvas")
    assert ts is not None
    assert "canvas_create_artifact" in ts.tools
    assert "canvas_update_artifact" in ts.tools
    assert "canvas_render_preview" in ts.tools
    assert "canvas" in BUILTIN_TOOLSETS


def test_canvas_artifact_creation_and_retrieval() -> None:
    """Verify creating, querying, and deleting artifacts."""
    engine = CanvasEngine()

    art = engine.create_artifact(
        title="Dashboard Architecture",
        artifact_type=ArtifactType.MERMAID,
        content="graph TD\n  A[Client] --> B[Gateway]\n  B --> C[Agent Core]",
        description_fa="\u0646\u0645\u0648\u062f\u0627\u0631 \u0645\u0639\u0645\u0627\u0631\u06cc",
    )

    assert art.id.startswith("art-")
    assert art.version == 1
    assert art.artifact_type == ArtifactType.MERMAID
    assert len(art.versions) == 1

    fetched = engine.get_artifact(art.id)
    assert fetched is not None
    assert fetched.title == "Dashboard Architecture"

    status = engine.get_status()
    assert status["total_artifacts"] == 1
    assert status["active_artifact_id"] == art.id

    deleted = engine.delete_artifact(art.id)
    assert deleted is True
    assert engine.get_artifact(art.id) is None


def test_canvas_versioning_diff_and_revert() -> None:
    """Verify version tracking, line diffing, and rollbacks."""
    engine = CanvasEngine()

    v1_code = "def calculate_tax(amount):\n    return amount * 0.09"
    art = engine.create_artifact(
        title="Tax Engine",
        artifact_type=ArtifactType.CODE,
        content=v1_code,
        language="python",
    )

    v2_code = "def calculate_tax(amount, rate=0.09):\n    return round(amount * rate, 2)"
    updated = engine.update_artifact(
        artifact_id=art.id,
        content=v2_code,
        diff_summary="Add default rate parameter and rounding",
    )

    assert updated.version == 2
    assert len(updated.versions) == 2

    # Check diff calculation
    diff_output = engine.diff_artifact_versions(art.id, v_from=1, v_to=2)
    assert "-def calculate_tax(amount):" in diff_output
    assert "+def calculate_tax(amount, rate=0.09):" in diff_output

    # Retrieve specific snapshot v1
    v1_snap = engine.get_artifact(art.id, version=1)
    assert v1_snap is not None
    assert v1_snap.version == 1
    assert "return amount * 0.09" in v1_snap.content

    # Revert back to v1
    reverted = engine.revert_artifact(art.id, target_version=1)
    assert reverted.version == 3
    assert "return amount * 0.09" in reverted.content


def test_canvas_html_and_markdown_rendering() -> None:
    """Verify standalone HTML generation with RTL support and markdown bundles."""
    engine = CanvasEngine()

    svg_content = '<svg width="100" height="100"><circle cx="50" cy="50" r="40" fill="blue"/></svg>'
    art_svg = engine.create_artifact(
        title="\u0646\u0645\u0648\u062f\u0627\u0631 \u062f\u0627\u06cc\u0631\u0647\u200c\u0627\u06cc",
        artifact_type=ArtifactType.SVG,
        content=svg_content,
    )

    preview_html = engine.render_preview(art_svg.id, theme="dark")
    assert "<!DOCTYPE html>" in preview_html
    assert 'dir="rtl"' in preview_html
    assert "<circle cx=" in preview_html
    assert "Dream Artifact Studio" in preview_html

    # Test markdown bundle export
    bundle_md = engine.export_bundle(format_type="markdown")
    assert "# \U0001f3a8" in bundle_md
    assert art_svg.id in bundle_md


def test_canvas_fork_and_session_export() -> None:
    """Verify artifact branching/forking and JSON session serialization."""
    engine = CanvasEngine()

    art = engine.create_artifact(
        title="Prompt Template",
        artifact_type=ArtifactType.MARKDOWN,
        content="# System Prompt\nYou are Dream.",
    )

    forked = engine.fork_artifact(art.id, new_title="Prompt Template (V2 Branch)")
    assert forked.id != art.id
    assert forked.title == "Prompt Template (V2 Branch)"
    assert forked.version == 1

    json_bundle = engine.export_bundle(format_type="json")
    assert '"total_artifacts": 2' in json_bundle
    assert art.id in json_bundle
    assert forked.id in json_bundle


def test_canvas_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /canvas CLI slash commands."""
    # Tool: create artifact
    res_create = canvas_create_artifact(
        title="Pricing Algorithm",
        artifact_type="code",
        content="x = 100",
        language="python",
    )
    assert res_create["success"] is True
    art_id = res_create["artifact"]["id"]

    # Tool: update artifact
    res_update = canvas_update_artifact(
        artifact_id=art_id,
        content="x = 200",
        diff_summary="Double price",
    )
    assert res_update["success"] is True
    assert res_update["artifact"]["version"] == 2

    # Tool: diff
    res_diff = canvas_diff_versions(art_id, v_from=1, v_to=2)
    assert res_diff["success"] is True
    assert "-x = 100" in res_diff["diff"]
    assert "+x = 200" in res_diff["diff"]

    # Tool: list & status
    res_list = canvas_list_artifacts()
    assert res_list["success"] is True
    assert len(res_list["artifacts"]) == 1

    res_st = canvas_get_status()
    assert res_st["success"] is True
    assert res_st["total_artifacts"] == 1

    # Slash: /canvas list
    slash_list = handle_canvas_slash_command("/canvas list")
    assert "Pricing Algorithm" in slash_list

    # Slash: /canvas view
    slash_view = handle_canvas_slash_command(f"/canvas view {art_id}")
    assert "x = 200" in slash_view

    # Slash: /canvas status
    slash_st = handle_canvas_slash_command("/canvas status")
    assert "\u0648\u0636\u0639\u06cc\u062a \u0628\u0648\u0645" in slash_st

    # Slash: /canvas reset
    slash_reset = handle_canvas_slash_command("/canvas reset")
    assert "\u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f" in slash_reset
''',
}


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root / "dream").exists():
        if (root / "dream-repo" / "dream").exists():
            root = root / "dream-repo"
        elif (Path.cwd() / "dream").exists():
            root = Path.cwd()
        else:
            print(f"Error: could not locate Dream repo root from {root}")
            sys.exit(1)

    print(f"Applying Phase 33 (Interactive Canvas & Visual Artifact Studio) to: {root}")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [written] {rel_path}")

    print("\nRunning pytest validation...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_canvas_and_artifacts.py", "-v"],
        cwd=root,
    )
    if res.returncode != 0:
        print("\n[FAIL] Pytest failed for Phase 33")
        sys.exit(res.returncode)

    print("\nRunning security audit...")
    audit_res = subprocess.run(
        [sys.executable, "tools/security_audit.py"],
        cwd=root,
    )
    if audit_res.returncode != 0:
        print("\n[FAIL] Security audit failed for Phase 33")
        sys.exit(audit_res.returncode)

    print("\n[SUCCESS] Phase 33 (Interactive Canvas & Visual Artifact Studio) applied and verified cleanly!")


if __name__ == "__main__":
    main()
