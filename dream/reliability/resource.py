"""Worker and resource hygiene: supervise, reap, restart, shut down cleanly.

Mirrors the sidecar restart policy: at most three restarts, backoff
2 s / 5 s / 10 s. Threads and subprocesses are tracked so a shutdown
does not leak FDs, connections, or joinable threads.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from enum import Enum
from typing import Any

from dream.reliability.cancel import CancelToken
from dream.reliability.deadline import MAX_TIMEOUT_SECONDS, clamp_timeout

# Sidecar process.rs policy: three restarts, 2-5-10 s backoff.
BACKOFF_SECONDS: tuple[float, float, float] = (2.0, 5.0, 10.0)
MAX_RESTARTS = 3
DEFAULT_IDLE_TIMEOUT = 30.0
MAX_WORKERS = 64

__all__ = [
    "BACKOFF_SECONDS",
    "MAX_RESTARTS",
    "ResourceSupervisor",
    "SupervisedWorker",
    "WorkerStatus",
]


class WorkerStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STALE = "stale"
    REAPED = "reaped"
    FAILED = "failed"
    STOPPED = "stopped"


class SupervisedWorker:
    """One thread or subprocess under the supervisor."""

    def __init__(
        self,
        name: str,
        *,
        kind: str,
        idle_timeout: float,
        token: CancelToken,
    ) -> None:
        self.name = name
        self.kind = kind
        self.idle_timeout = idle_timeout
        self.token = token
        self.status = WorkerStatus.IDLE
        self.started_at = time.monotonic()
        self.last_beat = self.started_at
        self.restarts = 0
        self.thread: threading.Thread | None = None
        self.proc: subprocess.Popen[Any] | None = None
        self.target: Callable[..., Any] | None = None
        self.args: tuple[Any, ...] = ()
        self.kwargs: dict[str, Any] = {}
        self.popen_args: list[str] | None = None
        self.popen_kwargs: dict[str, Any] = {}
        self.error: str | None = None

    def touch(self) -> None:
        self.last_beat = time.monotonic()
        if self.status is WorkerStatus.IDLE:
            self.status = WorkerStatus.RUNNING

    def idle_for(self) -> float:
        return time.monotonic() - self.last_beat

    def is_alive(self) -> bool:
        if self.kind == "process" and self.proc is not None:
            return self.proc.poll() is None
        if self.thread is not None:
            return self.thread.is_alive()
        return False

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "status": self.status.value,
            "alive": self.is_alive(),
            "idle_for": self.idle_for(),
            "restarts": self.restarts,
            "error": self.error,
        }


class ResourceSupervisor:
    """Owns worker threads/processes: idle detection, stale reaping, restart."""

    def __init__(
        self,
        *,
        max_workers: int = 32,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        backoff: Sequence[float] = BACKOFF_SECONDS,
        max_restarts: int = MAX_RESTARTS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        cap = 1 if max_workers < 1 else min(int(max_workers), MAX_WORKERS)
        self.max_workers = cap
        self.idle_timeout = clamp_timeout(
            idle_timeout,
            default=DEFAULT_IDLE_TIMEOUT,
            hard_max=MAX_TIMEOUT_SECONDS,
            hard_min=0.05,
        )
        self.backoff = tuple(
            clamp_timeout(item, default=2.0, hard_max=30.0, hard_min=0.0)
            for item in backoff
        ) or BACKOFF_SECONDS
        self.max_restarts = max(0, min(int(max_restarts), MAX_RESTARTS))
        self._sleep = sleep
        self._lock = threading.Lock()
        self._workers: dict[str, SupervisedWorker] = {}
        self.token = CancelToken(name="supervisor")

    def __enter__(self) -> ResourceSupervisor:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.shutdown()

    def get(self, name: str) -> SupervisedWorker | None:
        with self._lock:
            return self._workers.get(name)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [worker.snapshot() for worker in self._workers.values()]

    def spawn_thread(
        self,
        name: str,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> SupervisedWorker:
        with self._lock:
            if name in self._workers and self._workers[name].is_alive():
                raise RuntimeError(f"worker {name!r} is already running")
            if self._alive_count_unlocked() >= self.max_workers:
                raise RuntimeError(
                    f"supervisor at capacity ({self.max_workers} workers)"
                )
            worker = SupervisedWorker(
                name,
                kind="thread",
                idle_timeout=self.idle_timeout,
                token=self.token.child(name),
            )
            worker.target = fn
            worker.args = args
            worker.kwargs = kwargs
            self._workers[name] = worker
        self._start_thread(worker)
        return worker

    def spawn_process(
        self,
        name: str,
        args: Sequence[str],
        **popen_kwargs: Any,
    ) -> SupervisedWorker:
        popen_kwargs = dict(popen_kwargs)
        popen_kwargs.setdefault("close_fds", True)
        with self._lock:
            if name in self._workers and self._workers[name].is_alive():
                raise RuntimeError(f"worker {name!r} is already running")
            if self._alive_count_unlocked() >= self.max_workers:
                raise RuntimeError(
                    f"supervisor at capacity ({self.max_workers} workers)"
                )
            worker = SupervisedWorker(
                name,
                kind="process",
                idle_timeout=self.idle_timeout,
                token=self.token.child(name),
            )
            worker.popen_args = [str(item) for item in args]
            worker.popen_kwargs = popen_kwargs
            self._workers[name] = worker
        self._start_process(worker)
        return worker

    def _alive_count_unlocked(self) -> int:
        return sum(1 for worker in self._workers.values() if worker.is_alive())

    def _start_thread(self, worker: SupervisedWorker) -> None:
        target = worker.target
        if target is None:
            raise RuntimeError(f"worker {worker.name!r} has no target")

        def _runner() -> None:
            worker.status = WorkerStatus.RUNNING
            worker.touch()
            try:
                target(*worker.args, **worker.kwargs)
                worker.status = WorkerStatus.STOPPED
            except Exception as exc:
                worker.status = WorkerStatus.FAILED
                worker.error = f"{type(exc).__name__}: {exc}"

        thread = threading.Thread(
            target=_runner, name=f"dream-worker-{worker.name}", daemon=True
        )
        worker.thread = thread
        worker.started_at = time.monotonic()
        worker.touch()
        thread.start()

    def _start_process(self, worker: SupervisedWorker) -> None:
        argv = worker.popen_args
        if argv is None:
            raise RuntimeError(f"worker {worker.name!r} has no process argv")
        proc = subprocess.Popen(argv, **worker.popen_kwargs)  # noqa: S603
        worker.proc = proc
        worker.started_at = time.monotonic()
        worker.status = WorkerStatus.RUNNING
        worker.touch()
        worker.token.link_subprocess(proc)

    def touch(self, name: str) -> None:
        worker = self.get(name)
        if worker is not None:
            worker.touch()

    def reap_stale(self) -> list[str]:
        """Stop workers whose last heartbeat is older than ``idle_timeout``."""
        reaped: list[str] = []
        with self._lock:
            workers = list(self._workers.values())
        for worker in workers:
            if not worker.is_alive():
                if worker.status is WorkerStatus.RUNNING:
                    worker.status = WorkerStatus.STOPPED
                continue
            if worker.idle_for() < worker.idle_timeout:
                continue
            self._stop_worker(worker, reason="stale")
            worker.status = WorkerStatus.REAPED
            reaped.append(worker.name)
        return reaped

    def _stop_worker(self, worker: SupervisedWorker, *, reason: str) -> None:
        worker.token.cancel(reason=reason)
        if worker.proc is not None and worker.proc.poll() is None:
            worker.proc.terminate()
            try:
                worker.proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                worker.proc.kill()
                try:
                    worker.proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
        if worker.thread is not None and worker.thread.is_alive():
            worker.thread.join(timeout=1.0)

    def restart(self, name: str) -> bool:
        """Restart a dead worker with sidecar backoff. False if the budget is spent."""
        worker = self.get(name)
        if worker is None:
            return False
        if worker.is_alive():
            return True
        if worker.restarts >= self.max_restarts:
            worker.status = WorkerStatus.FAILED
            worker.error = worker.error or "restart budget exhausted"
            return False
        delay = self.backoff[min(worker.restarts, len(self.backoff) - 1)]
        if delay > 0:
            self._sleep(delay)
        worker.restarts += 1
        worker.error = None
        if worker.kind == "process":
            self._start_process(worker)
        else:
            self._start_thread(worker)
        return True

    def stop(self, name: str) -> None:
        worker = self.get(name)
        if worker is None:
            return
        self._stop_worker(worker, reason="stop")
        worker.status = WorkerStatus.STOPPED

    def shutdown(self, timeout: float = 5.0) -> None:
        """Cancel every worker and join/wait. Safe to call more than once."""
        timeout = clamp_timeout(timeout, default=5.0, hard_max=30.0, hard_min=0.05)
        self.token.cancel(reason="supervisor shutdown")
        with self._lock:
            workers = list(self._workers.values())
        deadline = time.monotonic() + timeout
        for worker in workers:
            leftover = max(0.05, deadline - time.monotonic())
            worker.token.cancel(reason="supervisor shutdown")
            if worker.proc is not None and worker.proc.poll() is None:
                worker.proc.terminate()
                try:
                    worker.proc.wait(timeout=min(1.0, leftover))
                except subprocess.TimeoutExpired:
                    worker.proc.kill()
                    try:
                        worker.proc.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        pass
            if worker.thread is not None and worker.thread.is_alive():
                leftover = max(0.05, deadline - time.monotonic())
                worker.thread.join(timeout=leftover)
            if not worker.is_alive():
                worker.status = WorkerStatus.STOPPED
        # Drop references so FDs and threads can be collected.
        with self._lock:
            self._workers.clear()
