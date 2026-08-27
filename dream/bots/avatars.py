"""Geometric avatars. Hues deliberately exclude Hermes-like blue."""

from __future__ import annotations

SHAPES = ("hex", "circle", "diamond", "square", "triangle")
HUES = ("teal", "amber", "rose", "slate", "violet")


def normalize_avatar(shape: str | None, hue: str | None) -> dict[str, str]:
    picked_shape = (shape or "hex").strip().lower()
    picked_hue = (hue or "teal").strip().lower()
    if picked_shape not in SHAPES:
        picked_shape = "hex"
    if picked_hue not in HUES:
        picked_hue = "teal"
    return {"shape": picked_shape, "hue": picked_hue}
