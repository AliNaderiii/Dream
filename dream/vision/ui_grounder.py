"""UI and Screen Visual Element Grounding and Spatial Coordinate Mapper."""

from __future__ import annotations

import uuid
from typing import Any

from dream.vision.types import BoundingBox, ElementType, UIElementGrounding


class UIGrounder:
    """Detects and grounds interactive GUI elements with normalized bounding boxes."""

    def __init__(self) -> None:
        self._grounded_history: list[UIElementGrounding] = []

    def ground_elements_from_descriptors(
        self,
        elements_spec: list[dict[str, Any]],
    ) -> list[UIElementGrounding]:
        """Convert visual detection descriptors into structured UI element groundings."""
        grounded: list[UIElementGrounding] = []

        for spec in elements_spec:
            elem_id = spec.get("id") or f"elem-{uuid.uuid4().hex[:6]}"
            label = spec.get("label_fa") or spec.get("label") or "عنصر بصری"
            type_str = str(spec.get("type", "custom")).lower()

            try:
                el_type = ElementType(type_str)
            except ValueError:
                el_type = ElementType.CUSTOM

            box_raw = spec.get("box", {})
            ymin = float(box_raw.get("ymin", 0.0))
            xmin = float(box_raw.get("xmin", 0.0))
            ymax = float(box_raw.get("ymax", 1.0))
            xmax = float(box_raw.get("xmax", 1.0))

            box = BoundingBox(
                ymin=max(0.0, min(1.0, ymin)),
                xmin=max(0.0, min(1.0, xmin)),
                ymax=max(0.0, min(1.0, ymax)),
                xmax=max(0.0, min(1.0, xmax)),
            )

            action = spec.get("suggested_action") or (
                "type" if el_type == ElementType.INPUT_FIELD else "click"
            )
            text_val = spec.get("text_content", "")

            item = UIElementGrounding(
                element_id=elem_id,
                label_fa=label,
                element_type=el_type,
                box=box,
                confidence=float(spec.get("confidence", 0.95)),
                interactive=bool(spec.get("interactive", True)),
                suggested_action=action,
                text_content=text_val,
                metadata=spec.get("metadata", {}),
            )
            grounded.append(item)
            self._grounded_history.append(item)

        return grounded

    def find_element_by_text(
        self,
        elements: list[UIElementGrounding],
        query_text: str,
    ) -> UIElementGrounding | None:
        """Find grounded element matching query label or text content."""
        clean_query = query_text.strip().lower()
        for el in elements:
            if clean_query in el.label_fa.lower() or clean_query in el.text_content.lower():
                return el
        return None

    def propose_action_sequence(
        self,
        elements: list[UIElementGrounding],
        intent_fa: str,
    ) -> list[dict[str, Any]]:
        """Synthesize interactive click/type action sequence to achieve visual user intent."""
        actions: list[dict[str, Any]] = []

        # Simple semantic intent matching heuristics: type in inputs first, then click buttons
        if any(w in intent_fa for w in ["ورود", "login", "ثبت نام", "signup", "جستجو", "search"]):
            input_elements = [e for e in elements if e.element_type == ElementType.INPUT_FIELD]
            button_elements = [e for e in elements if e.element_type == ElementType.BUTTON]

            for el in input_elements:
                actions.append({
                    "step": len(actions) + 1,
                    "action": "type",
                    "element_id": el.element_id,
                    "target_coords": {"x": el.box.center_x, "y": el.box.center_y},
                    "description_fa": f"ورود متن در فیلد `{el.label_fa}`",
                })

            for el in button_elements:
                actions.append({
                    "step": len(actions) + 1,
                    "action": "click",
                    "element_id": el.element_id,
                    "target_coords": {"x": el.box.center_x, "y": el.box.center_y},
                    "description_fa": f"کلیک روی دکمه `{el.label_fa}`",
                })
        else:
            # Default action on highest confidence interactive element
            interactive = [e for e in elements if e.interactive]
            if interactive:
                first = interactive[0]
                actions.append({
                    "step": 1,
                    "action": first.suggested_action,
                    "element_id": first.element_id,
                    "target_coords": {"x": first.box.center_x, "y": first.box.center_y},
                    "description_fa": f"تعامل با `{first.label_fa}`",
                })

        return actions
