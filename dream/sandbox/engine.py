"""Code Interpreter Sandbox Engine Coordinator."""

from __future__ import annotations

from typing import Any

from dream.sandbox.analyzer import DataScienceAnalyzer
from dream.sandbox.executor import SandboxExecutor
from dream.sandbox.types import DatasetSummary, ExecutionArtifact, ExecutionResult


class SandboxEngine:
    """Coordinates code execution, stateful REPL namespaces, and automated data analysis."""

    def __init__(
        self,
        executor: SandboxExecutor | None = None,
        analyzer: DataScienceAnalyzer | None = None,
    ) -> None:
        self.executor = executor or SandboxExecutor()
        self.analyzer = analyzer or DataScienceAnalyzer()
        self._history: list[ExecutionResult] = []
        self._all_artifacts: list[ExecutionArtifact] = []

    def run_code(
        self,
        code: str,
        timeout_seconds: float = 15.0,
    ) -> ExecutionResult:
        """Execute Python code in isolated sandbox and register output artifacts."""
        result = self.executor.execute_python(code, timeout_seconds=timeout_seconds)
        self._history.append(result)
        for art in result.artifacts:
            self._all_artifacts.append(art)
        return result

    def analyze_data(
        self,
        data_or_path: str,
    ) -> tuple[DatasetSummary, str]:
        """Perform statistical profiling on a CSV/JSON tabular dataset."""
        summary = self.analyzer.analyze_tabular_data(data_or_path)
        report_md = self.analyzer.format_summary_markdown(summary)
        return summary, report_md

    def reset(self) -> None:
        """Reset stateful session variables and clear history."""
        self.executor.reset_namespace()
        self._history.clear()

    def list_artifacts(self) -> list[ExecutionArtifact]:
        """Return all files and charts generated during this sandbox session."""
        return list(self._all_artifacts)

    def get_status(self) -> dict[str, Any]:
        """Get summary metrics on executions, namespaces, and generated artifacts."""
        return {
            "total_executions": len(self._history),
            "total_artifacts": len(self._all_artifacts),
            "workspace_dir": str(self.executor.workspace_dir),
            "variables_count": len(self.executor._namespace),
            "last_execution_status": self._history[-1].status.value if self._history else "ready",
        }
