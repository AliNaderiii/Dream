"""Skill package bundling, SHA-256 checksum integrity, export, and import."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class SkillBundleManager:
    """Manages exporting and importing standalone portable skill packages."""

    @staticmethod
    def export_bundle(skill_dir: Path | str, output_bundle_path: Path | str) -> dict[str, Any]:
        """Package a skill directory (SKILL.md + references) into a verified bundle."""
        s_dir = Path(skill_dir)
        if not s_dir.exists() or not s_dir.is_dir():
            return {"success": False, "error": f"Directory '{s_dir}' does not exist."}

        skill_md = s_dir / "SKILL.md"
        if not skill_md.exists():
            return {"success": False, "error": f"Missing SKILL.md in '{s_dir}'."}

        files_data: dict[str, str] = {
            "SKILL.md": skill_md.read_text(encoding="utf-8")
        }

        # Pack references
        ref_dir = s_dir / "references"
        if ref_dir.exists() and ref_dir.is_dir():
            for ref_file in ref_dir.glob("*"):
                if ref_file.is_file():
                    try:
                        files_data[f"references/{ref_file.name}"] = ref_file.read_text(
                            encoding="utf-8"
                        )
                    except Exception:
                        pass

        # Calculate payload checksum
        serialized_payload = json.dumps(files_data, sort_keys=True, ensure_ascii=False)
        sha256 = hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()

        bundle_payload = {
            "format": "dream_skill_bundle_v1",
            "skill_name": s_dir.name,
            "sha256": sha256,
            "files_count": len(files_data),
            "files": files_data,
        }

        out_path = Path(output_bundle_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload_str = json.dumps(bundle_payload, indent=2, ensure_ascii=False)
        out_path.write_text(payload_str, encoding="utf-8")

        return {
            "success": True,
            "bundle_path": str(out_path),
            "sha256": sha256,
            "files_count": len(files_data),
        }

    @staticmethod
    def import_bundle(bundle_path: Path | str, target_skills_dir: Path | str) -> dict[str, Any]:
        """Verify integrity and unpack skill bundle into the target directory."""
        b_path = Path(bundle_path)
        if not b_path.exists() or not b_path.is_file():
            return {"success": False, "error": f"Bundle file '{b_path}' not found."}

        try:
            data = json.loads(b_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"success": False, "error": f"Corrupted JSON in bundle: {exc}"}

        if data.get("format") != "dream_skill_bundle_v1":
            return {"success": False, "error": "Unrecognized bundle format."}

        skill_name = data.get("skill_name", "").strip()
        files = data.get("files", {})
        expected_sha = data.get("sha256", "")

        # Verify checksum
        serialized_payload = json.dumps(files, sort_keys=True, ensure_ascii=False)
        actual_sha = hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()
        if actual_sha != expected_sha:
            return {
                "success": False,
                "error": f"Checksum mismatch! Expected {expected_sha}, got {actual_sha}.",
            }

        target_base = Path(target_skills_dir)
        dest_dir = target_base / skill_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        written_files = []
        for rel_path_str, content in files.items():
            # Security guard against path traversal
            if ".." in rel_path_str or rel_path_str.startswith(("/", "\\")):
                continue
            dest_file = dest_dir / rel_path_str
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            dest_file.write_text(content, encoding="utf-8")
            written_files.append(rel_path_str)

        return {
            "success": True,
            "skill_name": skill_name,
            "target_dir": str(dest_dir),
            "files": written_files,
        }
