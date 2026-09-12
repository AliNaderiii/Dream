"""Domain models and data structures for Code Interpreter and Isolated Execution Sandbox."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class ExecutionLanguage(str, Enum):
    """Supported programming and query languages."""

    PYTHON = "python"
    BASH = "bash"
    SQL = "sql"
    JAVASCRIPT = "javascript"


class ExecutionStatus(str, Enum):
    """Outcome states of sandbox execution."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"


@dataclass(slots=True)
class ExecutionArtifact:
    """A file, chart, or dataset generated during sandbox execution."""

    name: str
    file_path: str
    mime_type: str
    size_bytes: int
    description_fa: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize artifact to dictionary."""
        return {
            "name": self.name,
            "file_path": self.file_path,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "description_fa": self.description_fa,
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class ExecutionResult:
    """Full outcome of a sandbox execution including stdout, stderr, and metrics."""

    code: str
    language: ExecutionLanguage
    status: ExecutionStatus
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    artifacts: list[ExecutionArtifact] = field(default_factory=list)
    error_message: str = ""
    variables_updated: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize execution result to dictionary."""
        return {
            "language": self.language.value,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": round(self.duration_ms, 2),
            "artifacts": [a.to_dict() for a in self.artifacts],
            "error_message": self.error_message,
            "variables_updated": self.variables_updated,
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class DatasetSummary:
    """Statistical and structural summary of an analyzed dataset."""

    total_rows: int
    total_columns: int
    column_names: list[str]
    column_types: dict[str, str]
    null_counts: dict[str, int]
    numeric_stats: dict[str, dict[str, float]]  # col -> {mean, min, max, std}
    sample_preview: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Serialize dataset summary to dictionary."""
        return {
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "column_names": self.column_names,
            "column_types": self.column_types,
            "null_counts": self.null_counts,
            "numeric_stats": self.numeric_stats,
            "sample_preview": self.sample_preview,
        }
