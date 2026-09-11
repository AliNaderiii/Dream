"""Slash command handlers for Skills Hub, Autonomous Evolution, and Bundles."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.skills.bundle import SkillBundleManager
from dream.skills.evolution import SkillEvolutionEngine
from dream.skills.hub import SkillsHubCatalog
from dream.skills.hub_tools import get_global_evolution_engine, get_global_skills_hub


def handle_hub_command(
    cmd_text: str,
    hub: SkillsHubCatalog | None = None,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/hub` slash command (search, install, list skills)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    h = hub or get_global_skills_hub()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "list"

    if subcmd in ("list", "all"):
        skills = h.search()
        output(cm.bold(f"🌐 Dream Community Skills Hub ({len(skills)} Skills Available):"))
        for s in skills:
            output(f"  • {cm.green(s.name):<25} [v{s.version}] {cm.yellow('★ ' + str(s.rating))}")
            output(f"    {cm.dim(s.description)}")
        return True

    if subcmd in ("search", "find") and len(parts) > 2:
        query = " ".join(parts[2:])
        results = h.search(query=query)
        if not results:
            output(cm.yellow(f"No skills found matching '{query}'."))
            return True
        output(cm.bold(f"Search results for '{query}' ({len(results)} found):"))
        for s in results:
            output(f"  • {cm.green(s.name)} [v{s.version}]: {s.description}")
        return True

    if subcmd in ("install", "get") and len(parts) > 2:
        name = parts[2]
        res = h.install(name, target_dir="skills")
        if res.get("success"):
            v = res.get("version")
            output(cm.green(f"✓ Successfully installed '{name}' v{v} into skills/"))
        else:
            output(cm.red(f"✗ Installation failed: {res.get('error')}"))
        return True

    # Usage
    output(cm.bold("Usage / راهنمای دستور /hub:"))
    output("  /hub list             - فهرست کل مهارت‌های موجود / List all hub skills")
    output("  /hub search <query>   - جستجوی مهارت در هاب / Search skills")
    output("  /hub install <name>   - نصب مهارت روی دستیار / Install skill")
    return True


def handle_evolve_command(
    cmd_text: str,
    engine: SkillEvolutionEngine | None = None,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/evolve` slash command (inspect health and propose optimization)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    eng = engine or get_global_evolution_engine()
    parts = cmd_text.strip().split()
    if len(parts) < 2:
        output(cm.yellow("Usage: /evolve <skill_name>"))
        return True

    skill_name = parts[1]
    health = eng.evaluate_health(skill_name)
    output(cm.bold(f"Autonomous Evolution Health: {skill_name}"))
    output(f"  • Total Runs:   {health.total_runs}")
    output(f"  • Success Rate: {health.success_rate * 100:.1f}%")
    output(f"  • Health Score: {health.health_score:.2f}")

    if health.needs_optimization:
        output(cm.yellow("⚠️ Skill is degraded. Generating self-healing optimization proposal..."))
    else:
        output(cm.green("✓ Skill health is optimal."))
    return True


def handle_bundle_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/bundle` slash command (export or import portable packages)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "help"

    if subcmd == "export" and len(parts) > 2:
        skill_name = parts[2]
        out_path = f"dist/{skill_name}.skill.json"
        res = SkillBundleManager.export_bundle(f"skills/{skill_name}", out_path)
        if res.get("success"):
            output(cm.green(f"✓ Skill '{skill_name}' bundled to {out_path}"))
            output(cm.dim(f"  SHA256: {res.get('sha256')}"))
        else:
            output(cm.red(f"✗ Export failed: {res.get('error')}"))
        return True

    if subcmd == "import" and len(parts) > 2:
        b_path = parts[2]
        res = SkillBundleManager.import_bundle(b_path, target_skills_dir="skills")
        if res.get("success"):
            s_name = res.get("skill_name")
            t_dir = res.get("target_dir")
            output(cm.green(f"✓ Imported skill '{s_name}' into {t_dir}"))
        else:
            output(cm.red(f"✗ Import failed: {res.get('error')}"))
        return True

    output(cm.bold("Usage / راهنمای دستور /bundle:"))
    output("  /bundle export <skill_name> - ایجاد بسته خروجی / Export skill bundle")
    output("  /bundle import <path>       - نصب بسته مهارت / Import skill bundle")
    return True
