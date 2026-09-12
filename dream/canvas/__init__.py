"""Multi-Modal Interactive Canvas & Visual Artifact Studio Subsystem."""

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
            description=(
                "Interactive visual artifacts, diagrams, standalone "
                "previews, and versioning."
            ),
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
