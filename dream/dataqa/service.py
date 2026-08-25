"""Stateful orchestration and the strict ``final_answer`` contract."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from dream.dataqa.charts import MAX_SVG_BYTES, choose_chart, render_svg
from dream.dataqa.dataio import DataReadError
from dream.dataqa.discovery import discover, profile_candidate, rank_candidate, workspace_root
from dream.dataqa.executor import execute_plan
from dream.dataqa.models import DatasetProfile, ExecutionResult, QueryPlan
from dream.dataqa.planner import plan_question
from dream.security.secrets import redact_structure, redact_text

MAX_SESSIONS = 100
MAX_TURNS_PER_SESSION = 20
MAX_SESSION_BYTES = 24 * 1024 * 1024


class DataQAError(ValueError):
    pass


class DataQAService:
    """File-backed sessions: every turn is bounded and survives bridge restarts."""

    def __init__(self, root: Path | None = None) -> None:
        base = (root or workspace_root() / "data/dataqa").resolve()
        if not base.is_relative_to(workspace_root()):
            raise DataQAError("Data Q&A state must remain in the Dream workspace")
        self.root = base
        self.sessions_dir = base / "sessions"
        self.charts_dir = base / "charts"
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in (self.sessions_dir, self.charts_dir):
            if directory.is_symlink():
                raise DataQAError("Data Q&A storage directories cannot be symbolic links")
            directory.mkdir(exist_ok=True)
            self._validate_storage_directory(directory)
        self._lock = threading.RLock()

    @staticmethod
    def _validate_storage_directory(directory: Path) -> None:
        resolved = directory.resolve()
        if (
            directory.is_symlink()
            or not resolved.is_dir()
            or resolved != directory
            or not resolved.is_relative_to(workspace_root())
        ):
            raise DataQAError("Data Q&A storage must remain a regular workspace directory")

    def _session_path(self, session_id: str) -> Path:
        self._validate_storage_directory(self.sessions_dir)
        if (
            not isinstance(session_id, str)
            or len(session_id) != 32
            or any(c not in "0123456789abcdef" for c in session_id)
        ):
            raise DataQAError("session_id must be a 32-character hexadecimal id")
        return self.sessions_dir / f"{session_id}.json"

    def _read(self, session_id: str) -> dict[str, Any]:
        path = self._session_path(session_id)
        try:
            if path.is_symlink() or path.stat().st_size > MAX_SESSION_BYTES:
                raise DataQAError("Data Q&A session is unsafe or exceeds its storage quota")
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DataQAError("unknown Data Q&A session") from exc
        except (OSError, ValueError) as exc:
            raise DataQAError("Data Q&A session is unreadable") from exc
        return data

    def _write(self, state: dict[str, Any]) -> None:
        path = self._session_path(state["session_id"])
        encoded = json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")
        if len(encoded) > MAX_SESSION_BYTES:
            raise DataQAError("Data Q&A session storage quota reached")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}-", dir=self.sessions_dir
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def discover(
        self,
        query: str = "",
        source: str | None = None,
        *,
        limit: int = 20,
        include_profiles: bool = True,
    ) -> dict[str, Any]:
        try:
            candidates = discover(query, source, limit=max(limit * 3, limit))
        except DataReadError as exc:
            raise DataQAError(str(exc)) from exc
        profiles: dict[str, DatasetProfile] = {}
        # Profile only bounded candidates; schema matches improve folder discovery.
        for candidate in candidates[: min(len(candidates), 30)]:
            if not candidate.loadable:
                continue
            try:
                profile = profile_candidate(candidate, sample_limit=500)
                profiles[candidate.dataset_id] = profile
                candidate.columns = [column.name for column in profile.columns]
                candidate.row_count = profile.row_count
                # Re-rank after bounded profiling so schema concepts and Persian/English
                # aliases can influence folder discovery, not only registry metadata.
                rank_candidate(candidate, query)
            except DataReadError as exc:
                candidate.loadable = False
                candidate.limitation = redact_text(str(exc))
        candidates.sort(key=lambda item: (-item.score, item.name.lower()))
        selected = candidates[: max(1, min(limit, 100))]
        return redact_structure(
            {
                "query": query,
                "source": source or "everything",
                "count": len(selected),
                "candidates": [
                    {
                        **item.public_dict(),
                        **(
                            {"profile": profiles[item.dataset_id].to_dict()}
                            if include_profiles and item.dataset_id in profiles
                            else {}
                        ),
                    }
                    for item in selected
                ],
            }
        )

    def create_session(
        self, *, source: str | None = None, query: str = "", dataset_id: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            if len(list(self.sessions_dir.glob("*.json"))) >= MAX_SESSIONS:
                raise DataQAError("Data Q&A session quota reached; delete an older session")
            candidates = discover(query, source, limit=100)
            candidate = next((item for item in candidates if item.dataset_id == dataset_id), None)
            if candidate is None and dataset_id is not None:
                raise DataQAError("The selected dataset is unavailable in this source")
            if candidate is None and candidates:
                candidate = candidates[0]
            if candidate is None:
                raise DataQAError("No supported dataset was found in the selected source")
            try:
                profile = profile_candidate(candidate)
            except DataReadError as exc:
                raise DataQAError(str(exc)) from exc
            if not profile.loadable:
                raise DataQAError(profile.limitation or "dataset cannot be loaded")
            session_id = uuid.uuid4().hex
            now = time.time()
            state = {
                "session_id": session_id,
                "created_at": now,
                "updated_at": now,
                "dataset": candidate.public_dict(),
                "dataset_path": candidate.path,
                "profile": profile.to_dict(),
                "last_plan": None,
                "turns": [],
            }
            self._write(state)
            return self._public_session(state)

    def _public_session(
        self, state: dict[str, Any], *, include_turns: bool = False
    ) -> dict[str, Any]:
        result = {
            key: state[key]
            for key in ("session_id", "created_at", "updated_at", "dataset", "profile")
        }
        result["turn_count"] = len(state.get("turns", []))
        result["stateful"] = state.get("last_plan") is not None
        if include_turns:
            result["turns"] = state.get("turns", [])[-20:]
        return redact_structure(result)

    def list_sessions(self) -> dict[str, Any]:
        self._validate_storage_directory(self.sessions_dir)
        sessions = []
        paths: list[Path] = []
        for path in self.sessions_dir.glob("*.json"):
            try:
                if not path.is_symlink() and path.stat().st_size <= MAX_SESSION_BYTES:
                    paths.append(path)
            except OSError:
                continue
        try:
            paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        except OSError:
            pass
        for path in paths:
            try:
                sessions.append(self._public_session(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError):
                continue
        return {"sessions": sessions[:MAX_SESSIONS]}

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._public_session(self._read(session_id), include_turns=True)

    def delete_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            path = self._session_path(session_id)
            existed = path.exists()
            path.unlink(missing_ok=True)
            self._validate_storage_directory(self.charts_dir)
            for asset in self.charts_dir.glob(f"{session_id}-*.svg"):
                asset.unlink(missing_ok=True)
            return {"deleted": existed, "session_id": session_id}

    @staticmethod
    def _profile(raw: dict[str, Any]) -> DatasetProfile:
        from dream.dataqa.models import ColumnProfile

        values = dict(raw)
        values.pop("infobox", None)
        values["columns"] = [ColumnProfile(**item) for item in raw.get("columns", [])]
        return DatasetProfile(**values)

    def _uncertain(
        self, plan: QueryPlan, profile: DatasetProfile, *, error: str | None = None
    ) -> dict[str, Any]:
        fa = plan.language == "fa"
        answer = (
            "از این داده‌ها قابل تعیین نیست." if fa else "I can't determine that from this data."
        )
        reason = error or plan.intent or "The question is not grounded in the available schema."
        return {
            "status": "insufficient_data",
            "answer": answer,
            "summary": answer,
            "reason": redact_text(reason),
            "language": plan.language,
            "evidence": {"dataset": profile.name, "schema": profile.infobox(), "rows": []},
            "plan": plan.to_dict(),
            "generated_code": plan.code,
            "chart": None,
            "warnings": [],
            "grounded": True,
        }

    @staticmethod
    def _answer_text(plan: QueryPlan, result: ExecutionResult) -> str:
        if not result.rows:
            return (
                "از این داده‌ها قابل تعیین نیست."
                if plan.language == "fa"
                else "I can't determine that from this data."
            )
        if len(result.rows) == 1 and len(result.rows[0]) == 1:
            name, value = next(iter(result.rows[0].items()))
            if value is None:
                return (
                    "از این داده‌ها قابل تعیین نیست."
                    if plan.language == "fa"
                    else "I can't determine that from this data."
                )
            return f"{name}: {value:,.4g}" if isinstance(value, float) else f"{name}: {value}"
        if plan.action == "aggregate" and plan.groups and len(result.rows) <= 8:
            value_name = (
                "count_rows" if plan.aggregate == "count" else f"{plan.aggregate}_{plan.metric}"
            )
            labels = [
                " / ".join(str(row.get(group, ""))[:80] for group in plan.groups)
                + f": {row.get(value_name)}"
                for row in result.rows
            ]
            if plan.language == "fa":
                aggregate_label = {
                    "mean": "میانگین",
                    "sum": "مجموع",
                    "count": "تعداد",
                    "min": "کمینه",
                    "max": "بیشینه",
                }.get(plan.aggregate, plan.aggregate or "نتیجه")
                heading = (
                    f"{aggregate_label} {plan.metric or 'ردیف'} به تفکیک {' / '.join(plan.groups)}"
                )
            else:
                heading = f"{value_name} by {' / '.join(plan.groups)}"
            return f"{heading} — " + "; ".join(labels)
        count = len(result.rows)
        return (
            f"{count} ردیف نتیجه در شواهد آمده است."
            if plan.language == "fa"
            else f"The evidence contains {count} result rows."
        )

    def ask(
        self,
        session_id: str,
        question: str,
        *,
        timeout: float = 10.0,
        force_chart: bool | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._read(session_id)
            profile = self._profile(state["profile"])
            previous = QueryPlan.from_dict(state["last_plan"]) if state.get("last_plan") else None
            plan = plan_question(question, profile, previous=previous)
            if plan.action == "reset":
                return self.reset(session_id)
            if force_chart is not None:
                plan.wants_chart = bool(force_chart)
            if plan.action == "insufficient":
                answer = self._uncertain(plan, profile)
            else:
                execution_started = time.monotonic()
                dataset_path = Path(state["dataset_path"])
                result = execute_plan(
                    dataset_path,
                    state["dataset"]["format"],
                    plan,
                    timeout=timeout,
                    workspace=workspace_root(),
                )
                unsafe_path_error = result.error and any(
                    marker in result.error.casefold()
                    for marker in ("workspace", "escaped", "symlink")
                )
                if result.status == "error" and not unsafe_path_error:
                    remaining = timeout - (time.monotonic() - execution_started)
                    if remaining >= 0.05:
                        # Re-ground from the immutable schema and retry once. The retry stays
                        # inside the original deadline and never re-reads an unsafe path.
                        repaired = plan_question(question, profile, previous=previous)
                        if repaired.action not in {"insufficient", "reset"}:
                            result = execute_plan(
                                dataset_path,
                                state["dataset"]["format"],
                                repaired,
                                timeout=remaining,
                                workspace=workspace_root(),
                            )
                            result.warnings.insert(0, "Execution was re-grounded and retried once.")
                            plan = repaired
                if result.status != "ok":
                    answer = self._uncertain(plan, profile, error=result.error)
                    if result.status == "cancelled":
                        answer["status"] = "cancelled"
                    elif result.status == "error" and not unsafe_path_error:
                        answer["status"] = "error"
                    answer["warnings"] = result.warnings
                else:
                    chart = None
                    chart_path = self.charts_dir / f"{session_id}-{len(state['turns']) + 1}.svg"
                    chart_spec = choose_chart(plan, result.rows)
                    if chart_spec:
                        try:
                            self._validate_storage_directory(self.charts_dir)
                            render_svg(chart_spec, chart_path)
                            chart = {
                                "type": chart_spec.kind,
                                "format": "svg",
                                "validated": True,
                                "points": len(chart_spec.data),
                                "labels": [chart_spec.x_label, chart_spec.y_label],
                                "consistency": (
                                    "Chart values and labels match the execution evidence."
                                ),
                                "asset_path": str(chart_path.relative_to(workspace_root())),
                                "svg": chart_path.read_text(encoding="utf-8"),
                            }
                        except ValueError as exc:
                            result.warnings.append(redact_text(str(exc)))
                    text = self._answer_text(plan, result)
                    answer = {
                        "status": "ok",
                        "answer": text,
                        "summary": text,
                        "language": plan.language,
                        "grounded": True,
                        "evidence": {
                            "dataset": profile.name,
                            "schema": profile.infobox(),
                            "columns": result.columns,
                            "rows": result.rows,
                            "rows_considered": result.rows_considered,
                            "operation": result.operation,
                        },
                        "plan": plan.to_dict(),
                        "generated_code": plan.code,
                        "chart": chart,
                        "warnings": result.warnings,
                        "sandbox": {"kind": result.sandbox, "network_enabled": False},
                    }
            answer = redact_structure(answer)
            stored_answer = json.loads(json.dumps(answer, ensure_ascii=False))
            if stored_answer.get("chart"):
                stored_answer["chart"].pop("svg", None)
            state["updated_at"] = time.time()
            state["last_plan"] = (
                plan.to_dict() if plan.action != "insufficient" else state.get("last_plan")
            )
            state["turns"] = [
                *state.get("turns", []),
                {"question": redact_text(question), "final_answer": stored_answer},
            ][-MAX_TURNS_PER_SESSION:]
            self._write(state)
            return {"session_id": session_id, "final_answer": answer}

    def chart(self, session_id: str) -> dict[str, Any]:
        state = self._read(session_id)
        self._validate_storage_directory(self.charts_dir)
        if not state.get("turns"):
            raise DataQAError("Ask a grounded question before requesting a chart")
        answer = state["turns"][-1]["final_answer"]
        if answer.get("chart"):
            chart = dict(answer["chart"])
            asset_reference = workspace_root() / chart["asset_path"]
            asset = asset_reference.resolve()
            if (
                asset_reference.is_symlink()
                or not asset.is_file()
                or not asset.is_relative_to(self.charts_dir)
                or asset.stat().st_size > MAX_SVG_BYTES
            ):
                raise DataQAError("The latest chart asset is unavailable or unsafe")
            chart["svg"] = asset.read_text(encoding="utf-8")
            return {"session_id": session_id, "chart": chart}
        raise DataQAError("The latest answer does not support a consistent chart")

    def reset(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._read(session_id)
            state["last_plan"] = None
            state["turns"] = []
            self._validate_storage_directory(self.charts_dir)
            for asset in self.charts_dir.glob(f"{session_id}-*.svg"):
                asset.unlink(missing_ok=True)
            state["updated_at"] = time.time()
            self._write(state)
            return {"session_id": session_id, "reset": True, "session": self._public_session(state)}
