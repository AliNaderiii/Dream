"""Core coordinator for Canvas Artifact Studio, session tracking, and rendering."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from dream.canvas.renderer import CanvasRenderer
from dream.canvas.types import (
    ArtifactType,
    ArtifactVersion,
    CanvasArtifact,
    CanvasSession,
)
from dream.canvas.versioning import ArtifactVersionManager


class CanvasEngine:
    """Coordinates active canvas artifacts, multi-version tracking, and visual exports."""

    def __init__(
        self,
        session_id: str | None = None,
        version_manager: ArtifactVersionManager | None = None,
        renderer: CanvasRenderer | None = None,
    ) -> None:
        self.session_id = session_id or f"canvas-{uuid.uuid4().hex[:6]}"
        self.version_manager = version_manager or ArtifactVersionManager()
        self.renderer = renderer or CanvasRenderer()
        self.session = CanvasSession(session_id=self.session_id)

    def create_artifact(
        self,
        title: str,
        artifact_type: str | ArtifactType,
        content: str,
        language: str = "",
        description_fa: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CanvasArtifact:
        """Create a new canvas artifact and set as active."""
        if isinstance(artifact_type, str):
            try:
                art_enum = ArtifactType(artifact_type.lower())
            except ValueError:
                art_enum = ArtifactType.CODE
        else:
            art_enum = artifact_type

        art_id = f"art-{uuid.uuid4().hex[:6]}"
        now = time.time()
        initial_v = ArtifactVersion(
            version_number=1,
            content=content,
            diff_summary="\u0646\u0633\u062e\u0647 \u0627\u0648\u0644\u06cc\u0647",
            timestamp=now,
        )

        artifact = CanvasArtifact(
            id=art_id,
            title=title,
            artifact_type=art_enum,
            content=content,
            language=language or ("python" if art_enum == ArtifactType.CODE else ""),
            version=1,
            versions=[initial_v],
            description_fa=description_fa,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

        self.session.artifacts[art_id] = artifact
        self.session.active_artifact_id = art_id
        self.session.updated_at = now
        return artifact

    def update_artifact(
        self,
        artifact_id: str,
        content: str,
        diff_summary: str = "",
    ) -> CanvasArtifact:
        """Update artifact content, appending a new version to its history."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found in canvas session.")

        updated = self.version_manager.record_update(
            artifact=art,
            new_content=content,
            diff_summary=diff_summary,
        )
        self.session.active_artifact_id = artifact_id
        self.session.updated_at = time.time()
        return updated

    def get_artifact(
        self,
        artifact_id: str,
        version: int | None = None,
    ) -> CanvasArtifact | None:
        """Retrieve artifact by ID, optionally scoped to a specific historical version."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            return None

        if version is not None and version != art.version:
            matched_v = next((v for v in art.versions if v.version_number == version), None)
            if matched_v:
                # Return snapshot clone
                return CanvasArtifact(
                    id=art.id,
                    title=f"{art.title} (v{version})",
                    artifact_type=art.artifact_type,
                    content=matched_v.content,
                    language=art.language,
                    version=matched_v.version_number,
                    versions=list(art.versions),
                    description_fa=art.description_fa,
                    metadata=dict(art.metadata),
                    created_at=art.created_at,
                    updated_at=matched_v.timestamp,
                )
        return art

    def list_artifacts(self) -> list[CanvasArtifact]:
        """List all artifacts currently managed in the session."""
        return list(self.session.artifacts.values())

    def delete_artifact(self, artifact_id: str) -> bool:
        """Remove an artifact from the session."""
        if artifact_id in self.session.artifacts:
            del self.session.artifacts[artifact_id]
            if self.session.active_artifact_id == artifact_id:
                self.session.active_artifact_id = (
                    next(iter(self.session.artifacts.keys()), None)
                    if self.session.artifacts
                    else None
                )
            return True
        return False

    def fork_artifact(
        self,
        artifact_id: str,
        new_title: str | None = None,
    ) -> CanvasArtifact:
        """Branch an existing artifact into a new independent version tree."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found.")

        forked = self.version_manager.fork_artifact(art, new_title=new_title)
        self.session.artifacts[forked.id] = forked
        self.session.active_artifact_id = forked.id
        return forked

    def revert_artifact(
        self,
        artifact_id: str,
        target_version: int,
    ) -> CanvasArtifact:
        """Rollback artifact to an earlier version."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found.")

        reverted = self.version_manager.revert_to_version(art, target_version)
        self.session.updated_at = time.time()
        return reverted

    def diff_artifact_versions(
        self,
        artifact_id: str,
        v_from: int | None = None,
        v_to: int | None = None,
    ) -> str:
        """Calculate line-by-line diff between two versions of an artifact."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found.")

        v_from_num = v_from if v_from is not None else (art.version - 1 if art.version > 1 else 1)
        v_to_num = v_to if v_to is not None else art.version

        c_from = next((v.content for v in art.versions if v.version_number == v_from_num), "")
        c_to = next((v.content for v in art.versions if v.version_number == v_to_num), art.content)

        return self.version_manager.compute_diff(c_from, c_to)

    def render_preview(
        self,
        artifact_id: str,
        theme: str = "dark",
    ) -> str:
        """Render single artifact as standalone HTML."""
        art = self.session.artifacts.get(artifact_id)
        if not art:
            raise KeyError(f"Artifact '{artifact_id}' not found.")
        return self.renderer.render_to_standalone_html(art, theme=theme)

    def export_bundle(self, format_type: str = "html") -> str:
        """Export all session artifacts as Markdown or JSON."""
        artifacts = list(self.session.artifacts.values())
        if format_type.lower() == "json":
            return json.dumps(
                {
                    "session": self.session.to_dict(),
                    "artifacts": [a.to_dict() for a in artifacts],
                },
                ensure_ascii=False,
                indent=2,
            )
        return self.renderer.render_to_markdown_bundle(artifacts)

    def reset(self) -> None:
        """Clear all session artifacts."""
        self.session.artifacts.clear()
        self.session.active_artifact_id = None
        self.session.updated_at = time.time()

    def get_status(self) -> dict[str, Any]:
        """Return operational summary of canvas session."""
        return {
            "session_id": self.session.session_id,
            "total_artifacts": len(self.session.artifacts),
            "active_artifact_id": self.session.active_artifact_id,
            "artifacts_summary": [
                {
                    "id": a.id,
                    "title": a.title,
                    "type": a.artifact_type.value,
                    "version": a.version,
                }
                for a in self.session.artifacts.values()
            ],
        }
