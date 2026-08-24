"""Size-capped quarantine for deletions (L4, G-11).

Dream never deletes outright: a deletion is a MOVE into the quarantine
under the data directory, with a JSON metadata sidecar. The owner can
restore (UI comes with the Stage F Security Center) or purge for good.
The quarantine is bounded — an item over the per-item cap or a store over
the total cap is REFUSED, never silently destroyed: fail closed, out loud,
in both languages.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

__all__ = [
    "QUARANTINE_DIR_ENV",
    "QuarantineError",
    "list_quarantine",
    "purge",
    "quarantine_delete",
    "restore",
]

QUARANTINE_DIR_ENV = "DREAM_QUARANTINE_DIR"
DEFAULT_QUARANTINE_DIR = "data/quarantine"

#: One item larger than this is refused, not destroyed.
MAX_ITEM_BYTES = 50 * 1024 * 1024
#: The whole quarantine is bounded too.
MAX_TOTAL_BYTES = 500 * 1024 * 1024

_ERROR_TOO_BIG_EN = "deletion refused: the item is larger than the quarantine cap"
_ERROR_TOO_BIG_FA = (
    "\u062d\u0630\u0641 \u0631\u062f \u0634\u062f: \u0645\u0648\u0631\u062f \u0627\u0632 "
    "\u0633\u0642\u0641 \u0642\u0631\u0646\u0637\u06cc\u0646\u0647 "
    "\u0628\u0632\u0631\u06af\u200c\u062a\u0631 "
    "\u0627\u0633\u062a"
)
_ERROR_FULL_EN = "deletion refused: the quarantine store is full"
_ERROR_FULL_FA = (
    "\u062d\u0630\u0641 \u0631\u062f \u0634\u062f: \u0641\u0636\u0627\u06cc "
    "\u0642\u0631\u0646\u0637\u06cc\u0646\u0647 "
    "\u067e\u0631 \u0627\u0633\u062a"
)
_ERROR_MISSING_EN = "deletion refused: nothing exists at that path"
_ERROR_MISSING_FA = (
    "\u062d\u0630\u0641 \u0631\u062f \u0634\u062f: \u0686\u06cc\u0632\u06cc \u062f\u0631 "
    "\u0627\u06cc\u0646 "
    "\u0645\u0633\u06cc\u0631 \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f"
)
_ERROR_RESTORE_EN = "restore refused: the original path is occupied"
_ERROR_RESTORE_FA = (
    "\u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc \u0631\u062f \u0634\u062f: "
    "\u0645\u0633\u06cc\u0631 "
    "\u0627\u0635\u0644\u06cc \u0627\u06a9\u0646\u0648\u0646 \u0627\u0634\u063a\u0627\u0644 "
    "\u0634\u062f\u0647 \u0627\u0633\u062a"
)


class QuarantineError(RuntimeError):
    """A bounded, bilingual refusal from the quarantine."""


def _root() -> Path:
    return Path(os.environ.get(QUARANTINE_DIR_ENV, "").strip() or DEFAULT_QUARANTINE_DIR)


def _bilingual(en: str, fa: str) -> QuarantineError:
    return QuarantineError(f"{en}\n{fa}")


def _tree_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _quarantined_bytes(root: Path) -> int:
    total = 0
    if root.exists():
        for item in root.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    return total


def quarantine_delete(
    path: str | os.PathLike[str],
    *,
    max_item_bytes: int = MAX_ITEM_BYTES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    """Move *path* into the quarantine; the deletion is the move.

    Returns the entry metadata. Raises :class:`QuarantineError` (bilingual)
    when the path is missing, oversized, or the store is full — in every
    refused case the original stays byte-identical.
    """
    source = Path(path)
    if not source.exists():
        raise _bilingual(_ERROR_MISSING_EN, _ERROR_MISSING_FA)
    size = _tree_bytes(source)
    if size > max_item_bytes:
        raise _bilingual(_ERROR_TOO_BIG_EN, _ERROR_TOO_BIG_FA)
    root = _root()
    if _quarantined_bytes(root) + size > max_total_bytes:
        raise _bilingual(_ERROR_FULL_EN, _ERROR_FULL_FA)

    entry_id = f"q_{uuid.uuid4().hex[:16]}"
    holder = root / entry_id
    holder.mkdir(parents=True, exist_ok=True)
    destination = holder / source.name
    shutil.move(str(source), str(destination))
    meta = {
        "id": entry_id,
        "original_path": str(Path(path).resolve()) if Path(path).is_absolute() else str(path),
        "name": source.name,
        "size_bytes": size,
        "is_dir": destination.is_dir(),
        "quarantined_at": time.time(),
    }
    (holder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def list_quarantine() -> list[dict[str, Any]]:
    """Newest-first metadata for every quarantined item."""
    root = _root()
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows
    for holder in root.iterdir():
        meta_path = holder / "meta.json"
        if not holder.is_dir() or not meta_path.exists():
            continue
        try:
            rows.append(json.loads(meta_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    rows.sort(key=lambda row: row.get("quarantined_at", 0.0), reverse=True)
    return rows


def _holder(entry_id: str) -> Path:
    holder = _root() / str(entry_id)
    if not holder.is_dir() or not (holder / "meta.json").exists():
        raise _bilingual(
            "restore refused: no quarantined item with that id",
            "\u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc \u0631\u062f "
            "\u0634\u062f: \u0645\u0648\u0631\u062f\u06cc "
            "\u0628\u0627 \u0627\u06cc\u0646 \u0634\u0646\u0627\u0633\u0647 \u062f\u0631 "
            "\u0642\u0631\u0646\u0637\u06cc\u0646\u0647 "
            "\u0646\u06cc\u0633\u062a",
        )
    return holder


def restore(entry_id: str) -> dict[str, Any]:
    """Move one quarantined item back to its original path."""
    holder = _holder(entry_id)
    meta = json.loads((holder / "meta.json").read_text(encoding="utf-8"))
    original = Path(str(meta["original_path"]))
    if original.exists():
        raise _bilingual(_ERROR_RESTORE_EN, _ERROR_RESTORE_FA)
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(holder / str(meta["name"])), str(original))
    shutil.rmtree(holder)
    return meta


def purge(entry_id: str) -> dict[str, Any]:
    """Permanently destroy one quarantined item (explicit, irreversible)."""
    holder = _holder(entry_id)
    meta = json.loads((holder / "meta.json").read_text(encoding="utf-8"))
    shutil.rmtree(holder)
    return meta
