"""Comprehensive unit and integration test suite for Multi-Modal Vision & Video Subsystem."""

from __future__ import annotations

import pytest

from dream.tools.toolsets import get_toolset
from dream.vision.diagram_inspector import DiagramInspector
from dream.vision.keyframe_extractor import KeyframeExtractor
from dream.vision.slash import handle_vision_command
from dream.vision.spatial_memory import SpatialMemory
from dream.vision.tools import (
    get_vision_tools,
    reset_global_vision_engine,
    vision_analyze_image,
    vision_decompose_video,
    vision_diff_visual_states,
    vision_get_metrics,
    vision_ground_ui_elements,
    vision_inspect_diagram,
    vision_query_spatial_memory,
    vision_reset,
)
from dream.vision.types import (
    BoundingBox,
    ElementType,
    SpatialEntity,
    SpatialRelationType,
)
from dream.vision.ui_grounder import UIGrounder


@pytest.fixture(autouse=True)
def cleanup_vision() -> None:
    reset_global_vision_engine()
    yield
    reset_global_vision_engine()


def test_toolset_includes_vision() -> None:
    """Verify vision toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("vision")
    assert ts is not None
    assert ts.name == "vision"
    assert "vision_analyze_image" in ts.tools
    assert "vision_decompose_video" in ts.tools
    assert "vision_ground_ui_elements" in ts.tools
    assert "vision_inspect_diagram" in ts.tools
    assert "vision_diff_visual_states" in ts.tools


def test_keyframe_extractor_and_video_timeline() -> None:
    """Test video keyframe sampling and scene change detection."""
    extractor = KeyframeExtractor()

    # 1. Simulated video stream
    timeline = extractor.extract_from_simulated_video(
        video_id="vid-test-01",
        duration_sec=8.0,
        fps=30.0,
        scene_changes_at_sec=[3.0, 6.0],
    )
    assert timeline.video_id == "vid-test-01"
    assert timeline.duration_sec == 8.0
    assert len(timeline.keyframes) == 8
    assert timeline.scene_count >= 2
    assert "صحنه" in timeline.narrative_summary_fa

    # 2. Raw stream frame extraction
    raw_frames = [b"frame_data_chunk_001", b"frame_data_chunk_002", b"totally_new_scene_003"]
    tl_raw = extractor.extract_from_stream("vid-stream", raw_frames, fps=10.0, sample_stride=1)
    assert len(tl_raw.keyframes) == 3


def test_ui_grounder_and_action_sequence() -> None:
    """Test UI interactive element coordinate grounding and action planning."""
    grounder = UIGrounder()
    specs = [
        {
            "id": "btn-login",
            "label_fa": "دکمه ورود",
            "type": "button",
            "box": {"ymin": 0.7, "xmin": 0.4, "ymax": 0.78, "xmax": 0.6},
            "interactive": True,
        },
        {
            "id": "inp-user",
            "label_fa": "نام کاربری",
            "type": "input_field",
            "box": {"ymin": 0.4, "xmin": 0.3, "ymax": 0.48, "xmax": 0.7},
            "interactive": True,
        },
    ]

    elements = grounder.ground_elements_from_descriptors(specs)
    assert len(elements) == 2
    assert elements[0].element_type == ElementType.BUTTON
    assert elements[0].box.center_x == 0.5

    # Text search
    found = grounder.find_element_by_text(elements, "ورود")
    assert found is not None
    assert found.element_id == "btn-login"

    # Action planning
    actions = grounder.propose_action_sequence(elements, "ورود به حساب کاربری")
    assert len(actions) == 2
    assert actions[0]["action"] == "type"
    assert actions[1]["action"] == "click"


def test_diagram_and_svg_inspector() -> None:
    """Test structural analysis of Mermaid diagrams and SVG visual files."""
    inspector = DiagramInspector()

    # Mermaid
    mermaid_code = """
    graph TD
        ورود --> داشبورد
        داشبورد --> گزارش
    """
    res_m = inspector.inspect_mermaid_source(mermaid_code)
    assert res_m["valid"] is True
    assert res_m["diagram_type"] == "graph"
    assert res_m["has_persian_text"] is True
    assert res_m["total_nodes"] >= 3

    # SVG
    svg_code = """
    <svg viewBox="0 0 100 100">
        <rect x="10" y="10" width="80" height="80" fill="blue"/>
        <circle cx="50" cy="50" r="30" fill="red"/>
        <text x="50" y="50">سلام دریم</text>
    </svg>
    """
    res_svg = inspector.inspect_svg_elements(svg_code)
    assert res_svg["valid"] is True
    assert res_svg["element_counts"]["rectangles"] == 1
    assert res_svg["element_counts"]["circles"] == 1
    assert res_svg["has_persian_text"] is True


def test_spatial_memory_and_visual_diffing() -> None:
    """Test spatial relationship reasoning and before/after visual diffs."""
    sm = SpatialMemory()

    ent_left = sm.register_entity(
        label_fa="منوی کناری",
        category="navigation",
        box=BoundingBox(ymin=0.0, xmin=0.0, ymax=1.0, xmax=0.2),
    )
    ent_right = sm.register_entity(
        label_fa="محتوای اصلی",
        category="panel",
        box=BoundingBox(ymin=0.0, xmin=0.25, ymax=1.0, xmax=1.0),
    )

    relations = sm.compute_relation(ent_left, ent_right)
    assert SpatialRelationType.LEFT_OF in relations

    # Visual Diffing
    before = [ent_left, ent_right]
    ent_modal = SpatialEntity(
        entity_id="modal-1",
        label_fa="پنجره پیام",
        category="modal",
        box=BoundingBox(ymin=0.3, xmin=0.3, ymax=0.7, xmax=0.7),
    )
    after = [ent_left, ent_right, ent_modal]

    diff = sm.compare_visual_states(before, after)
    assert diff.has_significant_change is True
    assert "پنجره پیام" in diff.added_elements


def test_vision_engine_and_tools() -> None:
    """Test master VisionEngine, LLM tools, and slash commands."""
    tools = get_vision_tools()
    assert len(tools) >= 5

    # 1. Image analysis tool
    res_img = vision_analyze_image(
        image_descriptor="یک نمودار جریان داده",
        detected_objects=[
            {"label_fa": "داده", "box": {"ymin": 0.1, "xmin": 0.1, "ymax": 0.5, "xmax": 0.5}}
        ],
    )
    assert res_img["success"] is True
    assert res_img["total_objects_detected"] == 1

    # 2. Video decomposition tool
    res_vid = vision_decompose_video(video_id="video-01", duration_sec=5.0)
    assert res_vid["success"] is True
    assert res_vid["duration_sec"] == 5.0

    # 3. Grounding tool
    res_gr = vision_ground_ui_elements(
        elements=[
            {
                "label_fa": "دکمه لغو",
                "box": {"ymin": 0.8, "xmin": 0.1, "ymax": 0.9, "xmax": 0.3},
            }
        ],
        intent_fa="لغو عملیات",
    )
    assert res_gr["success"] is True

    # 4. Diagram tool
    res_diag = vision_inspect_diagram(content="graph LR\nA-->B", diagram_format="mermaid")
    assert res_diag["valid"] is True

    # 5. Diff tool
    res_diff = vision_diff_visual_states(
        before_state=[{"label_fa": "دکمه ۱"}],
        after_state=[{"label_fa": "دکمه ۱"}, {"label_fa": "دکمه ۲"}],
    )
    assert res_diff["success"] is True
    assert "دکمه ۲" in res_diff["added_elements"]

    # 6. Spatial query tool
    res_sp = vision_query_spatial_memory()
    assert res_sp["success"] is True

    # 7. Metrics tool
    res_m = vision_get_metrics()
    assert res_m["success"] is True
    assert res_m["status"] == "healthy"

    # 8. Slash commands
    s_help = handle_vision_command("")
    assert "راهنمای دستورات بینایی" in s_help

    s_ana = handle_vision_command("analyze صفحه داشبورد")
    assert "تحلیل تصویر انجام شد" in s_ana

    s_vid = handle_vision_command("video vid-10 6.0")
    assert "تجزیه جریان ویدیویی" in s_vid

    s_diag = handle_vision_command("diagram graph TD\nشروع-->پایان")
    assert "تحلیل ساختاری دیاگرام" in s_diag

    s_mem = handle_vision_command("memory")
    assert "حافظه مکانی" in s_mem

    s_met = handle_vision_command("metrics")
    assert "تله‌متری سامانه بینایی" in s_met

    s_res = handle_vision_command("reset")
    assert "بازنشانی شد" in s_res

    # Tool reset
    t_res = vision_reset()
    assert t_res["success"] is True
