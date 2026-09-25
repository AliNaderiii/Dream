"""Tests for Desktop Multi-Modal Vision Bridge and JSON-RPC Methods."""

from __future__ import annotations

import asyncio

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.extensions import Registry
from dream.bridge.methods_vision import (
    vision_analyze_image,
    vision_decompose_video,
    vision_diff_visual_states,
    vision_get_backend_contract,
    vision_get_capabilities,
    vision_get_metrics,
    vision_ground_ui_elements,
    vision_inspect_diagram,
    vision_reset,
)
from dream.vision.engine import reset_global_vision_engine


@pytest.fixture(autouse=True)
def _clean_vision_engine():
    """Reset vision engine before and after each test."""
    reset_global_vision_engine()
    yield
    reset_global_vision_engine()


def test_vision_bridge_extension_discovery():
    """Verify vision.* methods are automatically registered in the Bridge Registry."""
    handlers = Registry.publish({})
    assert "vision.analyze_image" in handlers
    assert "vision.decompose_video" in handlers
    assert "vision.ground_ui_elements" in handlers
    assert "vision.inspect_diagram" in handlers
    assert "vision.diff_visual_states" in handlers
    assert "vision.get_metrics" in handlers
    assert "vision.get_backend_contract" in handlers
    assert "vision.get_capabilities" in handlers
    assert "vision.inspect_image" in handlers
    assert "vision.analyze_image_remote" in handlers
    assert "vision.reset" in handlers


def test_vision_backend_contract_fails_closed():
    async def _test():
        result = await vision_get_backend_contract({"provider": "openai", "model": "gpt-4o"})
        assert result["selection_allowed"] is False
        assert result["transport_implemented"] is False
        assert result["image_input"]["max_bytes"] == 20 * 1024 * 1024
        assert result["privacy"]["network_probe_performed"] is False

    asyncio.run(_test())


def test_vision_capabilities_are_truthful():
    async def _test():
        result = await vision_get_capabilities()
        assert result["image_intake"]["available"] is True
        assert result["image_intake"]["metadata_only"] is True
        assert result["image_inference"]["available"] is False
        assert result["network_sent_by_readiness_probe"] is False

    asyncio.run(_test())


def test_vision_analyze_image_and_spatial_memory():
    """Test vision.analyze_image with object bounding boxes."""
    async def _test():
        res = await vision_analyze_image(
            {
                "image_descriptor": "dashboard_screenshot.png",
                "objects": [
                    {
                        "label_fa": "دکمه ورود",
                        "category": "ui_element",
                        "box": {"ymin": 0.4, "xmin": 0.3, "ymax": 0.5, "xmax": 0.7},
                    }
                ],
            }
        )
        assert res["success"] is True
        assert res["total_objects_detected"] == 1
        assert "analysis_id" in res

        # Metrics check
        metrics = await vision_get_metrics()
        assert metrics["spatial_entities_in_memory"] >= 1
        assert metrics["total_analyses_count"] >= 1

    asyncio.run(_test())


def test_vision_decompose_video():
    """Test vision.decompose_video extracts keyframes and timeline."""
    async def _test():
        timeline = await vision_decompose_video(
            {"video_id": "product_demo_vid", "duration_sec": 12.0, "fps": 30.0}
        )
        assert timeline["video_id"] == "product_demo_vid"
        assert len(timeline["keyframes"]) >= 1
        assert "narrative_summary_fa" in timeline

    asyncio.run(_test())


def test_vision_ground_ui_elements_and_intent():
    """Test vision.ground_ui_elements with interactive action proposals."""
    async def _test():
        elements = [
            {
                "element_id": "btn_checkout",
                "label_fa": "تسویه حساب",
                "element_type": "button",
                "box": {"ymin": 0.7, "xmin": 0.6, "ymax": 0.8, "xmax": 0.9},
                "interactive": True,
            }
        ]
        res = await vision_ground_ui_elements(
            {"elements": elements, "intent_fa": "کلیک روی تسویه حساب"}
        )
        assert res["success"] is True
        assert res["total_elements"] == 1
        assert len(res["elements"]) == 1
        assert res["elements"][0]["click_target"]["x"] > 0

    asyncio.run(_test())


def test_vision_inspect_diagram():
    """Test vision.inspect_diagram for architectural structures."""
    async def _test():
        diag = (
            "graph TD\n"
            "  A[Client] --> B[API Gateway]\n"
            "  B --> C[Service]"
        )
        res = await vision_inspect_diagram({"content": diag, "diagram_format": "mermaid"})
        assert res["total_nodes"] >= 3
        assert res["total_edges"] >= 2

    asyncio.run(_test())


def test_vision_diff_and_reset():
    """Test vision.diff_visual_states and vision.reset."""
    async def _test():
        before = [
            {"label_fa": "کارت خرید", "box": {"ymin": 0.1, "xmin": 0.1, "ymax": 0.3, "xmax": 0.4}}
        ]
        after = [
            {"label_fa": "کارت خرید", "box": {"ymin": 0.1, "xmin": 0.1, "ymax": 0.3, "xmax": 0.4}},
            {"label_fa": "تخفیف ویژه", "box": {"ymin": 0.5, "xmin": 0.5, "ymax": 0.6, "xmax": 0.8}},
        ]
        diff_res = await vision_diff_visual_states(
            {"before_state": before, "after_state": after}
        )
        assert "similarity_score" in diff_res
        assert "diff_id" in diff_res

        # Reset
        reset_res = await vision_reset()
        assert reset_res["status"] == "reset"
        metrics = await vision_get_metrics()
        assert metrics["spatial_entities_in_memory"] == 0

        # Invalid diff params
        with pytest.raises(BridgeError):
            await vision_diff_visual_states({"before_state": "invalid", "after_state": []})

    asyncio.run(_test())
