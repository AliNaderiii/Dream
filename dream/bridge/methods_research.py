"""``research.*`` RPC surface, registered through the P0 extension seam.

This module is discovered automatically by
:mod:`dream.bridge.extensions` — ``dream/bridge/methods.py`` is never edited.
It exposes the research engine to the UI (P2) and to any JSON-RPC client:

===========================  =================================================
``research.create``          register a session (topic + workspace + config)
``research.list``            summaries of every persisted session
``research.get``             the full session record
``research.plan``            run the planner; stops at APPROVAL_PENDING
``research.approve``         the human checkpoint: unblock execution
``research.modify``          edit the outline by hand, or request a re-plan
``research.start``           execute the approved plan to a compiled report
``research.status``          lightweight poll (status, progress, cursor)
``research.stream``          streaming live trace of progress events
``research.stop``            cooperative cancellation
``research.export``          publish + return the report/bundle paths
===========================  =================================================

Handler conventions follow the bridge contract: every expected failure is a
:class:`~dream.bridge.errors.BridgeError` with ``INVALID_PARAMS``, blocking
work runs in a worker thread so the event loop never stalls, and the streaming
handler returns a :class:`~dream.bridge.streams.Stream` whose chunks are
progress events.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from dream.bridge.errors import BridgeError, invalid_params
from dream.bridge.streams import Stream
from dream.reliability.sleep import ainterruptible_sleep
from dream.research.errors import ResearchError, ResearchSecurityError

logger = logging.getLogger("dream.bridge.research")

__all__ = ["HANDLERS", "engine", "reset_engine"]

#: A start may run long; the RPC caller gets the session back either way.
_START_TIMEOUT_ENV = "DREAM_RESEARCH_START_TIMEOUT"
_DEFAULT_START_TIMEOUT = 1800.0
_STREAM_POLL_SECONDS = 0.05
_STREAM_MAX_EVENTS = 5000

_engine: Any = None


def engine() -> Any:
    """The process-wide :class:`~dream.research.session.ResearchEngine`.

    Built lazily so importing the bridge never constructs a data-science
    runtime (and so never imports pandas). The backend comes from Dream's
    normal selection path, which defaults to the offline EchoBackend.
    """
    global _engine
    if _engine is None:
        from dream.agent import build_backend
        from dream.research import ResearchEngine

        try:
            backend = build_backend()
        except Exception:  # a misconfigured provider must not block research
            logger.warning("backend construction failed; running offline", exc_info=True)
            backend = None
        _engine = ResearchEngine(backend=backend)
    return _engine


def reset_engine(new_engine: Any = None) -> Any:
    """Swap the engine (tests, and the desktop app's re-configuration path)."""
    global _engine
    _engine = new_engine
    return _engine


# --------------------------------------------------------------------------- #
# Parameter helpers
# --------------------------------------------------------------------------- #


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Accept both dispatch shapes: ``handler(params_dict)`` and ``**named``."""
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _session_id(params: dict[str, Any]) -> str:
    value = params.get("session_id")
    if not isinstance(value, str) or not value.strip():
        raise invalid_params("session_id must be a non-empty string")
    return value.strip()


def _get(params: dict[str, Any]) -> Any:
    try:
        return engine().get(_session_id(params))
    except ResearchError as exc:
        raise invalid_params(str(exc)) from None


async def _call(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run blocking engine work off the event loop, mapping errors to the taxonomy."""
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except ResearchSecurityError as exc:
        raise invalid_params(str(exc)) from None
    except ResearchError as exc:
        raise invalid_params(str(exc)) from None
    except BridgeError:
        raise
    except Exception as exc:
        logger.exception("research handler failed")
        raise invalid_params(f"{type(exc).__name__}: {str(exc)[:300]}") from None


def _summary(session: Any) -> dict[str, Any]:
    record = session.record
    sections = record.plan.sections
    done = len([s for s in sections if s.status in ("DONE", "SKIPPED", "FAILED")])
    return {
        "session_id": record.session_id,
        "status": record.status,
        "topic": record.topic,
        "sections_total": len(sections),
        "sections_done": done,
        "progress": round(done / len(sections), 3) if sections else 0.0,
        "events": len(record.events),
        "error": record.error,
        "published": record.published,
        "report": record.report.to_dict(),
        "cost_estimate": record.cost_estimate,
    }


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


async def research_create(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Register a session. Params: ``topic``, ``workspace``, optional ``config``."""
    data = _params(params, kwargs)
    topic = data.get("topic")
    workspace = data.get("workspace")
    if not isinstance(topic, str) or not topic.strip():
        raise invalid_params("topic must be a non-empty string")
    if not isinstance(workspace, str) or not workspace.strip():
        raise invalid_params("workspace must be a non-empty string")
    config = data.get("config")
    if config is not None and not isinstance(config, dict):
        raise invalid_params("config must be an object")
    session = await _call(engine().create, topic, workspace, config=config)
    return _summary(session)


async def research_list(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Summaries of every persisted session, newest first."""
    _params(params, kwargs)
    sessions = await _call(engine().list)
    return {"sessions": sessions, "count": len(sessions)}


async def research_get(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """The full session record: plan, sections, findings, report, events."""
    data = _params(params, kwargs)
    session = _get(data)
    return session.to_dict()


async def research_plan(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Run the planner. Leaves the session in APPROVAL_PENDING."""
    data = _params(params, kwargs)
    session = _get(data)
    force = bool(data.get("force"))
    plan = await _call(session.plan, force=force)
    return {
        **_summary(session),
        "plan": plan.to_dict(),
    }


async def research_approve(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """The human-in-the-loop checkpoint."""
    data = _params(params, kwargs)
    session = _get(data)
    plan = await _call(session.approve)
    return {**_summary(session), "plan": plan.to_dict()}


async def research_modify(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Edit the outline (``changes``) or request a re-plan (``{"replan": true}``)."""
    data = _params(params, kwargs)
    session = _get(data)
    changes = data.get("changes")
    if not isinstance(changes, dict) or not changes:
        raise invalid_params("changes must be a non-empty object")
    plan = await _call(session.modify, changes)
    return {**_summary(session), "plan": plan.to_dict()}


async def research_start(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Execute the approved plan. Bounded by a hard RPC-side deadline."""
    data = _params(params, kwargs)
    session = _get(data)
    try:
        timeout = float(os.environ.get(_START_TIMEOUT_ENV, _DEFAULT_START_TIMEOUT))
    except ValueError:
        timeout = _DEFAULT_START_TIMEOUT
    try:
        await asyncio.wait_for(_call(session.start), timeout=timeout)
    except asyncio.TimeoutError:
        # Belt and braces: the engine has its own budget, but the RPC layer
        # never leaves a caller hanging either.
        await asyncio.to_thread(session.cancel)
        raise invalid_params(
            f"the research run exceeded {timeout:.0f}s and was cancelled"
        ) from None
    return _summary(session)


async def research_status(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Cheap poll: status, progress, and the event cursor for ``research.stream``."""
    data = _params(params, kwargs)
    session = _get(data)
    cursor = data.get("cursor", 0)
    if not isinstance(cursor, int) or cursor < 0:
        raise invalid_params("cursor must be a non-negative integer")
    events = session.events_since(cursor)
    return {
        **_summary(session),
        "cursor": cursor + len(events),
        "new_events": events[-200:],
    }


async def research_stream(params: Any = None, **kwargs: Any) -> Stream:
    """Stream progress events as they are recorded (phase, section, iteration).

    Replays everything after ``cursor``, then follows the session live until it
    reaches a terminal state or ``timeout`` seconds elapse. The final result is
    the session summary, so a client that only wants the outcome can ignore the
    chunks entirely.
    """
    data = _params(params, kwargs)
    session = _get(data)
    cursor = data.get("cursor", 0)
    if not isinstance(cursor, int) or cursor < 0:
        raise invalid_params("cursor must be a non-negative integer")
    try:
        timeout = float(data.get("timeout", 30.0))
    except (TypeError, ValueError):
        raise invalid_params("timeout must be a number") from None
    timeout = max(0.0, min(timeout, 600.0))
    follow = bool(data.get("follow", True))

    async def chunks() -> AsyncIterator[dict[str, Any]]:
        index = cursor
        deadline = time.monotonic() + timeout
        emitted = 0
        while True:
            events = session.record.events[index:]
            for event in events:
                index += 1
                emitted += 1
                yield {"event": event, "cursor": index}
                if emitted >= _STREAM_MAX_EVENTS:
                    return
            terminal = session.record.status in ("COMPLETE", "FAILED", "CANCELLED")
            if not follow or terminal or time.monotonic() >= deadline:
                return
            # Follow mode has no per-session cancellation token today; the
            # helper keeps the 50 ms event-loop yield without a bare sleep.
            await ainterruptible_sleep(_STREAM_POLL_SECONDS)

    return Stream(final=_summary(session), chunks=chunks())


async def research_stop(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Cooperative cancellation; the run stops at its next step boundary."""
    data = _params(params, kwargs)
    session = _get(data)
    await _call(session.cancel)
    return _summary(session)


async def research_export(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Publish a COMPLETE session and return its artifact paths."""
    data = _params(params, kwargs)
    session = _get(data)
    report = await _call(session.publish)
    return {**_summary(session), "report": report}


HANDLERS = {
    "research.create": research_create,
    "research.list": research_list,
    "research.get": research_get,
    "research.plan": research_plan,
    "research.approve": research_approve,
    "research.modify": research_modify,
    "research.start": research_start,
    "research.status": research_status,
    "research.stream": research_stream,
    "research.stop": research_stop,
    "research.export": research_export,
}
