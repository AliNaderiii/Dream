"""SubAgentManager: lifecycle, concurrency, pipeline chaining, and execution monitoring."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import secrets
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from dream.agent import Dream
from dream.memory import MemoryStore
from dream.subagents.constants import (
    DEFAULT_GRACE_SECONDS,
    DEFAULT_TOOL_GRANT,
    MAX_CONTEXT_CHARS,
    MAX_LOG_ENTRIES,
    MAX_LOG_MESSAGE_CHARS,
    MAX_PIPELINE_STAGES,
    MAX_RETAINED_SUBAGENTS,
    _safe_error,
    _truncate,
    estimate_tokens,
)
from dream.subagents.isolation import build_child_tools
from dream.subagents.types import (
    LogEntry,
    SubAgent,
    SubAgentSpec,
    _LimitReached,
    _Stopped,
)
from dream.tools import Tool, execute, openai_schemas

logger = logging.getLogger(__name__)


class _Runtime:
    """The mutable machinery behind one SubAgent record."""

    __slots__ = (
        "agent",
        "spec",
        "stop",
        "resumed",
        "task",
        "store",
        "subscribers",
        "loop",
    )

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

    def get(self, subagent_id: str) -> SubAgent | None:
        runtime = self._runtimes.get(subagent_id)
        return runtime.agent if runtime else None

    def list(self) -> list[SubAgent]:
        """All subagents, newest first."""
        return [
            self._runtimes[i].agent
            for i in reversed(self._order)
            if i in self._runtimes
        ]

    def active_count(self) -> int:
        return sum(
            1
            for r in self._runtimes.values()
            if r.agent.status in ("running", "paused")
        )

    def pipeline(self, pipeline_id: str) -> list[SubAgent]:
        return [
            self._runtimes[i].agent
            for i in self._pipelines.get(pipeline_id, [])
            if i in self._runtimes
        ]

    def _create(self, spec: SubAgentSpec) -> _Runtime:
        import dream.subagents as subagents_mod

        retained_cap = getattr(
            subagents_mod, "MAX_RETAINED_SUBAGENTS", MAX_RETAINED_SUBAGENTS
        )
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
        self._evict_terminal(retained_cap)
        return runtime

    def _evict_terminal(self, cap: int = MAX_RETAINED_SUBAGENTS) -> None:
        excess = len(self._order) - cap
        if excess <= 0:
            return
        for subagent_id in list(self._order):
            if excess <= 0:
                break
            runtime = self._runtimes.get(subagent_id)
            if runtime is None:
                self._order.remove(subagent_id)
                excess -= 1
                continue
            if not runtime.agent.is_terminal:
                continue
            self._close_subscribers(runtime)
            self._order.remove(subagent_id)
            del self._runtimes[subagent_id]
            pipeline_id = runtime.agent.pipeline_id
            if pipeline_id and pipeline_id in self._pipelines:
                ids = [i for i in self._pipelines[pipeline_id] if i != subagent_id]
                if ids:
                    self._pipelines[pipeline_id] = ids
                else:
                    self._pipelines.pop(pipeline_id, None)
                    task = self._pipeline_tasks.pop(pipeline_id, None)
                    if task is not None and not task.done():
                        task.cancel()
            excess -= 1

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
        runtime.agent.status = "running"
        runtime.agent.started_at = time.time()
        runtime.task = loop.create_task(
            self._run(runtime), name=f"subagent:{runtime.agent.id}"
        )

    def spawn_pipeline(
        self, specs: Sequence[SubAgentSpec], *, name: str = ""
    ) -> tuple[str, list[SubAgent]]:
        """Queue a chain where each stage's result becomes the next's context."""
        if not specs:
            raise ValueError("a pipeline needs at least one stage")
        if len(specs) > MAX_PIPELINE_STAGES:
            raise ValueError(
                f"a pipeline may have at most {MAX_PIPELINE_STAGES} stages"
            )
        pipeline_id = f"pipe_{secrets.token_hex(6)}"
        runtimes: list[_Runtime] = []
        for index, spec in enumerate(specs):
            staged = replace(
                spec, name=spec.name or f"{name or 'pipeline'} {index + 1}"
            )
            runtime = self._create(staged)
            runtime.agent.pipeline_id = pipeline_id
            runtime.agent.pipeline_index = index
            runtimes.append(runtime)
        self._pipelines[pipeline_id] = [r.agent.id for r in runtimes]
        loop = asyncio.get_event_loop()
        self._pipeline_tasks[pipeline_id] = loop.create_task(
            self._drive_pipeline(pipeline_id, runtimes),
            name=f"pipeline:{pipeline_id}",
        )
        return pipeline_id, [r.agent for r in runtimes]

    async def _drive_pipeline(
        self, pipeline_id: str, runtimes: list[_Runtime]
    ) -> None:
        try:
            await self._drive_pipeline_stages(runtimes)
        finally:
            task = self._pipeline_tasks.get(pipeline_id)
            if task is not None and task is asyncio.current_task():
                self._pipeline_tasks.pop(pipeline_id, None)
        logger.debug("pipeline %s finished", pipeline_id)

    async def _drive_pipeline_stages(self, runtimes: list[_Runtime]) -> None:
        carried = ""
        for position, runtime in enumerate(runtimes):
            agent = runtime.agent
            if agent.status == "cancelled":
                self._skip_rest(runtimes[position + 1 :], "pipeline cancelled")
                return
            if carried:
                base = agent.context.strip()
                merged = f"{base}\n\n{carried}" if base else carried
                agent.context = _truncate(merged, MAX_CONTEXT_CHARS)
            runtime.loop = asyncio.get_event_loop()
            runtime.task = runtime.loop.create_task(
                self._run(runtime), name=f"subagent:{agent.id}"
            )
            with contextlib.suppress(asyncio.CancelledError):
                await runtime.task
            if agent.status != "completed":
                self._skip_rest(
                    runtimes[position + 1 :], "upstream stage did not complete"
                )
                return
            carried = agent.result or ""

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
        runtime = self._runtimes.get(subagent_id)
        if runtime is None:
            return None
        agent = runtime.agent
        if agent.is_terminal:
            return agent
        grace = (
            self.grace_seconds
            if grace_seconds is None
            else max(0.0, float(grace_seconds))
        )
        self._log(runtime, "warn", "cancellation requested")
        runtime.stop.set()
        runtime.resumed.set()
        task = runtime.task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=grace)
            except (TimeoutError, asyncio.TimeoutError):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug(
                    "subagent %s raised while cancelling",
                    subagent_id,
                    exc_info=True,
                )
        if not agent.is_terminal:
            self._finish(runtime, "cancelled", error="cancelled by parent")
        pipeline_id = agent.pipeline_id
        if pipeline_id:
            ids = self._pipelines.get(pipeline_id, [])
            index = ids.index(agent.id) if agent.id in ids else len(ids)
            self._skip_rest(
                [
                    self._runtimes[i]
                    for i in ids[index + 1 :]
                    if i in self._runtimes
                ],
                "pipeline cancelled",
            )
        return agent

    async def wait(
        self, subagent_id: str, *, timeout: float = 5.0
    ) -> SubAgent | None:
        runtime = self._runtimes.get(subagent_id)
        if runtime is None:
            return None
        task = runtime.task
        if task is not None:
            with contextlib.suppress(
                asyncio.CancelledError, TimeoutError, asyncio.TimeoutError
            ):
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return runtime.agent

    async def wait_pipeline(
        self, pipeline_id: str, *, timeout: float = 10.0
    ) -> list[SubAgent]:
        task = self._pipeline_tasks.get(pipeline_id)
        if task is not None:
            with contextlib.suppress(
                asyncio.CancelledError, TimeoutError, asyncio.TimeoutError
            ):
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return self.pipeline(pipeline_id)

    async def cancel_all(self, *, grace_seconds: float | None = None) -> None:
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

    def _log(self, runtime: _Runtime, level: str, message: str) -> None:
        agent = runtime.agent
        entry = LogEntry(
            ts=time.time(),
            level=level,
            message=_truncate(message, MAX_LOG_MESSAGE_CHARS),
            seq=agent.log_seq,
        )
        agent.log_seq += 1
        agent.log.append(entry)
        overflow = len(agent.log) - MAX_LOG_ENTRIES
        if overflow > 0:
            del agent.log[:overflow]
            agent.log_dropped += overflow
        payload = {"event": "log", "subagent_id": agent.id, **entry.to_dict()}
        for queue in list(runtime.subscribers):
            self._offer(queue, payload)

    @staticmethod
    def _offer(
        queue: asyncio.Queue[dict[str, Any] | None],
        item: dict[str, Any] | None,
    ) -> None:
        while True:
            try:
                queue.put_nowait(item)
                return
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()

    def _close_subscribers(self, runtime: _Runtime) -> None:
        for queue in list(runtime.subscribers):
            self._offer(queue, None)
        runtime.subscribers.clear()

    async def follow_logs(
        self, subagent_id: str
    ) -> AsyncIterator[dict[str, Any]]:
        runtime = self._runtimes.get(subagent_id)
        if runtime is None:
            return
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)
        terminal_at_subscribe = runtime.agent.is_terminal
        if not terminal_at_subscribe:
            runtime.subscribers.append(queue)
        try:
            history = list(runtime.agent.log)
            next_seq = (
                history[-1].seq + 1 if history else runtime.agent.log_dropped
            )
            for entry in history:
                yield {
                    "event": "log",
                    "subagent_id": subagent_id,
                    **entry.to_dict(),
                }
            if terminal_at_subscribe:
                return
            while True:
                item = await queue.get()
                if item is None:
                    return
                seq = item.get("seq")
                if isinstance(seq, int):
                    if seq < next_seq:
                        continue
                    next_seq = seq + 1
                yield item
        finally:
            if queue in runtime.subscribers:
                runtime.subscribers.remove(queue)

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
        self._log(
            runtime,
            "info" if status == "completed" else "warn",
            f"status: {status}",
        )
        self._close_subscribers(runtime)
        store = runtime.store
        runtime.store = None
        if store is not None:
            with contextlib.suppress(Exception):
                store.close()

    async def _run(self, runtime: _Runtime) -> None:
        import dream.subagents as subagents_mod

        agent = runtime.agent
        spec = runtime.spec
        if agent.status == "idle":
            agent.status = "running"
        if agent.started_at is None:
            agent.started_at = time.time()
        self._log(
            runtime,
            "info",
            f"spawned with tools: {', '.join(agent.tools) or 'none'}",
        )
        watchdog: asyncio.Task[None] | None = None
        try:
            runtime.store = self._store_factory()
            backend_builder = getattr(subagents_mod, "_build_backend", None)
            backend_instance = backend_builder(spec) if backend_builder else None
            child, table = build_child_tools(
                runtime.store,
                spec.tools,
                allow_dangerous=spec.allow_dangerous,
                backend=backend_instance,
            )
            agent.tools = sorted(table)
            watchdog = asyncio.get_event_loop().create_task(
                self._watch_duration(runtime)
            )
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
            self._finish(runtime, "failed", error=_safe_error(exc))
        else:
            self._finish(runtime, "completed", result=result)
        finally:
            if watchdog is not None and not watchdog.done():
                watchdog.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watchdog

    async def _watch_duration(self, runtime: _Runtime) -> None:
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
                    runtime,
                    "timeout",
                    error="duration limit reached",
                    limit_hit="duration",
                )
                task = runtime.task
                if task is not None and not task.done():
                    task.cancel()
                return

    async def _gate(self, runtime: _Runtime) -> None:
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
            user = f"<context>\n{context}\n</context>\n\n{user}"
        messages.append({"role": "user", "content": user})
        return messages

    async def _loop(
        self, runtime: _Runtime, child: Dream, table: Mapping[str, Tool]
    ) -> str:
        agent = runtime.agent
        messages = self._initial_messages(agent)
        agent.token_count += sum(
            estimate_tokens(m.get("content")) for m in messages
        )
        schemas = openai_schemas(table)
        final = ""
        while True:
            await self._gate(runtime)
            self._log(
                runtime,
                "debug",
                f"turn {agent.turn_count + 1} → {agent.model_provider}",
            )
            response = await asyncio.to_thread(
                child.backend.chat, messages, schemas if schemas else None
            )
            if runtime.stop.is_set():
                raise _Stopped
            agent.turn_count += 1
            if isinstance(response, dict):
                content = response.get("content") or ""
                tool_calls = response.get("tool_calls") or []
            else:
                content = getattr(response, "reply", "") or getattr(response, "content", "") or ""
                tool_calls = getattr(response, "tool_calls", []) or []

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
                if isinstance(call, dict):
                    call_id = call.get("id", "")
                    call_name = call.get("name", "")
                else:
                    call_id = getattr(call, "id", "")
                    call_name = getattr(call, "name", "")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": call_name,
                        "content": output,
                    }
                )
        return final

    def _call_tool(
        self,
        runtime: _Runtime,
        child: Dream,
        table: Mapping[str, Tool],
        call: Any,
    ) -> str:
        if isinstance(call, dict):
            name = str(call.get("name", ""))
            arguments = call.get("arguments") or {}
        else:
            name = str(getattr(call, "name", ""))
            arguments = getattr(call, "arguments", {}) or {}

        if not isinstance(arguments, dict):
            arguments = {}
        if name not in table:
            self._log(
                runtime, "warn", f"tool {name!r} is not granted to this subagent"
            )
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
