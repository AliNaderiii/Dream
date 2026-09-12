"""Unit and integration tests for Multi-Modal Interactive Canvas & Artifact Studio."""

from __future__ import annotations

import pytest

from dream.canvas import (
    ArtifactType,
    CanvasEngine,
    canvas_create_artifact,
    canvas_diff_versions,
    canvas_get_status,
    canvas_list_artifacts,
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
        description_fa="نمودار معماری",
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

    svg_content = (
        '<svg width="100" height="100">'
        '<circle cx="50" cy="50" r="40" fill="blue"/></svg>'
    )
    art_svg = engine.create_artifact(
        title="نمودار دایره‌ای",
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
    assert "# 🎨" in bundle_md
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
    assert "وضعیت بوم" in slash_st

    # Slash: /canvas reset
    slash_reset = handle_canvas_slash_command("/canvas reset")
    assert "بازنشانی شد" in slash_reset
