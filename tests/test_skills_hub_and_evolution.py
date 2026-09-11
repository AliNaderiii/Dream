"""Comprehensive test suite for Skills Hub, Autonomous Evolution, and Bundles."""

from __future__ import annotations

import json

from dream.skills.bundle import SkillBundleManager
from dream.skills.evolution import SkillEvolutionEngine
from dream.skills.hub import SkillsHubCatalog
from dream.skills.hub_slash import (
    handle_bundle_command,
    handle_evolve_command,
    handle_hub_command,
)
from dream.skills.hub_tools import (
    get_hub_tools,
    hub_install_skill,
    hub_search_skills,
    skill_evolve_optimize,
)
from dream.tools.toolsets import get_toolset


def test_skills_hub_catalog_search_and_filter():
    """Verify hub search, tag filtering, and metadata extraction."""
    hub = SkillsHubCatalog()

    # Search all
    all_skills = hub.search()
    assert len(all_skills) >= 5

    # Tag filter
    iran_skills = hub.search(tag="iran")
    assert len(iran_skills) >= 2
    assert any(s.name == "iran-tax-calculator" for s in iran_skills)

    # Keyword search
    seo_results = hub.search(query="سئو")
    assert len(seo_results) >= 1
    assert seo_results[0].name == "persian-content-seo"


def test_skills_hub_install_and_uninstall(tmp_path):
    """Verify installing a hub skill with SKILL.md and references, then uninstalling."""
    hub = SkillsHubCatalog()
    target = tmp_path / "skills"

    # Install
    res = hub.install("iran-tax-calculator", target_dir=target)
    assert res["success"] is True
    assert (target / "iran-tax-calculator" / "SKILL.md").exists()
    assert (target / "iran-tax-calculator" / "references" / "rules.md").exists()

    # Uninstall
    un_res = hub.uninstall("iran-tax-calculator", target_dir=target)
    assert un_res["success"] is True
    assert not (target / "iran-tax-calculator").exists()


def test_skill_evolution_telemetry_and_health_scoring():
    """Verify runtime telemetry recording, failure detection, and health score calculation."""
    engine = SkillEvolutionEngine(failure_threshold=0.25, min_runs_to_evaluate=3)

    # Healthy skill
    for _ in range(5):
        engine.record_run("math-helper", success=True, latency_ms=120.0)
    health_healthy = engine.evaluate_health("math-helper")
    assert health_healthy.total_runs == 5
    assert health_healthy.success_rate == 1.0
    assert health_healthy.health_score > 0.9
    assert health_healthy.needs_optimization is False

    # Degraded skill
    for _ in range(4):
        engine.record_run(
            "flaky-api",
            success=False,
            latency_ms=3000.0,
            error_message="HTTP Timeout 504",
        )
    health_degraded = engine.evaluate_health("flaky-api")
    assert health_degraded.total_runs == 4
    assert health_degraded.success_rate == 0.0
    assert health_degraded.needs_optimization is True
    assert "HTTP Timeout 504" in health_degraded.recent_errors


def test_skill_evolution_proposal_and_rollback(tmp_path):
    """Verify self-healing optimization proposals, version bumping, and backup rollbacks."""
    engine = SkillEvolutionEngine()
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"

    initial_content = (
        "---\n"
        "name: my-skill\n"
        "version: 1.0.0\n"
        "---\n\n"
        "# My Skill\n"
        "1. Step one\n"
    )
    skill_file.write_text(initial_content, encoding="utf-8")

    # Record errors to trigger degradation
    for _ in range(3):
        engine.record_run("my-skill", success=False, latency_ms=500.0, error_message="Null input")

    health = engine.evaluate_health("my-skill")
    proposal = engine.propose_optimization("my-skill", initial_content, health)
    assert "version: 1.1.0" in proposal["optimized_content"]
    assert "Self-Healing Guard" in proposal["optimized_content"]

    # Apply evolution
    apply_res = engine.apply_evolution(skill_file, proposal["optimized_content"])
    assert apply_res["success"] is True
    assert "version: 1.1.0" in skill_file.read_text(encoding="utf-8")

    # Rollback
    rollback_res = engine.rollback(skill_file)
    assert rollback_res["success"] is True
    assert "version: 1.0.0" in skill_file.read_text(encoding="utf-8")


def test_skill_bundle_export_and_import(tmp_path):
    """Verify portable bundle packaging with SHA-256 integrity verification."""
    skills_root = tmp_path / "src_skills"
    skill_dir = skills_root / "sample-skill"
    ref_dir = skill_dir / "references"
    ref_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text("# Sample Skill\n1. Do task", encoding="utf-8")
    (ref_dir / "data.txt").write_text("Reference content", encoding="utf-8")

    bundle_out = tmp_path / "bundles" / "sample.skill.json"

    # Export bundle
    export_res = SkillBundleManager.export_bundle(skill_dir, bundle_out)
    assert export_res["success"] is True
    assert bundle_out.exists()

    # Import bundle to fresh directory
    dest_skills = tmp_path / "dest_skills"
    import_res = SkillBundleManager.import_bundle(bundle_out, dest_skills)
    assert import_res["success"] is True
    assert (dest_skills / "sample-skill" / "SKILL.md").exists()
    assert (dest_skills / "sample-skill" / "references" / "data.txt").exists()


def test_skills_hub_tools_and_slash_commands(tmp_path):
    """Verify LLM tool calls and slash commands for Skills Hub."""
    # Tool: hub_search_skills
    search_json = hub_search_skills(query="tax")
    parsed_search = json.loads(search_json)
    assert parsed_search["status"] == "ok"
    assert parsed_search["count"] >= 1

    # Tool: hub_install_skill
    dest_dir = str(tmp_path / "installed_skills")
    install_json = hub_install_skill("jalali-cron-planner", target_dir=dest_dir)
    parsed_install = json.loads(install_json)
    assert parsed_install["success"] is True

    # Tool: skill_evolve_optimize
    evolve_json = skill_evolve_optimize(
        "jalali-cron-planner",
        skill_path=f"{dest_dir}/jalali-cron-planner/SKILL.md",
    )
    parsed_evolve = json.loads(evolve_json)
    assert parsed_evolve["status"] == "ok"

    # Tool dict registration
    hub_tools = get_hub_tools()
    assert "hub_search_skills" in hub_tools
    assert "hub_install_skill" in hub_tools
    assert "skill_evolve_optimize" in hub_tools

    # Slash commands
    out: list[str] = []
    handle_hub_command("/hub list", output=out.append)
    assert any("Dream Community Skills Hub" in line for line in out)

    out.clear()
    handle_evolve_command("/evolve math-helper", output=out.append)
    assert any("Autonomous Evolution Health" in line for line in out)

    out.clear()
    handle_bundle_command("/bundle help", output=out.append)
    assert any("Usage" in line for line in out)


def test_toolset_includes_all_skill_tools():
    """Verify toolset grouping contains all legacy and new hub tools."""
    skill_ts = get_toolset("skills")
    assert skill_ts is not None
    assert "hub_search_skills" in skill_ts.tools
    assert "hub_install_skill" in skill_ts.tools
    assert "skill_evolve_optimize" in skill_ts.tools
    assert "save_skill" in skill_ts.tools
