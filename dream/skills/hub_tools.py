"""Agent tool interfaces for Skills Hub, Autonomous Evolution, and Bundles."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dream.skills.bundle import SkillBundleManager
from dream.skills.evolution import SkillEvolutionEngine
from dream.skills.hub import SkillsHubCatalog

_GLOBAL_HUB: SkillsHubCatalog | None = None
_GLOBAL_EVOLUTION: SkillEvolutionEngine | None = None


def get_global_skills_hub() -> SkillsHubCatalog:
    """Get singleton skills hub catalog."""
    global _GLOBAL_HUB
    if _GLOBAL_HUB is None:
        _GLOBAL_HUB = SkillsHubCatalog()
    return _GLOBAL_HUB


def get_global_evolution_engine() -> SkillEvolutionEngine:
    """Get singleton skill evolution engine."""
    global _GLOBAL_EVOLUTION
    if _GLOBAL_EVOLUTION is None:
        _GLOBAL_EVOLUTION = SkillEvolutionEngine()
    return _GLOBAL_EVOLUTION


def hub_search_skills(query: str = "", tag: str = "") -> str:
    """Search community skills catalog by keyword or category tag.

    Args:
        query: Search term (e.g. 'tax', 'jalali', 'seo', 'coding').
        tag: Optional category filter.

    Returns:
        JSON string listing available community skills.
    """
    hub = get_global_skills_hub()
    tag_val = tag if tag.strip() else None
    results = hub.search(query=query, tag=tag_val)
    return json.dumps(
        {
            "status": "ok",
            "count": len(results),
            "skills": [s.to_dict() for s in results],
        },
        ensure_ascii=False,
        indent=2,
    )


def hub_install_skill(name: str, target_dir: str = "skills") -> str:
    """Install a vetted skill from the community Skills Hub into the workspace.

    Args:
        name: Name of the skill (e.g. 'iran-tax-calculator', 'jalali-cron-planner').
        target_dir: Destination skills directory.

    Returns:
        JSON string with installation status.
    """
    hub = get_global_skills_hub()
    result = hub.install(name, target_dir=target_dir)
    return json.dumps(result, ensure_ascii=False, indent=2)


def skill_evolve_optimize(skill_name: str, skill_path: str = "") -> str:
    """Autonomously analyze skill execution health and propose self-healing optimizations.

    Args:
        skill_name: Name of the skill to optimize.
        skill_path: Path to the skill file/directory.

    Returns:
        JSON string containing diagnostics, health score, and proposed diff.
    """
    engine = get_global_evolution_engine()
    health = engine.evaluate_health(skill_name)

    path = Path(skill_path) if skill_path else Path(f"skills/{skill_name}/SKILL.md")
    if not path.exists():
        path = Path(f"skills/{skill_name}.txt")

    if not path.exists():
        return json.dumps(
            {
                "status": "error",
                "message": f"Skill file for '{skill_name}' not found at {path}.",
                "health": {
                    "runs": health.total_runs,
                    "success_rate": health.success_rate,
                },
            },
            ensure_ascii=False,
        )

    content = path.read_text(encoding="utf-8")
    proposal = engine.propose_optimization(skill_name, content, health)
    return json.dumps(
        {
            "status": "ok",
            "health": health.to_dict(),
            "proposal": proposal,
        },
        indent=2,
    )


def skill_export_bundle(skill_dir: str, output_path: str) -> str:
    """Package a local skill into a portable bundle with SHA-256 integrity verification.

    Args:
        skill_dir: Path to the skill folder (e.g. 'skills/iran-tax-calculator').
        output_path: Destination bundle file (e.g. 'dist/iran-tax.skill.json').

    Returns:
        JSON string with bundling outcome and checksum.
    """
    res = SkillBundleManager.export_bundle(skill_dir, output_path)
    return json.dumps(res, ensure_ascii=False, indent=2)


def skill_import_bundle(bundle_path: str, target_dir: str = "skills") -> str:
    """Import and verify a skill bundle into the workspace.

    Args:
        bundle_path: Path to the .skill.json bundle file.
        target_dir: Target skills workspace folder.

    Returns:
        JSON string with unpack results.
    """
    res = SkillBundleManager.import_bundle(bundle_path, target_dir)
    return json.dumps(res, ensure_ascii=False, indent=2)


def get_hub_tools() -> dict[str, Callable[..., Any]]:
    """Return dict of skill hub and evolution tools."""
    return {
        "hub_search_skills": hub_search_skills,
        "hub_install_skill": hub_install_skill,
        "skill_evolve_optimize": skill_evolve_optimize,
        "skill_export_bundle": skill_export_bundle,
        "skill_import_bundle": skill_import_bundle,
    }
