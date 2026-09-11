"""Task Directed Acyclic Graph (DAG) for parallel and dependency-aware swarm execution."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.swarm.types import SwarmTask, TaskStatus


class TaskDAG:
    """Manages decomposed tasks, dependency graphs, and parallel execution sequencing."""

    def __init__(self) -> None:
        self._tasks: dict[str, SwarmTask] = {}

    def add_task(
        self,
        title: str,
        description: str = "",
        assigned_to: str = "",
        dependencies: list[str] | None = None,
        priority: int = 1,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SwarmTask:
        """Add a new task node to the DAG."""
        tid = task_id or f"task_{uuid.uuid4().hex[:6]}"
        task = SwarmTask(
            task_id=tid,
            title=title,
            description=description,
            assigned_to=assigned_to,
            dependencies=dependencies or [],
            status=TaskStatus.PENDING,
            priority=priority,
            created_at=time.time(),
            metadata=metadata or {},
        )
        self._tasks[tid] = task
        return task

    def get_task(self, task_id: str) -> SwarmTask | None:
        """Retrieve task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[SwarmTask]:
        """List all tasks sorted by priority."""
        return sorted(self._tasks.values(), key=lambda t: t.priority)

    def get_ready_tasks(self) -> list[SwarmTask]:
        """Return all pending tasks whose dependencies have all completed successfully."""
        ready = []
        for task in self._tasks.values():
            if task.status != TaskStatus.PENDING:
                continue

            # Check if all dependencies are satisfied
            deps_satisfied = True
            for dep_id in task.dependencies:
                dep_task = self._tasks.get(dep_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    deps_satisfied = False
                    break

            if deps_satisfied:
                ready.append(task)

        # Sort ready tasks by priority
        return sorted(ready, key=lambda t: t.priority)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus | str,
        result: str = "",
        error: str = "",
    ) -> bool:
        """Update task status and store execution output."""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        if isinstance(status, str):
            try:
                task.status = TaskStatus(status.lower())
            except Exception:
                task.status = TaskStatus.FAILED
        else:
            task.status = status

        if result:
            task.result = result
        if error:
            task.error = error

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            task.completed_at = time.time()

        return True

    def detect_cycles(self) -> bool:
        """Detect if the task graph has any circular dependencies using DFS."""
        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited

        for tid in self._tasks:
            visited[tid] = 0

        def has_cycle(curr_id: str) -> bool:
            visited[curr_id] = 1  # visiting
            curr_task = self._tasks.get(curr_id)
            if curr_task:
                for dep_id in curr_task.dependencies:
                    if dep_id in self._tasks:
                        if visited.get(dep_id) == 1:
                            return True
                        if visited.get(dep_id) == 0 and has_cycle(dep_id):
                            return True
            visited[curr_id] = 2  # visited
            return False

        for tid in self._tasks:
            if visited[tid] == 0:
                if has_cycle(tid):
                    return True
        return False

    def is_complete(self) -> bool:
        """Return True if all tasks have terminated (completed or failed)."""
        if not self._tasks:
            return True
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            for t in self._tasks.values()
        )

    def get_progress(self) -> dict[str, Any]:
        """Compute execution progress statistics."""
        total = len(self._tasks)
        if total == 0:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0, "pct": 100.0}

        completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
        in_progress = sum(1 for t in self._tasks.values() if t.status == TaskStatus.IN_PROGRESS)
        pending = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)

        pct = round((completed / total) * 100.0, 1)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "pending": pending,
            "pct": pct,
        }

    def clear(self) -> None:
        """Reset DAG tasks."""
        self._tasks.clear()
