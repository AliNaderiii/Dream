"""The :class:`Dream` agent runtime.

The class is the *stable seam* of the agent package: its public
signature, the :class:`Turn` return type, and the public dataclasses
(:class:`ApprovalPolicy`, :class:`_ExtractionOutcome`) are unchanged
from the previous single-file layout. Internally the class delegates
to the sibling modules, so a future change in, say, how the system
prompt is built, or how reminders match, touches one sibling rather
than a single ~1900-line file.

The class wires together:

* a backend (``OpenAIBackend``, ``OllamaBackend``, or ``EchoBackend``),
* a :class:`MemoryStore`,
* an :class:`ApprovalPolicy`,
* an optional :class:`ProviderManager` (skills + memory providers),
* an optional :class:`BoundedMemory` (MEM Stage A: agent notes + user
  profile),
* an optional usage :class:`Ledger` (commercial kernel).

The main loop is :meth:`Dream.run`; it dispatches the conversation
one user message at a time and returns a :class:`Turn` carrying the
reply, the tool calls it issued, the memories it created or
superseded, and the elapsed wall-clock time. The class also exposes
:meth:`Dream.compact` for an explicit ``/compress`` and
:meth:`Dream.context_usage` for the transcript's live token
counter.
"""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from dream.agent.approval import ApprovalPolicy
from dream.agent.backends.echo import EchoBackend
from dream.agent.backends.factory import build_backend
from dream.agent.backends.ollama import OllamaBackend
from dream.agent.backends.openai import OpenAIBackend
from dream.agent.constants import (
    EXTRACTION_TEMPERATURE,
    log,
)
from dream.agent.env_config import (
    _fraction,
    _positive_int,
    _resolve_extraction_timeout,
    _resolve_memory_block_char_limit,
)
from dream.agent.extraction import (
    _ExtractionOutcome,
    _record_extraction_status,
    _record_store_failure,
    _safe_log_message,
)
from dream.agent.http_utils import _arguments
from dream.agent.prompts import (
    _BASE_PROMPT,
    _MEMORIES_CLOSE,
    _MEMORIES_OPEN,
    _MEMORY_USAGE,
    _REMINDER_CANCEL_USAGE,
    _REMINDER_TOOL_USAGE,
    _REMINDER_USAGE,
    _REMINDERS_CLOSE,
    _REMINDERS_OPEN,
)
from dream.agent.reminders import (
    _CANCEL_TIME_HINT,
    _CREATE_TIME_HINT,
    _cancel_ambiguous_message,
    _cancel_no_date_match_message,
    _cancel_not_found_message,
    _cancelled_message,
    _match_reminders,
    _relative_age,
    _resolve_reminder_date,
)
from dream.agent.tools_wire import _wire_tool_calls
from dream.claims import guard_claims
from dream.commerce import Ledger, LedgerError, QuotaExceeded, ledger_attached
from dream.compaction import (
    DEFAULT_ECHO_CONTEXT_TOKENS,
    DEFAULT_MODEL_CONTEXT_TOKENS,
    DEFAULT_THRESHOLD,
    deterministic_summary,
    split_for_compaction,
    usage,
)
from dream.extraction import (
    STATUS_ABANDONED,
    STATUS_ERROR,
    ExtractionResult,
    extract_facts,
)
from dream.memory import Memory, MemoryStore
from dream.memory_stores import (
    BOUNDED_MEMORY_USAGE,
    NOTES_LABEL,
    PROFILE_LABEL,
    TARGET_MEMORY,
    TARGET_USER,
    BoundedMemory,
    BoundedSnapshot,
)
from dream.normalization import normalize_importance, normalize_kind
from dream.providers import BuiltInMemoryProvider, ProviderManager
from dream.reminders import Reminder, format_jalali, prompt_reminders
from dream.skills import SkillPromptProvider, apply_slash_invocation, render_skill_catalog
from dream.tools import REGISTRY, execute, openai_schemas, tool


@dataclass(slots=True)
class Turn:
    """Observable record of one user turn through the agent loop."""

    reply: str
    tool_calls: list[dict[str, Any]]
    memories_used: list[Memory]
    memories_created: list[Memory]
    elapsed_seconds: float
    extraction: Any = None
    memory_errors: list[str] = field(default_factory=list)
    memories_superseded: list[Memory] = field(default_factory=list)
    memories_merged: list[Memory] = field(default_factory=list)
    memories_injected: list[Memory] | None = None


class Dream:
    """An agent runtime that combines durable memory, tools, and approval."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        backend: OpenAIBackend | OllamaBackend | EchoBackend | None = None,
        approval_policy: ApprovalPolicy | None = None,
        max_iterations: int = 4,
        manager: ProviderManager | None = None,
        bounded: BoundedMemory | None = None,
        demo: bool = False,
    ) -> None:
        if manager is not None:
            self.manager = manager
            self.store = None
            for p in manager.providers:
                if isinstance(p, BuiltInMemoryProvider):
                    self.store = p.store
                    break
            if self.store is None and store is not None:
                self.store = store
            # The skills usage line is part of Dream's own behaviour, not of
            # any caller's provider choice; the manager seam carries it
            # either way.
            self.manager.register(SkillPromptProvider())
        else:
            if store is None:
                raise TypeError("Dream requires either a store or a manager")
            self.store = store
            self.manager = ProviderManager()
            self.manager.register(BuiltInMemoryProvider(store))
            self.manager.register(SkillPromptProvider())
        self.backend = backend or build_backend()
        self.approval_policy = approval_policy or ApprovalPolicy()
        self.max_iterations = max_iterations
        self.demo = bool(demo)
        # The usage ledger hook: attached only when DREAM_PLAN is not local
        # or DREAM_LEDGER is set, so the unlimited local plan runs with no
        # ledger file at all. Metered plans fail closed on a corrupt ledger.
        # A misconfigured ledger (unknown plan name) must not crash the agent
        # at construction: the Persian refusal is held and returned by run().
        self.ledger: Ledger | None = None
        self._ledger_refusal: str | None = None
        try:
            self.ledger = Ledger.from_env() if ledger_attached() else None
        except LedgerError as exc:
            self._ledger_refusal = str(exc)
        self.memory_block_char_limit = _resolve_memory_block_char_limit(
            os.environ.get("DREAM_MEMORY_BLOCK_CHAR_LIMIT")
        )
        self.extraction_timeout_seconds = _resolve_extraction_timeout(
            os.environ.get("DREAM_EXTRACTION_TIMEOUT_SECONDS")
        )
        self.history: list[dict[str, Any]] = []
        # Stage E: accounting is local and deterministic. Echo defaults generously
        # so ordinary offline turns never compact unless explicitly configured.
        default_window = (
            DEFAULT_ECHO_CONTEXT_TOKENS
            if isinstance(self.backend, EchoBackend)
            else DEFAULT_MODEL_CONTEXT_TOKENS  # noqa: E501
        )
        self.context_tokens = _positive_int(
            os.environ.get("DREAM_CONTEXT_TOKENS"), default_window
        )
        self.compaction_threshold = _fraction(
            os.environ.get("DREAM_COMPACTION_THRESHOLD"), DEFAULT_THRESHOLD
        )  # noqa: E501
        self.compaction_keep_messages = _positive_int(
            os.environ.get("DREAM_COMPACTION_KEEP_MESSAGES"), 4, 2, 100
        )  # noqa: E501
        self._compaction_summary = ""
        self._turn_count = 0
        self.nudge_every_turns = _positive_int(
            os.environ.get("DREAM_MEMORY_NUDGE_EVERY_TURNS"), 8, 1, 10_000
        )  # noqa: E501
        self.nudges_enabled = (
            os.environ.get("DREAM_MEMORY_NUDGES", "1").lower()
            not in {"0", "false", "off", "no"}
        )  # noqa: E501
        self._nudge_sent = False
        self._created: list[Memory] = []
        self._superseded: list[Memory] = []
        self._merged: list[Memory] = []
        # The dual bounded stores (MEM Stage A): agent notes + user profile.
        # Attachment is explicit so existing embedders see no new files; the
        # snapshots are frozen for the session at construction time.
        self.bounded = bounded
        self._bounded_snapshots: dict[str, BoundedSnapshot] | None = None
        self._bounded_prompt: str | None = None
        self._refresh_bounded_snapshots()
        self._register_memory_tools()
        self._register_reminder_tools()
        self._register_bounded_memory_tools()

    def _register_memory_tools(self) -> None:
        store = self.store
        created = self._created
        superseded = self._superseded
        merged = self._merged

        @tool(risk="guarded")
        def remember_fact(
            content: str,
            kind: str = "semantic",
            importance: float = 0.5,
            tags: list | None = None,
        ) -> dict[str, Any]:
            """Store a durable fact in Dream's memory.

            :param content: Fact to remember.
            :param kind: Memory kind — semantic, episodic, or procedural.
            :param importance: Importance from zero to one.
            :param tags: Optional labels for retrieval.
            """
            memory = store.remember(
                content,
                kind=normalize_kind(kind),
                importance=normalize_importance(importance),
                tags=tags or [],
                on_supersede=superseded.append,
                on_merge=merged.append,
            )
            created.append(memory)
            return {
                "id": memory.id,
                "content": memory.content,
                "kind": memory.kind,
                "importance": memory.importance,
            }

        @tool(risk="safe")
        def search_memory(query: str, limit: int = 8) -> list[dict[str, Any]]:
            """Search durable Dream memory.

            :param query: Text to search for.
            :param limit: Maximum matching memories.
            """
            return [
                {"id": m.id, "content": m.content, "kind": m.kind}
                for m in store.recall(query, limit=limit)
            ]

        @tool(risk="guarded")
        def forget_memory(memory_id: int) -> bool:
            """Archive one memory.

            :param memory_id: Identifier of the memory to archive.
            """
            return store.forget(memory_id)

    def _register_reminder_tools(self) -> None:
        store = self.store
        if store is None:
            return

        @tool(risk="guarded")
        def create_reminder(
            date: str,
            text: str,
            repeat_days: int | None = None,
            repeat_months: int | None = None,
        ) -> dict[str, Any]:
            """Create a durable reminder for the owner.

            :param date: Due date as Jalali YYYY-MM-DD (year <1700) or a
                natural Persian phrase. Pure date only; time words cause refusal.
            :param text: Reminder text, what to remind about.
            :param repeat_days: Repeat every N days (optional).
            :param repeat_months: Repeat every N months (optional).
            """
            if not text or not text.strip():
                raise ValueError("text must not be empty")
            if repeat_days is not None and repeat_days == 0:
                raise ValueError("repeat must be non-zero")
            if repeat_months is not None and repeat_months == 0:
                raise ValueError("repeat must be non-zero")
            if repeat_days is not None and repeat_months is not None:
                raise ValueError("repeat must be either days or months, not both")
            due_at = _resolve_reminder_date(date, _CREATE_TIME_HINT)
            rem = store.add_reminder(
                text.strip(), due_at, repeat_days, repeat_months
            )
            return {
                "id": rem.id,
                "due": format_jalali(rem.due_at),
                "text": rem.text,
                "repeat_days": rem.repeat_days,
                "repeat_months": rem.repeat_months,
                "due_at": rem.due_at,
            }

        @tool(risk="guarded")
        def cancel_reminder(
            text: str, date: str | None = None
        ) -> dict[str, Any]:
            """Cancel one of the owner's reminders, by text and optional date.

            The match runs over the active reminders: an exact text match,
            otherwise a unique substring match, narrowed by the date when one
            is sent. A row is removed only when exactly one row fits; zero or
            several fits refuse with the candidates named in Persian, and no
            row is touched. The removal is the same permanent delete
            ``/unremind`` performs, so the two surfaces stay identical.

            :param text: Reminder text as the owner says it; a unique
                fragment is accepted.
            :param date: Optional due date — Jalali YYYY-MM-DD (year <1700)
                or a natural Persian phrase. Pure date only.
            """
            if not text or not text.strip():
                raise ValueError("text must not be empty")
            matches = _match_reminders(store, text)
            if not matches:
                raise ValueError(_cancel_not_found_message(text.strip()))
            if date is not None and str(date).strip():
                wanted = format_jalali(
                    _resolve_reminder_date(str(date), _CANCEL_TIME_HINT)
                )
                dated = [rem for rem in matches if format_jalali(rem.due_at) == wanted]
                if not dated:
                    raise ValueError(
                        _cancel_no_date_match_message(text.strip(), wanted, matches)
                    )
                matches = dated
            if len(matches) > 1:
                raise ValueError(_cancel_ambiguous_message(text.strip(), matches))
            victim = matches[0]
            # The store cascades reminder deletion to its delivery rows, so a
            # fired reminder deletes cleanly and the child rows go with the
            # parent. No hand cleanup here: that duty belongs under the store,
            # where every caller gets it.
            if not store.delete_reminder(victim.id):
                raise ValueError(_cancel_not_found_message(text.strip()))
            return {
                "id": victim.id,
                "text": victim.text,
                "due": format_jalali(victim.due_at),
                "repeat_days": victim.repeat_days,
                "repeat_months": victim.repeat_months,
                "message": _cancelled_message(victim),
            }

    def reset_session(self) -> None:
        """Discard conversational context without touching durable memory.

        Starting a new conversational session also takes a fresh frozen
        snapshot of the bounded stores: the previous session's snapshot was
        frozen for that session's lifetime, and the new one must reflect
        everything the tools wrote since.
        """
        self.history.clear()
        self._compaction_summary = ""
        self._turn_count = 0
        self._nudge_sent = False
        self._refresh_bounded_snapshots()

    def _refresh_bounded_snapshots(self) -> None:
        """Freeze the bounded-store snapshots and render their prompt block.

        Called once at construction (session start) and again by
        :meth:`reset_session`. Between those points the block is a constant
        string: writes made through the tools land in the stores and in the
        tools' own result payloads, never retroactively in the running
        session's prompt.
        """
        if self.bounded is None:
            self._bounded_snapshots = None
            self._bounded_prompt = None
            return
        snapshots = self.bounded.snapshots()
        self._bounded_snapshots = snapshots
        sections = [BOUNDED_MEMORY_USAGE]
        for label, snapshot in (
            (NOTES_LABEL, snapshots[TARGET_MEMORY]),
            (PROFILE_LABEL, snapshots[TARGET_USER]),
        ):
            section = f"\n\n[{label}]\n{snapshot.header}"
            if snapshot.text:
                section += f"\n{snapshot.text}"
            sections.append(section)
        self._bounded_prompt = "".join(sections)

    def _register_bounded_memory_tools(self) -> None:
        """Register the two bounded-store edit tools (MEM Stage A).

        The action surface is exactly add / replace / remove; there is no
        read action because the frozen snapshot is already in the system
        prompt and every mutation returns the fresh store state. The risk
        tier is ``guarded`` — local, reversible writes, logged on execution —
        matching ``remember_fact``.
        """
        if self.bounded is None:
            return
        bounded = self.bounded

        def _bounded_result(
            target: str, action: str, snapshot: BoundedSnapshot
        ) -> dict[str, Any]:
            return {
                "target": target,
                "action": action,
                "header": snapshot.header,
                "used_chars": snapshot.used_chars,
                "capacity": snapshot.capacity,
                "entries": len(snapshot.entries),
                "content": snapshot.text,
            }

        def _apply(
            store, target: str, action: str, text: str, old: str, new: str
        ) -> dict[str, Any]:
            if action == "add":
                return _bounded_result(target, action, store.add(text))
            if action == "replace":
                return _bounded_result(target, action, store.replace(old, new))
            if action == "remove":
                return _bounded_result(target, action, store.remove(old))
            raise ValueError(
                f"action must be add, replace, or remove, got {action!r}"
            )

        @tool(risk="guarded")
        def agent_notes(
            action: Literal["add", "replace", "remove"],
            text: str = "",
            old: str = "",
            new: str = "",
        ) -> dict[str, Any]:
            """Edit the agent's durable notes store (bounded, §-separated).

            The store is character-bounded; when it is full the tool returns
            an error instead of truncating — consolidate near-duplicate
            entries with replace, or drop stale ones with remove, then retry
            in the same turn.

            :param action: add appends an entry; replace swaps the unique
                entry containing old for new; remove deletes the unique entry
                containing old.
            :param text: Entry text, for action add.
            :param old: Substring identifying one entry, for replace/remove.
            :param new: Replacement entry text, for action replace.
            """
            return _apply(bounded.notes, TARGET_MEMORY, action, text, old, new)

        @tool(risk="guarded")
        def user_profile(
            action: Literal["add", "replace", "remove"],
            text: str = "",
            old: str = "",
            new: str = "",
        ) -> dict[str, Any]:
            """Edit the durable user-profile store (bounded, §-separated).

            Holds durable facts about the user: preferences, constraints,
            identity details worth remembering across sessions. The store is
            character-bounded; on overflow the tool errors — consolidate with
            replace or remove, then retry in the same turn.

            :param action: add appends an entry; replace swaps the unique
                entry containing old for new; remove deletes the unique entry
                containing old.
            :param text: Entry text, for action add.
            :param old: Substring identifying one entry, for replace/remove.
            :param new: Replacement entry text, for action replace.
            """
            return _apply(bounded.profile, TARGET_USER, action, text, old, new)

    @property
    def ledger_attached(self) -> bool:
        """True when this agent meters turns against a usage ledger.

        False for the default local plan: ``Dream(store, EchoBackend())``
        carries no meter and needs no ledger file. It is also true when the
        ledger is misconfigured, because a broken meter still gates the turn
        (fail-closed) rather than disappearing.
        """
        return self.ledger is not None or self._ledger_refusal is not None

    def _ledger_block(self) -> str | None:
        """Consume one turn on the attached ledger; return a Persian refusal.

        Returns ``None`` when the turn may proceed. Raises nothing: every
        ledger refusal (quota exhausted, corrupt file, unknown plan) becomes
        the turn's reply so the caller always receives a ``Turn``.
        """
        if self._ledger_refusal is not None:
            return self._ledger_refusal
        if self.ledger is None:
            return None
        try:
            self.ledger.consume()
        except (QuotaExceeded, LedgerError) as exc:
            return str(exc)
        return None

    def _memory_block(
        self, memories: list[Memory]
    ) -> tuple[str, list[Memory]]:
        """Render complete recalled-memory lines that fit the prompt budget."""
        lines: list[str] = []
        injected: list[Memory] = []
        used = 0
        for memory in sorted(memories, key=lambda memory: memory.score, reverse=True):
            line = f"- [{_relative_age(memory.created_at)}] {memory.content}"
            addition = len(line) + (1 if lines else 0)
            if used + addition > self.memory_block_char_limit:
                break
            lines.append(line)
            injected.append(memory)
            used += addition

        block = f"\n\n{_MEMORIES_OPEN}\n"
        if lines:
            block += "\n".join(lines) + "\n"
        block += _MEMORIES_CLOSE
        return block, injected

    def _reminder_block(
        self, reminders: list[Reminder], query: str, budget: int
    ) -> tuple[str, list[Reminder]]:
        """Render the reminder section of the prompt within *budget* chars.

        Memories are fitted to the shared budget first and this section is
        omitted when nothing qualifies or nothing fits, so reminders can never
        crowd memories out of the prompt.
        """
        if budget <= 0 or not reminders:
            return "", []
        overhead = len("\n\n" + _REMINDERS_OPEN + "\n") + len("\n" + _REMINDERS_CLOSE)
        usable = budget - overhead
        if usable <= 0:
            return "", []
        lines: list[str] = []
        injected: list[Reminder] = []
        used = 0
        from dream.agent.reminders import _render_reminder_line  # local import: avoid cycle

        for reminder in prompt_reminders(reminders, query):
            line = _render_reminder_line(reminder)
            addition = len(line) + (1 if lines else 0)
            if used + addition > usable:
                break
            lines.append(line)
            injected.append(reminder)
            used += addition
        if not lines:
            return "", []
        block = "\n\n" + _REMINDERS_OPEN + "\n" + "\n".join(lines) + "\n" + _REMINDERS_CLOSE
        return block, injected

    def _system_message(
        self,
        memories: list[Memory],
        memory_block: str | None = None,
        reminder_block: str | None = None,
        query: str = "",
    ) -> dict[str, str]:
        prompt = (
            _BASE_PROMPT + _MEMORY_USAGE + _REMINDER_TOOL_USAGE + _REMINDER_CANCEL_USAGE
        )
        # The M4 contribute_prompt hook, wired for the first time: subsystems
        # (here: skills) add their own usage line to the system prompt.
        skills_block, _ = self.manager.contribute_prompt(
            query, self.memory_block_char_limit
        )
        if skills_block:
            prompt += skills_block
        # Stage C catalog: name + description only, own budget, never a body.
        catalog_block, _ = render_skill_catalog()
        if catalog_block:
            prompt += catalog_block
        # The frozen bounded-store snapshots (MEM Stage A) ride with the
        # system prompt as a constant per-session block, after the usage
        # sentences and before the per-turn reminder/recalled-memory sections.
        if self._bounded_prompt is not None:
            prompt += self._bounded_prompt
        if self._compaction_summary:
            prompt += "\n\n" + self._compaction_summary
        if self._nudge_due():
            prompt += (
                "\n\nMemory nudge / "
                "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
                "\u062d\u0627\u0641\u0638\u0647: "
                "Persist only durable preferences or facts through the bounded memory tools; "
                "\u0641\u0642\u0637 "
                "\u062f\u0627\u0646\u0633\u062a\u0647\u200c\u0647\u0627\u06cc "
                "\u0645\u0627\u0646\u062f\u06af\u0627\u0631 \u0631\u0627 "
                "\u0630\u062e\u06cc\u0631\u0647 \u06a9\u0646."
            )
        if memory_block is None:
            memory_block, _ = self._memory_block(memories)
        middle = ""
        if reminder_block:
            middle = _REMINDER_USAGE + reminder_block
        return {"role": "system", "content": prompt + middle + memory_block}

    def context_usage(self) -> dict[str, float | int]:
        """Expose local accounting for transcripts, tests, and bridge clients."""
        current = usage(self.history, self.context_tokens)
        return {
            "tokens": current.tokens,
            "window": current.window,
            "ratio": current.ratio,
        }

    def _nudge_due(self) -> bool:
        return (
            self.nudges_enabled
            and not self.demo
            and not self._nudge_sent
            and self._turn_count >= self.nudge_every_turns
        )  # noqa: E501

    def compact(self, reason: str = "threshold") -> dict[str, Any]:
        """Compact only at a turn boundary; retain the active recent exchange."""
        model_history = [
            item
            for item in self.history
            if item.get("role") in {"user", "assistant", "tool"}
        ]  # noqa: E501
        before = usage(model_history, self.context_tokens)
        dropped, kept = split_for_compaction(
            model_history, self.compaction_keep_messages
        )
        if not dropped:
            return {
                "compacted": False,
                "before_tokens": before.tokens,
                "after_tokens": before.tokens,
            }  # noqa: E501
        summary = deterministic_summary(dropped, reason)
        self._compaction_summary = (self._compaction_summary + "\n" + summary).strip()
        prior_events = [item for item in self.history if item.get("kind") == "compaction"]
        self.history = prior_events + kept
        after = usage(kept, self.context_tokens)
        event = {
            "kind": "compaction",
            "timestamp": time.time(),
            "reason": reason,
            "before_tokens": before.tokens,
            "after_tokens": after.tokens,
            "preserved_messages": len(kept),
            "summary": summary,
        }
        self.history.insert(0, event)
        return {"compacted": True, **event}

    def _compact_if_needed(self) -> None:
        estimate = usage(self.history, self.context_tokens)
        if estimate.ratio >= self.compaction_threshold:
            self.compact("threshold")

    def run(self, message: str) -> Turn:
        """Run one complete user turn, including any model-requested tools."""
        self._compact_if_needed()
        # Metering gate: a turn is consumed (and possibly refused) before any
        # backend call, memory write, or journal entry. The refusal is a
        # normal Turn whose reply is the Persian quota/corruption sentence, so
        # every caller gets a reply and no code path grants a free turn on a
        # broken meter.
        ledger_block = self._ledger_block()
        if ledger_block is not None:
            return Turn(ledger_block, [], [], [], 0.0)
        started = time.monotonic()
        self._created.clear()
        self._superseded.clear()
        self._merged.clear()
        if self.store is not None:
            self.store.log("user", message)
        original_message = message
        stripped = message.lstrip()
        if stripped.lower() == "/compress":
            outcome = self.compact("explicit")
            reply = (
                "Context compacted."
                if outcome["compacted"]
                else "Nothing eligible for compaction."
            )  # noqa: E501
            self.history.append({"role": "assistant", "content": reply})
            return Turn(reply, [], [], [], time.monotonic() - started)
        if stripped.startswith("\\"):
            stripped = "/" + stripped[1:]
        if stripped.lower().startswith("/learn"):
            from dream.skills.learn import LearnError, prepare_learn_turn

            try:
                message = prepare_learn_turn(message, history=self.history)
            except LearnError as exc:
                return Turn(str(exc), [], [], [], time.monotonic() - started)
        # Slash stacking: leading skill tokens load bodies into the user turn.
        model_message, slash_stack = apply_slash_invocation(message)
        if slash_stack.invoked:
            try:
                from dream.skills.store import get_ledger

                with get_ledger() as ledger:
                    for skill in slash_stack.skills:
                        ledger.log_use(
                            skill.name, "invoked", duration_ms=0.0, source="slash"
                        )
            except Exception:
                pass
        memories = self.manager.recall(message, limit=8, reinforce=True)
        memory_block, injected_memories = self._memory_block(memories)
        reminder_block, _ = self._reminder_block(
            self.manager.list_reminders(),
            message,
            self.memory_block_char_limit - len(memory_block),
        )
        self.history.append({"role": "user", "content": model_message})
        # A second boundary before dispatch ensures a small configured window
        # is never sent an already-overflowing transcript. The just-added user
        # message remains active; no in-flight tool exchange exists yet.
        self._compact_if_needed()
        calls_made: list[dict[str, Any]] = []
        reply = "I could not produce an answer."

        for _ in range(self.max_iterations):
            messages = [
                self._system_message(memories, memory_block, reminder_block, message),
                *(
                    item
                    for item in self.history
                    if item.get("role") in {"user", "assistant", "tool"}
                ),  # noqa: E501
            ]
            response = self.backend.chat(messages, tools=openai_schemas())
            calls = response.get("tool_calls", [])
            if not calls:
                reply = response.get("content") or reply
                break
            wire_calls = _wire_tool_calls(calls)
            self.history.append(
                {
                    "role": "assistant",
                    "content": response.get("content"),
                    "tool_calls": wire_calls,
                }
            )
            for call, wire_call in zip(calls, wire_calls, strict=True):
                name = str(call.get("name", ""))
                arguments = _arguments(call.get("arguments", {}))
                allowed, reason = self.approval_policy.allows(name, arguments)
                if allowed:
                    result = execute(
                        name, arguments, approved=REGISTRY[name].risk == "dangerous"
                    )
                else:
                    result = json.dumps(
                        {"blocked": True, "reason": reason}, ensure_ascii=False
                    )
                calls_made.append(
                    {
                        "name": name,
                        "arguments": arguments,
                        "allowed": allowed,
                        "result": result,
                    }
                )
                self.history.append(
                    {"role": "tool", "tool_call_id": wire_call["id"], "content": result}
                )

        self.manager.persist()

        extraction_result, store_errors = self._run_extraction(message)

        # The claim guards run after extraction so the outcome of the turn —
        # the rows it wrote, the memories the model was shown, and whether the
        # extraction pass was abandoned — is complete before any warning is
        # decided. A save-claim reply is only truthful when the write it claims
        # actually happened; an unconfirmed claim gets a Persian warning
        # appended so the owner is never left believing a durable write
        # occurred. A truthful reply passes through byte for byte. The seam is
        # a single call so a mixed sentence never reads two warnings.
        reply = guard_claims(
            reply,
            calls_made,
            list(self._created),
            injected_memories,
            extraction_result.status,
        )
        from dream.skills.propose import format_proposal_notice, maybe_propose

        proposal = maybe_propose(original_message, calls_made, demo=self.demo)
        if proposal is not None:
            reply = reply + format_proposal_notice(proposal)
        self.history.append({"role": "assistant", "content": reply})
        if self.store is not None:
            self.store.log("assistant", reply)
        if self._nudge_due():
            self._nudge_sent = True
        self._turn_count += 1

        return Turn(
            reply,
            calls_made,
            memories,
            list(self._created),
            time.monotonic() - started,
            extraction=extraction_result,
            memory_errors=store_errors,
            memories_superseded=list(self._superseded),
            memories_merged=list(self._merged),
            memories_injected=list(injected_memories),
        )

    def _extraction_backend(self) -> Any:
        """Return the backend handle for the post-turn extraction pass.

        Extraction must emit parseable JSON, so it samples at a fixed low
        temperature rather than the conversational one. Only the real HTTP
        clients carry sampling; offline and scripted backends ignore
        temperature and are returned unchanged. The real client also gets
        retries disabled: the pass runs inside a wall-clock budget, so it
        must never retry a rate limit into that budget.
        """
        backend = self.backend
        if isinstance(backend, OpenAIBackend):
            colder = copy.copy(backend)
            colder.temperature = EXTRACTION_TEMPERATURE
            colder.max_retries = 0
            return colder
        return backend

    def _extract_in_background(
        self, message: str, outcome: _ExtractionOutcome
    ) -> None:
        """Run the extraction pass and store any facts it finds.

        Runs on a worker thread so the reply is never delayed by it. A broken
        provider or fact must never escape into the turn that already produced
        its reply: extract_facts returns a typed ExtractionResult for every
        failure class it knows, and the two bounded catches below only guard
        the unexpected. Cancellation and system exits are always re-raised —
        they are never flattened into a fake result.
        """
        try:
            result = extract_facts(self._extraction_backend(), message)
        except (KeyboardInterrupt, SystemExit):
            raise
        # Redact raw_text after extract_facts returns (extract_facts may have
        # set raw_text directly; this ensures sensitive data is always bounded).
        result.raw_text = _safe_log_message(result.raw_text)
        errors: list[str] = []
        for fact in result.facts:
            try:
                memory = self.store.remember(
                    fact.content,
                    kind=fact.kind,
                    importance=fact.importance,
                    source="extraction",
                    on_supersede=self._superseded.append,
                    on_merge=self._merged.append,
                )
                if not any(m.id == memory.id for m in self._created):
                    self._created.append(memory)
            except ValueError:
                # The one expected case: an unusable fact (e.g. empty content).
                # Skip it and keep the rest of the batch.
                log.debug("extraction store rejected an unusable fact")
                continue
            except (KeyboardInterrupt, SystemExit):
                raise
            except sqlite3.Error as exc:
                # A real storage failure (locked database, full disk, broken
                # constraint, ...). Never silent: record it for the CLI, count
                # it, and log it redacted.
                _record_store_failure(errors, exc)
        outcome.result = result
        outcome.errors = errors

    def _run_extraction(
        self, message: str
    ) -> tuple[ExtractionResult, list[str]]:
        """Start the extraction pass in the background and wait at most the
        extraction budget for it.

        When the pass finishes within the budget its facts are already in the
        store and are reported on the turn, exactly as before. When it does
        not — the provider hangs — the turn is marked abandoned and the reply
        is returned anyway; the worker keeps running and stores the facts
        when the provider finally answers. The finalized status is recorded
        (metric + structured log) exactly once per turn.
        """
        outcome = _ExtractionOutcome()
        worker = threading.Thread(
            target=self._extract_in_background, args=(message, outcome), daemon=True
        )
        worker.start()
        worker.join(timeout=self.extraction_timeout_seconds)
        if worker.is_alive():
            result = ExtractionResult(
                facts=[],
                status=STATUS_ABANDONED,
                raw_text=(
                    "did not finish within "
                    f"{self.extraction_timeout_seconds:.1f}s"
                ),
            )
            errors: list[str] = []
        else:
            result = outcome.result
            if result is None:
                result = ExtractionResult(
                    facts=[], status=STATUS_ERROR, raw_text="extraction produced no result"
                )
            errors = outcome.errors
        _record_extraction_status(result)
        return result, errors
