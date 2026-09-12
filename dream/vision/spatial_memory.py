"""Spatial-Visual Memory and Cross-Turn Visual Entity Relationship Graph."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.vision.types import (
    BoundingBox,
    SpatialEntity,
    SpatialRelationType,
    VisualDiffResult,
)


class SpatialMemory:
    """Maintains persistent spatial-visual memory and reasons over geometric entity relations."""

    def __init__(self) -> None:
        self._entities: dict[str, SpatialEntity] = {}

    def register_entity(
        self,
        label_fa: str,
        category: str,
        box: BoundingBox,
        attributes: dict[str, Any] | None = None,
    ) -> SpatialEntity:
        """Register a recognized visual entity into spatial memory."""
        entity_id = f"ent-{uuid.uuid4().hex[:6]}"
        now = time.time()
        entity = SpatialEntity(
            entity_id=entity_id,
            label_fa=label_fa,
            category=category,
            box=box,
            first_seen_timestamp=now,
            last_seen_timestamp=now,
            attributes=attributes or {},
        )
        self._entities[entity_id] = entity
        return entity

    def get_entity(self, entity_id: str) -> SpatialEntity | None:
        """Retrieve entity by ID."""
        return self._entities.get(entity_id)

    def list_entities(self) -> list[SpatialEntity]:
        """List all active entities in spatial memory."""
        return list(self._entities.values())

    def compute_relation(
        self,
        entity_a: SpatialEntity,
        entity_b: SpatialEntity,
    ) -> list[SpatialRelationType]:
        """Compute geometric spatial relations from entity A relative to entity B."""
        box_a = entity_a.box
        box_b = entity_b.box
        relations: list[SpatialRelationType] = []

        # Horizontal relations
        if box_a.xmax < box_b.xmin:
            relations.append(SpatialRelationType.LEFT_OF)
        elif box_a.xmin > box_b.xmax:
            relations.append(SpatialRelationType.RIGHT_OF)
        elif abs(box_a.center_y - box_b.center_y) < 0.05:
            relations.append(SpatialRelationType.ALIGNED_HORIZONTALLY)

        # Vertical relations
        if box_a.ymax < box_b.ymin:
            relations.append(SpatialRelationType.ABOVE)
        elif box_a.ymin > box_b.ymax:
            relations.append(SpatialRelationType.BELOW)
        elif abs(box_a.center_x - box_b.center_x) < 0.05:
            relations.append(SpatialRelationType.ALIGNED_VERTICALLY)

        # Containment
        if (
            box_a.xmin >= box_b.xmin
            and box_a.xmax <= box_b.xmax
            and box_a.ymin >= box_b.ymin
            and box_a.ymax <= box_b.ymax
        ):
            relations.append(SpatialRelationType.INSIDE)
        elif (
            box_b.xmin >= box_a.xmin
            and box_b.xmax <= box_a.xmax
            and box_b.ymin >= box_a.ymin
            and box_b.ymax <= box_a.ymax
        ):
            relations.append(SpatialRelationType.CONTAINS)

        return relations

    def compare_visual_states(
        self,
        before_entities: list[SpatialEntity],
        after_entities: list[SpatialEntity],
    ) -> VisualDiffResult:
        """Compute visual diff and state transition between two scenes."""
        before_labels = {e.label_fa for e in before_entities}
        after_labels = {e.label_fa for e in after_entities}

        added = list(after_labels - before_labels)
        removed = list(before_labels - after_labels)

        modified_boxes: list[BoundingBox] = []
        for e_after in after_entities:
            for e_before in before_entities:
                if e_after.label_fa == e_before.label_fa:
                    # Check if position moved
                    dx = abs(e_after.box.center_x - e_before.box.center_x)
                    dy = abs(e_after.box.center_y - e_before.box.center_y)
                    if dx > 0.05 or dy > 0.05:
                        modified_boxes.append(e_after.box)

        total_unique = len(before_labels | after_labels)
        intersection_count = len(before_labels & after_labels)
        similarity = (
            intersection_count / total_unique if total_unique > 0 else 1.0
        ) - (len(modified_boxes) * 0.1)
        similarity = max(0.0, min(1.0, similarity))

        has_change = bool(added or removed or modified_boxes)
        summary_fa = (
            f"تغییرات بصری: {len(added)} مورد افزوده، {len(removed)} مورد حذف و "
            f"{len(modified_boxes)} تغییر موقعیت مکان."
            if has_change
            else "هیچ تغییر بصری معناداری مشاهده نشد."
        )

        return VisualDiffResult(
            diff_id=f"vdiff-{uuid.uuid4().hex[:6]}",
            similarity_score=similarity,
            has_significant_change=has_change,
            added_elements=added,
            removed_elements=removed,
            modified_regions=modified_boxes,
            summary_fa=summary_fa,
        )

    def clear(self) -> None:
        """Reset spatial memory."""
        self._entities.clear()
