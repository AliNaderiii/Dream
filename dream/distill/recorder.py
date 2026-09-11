"""Trajectory recorder for multi-step agent execution tracing and quality scoring."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from dream.distill.types import TrajectoryStep, TrajectoryTrace


class TrajectoryRecorder:
    """Records and scores execution trajectories for model fine-tuning and evaluation."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ":memory:"
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._active_trajectories: dict[str, TrajectoryTrace] = {}
        self._init_tables()

    def close(self) -> None:
        """Close the SQLite database connection."""
        if hasattr(self, "_conn") and self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> TrajectoryRecorder:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def _init_tables(self) -> None:
        """Initialize trajectory storage schema."""
        if self._conn is None:
            return
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS distill_trajectories (
                    session_id TEXT PRIMARY KEY,
                    task_prompt TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    final_answer TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    quality_score REAL NOT NULL,
                    tags_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trajectories_quality "
                "ON distill_trajectories (quality_score)"
            )

    def start_trajectory(
        self,
        task_prompt: str,
        session_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Initialize a new recording session."""
        sid = session_id or f"traj_{uuid.uuid4().hex[:12]}"
        trace = TrajectoryTrace(
            session_id=sid,
            task_prompt=task_prompt,
            steps=[TrajectoryStep(step_id=0, role="user", content=task_prompt)],
            tags=tags or [],
            metadata=metadata or {},
        )
        self._active_trajectories[sid] = trace
        return sid

    def add_step(
        self,
        session_id: str,
        role: str,
        content: str = "",
        thought: str = "",
        tool_name: str = "",
        tool_args: dict[str, Any] | None = None,
        tool_result: str = "",
        latency_ms: float = 0.0,
    ) -> None:
        """Append an action or thought step to the active trajectory."""
        trace = self._active_trajectories.get(session_id)
        if not trace:
            return

        step = TrajectoryStep(
            step_id=len(trace.steps),
            role=role,
            thought=thought,
            tool_name=tool_name,
            tool_args=tool_args or {},
            tool_result=tool_result,
            content=content,
            latency_ms=latency_ms,
        )
        trace.steps.append(step)

    def complete_trajectory(
        self,
        session_id: str,
        final_answer: str,
        success: bool = True,
        user_rating: float | None = None,
    ) -> TrajectoryTrace | None:
        """Finalize, score, and persist the trajectory trace."""
        trace = self._active_trajectories.pop(session_id, None)
        if not trace:
            return None

        trace.final_answer = final_answer
        trace.success = success

        # Compute Quality Score (0.0 to 1.0)
        score = 1.0
        if not success:
            score -= 0.5

        # Penalize for error occurrences in tool results
        error_count = sum(
            1 for s in trace.steps if s.tool_result and "error" in s.tool_result.lower()
        )
        score -= min(0.3, error_count * 0.1)

        # User feedback adjustment if provided
        if user_rating is not None:
            score = (score * 0.7) + (max(0.0, min(1.0, user_rating / 5.0)) * 0.3)

        trace.quality_score = max(0.0, min(1.0, score))

        # Save to SQLite
        steps_serialized = [
            {
                "step_id": s.step_id,
                "role": s.role,
                "thought": s.thought,
                "tool_name": s.tool_name,
                "tool_args": s.tool_args,
                "tool_result": s.tool_result,
                "content": s.content,
                "latency_ms": s.latency_ms,
            }
            for s in trace.steps
        ]

        if self._conn is not None:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO distill_trajectories (
                        session_id, task_prompt, steps_json, final_answer,
                        success, quality_score, tags_json, metadata_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace.session_id,
                        trace.task_prompt,
                        json.dumps(steps_serialized, ensure_ascii=False),
                        trace.final_answer,
                        1 if trace.success else 0,
                        trace.quality_score,
                        json.dumps(trace.tags, ensure_ascii=False),
                        json.dumps(trace.metadata, ensure_ascii=False),
                        time.time(),
                    ),
                )
        return trace

    def list_trajectories(
        self,
        min_quality: float = 0.7,
        limit: int = 100,
    ) -> list[TrajectoryTrace]:
        """Fetch high-quality trajectories matching filtering criteria."""
        if self._conn is None:
            return []
        rows = self._conn.execute(
            """
            SELECT * FROM distill_trajectories
            WHERE quality_score >= ?
            ORDER BY quality_score DESC, created_at DESC
            LIMIT ?
            """,
            (min_quality, limit),
        ).fetchall()

        results: list[TrajectoryTrace] = []
        for r in rows:
            raw_steps = json.loads(r["steps_json"] or "[]")
            steps = [
                TrajectoryStep(
                    step_id=s.get("step_id", 0),
                    role=s.get("role", "assistant"),
                    thought=s.get("thought", ""),
                    tool_name=s.get("tool_name", ""),
                    tool_args=s.get("tool_args", {}),
                    tool_result=s.get("tool_result", ""),
                    content=s.get("content", ""),
                    latency_ms=s.get("latency_ms", 0.0),
                )
                for s in raw_steps
            ]
            results.append(
                TrajectoryTrace(
                    session_id=r["session_id"],
                    task_prompt=r["task_prompt"],
                    steps=steps,
                    final_answer=r["final_answer"],
                    success=bool(r["success"]),
                    quality_score=r["quality_score"],
                    tags=json.loads(r["tags_json"] or "[]"),
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    created_at=r["created_at"],
                )
            )
        return results
