"""Data models and type definitions for Multi-Modal Vision & Video Stream Subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ImageFormat(str, Enum):
    """Supported image encoding formats."""

    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"
    SVG = "svg"
    BASE64 = "base64"


class ElementType(str, Enum):
    """Categorization of visual GUI/UI interactive elements."""

    BUTTON = "button"
    INPUT_FIELD = "input_field"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    TEXT_LABEL = "text_label"
    ICON = "icon"
    IMAGE = "image"
    MODAL = "modal"
    NAVIGATION = "navigation"
    CUSTOM = "custom"


class SpatialRelationType(str, Enum):
    """Spatial geometric relationship between visual entities."""

    LEFT_OF = "left_of"
    RIGHT_OF = "right_of"
    ABOVE = "above"
    BELOW = "below"
    INSIDE = "inside"
    CONTAINS = "contains"
    ALIGNED_HORIZONTALLY = "aligned_horizontally"
    ALIGNED_VERTICALLY = "aligned_vertically"
    OVERLAPPING = "overlapping"


@dataclass
class BoundingBox:
    """Normalized spatial bounding box (coordinates scaled between 0.0 and 1.0)."""

    ymin: float
    xmin: float
    ymax: float
    xmax: float

    @property
    def center_x(self) -> float:
        """Center X coordinate."""
        return (self.xmin + self.xmax) / 2.0

    @property
    def center_y(self) -> float:
        """Center Y coordinate."""
        return (self.ymin + self.ymax) / 2.0

    @property
    def width(self) -> float:
        """Box width."""
        return max(0.0, self.xmax - self.xmin)

    @property
    def height(self) -> float:
        """Box height."""
        return max(0.0, self.ymax - self.ymin)

    @property
    def area(self) -> float:
        """Box surface area."""
        return self.width * self.height

    def to_dict(self) -> dict[str, float]:
        """Serialize bounding box to dictionary."""
        return {
            "ymin": round(self.ymin, 4),
            "xmin": round(self.xmin, 4),
            "ymax": round(self.ymax, 4),
            "xmax": round(self.xmax, 4),
            "center_x": round(self.center_x, 4),
            "center_y": round(self.center_y, 4),
            "width": round(self.width, 4),
            "height": round(self.height, 4),
        }


@dataclass
class KeyFrame:
    """Keyframe extracted from a multi-frame video stream."""

    frame_id: str
    timestamp_sec: float
    frame_index: int
    scene_id: int = 1
    entropy_score: float = 0.0
    is_scene_transition: bool = False
    caption_fa: str = ""
    detected_entities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize keyframe to dictionary."""
        return {
            "frame_id": self.frame_id,
            "timestamp_sec": round(self.timestamp_sec, 2),
            "frame_index": self.frame_index,
            "scene_id": self.scene_id,
            "entropy_score": round(self.entropy_score, 4),
            "is_scene_transition": self.is_scene_transition,
            "caption_fa": self.caption_fa,
            "detected_entities": self.detected_entities,
            "metadata": self.metadata,
        }


@dataclass
class VideoTimeline:
    """Temporal decomposition and narrative timeline of a video."""

    video_id: str
    duration_sec: float
    total_frames: int
    sample_rate_fps: float
    keyframes: list[KeyFrame] = field(default_factory=list)
    narrative_summary_fa: str = ""
    scene_count: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize timeline to dictionary."""
        return {
            "video_id": self.video_id,
            "duration_sec": round(self.duration_sec, 2),
            "total_frames": self.total_frames,
            "sample_rate_fps": self.sample_rate_fps,
            "scene_count": self.scene_count,
            "keyframes": [kf.to_dict() for kf in self.keyframes],
            "narrative_summary_fa": self.narrative_summary_fa,
            "metadata": self.metadata,
        }


@dataclass
class UIElementGrounding:
    """Grounding interactive UI element with pixel coordinates and click targets."""

    element_id: str
    label_fa: str
    element_type: ElementType
    box: BoundingBox
    confidence: float = 0.95
    interactive: bool = True
    suggested_action: str = "click"  # "click", "type", "scroll", "hover"
    text_content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize element grounding to dictionary."""
        return {
            "element_id": self.element_id,
            "label_fa": self.label_fa,
            "element_type": self.element_type.value,
            "box": self.box.to_dict(),
            "confidence": round(self.confidence, 4),
            "interactive": self.interactive,
            "suggested_action": self.suggested_action,
            "text_content": self.text_content,
            "click_target": {"x": round(self.box.center_x, 4), "y": round(self.box.center_y, 4)},
            "metadata": self.metadata,
        }


@dataclass
class SpatialEntity:
    """Entity mapped in spatial-visual memory."""

    entity_id: str
    label_fa: str
    category: str
    box: BoundingBox
    first_seen_timestamp: float = field(default_factory=time.time)
    last_seen_timestamp: float = field(default_factory=time.time)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize spatial entity to dictionary."""
        return {
            "entity_id": self.entity_id,
            "label_fa": self.label_fa,
            "category": self.category,
            "box": self.box.to_dict(),
            "first_seen": self.first_seen_timestamp,
            "last_seen": self.last_seen_timestamp,
            "attributes": self.attributes,
        }


@dataclass
class VisualDiffResult:
    """Visual state change comparison between two images or screens."""

    diff_id: str
    similarity_score: float  # 0.0 to 1.0 (1.0 = identical)
    has_significant_change: bool
    added_elements: list[str] = field(default_factory=list)
    removed_elements: list[str] = field(default_factory=list)
    modified_regions: list[BoundingBox] = field(default_factory=list)
    summary_fa: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize visual diff to dictionary."""
        return {
            "diff_id": self.diff_id,
            "similarity_score": round(self.similarity_score, 4),
            "has_significant_change": self.has_significant_change,
            "added_elements": self.added_elements,
            "removed_elements": self.removed_elements,
            "modified_regions": [r.to_dict() for r in self.modified_regions],
            "summary_fa": self.summary_fa,
        }
