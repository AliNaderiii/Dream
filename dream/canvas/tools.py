"""LLM tool bindings for Interactive Canvas & Visual Artifact Studio."""

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
    """Create a new interactive visual artifact (code, HTML, SVG, Mermaid diagram)."""
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
            "message": f"آرتیفکت '{art.title}' ({art.id}) ایجاد شد.",
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
            "message": f"آرتیفکت '{updated.title}' به نسخه v{updated.version} به‌روزرسانی شد.",
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
    return {"success": True, "message": "بوم تعاملی بازنشانی شد."}


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
