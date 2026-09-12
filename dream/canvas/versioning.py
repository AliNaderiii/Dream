"""Artifact version control, differential computation, and branching."""

from __future__ import annotations

import difflib
import time
import uuid

from dream.canvas.types import ArtifactVersion, CanvasArtifact


class ArtifactVersionManager:
    """Manages version evolution, diff calculation, and history rollbacks."""

    @staticmethod
    def compute_diff(old_content: str, new_content: str) -> str:
        """Calculate unified line-by-line diff between two text versions."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="v_previous",
            tofile="v_current",
            lineterm="",
        )
        return "".join(diff)

    def record_update(
        self,
        artifact: CanvasArtifact,
        new_content: str,
        diff_summary: str = "",
        author: str = "assistant",
    ) -> CanvasArtifact:
        """Append current state to version history and apply new content."""
        if not artifact.versions:
            # Seed version 1 snapshot
            artifact.versions.append(
                ArtifactVersion(
                    version_number=artifact.version,
                    content=artifact.content,
                    diff_summary="نسخه اولیه",
                    timestamp=artifact.created_at,
                    author=author,
                )
            )

        new_version_num = artifact.version + 1
        calculated_diff = diff_summary or f"Update to v{new_version_num}"

        new_snapshot = ArtifactVersion(
            version_number=new_version_num,
            content=new_content,
            diff_summary=calculated_diff,
            timestamp=time.time(),
            author=author,
        )

        artifact.versions.append(new_snapshot)
        artifact.content = new_content
        artifact.version = new_version_num
        artifact.updated_at = time.time()
        return artifact

    def revert_to_version(
        self,
        artifact: CanvasArtifact,
        target_version: int,
    ) -> CanvasArtifact:
        """Rollback artifact content to a previous version and record rollback."""
        matched = next(
            (v for v in artifact.versions if v.version_number == target_version), None
        )
        if not matched:
            raise ValueError(f"Version {target_version} does not exist in artifact history.")

        return self.record_update(
            artifact=artifact,
            new_content=matched.content,
            diff_summary=f"بازگردانی به نسخه {target_version}",
        )

    def fork_artifact(
        self,
        artifact: CanvasArtifact,
        new_title: str | None = None,
    ) -> CanvasArtifact:
        """Create an independent fork/branch of an existing artifact."""
        fork_id = f"art-{uuid.uuid4().hex[:8]}"
        title = new_title or f"{artifact.title} (انشعاب)"
        now = time.time()
        initial_v = ArtifactVersion(
            version_number=1,
            content=artifact.content,
            diff_summary=f"انشعاب از {artifact.id} (v{artifact.version})",
            timestamp=now,
        )
        return CanvasArtifact(
            id=fork_id,
            title=title,
            artifact_type=artifact.artifact_type,
            content=artifact.content,
            language=artifact.language,
            version=1,
            versions=[initial_v],
            description_fa=artifact.description_fa,
            metadata=dict(artifact.metadata),
            created_at=now,
            updated_at=now,
        )
