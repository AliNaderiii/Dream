"""Isolated child agents that run beside a conversation.

A subagent is a second Dream instance the parent delegates a bounded piece of
work to. It runs as an ``asyncio.Task`` on the caller's event loop, talks to its
own provider backend, writes to an ephemeral in-memory store, and dispatches
tools through a private table holding only the subset its parent granted. It
returns exactly one thing to the parent: its final text. It can read nothing of
the parent's.

The isolation that needs the most care is the tool registry. ``dream.tools``
keeps a process-global ``REGISTRY``, and ``Dream.__init__`` registers memory and
reminder closures bound to *its* store into that global. Constructing a child
Dream therefore rebinds the parent's ``remember_fact`` to the child's throwaway
database. :func:`build_child_tools` closes that hole by snapshotting the global
around the child's construction, capturing the closures the child installed, and
restoring the parent's — all under :data:`REGISTRY_LOCK`, so concurrent spawns
serialise against each other.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import secrets
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from dream.agent import ApprovalPolicy, Dream, build_backend
from dream.memory import MemoryStore
from dream.tools import REGISTRY, Tool, execute, openai_schemas

__all__ = [
    "DEFAULT_MAX_DURATION",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_TOOL_GRANT",
    "REGISTRY_LOCK",
    "SUBAGENT_STATUSES",
    "TERMINAL_STATUSES",
    "LogEntry",
    "SubAgent",
    "SubAgentManager",
    "SubAgentSpec",
    "build_child_tools",
    "estimate_tokens",
    "subagent_to_dict",
]

logger = logging.getLogger(__name__)

SUBAGENT_STATUSES: frozenset[str] = frozenset(
    {"idle", "running", "paused", "completed", "failed", "cancelled", "timeout"}
)
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled", "timeout"})

DEFAULT_MAX_TURNS = 8
DEFAULT_MAX_TOKENS = 20_000
DEFAULT_MAX_DURATION = 120.0
DEFAULT_GRACE_SECONDS = 2.0

#: Tools a subagent may use when its parent names none. Deliberately excludes
#: every filesystem, shell, network and mail capability: an unattended child
#: gets arithmetic, the clock, and the memory of its own ephemeral store.
DEFAULT_TOOL_GRANT: tuple[str, ...] = (
    "calculate",
    "get_datetime",
    "remember_fact",
    "search_memory",
)

#: Serialises every mutation of the global tool registry performed on behalf of
#: a child agent. Exported so other constructors of :class:`Dream` (notably the
#: bridge's session factory) can take the same lock.
REGISTRY_LOCK = threading.RLock()

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str | None) -> int:
    """Approximate a token count from text length.

    Not every backend reports usage — ``EchoBackend`` reports none — so the
    budget has to be enforceable without provider cooperation. Four characters
    per token is the usual English rule of thumb; a non-empty string always
    costs at least one token so a long run of tiny messages still accrues.
    """
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass(slots=True)
class LogEntry:
    """One line of a subagent's execution log."""

    ts: float
    level: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "level": self.level, "message": self.message}


@dataclass(slots=True)
class SubAgentSpec:
    """Everything the parent decides before a child exists."""

    prompt: str
    name: str = ""
    context: str = ""
    system_prompt: str = ""
    model_provider: str = "echo"
    model_name: str = ""
    tools: Sequence[str] | None = None
    max_turns: int = DEFAULT_MAX_TURNS
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_duration: float = DEFAULT_MAX_DURATION
    parent_session_id: str | None = None
    allow_dangerous: bool = False

    def __post_init__(self) -> None:
        self.prompt = (self.prompt or "").strip()
        if not self.prompt:
            raise ValueError("subagent prompt must not be empty")
        self.name = (self.name or "").strip() or "subagent"
        self.max_turns = max(1, int(self.max_turns))
        self.max_tokens = max(1, int(self.max_tokens))
        self.max_duration = max(0.05, float(self.max_duration))


@dataclass(slots=True)
class SubAgent:
    """Observable state of one child agent."""

    id: str
    name: str
    parent_session_id: str | None
    model_provider: str
    model_name: str
    system_prompt: str
    tools: list[str]
    prompt: str
    context: str
    status: str = "idle"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    max_turns: int = DEFAULT_MAX_TURNS
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_duration: float = DEFAULT_MAX_DURATION
    turn_count: int = 0
    token_count: int = 0
    result: str | None = None
    error: str | None = None
    pipeline_id: str | None = None
    pipeline_index: int | None = None
    limit_hit: str | None = None
    log: list[LogEntry] = field(default_factory=list)
    paused_seconds: float = 0.0
    paused_at: float | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def elapsed(self, now: float | None = None) -> float:
        """Seconds of *active* run time, frozen once terminal.

        Time spent ``paused`` is excluded, so this is the quantity
        ``max_duration`` bounds: a human pausing a child to read its log should
        not consume the budget they paused to protect. It is also what the UI
        shows, because a stopwatch that keeps ticking while paused would
        contradict the badge next to it.
        """
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else (now or time.time())
        paused = self.paused_seconds
        if self.paused_at is not None and self.finished_at is None:
            paused += max(0.0, end - self.paused_at)
        return max(0.0, end - self.started_at - paused)

    def progress(self, now: float | None = None) -> float:
        """Fraction of the tightest budget consumed, clamped to ``[0, 1]``.

        Whichever limit is closest to firing is the one that will end the run,
        so the honest progress bar tracks the maximum of the three ratios.
        """
        if self.is_terminal:
            return 1.0
        ratios = (
            self.turn_count / self.max_turns,
            self.token_count / self.max_tokens,
            self.elapsed(now) / self.max_duration,
        )
        return min(1.0, max(0.0, max(ratios)))


def subagent_to_dict(agent: SubAgent, *, include_log: bool = True) -> dict[str, Any]:
    """Serialise a subagent for the JSON-RPC wire."""
    payload: dict[str, Any] = {
        "subagent_id": agent.id,
        "id": agent.id,
        "name": agent.name,
        "parent_session_id": agent.parent_session_id,
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
        "system_prompt": agent.system_prompt,
        "tools": list(agent.tools),
        "prompt": agent.prompt,
        "context": agent.context,
        "status": agent.status,
        "created_at": agent.created_at,
        "started_at": agent.started_at,
        "finished_at": agent.finished_at,
        "max_turns": agent.max_turns,
        "max_tokens": agent.max_tokens,
        "max_duration": agent.max_duration,
        "turn_count": agent.turn_count,
        "token_count": agent.token_count,
        "result": agent.result,
        "error": agent.error,
        "pipeline_id": agent.pipeline_id,
        "pipeline_index": agent.pipeline_index,
        "limit_hit": agent.limit_hit,
        "elapsed": agent.elapsed(),
        "progress": agent.progress(),
    }
    if include_log:
        payload["log"] = [entry.to_dict() for entry in agent.log]
    return payload


def build_child_tools(
    store: MemoryStore,
    granted: Iterable[str] | None,
    *,
    allow_dangerous: bool = False,
    backend: Any | None = None,
) -> tuple[Dream, dict[str, Tool]]:
    """Build a child ``Dream`` and its private tool table without side effects.

    Returns the child agent and the mapping it must dispatch through. The
    global :data:`dream.tools.REGISTRY` is byte-identical afterwards, including
    the parent's store-bound memory closures, which is what lets several
    subagents and their parent coexist in one process.
    """
    names = list(DEFAULT_TOOL_GRANT if granted is None else granted)
    with REGISTRY_LOCK:
        snapshot = dict(REGISTRY)
        try:
            child = Dream(store=store, backend=backend)
            captured = dict(REGISTRY)
        finally:
            REGISTRY.clear()
            REGISTRY.update(snapshot)
    table: dict[str, Tool] = {}
    for name in names:
        registered = captured.get(name)
        if registered is None:
            continue
        if registered.risk == "dangerous" and not allow_dangerous:
            continue
        table[name] = registered
    # The child's own policy resolves risk from the private table, and carries
    # no approver, so a granted dangerous tool is still refused at call time.
    child.approval_policy = ApprovalPolicy(registry=table)
    return child, table


def _build_backend(spec: SubAgentSpec) -> Any:
    backend = build_backend(spec.model_provider or "echo")
    if spec.model_name and hasattr(backend, "model"):
        backend.model = spec.model_name
    return backend


class _Runtime:
    """The mutable machinery behind one :class:`SubAgent` record."""

    __slots__ = ("agent", "spec", "stop", "resumed", "task", "store", "subscribers", "loop")

    def __init__(self, agent: SubAgent, spec: SubAgentSpec) -> None:
        self.agent = agent
        self.spec = spec
        self.stop = asyncio.Event()
        self.resumed = asyncio.Event()
        self.resumed.set()
        self.task: asyncio.Task[None] | None = None
        self.store: MemoryStore | None = None
        self.subscribers: list[asyncio.Queue[dict[str, Any] | None]] = []
        self.loop: asyncio.AbstractEventLoop | None = None


class _LimitReached(Exception):
    """Raised inside the loop when a budget is exhausted."""

    def __init__(self, which: str) -> None:
        super().__init__(which)
        self.which = which


class _Stopped(Exception):
    """Raised inside the loop when the parent asked the child to stop."""


class SubAgentManager:
    """Spawns, tracks and stops child agents for one bridge process."""

    def __init__(
        self,
        *,
        max_concurrent: int = 8,
        grace_seconds: float = DEFAULT_GRACE_SECONDS,
        store_factory: Callable[[], MemoryStore] | None = None,
    ) -> None:
        self.max_concurrent = max(1, int(max_concurrent))
        self.grace_seconds = max(0.0, float(grace_seconds))
        self._store_factory = store_factory or (lambda: MemoryStore(":memory:"))
        self._runtimes: dict[str, _Runtime] = {}
        self._order: list[str] = []
        self._pipelines: dict[str, list[str]] = {}
        self._pipeline_tasks: dict[str, asyncio.Task[None]] = {}

    # ---------------------------------------------------------------- lookup

    def get(self, subagent_id: str) -> SubAgent | None:
        runtime = self._runtimes.get(subagent_id)
        return runtime.agent if runtime else None

    def list(self) -> list[SubAgent]:
        """All subagents, newest first — the order the dashboard renders."""
        return [self._runtimes[i].agent for i in reversed(self._order) if i in self._runtimes]

    def active_count(self) -> int:
        return sum(1 for r in self._runtimes.values() if r.agent.status in ("running", "paused"))

    def pipeline(self, pipeline_id: str) -> list[SubAgent]:
        return [
            self._runtimes[i].agent
            for i in self._pipelines.get(pipeline_id, [])
            if i in self._runtimes
        ]

    # ----------------------------------------------------------------- spawn

    def _create(self, spec: SubAgentSpec) -> _Runtime:
        agent = SubAgent(
            id=f"sub_{secrets.token_hex(6)}",
            name=spec.name,
            parent_session_id=spec.parent_session_id,
            model_provider=spec.model_provider or "echo",
            model_name=spec.model_name or os.environ.get("DREAM_MODEL", ""),
            system_prompt=spec.system_prompt,
            tools=list(DEFAULT_TOOL_GRANT if spec.tools is None else spec.tools),
            prompt=spec.prompt,
            context=spec.context,
            max_turns=spec.max_turns,
            max_tokens=spec.max_tokens,
            max_duration=spec.max_duration,
        )
        runtime = _Runtime(agent, spec)
        self._runtimes[agent.id] = runtime
        self._order.append(agent.id)
        return runtime

    def spawn(self, spec: SubAgentSpec) -> SubAgent:
        """Start a child agent and return immediately (fire-and-forget)."""
        if self.active_count() >= self.max_concurrent:
            raise ResourceWarning(
                f"subagent limit reached: {self.active_count()}/{self.max_concurrent} active"
            )
        runtime = self._create(spec)
        self._launch(runtime)
        return runtime.agent

    def _launch(self, runtime: _Runtime) -> None:
        loop = asyncio.get_event_loop()
        runtime.loop = loop
        # Marked running here, not inside the task: ``spawn`` returns before the
        # loop gets a step, and a parent that immediately pauses or cancels must
        # act on a live agent rather than one still reported as idle.
        runtime.agent.status = "running"
        runtime.agent.started_at = time.time()
        runtime.task = loop.create_task(self._run(runtime), name=f"subagent:{runtime.agent.id}")

    def spawn_pipeline(
        self, specs: Sequence[SubAgentSpec], *, name: str = ""
    ) -> tuple[str, list[SubAgent]]:
        """Queue a chain where each stage's result becomes the next's context."""
        if not specs:
            raise ValueError("a pipeline needs at least one stage")
        pipeline_id = f"pipe_{secrets.token_hex(6)}"
        runtimes: list[_Runtime] = []
        for index, spec in enumerate(specs):
            staged = replace(spec, name=spec.name or f"{name or 'pipeline'} {index + 1}")
            runtime = self._create(staged)
            runtime.agent.pipeline_id = pipeline_id
            runtime.agent.pipeline_index = index
            runtimes.append(runtime)
        self._pipelines[pipeline_id] = [r.agent.id for r in runtimes]
        loop = asyncio.get_event_loop()
        self._pipeline_tasks[pipeline_id] = loop.create_task(
            self._drive_pipeline(pipeline_id, runtimes), name=f"pipeline:{pipeline_id}"
        )
        return pipeline_id, [r.agent for r in runtimes]

    async def _drive_pipeline(self, pipeline_id: str, runtimes: list[_Runtime]) -> None:
        carried = ""
        for position, runtime in enumerate(runtimes):
            agent = runtime.agent
            if agent.status == "cancelled":  # cancelled before its turn came up
                self._skip_rest(runtimes[position + 1 :], "pipeline cancelled")
                return
            if carried:
                base = agent.context.strip()
                agent.context = f"{base}\n\n{carried}" if base else carried
            runtime.loop = asyncio.get_event_loop()
            runtime.task = runtime.loop.create_task(
                self._run(runtime), name=f"subagent:{agent.id}"
            )
            with contextlib.suppress(asyncio.CancelledError):
                await runtime.task
            if agent.status != "completed":
                self._skip_rest(runtimes[position + 1 :], "upstream stage did not complete")
                return
            carried = agent.result or ""
        logger.debug("pipeline %s finished", pipeline_id)

    def _skip_rest(self, runtimes: Sequence[_Runtime], reason: str) -> None:
        for runtime in runtimes:
            agent = runtime.agent
            if agent.is_terminal:
                continue
            agent.status = "cancelled"
            agent.error = reason
            agent.finished_at = time.time()
            self._log(runtime, "warn", reason)
            self._close_subscribers(runtime)

    # ------------------------------------------------------------- lifecycle

    def pause(self, subagent_id: str) -> SubAgent | None:
        runtime = self._runtimes.get(subagent_id)
        if runtime is None:
            return None
        agent = runtime.agent
        if agent.status == "running":
            agent.status = "paused"
            agent.paused_at = time.time()
            runtime.resumed.clear()
            self._log(runtime, "info", "paused by parent")
        return agent

    def resume(self, subagent_id: str) -> SubAgent | None:
        runtime = self._runtimes.get(subagent_id)
        if runtime is None:
            return None
        agent = runtime.agent
        if agent.status == "paused":
            agent.status = "running"
            if agent.paused_at is not None:
                agent.paused_seconds += max(0.0, time.time() - agent.paused_at)
                agent.paused_at = None
            runtime.resumed.set()
            self._log(runtime, "info", "resumed by parent")
        return agent

    async def cancel(
        self, subagent_id: str, *, grace_seconds: float | None = None
    ) -> SubAgent | None:
        """Stop a child, escalating to task cancellation if it does not yield.

        Returns only once the status is terminal, so a UI that awaits this call
        can redraw the badge with the final state rather than an optimistic one.
        """
        runtime = self._runtimes.get(subagent_id)
        if runtime is None:
            return None
        agent = runtime.agent
        if agent.is_terminal:
            return agent
        grace = self.grace_seconds if grace_seconds is None else max(0.0, float(grace_seconds))
        self._log(runtime, "warn", "cancellation requested")
        runtime.stop.set()
        runtime.resumed.set()  # a paused agent must wake to observe the stop
        task = runtime.task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=grace)
            except (TimeoutError, asyncio.TimeoutError):
                # Still inside a provider call: detach it. The worker thread
                # finishes into the void and its result is discarded.
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            except asyncio.CancelledError:
                pass
            except Exception:  # pragma: no cover - the runner records its own failure
                logger.debug("subagent %s raised while cancelling", subagent_id, exc_info=True)
        if not agent.is_terminal:
            self._finish(runtime, "cancelled", error="cancelled by parent")
        pipeline_id = agent.pipeline_id
        if pipeline_id:
            ids = self._pipelines.get(pipeline_id, [])
            index = ids.index(agent.id) if agent.id in ids else len(ids)
            self._skip_rest(
                [self._runtimes[i] for i in ids[index + 1 :] if i in self._runtimes],
                "pipeline cancelled",
            )
        return agent

    async def wait(self, subagent_id: str, *, timeout: float = 5.0) -> SubAgent | None:
        """Await one subagent's terminal state.

        Returns the record whether the run finished, was cancelled, or the wait
        timed out; callers read ``status`` rather than trusting the return.
        """
        runtime = self._runtimes.get(subagent_id)
        if runtime is None:
            return None
        task = runtime.task
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError, TimeoutError, asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return runtime.agent

    async def wait_pipeline(self, pipeline_id: str, *, timeout: float = 10.0) -> list[SubAgent]:
        """Await every stage of a pipeline."""
        task = self._pipeline_tasks.get(pipeline_id)
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError, TimeoutError, asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return self.pipeline(pipeline_id)

    async def cancel_all(self, *, grace_seconds: float | None = None) -> None:
        """Stop every child. Signals all of them first, then drains in order.

        Draining one at a time without signalling first would let a slow
        sibling run to completion while an earlier child is still winding down.
        """
        for runtime in self._runtimes.values():
            if not runtime.agent.is_terminal:
                runtime.stop.set()
                runtime.resumed.set()
        for subagent_id in list(self._order):
            await self.cancel(subagent_id, grace_seconds=grace_seconds)
        for task in list(self._pipeline_tasks.values()):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._pipeline_tasks.clear()

    # --------------------------------------------------------------- logging

    def _log(self, runtime: _Runtime, level: str, message: str) -> None:
        entry = LogEntry(ts=time.time(), level=level, message=message)
        runtime.agent.log.append(entry)
        payload = {"event": "log", "subagent_id": runtime.agent.id, **entry.to_dict()}
        for queue in list(runtime.subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(payload)

    def _close_subscribers(self, runtime: _Runtime) -> None:
        for queue in list(runtime.subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)
        runtime.subscribers.clear()

    async def follow_logs(self, subagent_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield log entries as they happen, ending when the agent is terminal.

        Entries already recorded are replayed first so a late subscriber sees
        the whole run, not just its tail.
        """
        runtime = self._runtimes.get(subagent_id)
        if runtime is None:
            return
        for entry in list(runtime.agent.log):
            yield {"event": "log", "subagent_id": subagent_id, **entry.to_dict()}
        if runtime.agent.is_terminal:
            return
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)
        runtime.subscribers.append(queue)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item
        finally:
            if queue in runtime.subscribers:
                runtime.subscribers.remove(queue)

    # ------------------------------------------------------------- execution

    def _finish(
        self,
        runtime: _Runtime,
        status: str,
        *,
        result: str | None = None,
        error: str | None = None,
        limit_hit: str | None = None,
    ) -> None:
        agent = runtime.agent
        if agent.is_terminal:
            return
        agent.status = status
        agent.result = result
        agent.error = error
        agent.limit_hit = limit_hit
        now = time.time()
        if agent.paused_at is not None:
            agent.paused_seconds += max(0.0, now - agent.paused_at)
            agent.paused_at = None
        agent.finished_at = now
        self._log(runtime, "info" if status == "completed" else "warn", f"status: {status}")
        self._close_subscribers(runtime)
        store = runtime.store
        runtime.store = None
        if store is not None:
            with contextlib.suppress(Exception):
                store.close()

    async def _run(self, runtime: _Runtime) -> None:
        agent = runtime.agent
        spec = runtime.spec
        if agent.status == "idle":  # pipeline stages are launched without _launch
            agent.status = "running"
        if agent.started_at is None:
            agent.started_at = time.time()
        self._log(runtime, "info", f"spawned with tools: {', '.join(agent.tools) or 'none'}")
        watchdog: asyncio.Task[None] | None = None
        try:
            runtime.store = self._store_factory()
            child, table = build_child_tools(
                runtime.store,
                spec.tools,
                allow_dangerous=spec.allow_dangerous,
                backend=_build_backend(spec),
            )
            agent.tools = sorted(table)
            watchdog = asyncio.get_event_loop().create_task(self._watch_duration(runtime))
            result = await self._loop(runtime, child, table)
        except _Stopped:
            self._finish(runtime, "cancelled", error="cancelled by parent")
        except _LimitReached as limit:
            self._finish(
                runtime,
                "timeout",
                error=f"{limit.which} limit reached",
                limit_hit=limit.which,
            )
        except asyncio.CancelledError:
            self._finish(runtime, "cancelled", error="cancelled by parent")
            raise
        except Exception as exc:
            logger.debug("subagent %s failed", agent.id, exc_info=True)
            self._finish(runtime, "failed", error=f"{type(exc).__name__}: {exc}")
        else:
            self._finish(runtime, "completed", result=result)
        finally:
            if watchdog is not None and not watchdog.done():
                watchdog.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watchdog

    async def _watch_duration(self, runtime: _Runtime) -> None:
        """Fire the wall-clock limit even while the loop blocks on a provider.

        Time spent ``paused`` is not charged: a human pausing a child to read
        its log should not consume the budget they paused to protect.
        """
        agent = runtime.agent
        tick = min(0.05, agent.max_duration / 4)
        while not agent.is_terminal:
            await asyncio.sleep(tick)
            if agent.status == "paused":
                continue
            if agent.elapsed() >= agent.max_duration:
                self._log(runtime, "warn", "duration limit reached")
                runtime.stop.set()
                runtime.resumed.set()
                self._finish(
                    runtime, "timeout", error="duration limit reached", limit_hit="duration"
                )
                task = runtime.task
                if task is not None and not task.done():
                    task.cancel()
                return

    async def _gate(self, runtime: _Runtime) -> None:
        """Pause barrier plus stop and budget checks, run before every turn."""
        if runtime.stop.is_set():
            raise _Stopped
        while runtime.agent.status == "paused" and not runtime.stop.is_set():
            await runtime.resumed.wait()
        if runtime.stop.is_set():
            raise _Stopped
        agent = runtime.agent
        if agent.turn_count >= agent.max_turns:
            raise _LimitReached("turns")
        if agent.token_count >= agent.max_tokens:
            raise _LimitReached("tokens")
        if agent.elapsed() >= agent.max_duration:
            raise _LimitReached("duration")

    def _initial_messages(self, agent: SubAgent) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        system = agent.system_prompt.strip()
        if system:
            messages.append({"role": "system", "content": system})
        user = agent.prompt
        context = agent.context.strip()
        if context:
            # Fenced, so the child can tell handed-down facts from its task and
            # the parent's context can never be mistaken for an instruction.
            user = f"<context>\n{context}\n</context>\n\n{user}"
        messages.append({"role": "user", "content": user})
        return messages

    async def _loop(
        self, runtime: _Runtime, child: Dream, table: Mapping[str, Tool]
    ) -> str:
        agent = runtime.agent
        messages = self._initial_messages(agent)
        agent.token_count += sum(estimate_tokens(m.get("content")) for m in messages)
        schemas = openai_schemas(table)
        final = ""
        while True:
            await self._gate(runtime)
            self._log(runtime, "debug", f"turn {agent.turn_count + 1} → {agent.model_provider}")
            response = await asyncio.to_thread(
                child.backend.chat, messages, schemas if schemas else None
            )
            if runtime.stop.is_set():
                # The parent cancelled while the provider call was in flight.
                # Its answer is stale by definition, so it is dropped rather
                # than recorded as this subagent's result.
                raise _Stopped
            agent.turn_count += 1
            content = response.get("content") or ""
            tool_calls = response.get("tool_calls") or []
            agent.token_count += estimate_tokens(content)
            if not tool_calls:
                final = content
                self._log(runtime, "info", "produced final answer")
                break
            messages.append(
                {"role": "assistant", "content": content or None, "tool_calls": tool_calls}
            )
            for call in tool_calls:
                await self._gate(runtime)
                output = self._call_tool(runtime, child, table, call)
                agent.token_count += estimate_tokens(output)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "name": call.get("name", ""),
                        "content": output,
                    }
                )
        return final

    def _call_tool(
        self,
        runtime: _Runtime,
        child: Dream,
        table: Mapping[str, Tool],
        call: Mapping[str, Any],
    ) -> str:
        name = str(call.get("name", ""))
        arguments = call.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        if name not in table:
            self._log(runtime, "warn", f"tool {name!r} is not granted to this subagent")
            return json.dumps(
                {
                    "status": "error",
                    "error": {
                        "type": "not_granted",
                        "message": f"Tool call failed: {name} is not granted to this subagent",
                    },
                },
                ensure_ascii=False,
            )
        allowed, reason = child.approval_policy.allows(name, arguments)
        self._log(runtime, "info", f"tool {name}: {reason}")
        output = execute(name, arguments, approved=allowed, registry=table)
        return output


