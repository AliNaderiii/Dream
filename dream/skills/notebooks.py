"""Jupyter notebook integration: kernel lifecycle, .ipynb IO, JupyterLab.

The host reads and writes notebook JSON (nbformat v4 is a plain JSON schema,
so no third-party dependency is needed) and drives execution through
``jupyter_client`` when it is installed — kernels are per ``dataset_id`` and
live inside the dataset's session. If ``jupyter_client`` is missing every
execution entry point degrades to a clear :class:`NotebookUnavailableError`
instead of failing at import time, matching the P-08 Docker pattern.

Notebooks live at ``data/datasets/{dataset_id}/notebooks/{name}.ipynb``.
The agent manipulates cells only through these tools; nothing else touches
``.ipynb`` files directly.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "NotebookManager",
    "NotebookUnavailableError",
    "new_notebook",
    "read_notebook_file",
    "validate_notebook_name",
]

NOTEBOOK_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\- ]{0,79}$")

#: Truncation caps for outputs ferried back to the agent/frontend.
MAX_TEXT_OUTPUT = 20_000
MAX_IMAGE_B64 = 4 * 1024 * 1024


class NotebookUnavailableError(RuntimeError):
    """Raised when jupyter_client (or JupyterLab) is not installed."""


def validate_notebook_name(name: Any) -> str:
    """Validate a notebook display name (used as the file stem)."""
    if not isinstance(name, str) or not NOTEBOOK_NAME_RE.match(name):
        raise ValueError(
            "notebook name must be 1-80 characters of letters, digits, "
            "space, underscore, or hyphen"
        )
    return name.strip()


def new_notebook(cells: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build an nbformat-v4 notebook document from ``[{type, source}]`` cells."""
    nb_cells: list[dict[str, Any]] = []
    for cell in cells or []:
        if not isinstance(cell, dict):
            raise ValueError("each cell must be an object with 'type' and 'source'")
        cell_type = cell.get("type", "code")
        if cell_type not in ("code", "markdown"):
            raise ValueError("cell type must be 'code' or 'markdown'")
        source = cell.get("source", "")
        if not isinstance(source, str):
            raise ValueError("cell source must be a string")
        if len(source) > 100_000:
            raise ValueError("cell source must be under 100 KB")
        entry: dict[str, Any] = {
            "cell_type": cell_type,
            "metadata": {},
            "source": source.splitlines(keepends=True) or [""],
        }
        if cell_type == "code":
            entry["execution_count"] = None
            entry["outputs"] = []
        nb_cells.append(entry)
    return {
        "cells": nb_cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def read_notebook_file(path: Path) -> dict[str, Any]:
    """Read and minimally validate an .ipynb document."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("cells"), list):
        raise ValueError(f"{path.name} is not a valid notebook document")
    return raw


def _join_source(source: Any) -> str:
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source or "")


def _truncate(text: str, limit: int = MAX_TEXT_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated {len(text) - limit} characters]"


def _summarise_output(output: dict[str, Any]) -> dict[str, Any]:
    """Convert one raw nbformat output into a small transport-safe dict."""
    output_type = output.get("output_type", "")
    if output_type == "stream":
        return {
            "type": "stream",
            "name": output.get("name", "stdout"),
            "text": _truncate(_join_source(output.get("text", ""))),
        }
    if output_type in ("execute_result", "display_data"):
        data = output.get("data", {}) or {}
        entry: dict[str, Any] = {"type": output_type}
        if "text/plain" in data:
            entry["text"] = _truncate(_join_source(data["text/plain"]))
        for mime in ("image/png", "image/svg+xml"):
            if mime in data:
                blob = _join_source(data[mime])
                if len(blob) <= MAX_IMAGE_B64:
                    entry["image_mime"] = mime
                    entry["image_data"] = blob
                else:
                    entry["image_mime"] = mime
                    entry["image_truncated"] = True
                break
        if "text/html" in data and "image_data" not in entry:
            entry["html"] = _truncate(_join_source(data["text/html"]), 50_000)
        return entry
    if output_type == "error":
        return {
            "type": "error",
            "ename": str(output.get("ename", "")),
            "evalue": _truncate(str(output.get("evalue", "")), 2000),
            "traceback": _truncate("\n".join(output.get("traceback", [])), 8000),
        }
    return {"type": output_type or "unknown"}


@dataclass(slots=True)
class _KernelHandle:
    """A live kernel bound to one dataset session."""

    kernel_id: str
    dataset_id: str
    manager: Any
    client: Any
    started_at: float = field(default_factory=time.time)


class NotebookManager:
    """Owns notebook files and per-dataset kernels.

    Kernel lifecycle: ``ensure_kernel(dataset_id)`` starts (or reuses) one
    kernel per dataset; ``shutdown_kernel``/``shutdown_all`` stop them. The
    default kernel is Python 3; an R kernel is used only when the kernelspec
    is installed, otherwise the request degrades to Python with a warning.
    """

    def __init__(self, datasets_root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(datasets_root or os.environ.get("DREAM_DATASETS_DIR", "data/datasets"))
        self._kernels: dict[str, _KernelHandle] = {}
        self._lab_process: subprocess.Popen[bytes] | None = None
        self._lab_url: str | None = None

    # -- notebook files --------------------------------------------------- #

    def _dataset_dir(self, dataset_id: str) -> Path:
        if not isinstance(dataset_id, str) or not re.match(r"^[0-9a-f]{32}$", dataset_id):
            raise ValueError("dataset_id must be a 32-character hex id")
        directory = self.root / dataset_id
        if not directory.is_dir():
            raise ValueError(f"unknown dataset: {dataset_id}")
        return directory

    def _resolve_notebook(self, path: Any) -> Path:
        """Resolve a notebook path, confined to the datasets root."""
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty string")
        candidate = Path(path)
        resolved = (
            candidate if candidate.is_absolute() else (self.root / candidate)
        ).resolve()
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as exc:
            raise PermissionError("notebook path escapes the datasets directory") from exc
        if resolved.suffix != ".ipynb":
            raise ValueError("path must point to an .ipynb file")
        return resolved

    def create_notebook(
        self,
        dataset_id: str,
        name: str,
        cells: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create ``notebooks/{name}.ipynb`` under the dataset directory."""
        directory = self._dataset_dir(dataset_id) / "notebooks"
        directory.mkdir(exist_ok=True)
        stem = validate_notebook_name(name).replace(" ", "_")
        path = directory / f"{stem}.ipynb"
        document = new_notebook(cells)
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return {
            "notebook_path": str(path),
            "dataset_id": dataset_id,
            "name": stem,
            "cell_count": len(document["cells"]),
        }

    def read_notebook(self, path: str) -> dict[str, Any]:
        """Return ``[[cell_type, source, outputs?], ...]`` for a notebook."""
        resolved = self._resolve_notebook(path)
        if not resolved.exists():
            raise FileNotFoundError(f"notebook not found: {path}")
        document = read_notebook_file(resolved)
        cells = []
        for cell in document["cells"]:
            entry: dict[str, Any] = {
                "cell_type": cell.get("cell_type", "code"),
                "source": _join_source(cell.get("source")),
            }
            if cell.get("cell_type") == "code":
                entry["outputs"] = [
                    _summarise_output(o) for o in cell.get("outputs", [])
                ]
                entry["execution_count"] = cell.get("execution_count")
            cells.append(entry)
        return {"notebook_path": str(resolved), "cells": cells}

    # -- kernels ----------------------------------------------------------- #

    @staticmethod
    def _require_jupyter() -> Any:
        try:
            import jupyter_client
        except ImportError as exc:
            raise NotebookUnavailableError(
                "jupyter_client is not installed; notebook execution is unavailable"
            ) from exc
        return jupyter_client

    def ensure_kernel(self, dataset_id: str, kernel_name: str = "python3") -> str:
        """Start (or reuse) the kernel for a dataset. Returns the kernel id."""
        self._dataset_dir(dataset_id)
        existing = self._kernels.get(dataset_id)
        if existing is not None and existing.manager.is_alive():
            return existing.kernel_id
        jupyter_client = self._require_jupyter()
        if kernel_name not in ("python3", "ir"):
            raise ValueError("kernel must be 'python3' or 'ir'")
        if kernel_name == "ir":
            # Quietly fall back to Python when the R kernelspec is absent.
            try:
                specs = jupyter_client.kernelspec.KernelSpecManager().find_kernel_specs()
            except Exception:
                specs = {}
            if "ir" not in specs:
                logger.warning("R kernelspec not installed; falling back to python3")
                kernel_name = "python3"
        manager = jupyter_client.KernelManager(kernel_name=kernel_name)
        manager.start_kernel(cwd=str(self.root / dataset_id))
        client = manager.client()
        client.start_channels()
        try:
            client.wait_for_ready(timeout=60)
        except RuntimeError:
            client.stop_channels()
            manager.shutdown_kernel(now=True)
            raise NotebookUnavailableError("kernel failed to become ready") from None
        kernel_id = uuid.uuid4().hex[:12]
        self._kernels[dataset_id] = _KernelHandle(
            kernel_id=kernel_id, dataset_id=dataset_id, manager=manager, client=client
        )
        return kernel_id

    def _handle_for(self, kernel_id: str | None, dataset_id: str | None) -> _KernelHandle:
        if kernel_id:
            for handle in self._kernels.values():
                if handle.kernel_id == kernel_id:
                    return handle
            raise ValueError(f"unknown kernel: {kernel_id}")
        if dataset_id and dataset_id in self._kernels:
            return self._kernels[dataset_id]
        raise ValueError("no kernel running; call ensure_kernel first")

    def _execute_source(self, handle: _KernelHandle, source: str, timeout: int = 120) -> tuple[
        list[dict[str, Any]], int | None
    ]:
        """Run one code cell on a kernel; returns (outputs, execution_count)."""
        client = handle.client
        msg_id = client.execute(source)
        outputs: list[dict[str, Any]] = []
        execution_count: int | None = None
        deadline = time.monotonic() + timeout
        idle = False
        while not idle:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"cell execution exceeded {timeout}s")
            try:
                message = client.get_iopub_msg(timeout=min(remaining, 5.0))
            except Exception:
                continue
            if message.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            msg_type = message.get("msg_type", "")
            content = message.get("content", {})
            if msg_type == "status" and content.get("execution_state") == "idle":
                idle = True
            elif msg_type == "execute_input":
                execution_count = content.get("execution_count")
            elif msg_type == "stream":
                outputs.append({
                    "output_type": "stream",
                    "name": content.get("name", "stdout"),
                    "text": content.get("text", ""),
                })
            elif msg_type in ("execute_result", "display_data"):
                outputs.append({
                    "output_type": msg_type,
                    "data": content.get("data", {}),
                    "metadata": content.get("metadata", {}),
                    **(
                        {"execution_count": content.get("execution_count")}
                        if msg_type == "execute_result"
                        else {}
                    ),
                })
            elif msg_type == "error":
                outputs.append({
                    "output_type": "error",
                    "ename": content.get("ename", ""),
                    "evalue": content.get("evalue", ""),
                    "traceback": content.get("traceback", []),
                })
        return outputs, execution_count

    def execute_notebook(
        self, path: str, kernel_id: str | None = None, timeout: int = 120
    ) -> dict[str, Any]:
        """Execute every code cell in order, persisting outputs to the file."""
        resolved = self._resolve_notebook(path)
        if not resolved.exists():
            raise FileNotFoundError(f"notebook not found: {path}")
        dataset_id = resolved.parent.parent.name
        if kernel_id:
            handle = self._handle_for(kernel_id, None)
        else:
            if dataset_id not in self._kernels or not self._kernels[
                dataset_id
            ].manager.is_alive():
                self.ensure_kernel(dataset_id)
            handle = self._kernels[dataset_id]
        document = read_notebook_file(resolved)
        executed = []
        for index, cell in enumerate(document["cells"]):
            if cell.get("cell_type") != "code":
                continue
            outputs, execution_count = self._execute_source(
                handle, _join_source(cell.get("source")), timeout
            )
            cell["outputs"] = outputs
            cell["execution_count"] = execution_count
            executed.append({
                "cell_index": index,
                "execution_count": execution_count,
                "outputs": [_summarise_output(o) for o in outputs],
            })
        resolved.write_text(
            json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return {
            "notebook_path": str(resolved),
            "kernel_id": handle.kernel_id,
            "cells_executed": len(executed),
            "outputs": executed,
        }

    def run_cell(self, path: str, cell_index: int, timeout: int = 120) -> dict[str, Any]:
        """Execute a single cell by index; persists outputs to the file."""
        if not isinstance(cell_index, int) or cell_index < 0:
            raise ValueError("cell_index must be a non-negative integer")
        resolved = self._resolve_notebook(path)
        if not resolved.exists():
            raise FileNotFoundError(f"notebook not found: {path}")
        document = read_notebook_file(resolved)
        if cell_index >= len(document["cells"]):
            raise ValueError(
                f"cell_index {cell_index} out of range "
                f"(notebook has {len(document['cells'])} cells)"
            )
        cell = document["cells"][cell_index]
        if cell.get("cell_type") != "code":
            return {
                "notebook_path": str(resolved),
                "cell_index": cell_index,
                "cell_type": cell.get("cell_type"),
                "outputs": [],
            }
        dataset_id = resolved.parent.parent.name
        if dataset_id not in self._kernels or not self._kernels[dataset_id].manager.is_alive():
            self.ensure_kernel(dataset_id)
        handle = self._kernels[dataset_id]
        outputs, execution_count = self._execute_source(
            handle, _join_source(cell.get("source")), timeout
        )
        cell["outputs"] = outputs
        cell["execution_count"] = execution_count
        resolved.write_text(
            json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return {
            "notebook_path": str(resolved),
            "cell_index": cell_index,
            "cell_type": "code",
            "execution_count": execution_count,
            "outputs": [_summarise_output(o) for o in outputs],
        }

    def shutdown_kernel(self, dataset_id: str) -> bool:
        """Stop the kernel bound to a dataset, if any."""
        handle = self._kernels.pop(dataset_id, None)
        if handle is None:
            return False
        try:
            handle.client.stop_channels()
            handle.manager.shutdown_kernel(now=True)
        except Exception:  # pragma: no cover - teardown must never raise
            logger.exception("kernel shutdown failed for dataset %s", dataset_id)
        return True

    def shutdown_all(self) -> None:
        """Stop every kernel and any JupyterLab process."""
        for dataset_id in list(self._kernels):
            self.shutdown_kernel(dataset_id)
        if self._lab_process is not None and self._lab_process.poll() is None:
            self._lab_process.terminate()
            try:
                self._lab_process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self._lab_process.kill()
        self._lab_process = None
        self._lab_url = None

    # -- JupyterLab -------------------------------------------------------- #

    def open_jupyterlab(self, path: str, port: int = 8890) -> dict[str, Any]:
        """Spawn JupyterLab rooted at the datasets directory; return its URL."""
        resolved = self._resolve_notebook(path)
        if not resolved.exists():
            raise FileNotFoundError(f"notebook not found: {path}")
        if self._lab_process is not None and self._lab_process.poll() is None:
            relative = resolved.relative_to(self.root.resolve())
            return {"url": f"{self._lab_url}/lab/tree/{relative}", "already_running": True}
        try:
            import jupyterlab  # noqa: F401
        except ImportError as exc:
            raise NotebookUnavailableError(
                "JupyterLab is not installed; run 'pip install jupyterlab'"
            ) from exc
        token = uuid.uuid4().hex
        command = [
            sys.executable,
            "-m",
            "jupyterlab",
            "--no-browser",
            f"--port={port}",
            "--ip=127.0.0.1",
            f"--ServerApp.token={token}",
            f"--ServerApp.root_dir={self.root.resolve()}",
        ]
        self._lab_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(self.root.resolve()),
        )
        self._lab_url = f"http://127.0.0.1:{port}/?token={token}"
        relative = resolved.relative_to(self.root.resolve())
        return {
            "url": f"http://127.0.0.1:{port}/lab/tree/{relative}?token={token}",
            "already_running": False,
        }
