"""Data models and symbol structures for Code Intelligence & AST Refactoring Subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SymbolType(str, Enum):
    """Types of Python code symbols identified by AST analyzer."""

    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    MODULE = "module"


class PatchStatus(str, Enum):
    """Lifecycle state of a code refactoring patch."""

    PENDING = "pending"
    VALIDATED = "validated"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass(slots=True)
class CodeSymbol:
    """An indexed structural code symbol extracted via AST parsing."""

    name: str
    symbol_type: SymbolType
    file_path: str
    line_start: int
    line_end: int
    docstring: str = ""
    signature: str = ""
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize code symbol to dictionary."""
        return {
            "name": self.name,
            "symbol_type": self.symbol_type.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "docstring": self.docstring,
            "signature": self.signature,
            "dependencies": self.dependencies,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class PatchChange:
    """An atomic file modification with AST syntax validation."""

    file_path: str
    old_content: str
    new_content: str
    diff_unified: str = ""
    ast_valid: bool = False
    syntax_error: str | None = None
    backup_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize patch change to dictionary."""
        return {
            "file_path": self.file_path,
            "diff_unified": self.diff_unified,
            "ast_valid": self.ast_valid,
            "syntax_error": self.syntax_error,
            "backup_path": self.backup_path,
        }


@dataclass(slots=True)
class RefactorPlan:
    """A collection of planned file modifications with rollback checkpoints."""

    plan_id: str
    goal_fa: str
    changes: list[PatchChange]
    status: PatchStatus = PatchStatus.PENDING
    created_at: float = field(default_factory=time.time)
    applied_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize refactor plan to dictionary."""
        return {
            "plan_id": self.plan_id,
            "goal_fa": self.goal_fa,
            "status": self.status.value,
            "total_files": len(self.changes),
            "changes": [c.to_dict() for c in self.changes],
            "created_at": self.created_at,
            "applied_at": self.applied_at,
        }


@dataclass(slots=True)
class RefactorReport:
    """Execution telemetry and audit trail for applied code changes."""

    plan_id: str
    status: PatchStatus
    files_modified: list[str]
    syntax_valid: bool
    summary_fa: str
    diff_summary: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize refactor report to dictionary."""
        return {
            "plan_id": self.plan_id,
            "status": self.status.value,
            "files_modified": self.files_modified,
            "syntax_valid": self.syntax_valid,
            "summary_fa": self.summary_fa,
            "diff_summary": self.diff_summary,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp,
        }
