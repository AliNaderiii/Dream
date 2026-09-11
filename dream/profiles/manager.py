"""Profile manager for creating, switching, and isolating personas and memory spaces."""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

from dream.profiles.types import Profile

DEFAULT_PROFILES_DIR = Path.home() / ".dream" / "profiles"

BUILTIN_PERSONAS = {
    "default": (
        "\u062f\u0633\u062a\u06cc\u0627\u0631 \u0647\u0648\u0634\u0645\u0646\u062f "
        "\u0634\u062e\u0635\u06cc \u062f\u0648\u0632\u0628\u0627\u0646\u0647 "
        "\u062f\u0631\u06cc\u0645"
    ),
    "coding": (
        "\u0645\u0647\u0646\u062f\u0633 \u0627\u0631\u0634\u062f "
        "\u0646\u0631\u0645\u200c\u0627\u0641\u0632\u0627\u0631\u060c "
        "\u0645\u0639\u0645\u0627\u0631 \u0633\u06cc\u0633\u062a\u0645 "
        "\u0648 \u0645\u062a\u062e\u0635\u0635 "
        "\u06a9\u062f\u0646\u0648\u06cc\u0633\u06cc"
    ),
    "research": (
        "\u067e\u0698\u0648\u0647\u0634\u06af\u0631 \u0639\u0644\u0645\u06cc\u060c "
        "\u062a\u062d\u0644\u06cc\u0644\u200c\u06af\u0631 \u062f\u0627\u062f\u0647 "
        "\u0648 \u0645\u062a\u062e\u0635\u0635 \u0627\u0633\u062a\u062e\u0631\u0627\u062c "
        "\u062f\u0627\u0646\u0634"
    ),
    "finance": (
        "\u0645\u0634\u0627\u0648\u0631 \u0645\u0627\u0644\u06cc\u060c "
        "\u062a\u062d\u0644\u06cc\u0644\u200c\u06af\u0631 \u0628\u0627\u0632\u0627\u0631 "
        "\u0648 \u0645\u062d\u0627\u0633\u0628\u0627\u062a "
        "\u0627\u0642\u062a\u0635\u0627\u062f\u06cc"
    ),
}


class ProfileManager:
    """Manages isolated personas, scoped settings, and storage spaces."""

    def __init__(self, root_dir: Path | str | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else DEFAULT_PROFILES_DIR
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root_dir / "profiles_config.json"
        self._ensure_default_profile()

    def _load_config(self) -> dict[str, Any]:
        """Load global profiles configuration state."""
        if not self.config_path.exists():
            return {"active_profile": "default"}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {"active_profile": "default"}

    def _save_config(self, config: dict[str, Any]) -> None:
        """Persist global profiles configuration state."""
        self.config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _sanitize_name(self, name: str) -> str:
        """Normalize profile name to safe alphanumeric slug."""
        clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip().lower())
        return clean or "unnamed"

    def _profile_dir(self, name: str) -> Path:
        return self.root_dir / self._sanitize_name(name)

    def _profile_file(self, name: str) -> Path:
        return self._profile_dir(name) / "profile.json"

    def _ensure_default_profile(self) -> None:
        """Ensure initial default profile exists."""
        def_file = self._profile_file("default")
        if not def_file.exists():
            p_dir = self._profile_dir("default")
            p_dir.mkdir(parents=True, exist_ok=True)
            prof = Profile(
                name="default",
                display_name="Default Workspace",
                persona_prompt=BUILTIN_PERSONAS["default"],
                language="fa",
                default_model="gpt-4o",
                allowed_toolsets=[
                    "core",
                    "workspace",
                    "web",
                    "skills",
                    "scheduler",
                    "retrieval",
                    "distill",
                ],
                memory_db_path=str(p_dir / "memory.db"),
            )
            def_file.write_text(
                json.dumps(prof.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._save_config({"active_profile": "default"})

    def create_profile(
        self,
        name: str,
        display_name: str = "",
        persona_prompt: str = "",
        language: str = "fa",
        default_model: str = "gpt-4o",
        allowed_toolsets: list[str] | None = None,
        system_instructions: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Profile:
        """Create and register a new isolated profile."""
        slug = self._sanitize_name(name)
        p_dir = self._profile_dir(slug)
        p_dir.mkdir(parents=True, exist_ok=True)

        persona = persona_prompt or BUILTIN_PERSONAS.get(slug, BUILTIN_PERSONAS["default"])
        toolsets = allowed_toolsets or [
            "core",
            "workspace",
            "web",
            "skills",
            "scheduler",
            "retrieval",
            "distill",
        ]

        prof = Profile(
            name=slug,
            display_name=display_name or name,
            persona_prompt=persona,
            language=language,
            default_model=default_model,
            allowed_toolsets=toolsets,
            memory_db_path=str(p_dir / "memory.db"),
            system_instructions=system_instructions,
            metadata=metadata or {},
            created_at=time.time(),
            updated_at=time.time(),
        )

        file_p = self._profile_file(slug)
        file_p.write_text(
            json.dumps(prof.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return prof

    def get_profile(self, name: str) -> Profile | None:
        """Retrieve profile by name."""
        slug = self._sanitize_name(name)
        file_p = self._profile_file(slug)
        if not file_p.exists():
            return None
        try:
            data = json.loads(file_p.read_text(encoding="utf-8"))
            return Profile.from_dict(data)
        except Exception:
            return None

    def list_profiles(self) -> list[Profile]:
        """List all registered profiles."""
        profiles = []
        for d in sorted(self.root_dir.iterdir()):
            if d.is_dir():
                prof_file = d / "profile.json"
                if prof_file.exists():
                    try:
                        data = json.loads(prof_file.read_text(encoding="utf-8"))
                        profiles.append(Profile.from_dict(data))
                    except Exception:
                        pass
        return profiles

    def get_active_profile(self) -> Profile:
        """Return currently active profile (falls back to default)."""
        cfg = self._load_config()
        active_name = cfg.get("active_profile", "default")
        prof = self.get_profile(active_name)
        if prof:
            return prof
        return self.get_profile("default") or self.create_profile("default")

    def switch_profile(self, name: str) -> Profile:
        """Switch current active profile."""
        slug = self._sanitize_name(name)
        prof = self.get_profile(slug)
        if not prof:
            prof = self.create_profile(slug)
        self._save_config({"active_profile": slug})
        return prof

    def delete_profile(self, name: str) -> bool:
        """Delete profile directory (refuses to delete default or active profile)."""
        slug = self._sanitize_name(name)
        if slug == "default":
            return False
        cfg = self._load_config()
        if cfg.get("active_profile") == slug:
            return False

        p_dir = self._profile_dir(slug)
        if p_dir.exists():
            shutil.rmtree(p_dir, ignore_errors=True)
            return True
        return False

    def export_profile(self, name: str, output_path: Path | str) -> bool:
        """Export profile metadata and memory configuration to a JSON file."""
        prof = self.get_profile(name)
        if not prof:
            return False
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(
            json.dumps(prof.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True

    def import_profile(self, source_path: Path | str) -> Profile | None:
        """Import profile definition from a JSON file."""
        src = Path(source_path)
        if not src.exists():
            return None
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
            prof = Profile.from_dict(data)
            return self.create_profile(
                name=prof.name,
                display_name=prof.display_name,
                persona_prompt=prof.persona_prompt,
                language=prof.language,
                default_model=prof.default_model,
                allowed_toolsets=prof.allowed_toolsets,
                system_instructions=prof.system_instructions,
                metadata=prof.metadata,
            )
        except Exception:
            return None
