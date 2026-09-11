"""Self-improving skill synthesis, execution telemetry, and autonomous optimization."""

from __future__ import annotations

import difflib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SkillRunRecord:
    """Telemetry entry for a single skill invocation."""

    skill_name: str
    success: bool
    latency_ms: float
    error_message: str = ""
    user_feedback_score: float | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass(slots=True)
class SkillHealthReport:
    """Aggregated health score and telemetry diagnostics for a skill."""

    skill_name: str
    total_runs: int
    success_rate: float
    avg_latency_ms: float
    error_count: int
    health_score: float  # 0.0 to 1.0
    needs_optimization: bool
    recent_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "total_runs": self.total_runs,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "error_count": self.error_count,
            "health_score": self.health_score,
            "needs_optimization": self.needs_optimization,
            "recent_errors": self.recent_errors,
        }


class SkillEvolutionEngine:
    """Tracks skill execution telemetry and autonomously proposes optimizations."""

    def __init__(self, failure_threshold: float = 0.25, min_runs_to_evaluate: int = 3) -> None:
        self.failure_threshold = failure_threshold
        self.min_runs_to_evaluate = min_runs_to_evaluate
        self._telemetry: dict[str, list[SkillRunRecord]] = {}

    def record_run(
        self,
        skill_name: str,
        success: bool,
        latency_ms: float,
        error_message: str = "",
        user_feedback_score: float | None = None,
    ) -> None:
        """Record execution outcome for a skill."""
        record = SkillRunRecord(
            skill_name=skill_name,
            success=success,
            latency_ms=latency_ms,
            error_message=error_message,
            user_feedback_score=user_feedback_score,
        )
        if skill_name not in self._telemetry:
            self._telemetry[skill_name] = []
        self._telemetry[skill_name].append(record)

    def evaluate_health(self, skill_name: str) -> SkillHealthReport:
        """Calculate health score and determine if self-improving evolution is required."""
        runs = self._telemetry.get(skill_name, [])
        if not runs:
            return SkillHealthReport(
                skill_name=skill_name,
                total_runs=0,
                success_rate=1.0,
                avg_latency_ms=0.0,
                error_count=0,
                health_score=1.0,
                needs_optimization=False,
            )

        total = len(runs)
        successes = sum(1 for r in runs if r.success)
        errors = [r.error_message for r in runs if not r.success and r.error_message]
        success_rate = successes / total
        avg_latency = sum(r.latency_ms for r in runs) / total

        # Composite score: success rate (80%) + latency factor (20%)
        latency_factor = max(0.0, min(1.0, 1.0 - (avg_latency / 5000.0)))
        health_score = (success_rate * 0.8) + (latency_factor * 0.2)

        needs_optimization = (
            total >= self.min_runs_to_evaluate
            and (1.0 - success_rate) >= self.failure_threshold
        )

        return SkillHealthReport(
            skill_name=skill_name,
            total_runs=total,
            success_rate=success_rate,
            avg_latency_ms=avg_latency,
            error_count=len(errors),
            health_score=health_score,
            needs_optimization=needs_optimization,
            recent_errors=errors[-5:],
        )

    def propose_optimization(
        self,
        skill_name: str,
        current_content: str,
        health: SkillHealthReport,
    ) -> dict[str, Any]:
        """Synthesize an optimized revision for a degraded skill."""
        lines = current_content.splitlines()
        updated_lines: list[str] = []

        # Version bumping logic: v1.0.0 -> v1.1.0
        version_bumped = False
        for line in lines:
            if line.startswith("version:") and not version_bumped:
                m = re.search(r"(\d+)\.(\d+)\.(\d+)", line)
                if m:
                    major, minor = int(m.group(1)), int(m.group(2))
                    new_ver = f"{major}.{minor + 1}.0"
                    updated_lines.append(f"version: {new_ver}")
                    version_bumped = True
                    continue
            updated_lines.append(line)

        # Inject guard steps based on error patterns
        if health.recent_errors:
            error_summary = "; ".join(set(health.recent_errors[:2]))
            guard_note = (
                f"\n## Self-Healing Guard (Auto-Evolved):\n"
                f"- Pre-check inputs to prevent: {error_summary}\n"
                f"- Ensure fallback validation before final step.\n"
            )
            updated_lines.append(guard_note)

        new_content = "\n".join(updated_lines).strip() + "\n"
        diff = list(
            difflib.unified_diff(
                current_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"{skill_name}.v_old",
                tofile=f"{skill_name}.v_evolved",
            )
        )

        return {
            "skill_name": skill_name,
            "original_content": current_content,
            "optimized_content": new_content,
            "diff": "".join(diff),
            "diagnostics": {
                "success_rate": health.success_rate,
                "error_count": health.error_count,
                "reason": "Autonomous recovery from runtime execution failures.",
            },
        }

    def apply_evolution(
        self,
        skill_path: Path | str,
        optimized_content: str,
        backup_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        """Apply the optimized content and save rollback checkpoint."""
        p = Path(skill_path)
        if p.is_dir():
            target_file = p / "SKILL.md"
        else:
            target_file = p

        if not target_file.exists():
            return {"success": False, "error": f"File {target_file} does not exist."}

        # Backup previous version
        original = target_file.read_text(encoding="utf-8")
        b_dir = Path(backup_dir) if backup_dir else target_file.parent / ".backups"
        b_dir.mkdir(parents=True, exist_ok=True)
        backup_file = b_dir / f"{target_file.name}.bak_{int(time.time())}"
        backup_file.write_text(original, encoding="utf-8")

        # Write new version
        target_file.write_text(optimized_content, encoding="utf-8")

        return {
            "success": True,
            "file": str(target_file),
            "backup_file": str(backup_file),
            "timestamp": time.time(),
        }

    def rollback(
        self,
        skill_path: Path | str,
        backup_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        """Restore most recent backup checkpoint."""
        p = Path(skill_path)
        target_file = (p / "SKILL.md") if p.is_dir() else p
        b_dir = Path(backup_dir) if backup_dir else target_file.parent / ".backups"

        if not b_dir.exists():
            return {"success": False, "error": f"No backups found in {b_dir}."}

        backups = sorted(b_dir.glob("*.bak_*"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not backups:
            return {"success": False, "error": "No backup checkpoints found."}

        latest_backup = backups[0]
        content = latest_backup.read_text(encoding="utf-8")
        target_file.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "restored_from": str(latest_backup),
            "file": str(target_file),
        }
