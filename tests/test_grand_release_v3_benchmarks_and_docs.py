"""Comprehensive validation tests for Dream v3.0 Grand Release, Benchmarks, and Documentation."""

from __future__ import annotations

from pathlib import Path

from dream.core.engine import get_dream_kernel
from dream.tools.toolsets import BUILTIN_TOOLSETS, list_toolsets


def test_v3_documentation_files_exist_and_non_empty() -> None:
    """Verify all major v3.0 documentation files exist and have substantial content."""
    repo_root = Path(__file__).resolve().parent.parent

    readme_en = repo_root / "README.md"
    readme_fa = repo_root / "README_FA.md"
    benchmarks_v3 = repo_root / "docs" / "BENCHMARKS_V3.md"
    arch_v3 = repo_root / "docs" / "ARCHITECTURE_V3.md"

    assert readme_en.exists()
    assert len(readme_en.read_text(encoding="utf-8")) > 1000

    assert readme_fa.exists()
    assert len(readme_fa.read_text(encoding="utf-8")) > 1000

    assert benchmarks_v3.exists()
    assert len(benchmarks_v3.read_text(encoding="utf-8")) > 500

    assert arch_v3.exists()
    assert len(arch_v3.read_text(encoding="utf-8")) > 500


def test_v3_toolset_catalog_completeness() -> None:
    """Verify all major advanced toolsets are fully registered in BUILTIN_TOOLSETS."""
    toolsets = list_toolsets()
    toolset_names = {ts.name for ts in toolsets}

    expected_toolsets = {
        "core",
        "workspace",
        "web",
        "skills",
        "system",
        "subagents",
        "swarm",
        "speech",
        "ocr",
        "knowledge",
        "research",
        "cache",
        "sandbox",
        "canvas",
        "debate",
        "reasoning",
        "healing",
        "consolidation",
        "isolation",
        "workflow",
        "refactor",
        "duplex",
        "rbac",
        "reactive",
        "dashboard",
        "vision",
        "federation",
        "synthetic",
        "kernel",
    }

    for expected in expected_toolsets:
        assert expected in toolset_names, f"Toolset '{expected}' missing from registered catalog."
        assert expected in BUILTIN_TOOLSETS


def test_dream_kernel_lazy_subsystem_coverage() -> None:
    """Verify DreamKernel tracks and coordinates all lazy subsystems."""
    kernel = get_dream_kernel()
    snap = kernel.get_snapshot()

    assert snap.total_subsystems_registered >= 12
    assert "vision" in snap.subsystems
    assert "synthetic" in snap.subsystems
    assert "federation" in snap.subsystems
    assert "dashboard" in snap.subsystems
    assert "reactive" in snap.subsystems
    assert "rbac" in snap.subsystems
    assert "duplex" in snap.subsystems
    assert "refactor" in snap.subsystems
    assert "workflow" in snap.subsystems
