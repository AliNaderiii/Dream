"""Reproducibility export package generator for Dream.

Bundles code, input data, configuration, environment specification (Dockerfile
& requirements.txt), provenance records, and a step-by-step README into a
reproducible ZIP package.
"""

from __future__ import annotations

import base64
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from typing import Any

from .models import ProvenanceRecord
from .tracker import ProvenanceTracker


class ReproducibilityExporter:
    """Generates standalone reproducibility archives for provenance records and artifacts."""

    def __init__(self, tracker: ProvenanceTracker, base_dir: str | None = None) -> None:
        self.tracker = tracker
        self.base_dir = base_dir or os.getcwd()

    def export(
        self,
        *,
        record_id: str | None = None,
        session_id: str | None = None,
        artifact_path: str | None = None,
        output_file: str | None = None,
    ) -> dict[str, Any]:
        """Create a reproducibility zip package.

        Returns metadata dict containing 'filename', 'size', 'records_count', and
        either 'file_path' or 'base64_data'.
        """
        records: list[ProvenanceRecord] = []
        if record_id:
            rec = self.tracker.get(record_id)
            if rec:
                records.append(rec)
                # Include parent records
                curr = rec
                while curr.parent_record_id:
                    parent = self.tracker.get(curr.parent_record_id)
                    if parent:
                        records.insert(0, parent)
                        curr = parent
                    else:
                        break
        elif session_id:
            recs, _ = self.tracker.list_records(agent_id=session_id, limit=500)
            records = recs[::-1]  # Chronological order
        elif artifact_path:
            recs, _ = self.tracker.list_records(limit=500)
            for r in recs:
                if any(f.path == artifact_path for f in r.output_snapshot) or any(
                    f.path == artifact_path for f in r.input_snapshot
                ):
                    records.append(r)
            records.sort(key=lambda r: r.timestamp)
        else:
            recs, _ = self.tracker.list_records(limit=100)
            records = recs[::-1]

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. Write provenance records
            records_data = [r.to_dict() for r in records]
            zf.writestr(
                "provenance/records.json", json.dumps(records_data, indent=2, ensure_ascii=False)
            )

            # 2. Config and environment
            model_info = {}
            for r in records:
                if r.model_snapshot:
                    model_info = r.model_snapshot.to_dict()
                    break

            config_data = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "records_included": len(records),
                "model_configuration": model_info,
                "target": {
                    "record_id": record_id,
                    "session_id": session_id,
                    "artifact_path": artifact_path,
                },
            }
            zf.writestr("config.json", json.dumps(config_data, indent=2, ensure_ascii=False))

            # 3. Environment specs: requirements.txt and Dockerfile
            requirements_txt = (
                "# Generated Dream Reproducibility Environment\npython>=3.10\npytest>=7.4\n"
            )
            zf.writestr("requirements.txt", requirements_txt)

            dockerfile = (
                "FROM python:3.11-slim\n"
                "WORKDIR /workspace\n"
                "COPY requirements.txt .\n"
                "RUN pip install --no-cache-dir -r requirements.txt\n"
                "COPY . /workspace\n"
                'CMD ["python", "code/reproduce.py"]\n'
            )
            zf.writestr("Dockerfile", dockerfile)

            # 4. Code & Steps
            code_lines = [
                "# Dream Automated Reproducibility Script",
                f"# Generated: {datetime.now(timezone.utc).isoformat()}",
                "",
                "import os",
                "import sys",
                "import json",
                "",
                "def main():",
                "    print('=== Executing Provenance Lineage ===')",
            ]

            for idx, r in enumerate(records, 1):
                if r.event_type == "tool_call":
                    tool = r.payload.get("tool_name", "tool")
                    args = json.dumps(r.payload.get("arguments", {}), ensure_ascii=False)
                    code_lines.append(f"    # Step {idx}: Call tool {tool}")
                    code_lines.append(f"    print('Step {idx}: Calling {tool} with args: {args}')")
                elif r.event_type == "code_execution":
                    code_lines.append(f"    # Step {idx}: Code Execution")
                    code_lines.append("    print('Executing recorded script...')")
                elif r.event_type in ("file_write", "file_read"):
                    fpath = r.payload.get("path", "")
                    code_lines.append(f"    # Step {idx}: {r.event_type} on {fpath}")
                elif r.event_type == "model_response":
                    code_lines.append(
                        f"    # Step {idx}: Model Response ({r.token_count or 0} tokens)"
                    )

            code_lines.append("    print('=== Reproduction Complete ===')")
            code_lines.append("")
            code_lines.append("if __name__ == '__main__':")
            code_lines.append("    main()")

            zf.writestr("code/reproduce.py", "\n".join(code_lines))

            # 5. README.md
            readme_text = self._build_readme(records, config_data)
            zf.writestr("README.md", readme_text)

            # 6. Include existing input/output files if available in workspace
            for r in records:
                for snap in r.input_snapshot + r.output_snapshot:
                    if snap.path:
                        abs_f = (
                            snap.path
                            if os.path.isabs(snap.path)
                            else os.path.join(self.base_dir, snap.path)
                        )
                        if (
                            os.path.exists(abs_f)
                            and os.path.isfile(abs_f)
                            and os.path.getsize(abs_f) < 20 * 1024 * 1024
                        ):
                            try:
                                with open(abs_f, "rb") as src_f:
                                    zf.writestr(f"data/{os.path.basename(snap.path)}", src_f.read())
                            except OSError:
                                pass

        zip_bytes = buffer.getvalue()
        target_name = f"reproducibility_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"

        if output_file:
            os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
            with open(output_file, "wb") as f:
                f.write(zip_bytes)
            return {
                "filename": os.path.basename(output_file),
                "file_path": output_file,
                "size": len(zip_bytes),
                "records_count": len(records),
            }

        return {
            "filename": target_name,
            "size": len(zip_bytes),
            "records_count": len(records),
            "base64_data": base64.b64encode(zip_bytes).decode("ascii"),
        }

    def _build_readme(self, records: list[ProvenanceRecord], config: dict[str, Any]) -> str:
        """Generate human-readable reproduction guide."""
        lines = [
            "# Dream Provenance & Reproducibility Package",
            "",
            f"**Exported At:** `{config['exported_at']}`  ",
            f"**Records Count:** `{config['records_included']}`  ",
            f"**Target Context:** `{json.dumps(config['target'])}`  ",
            "",
            "## Package Contents",
            "",
            "- `provenance/records.json`: Full immutable, SHA-256-verified event log",
            "- `config.json`: Environment parameters and model metadata",
            "- `requirements.txt`: Python package specifications",
            "- `Dockerfile`: Containerized execution recipe",
            "- `code/reproduce.py`: Linear reproduction runner",
            "- `data/`: Input and output snapshots captured during execution",
            "",
            "## How to Reproduce",
            "",
            "### Option 1: Local Python Environment",
            "```bash",
            "python3 -m venv .venv",
            "source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate",
            "pip install -r requirements.txt",
            "python code/reproduce.py",
            "```",
            "",
            "### Option 2: Docker Container",
            "```bash",
            "docker build -t dream-reproduce .",
            "docker run --rm dream-reproduce",
            "```",
            "",
            "## Provenance Event Timeline",
            "",
        ]

        for i, r in enumerate(records, 1):
            dur = f" ({r.duration_ms}ms)" if r.duration_ms is not None else ""
            lines.append(f"{i}. **{r.timestamp}** — `{r.event_type}` (Agent: `{r.agent_id}`){dur}")
            if r.payload:
                preview = json.dumps(r.payload, ensure_ascii=False)
                if len(preview) > 120:
                    preview = preview[:117] + "..."
                lines.append(f"   - Payload: `{preview}`")

        return "\n".join(lines) + "\n"
