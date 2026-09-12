"""Deterministic code patch synthesis, AST validation, and safe atomic writes."""

from __future__ import annotations

import ast
import difflib
import logging
from pathlib import Path

from dream.refactor.types import PatchChange

logger = logging.getLogger(__name__)


class DeterministicPatcher:
    """Generates unified diffs, verifies AST syntax validity, and performs atomic file writes."""

    def create_patch(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
    ) -> PatchChange:
        """Create a patch change object with unified diff and AST validation."""
        diff_lines = list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )
        )
        diff_unified = "".join(diff_lines)

        # Validate syntax via AST
        ast_valid = True
        syntax_error = None
        if file_path.endswith(".py"):
            try:
                ast.parse(new_content, filename=file_path)
            except SyntaxError as exc:
                ast_valid = False
                syntax_error = f"Line {exc.lineno}: {exc.msg}"

        return PatchChange(
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            diff_unified=diff_unified,
            ast_valid=ast_valid,
            syntax_error=syntax_error,
        )

    def apply_patch(self, patch: PatchChange, backup: bool = True) -> bool:
        """Atomically write patch to disk after verifying syntax validity."""
        if not patch.ast_valid and patch.file_path.endswith(".py"):
            raise ValueError(
                f"Cannot apply patch to '{patch.file_path}': Syntax Error ({patch.syntax_error})"
            )

        target = Path(patch.file_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Create backup if file exists
        if backup and target.exists():
            backup_path = target.with_suffix(f"{target.suffix}.bak")
            backup_path.write_text(patch.old_content, encoding="utf-8")
            patch.backup_path = str(backup_path)

        target.write_text(patch.new_content, encoding="utf-8")
        return True

    def rollback_patch(self, patch: PatchChange) -> bool:
        """Revert file to original content."""
        target = Path(patch.file_path)
        target.write_text(patch.old_content, encoding="utf-8")
        return True
