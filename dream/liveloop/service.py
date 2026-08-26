"""Live loops: arm approved Space drafts onto the scheduler; honest role turns."""

from __future__ import annotations

import os
import threading
from typing import Any

from dream.liveloop.errors import LiveLoopError, LiveLoopSecurityError
from dream.liveloop.honesty import snapshot
from dream.memory import MemoryStore
from dream.reliability import CancelToken, Deadline
from dream.scheduler import create_schedule, schedule_to_dict
from dream.space.catalog import clamp_ceiling, get_role
from dream.space.errors import SpaceError
from dream.space.service import SpaceService
from dream.space.service import get_service as space_service

_LIVE_ON = frozenset({"1", "true", "yes", "on"})


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


class LiveLoopService:
    def __init__(
        self,
        *,
        spaces: SpaceService | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.spaces = spaces or space_service()
        path = os.environ.get("DREAM_LIVELOOP_DB")
        self.store = store or (MemoryStore(path) if path else MemoryStore())
        self._lock = threading.RLock()

    def route_snapshot(
        self,
        *,
        bar_provider: str | None = None,
        pane_provider: str | None = None,
        pane_model: str | None = None,
    ) -> dict[str, Any]:
        return snapshot(
            bar_provider=bar_provider,
            pane_provider=pane_provider,
            pane_model=pane_model,
        )

    def arm_draft(self, draft_id: str, *, approved: bool = False) -> dict[str, Any]:
        """Register an approved Space draft on the live scheduler.

        Each later fire still requires approval (require_approval=True).
        Dangerous drafts never become schedules.
        """
        if not approved:
            raise LiveLoopSecurityError(
                _bilingual("missing approver — refuse", "تأییدکننده نیست — رد شد")
            )
        try:
            draft = self.spaces.store.get_draft(draft_id)
        except SpaceError as exc:
            raise LiveLoopError(str(exc)) from exc
        if draft.get("status") != "APPROVED":
            raise LiveLoopError(
                _bilingual(
                    "draft is not approved; nothing was scheduled",
                    "پیشنویس تأیید نشده؛ چیزی زمان‌بندی نشد",
                )
            )
        if draft.get("schedule_id"):
            raise LiveLoopError(
                _bilingual(
                    "draft is already armed on the scheduler",
                    "این پیشنویس از قبل روی زمان‌بند مسلح است",
                )
            )
        shells = draft.get("shell") or []
        if draft.get("dangerous") or any(row.get("risk") == "dangerous" for row in shells):
            raise LiveLoopSecurityError(
                _bilingual(
                    "dangerous shell drafts are never scheduled",
                    "پیشنویس پوستهٔ خطرناک هرگز زمان‌بندی نمی‌شود",
                )
            )
        cron = (draft.get("cron") or "").strip()
        if not cron:
            raise LiveLoopError(
                _bilingual(
                    "draft has no understood schedule",
                    "پیشنویس زمان‌بندی قابل‌فهم ندارد",
                )
            )
        space = self.spaces.store.get_space(draft["space_id"])
        prompt = (
            f"[space:{space['space_id']} draft:{draft_id}]\n"
            f"{draft.get('rule') or ''}\n"
            "Do not run shell. Wait for approval on every fire."
        )
        schedule = create_schedule(
            self.store,
            name=f"space:{space.get('name') or space['space_id']}",
            prompt=prompt,
            cron_expression=cron,
            natural_language=draft.get("rule") or "",
            description="Armed from an approved Space draft. Each fire still needs approval.",
            require_approval=True,
            enabled=True,
        )
        draft["schedule_id"] = schedule.id
        draft["armed"] = True
        self.spaces.store.put_draft(draft)
        return {
            "draft_id": draft_id,
            "armed": True,
            "spawned": False,
            "schedule": schedule_to_dict(schedule),
            "require_approval": True,
        }

    def role_turn(
        self,
        space_id: str,
        role_id: str,
        question: str,
        *,
        live: bool = False,
        timeout: float = 8.0,
    ) -> dict[str, Any]:
        """Answer as a specialized role. Live hosted turns fail closed without a key."""
        briefing = self.spaces.ask(space_id, role_id, question, timeout=timeout)
        token = CancelToken(name="liveloop.role_turn")
        deadline = Deadline.after(
            min(max(float(timeout), 0.2), 15.0), owner="liveloop", step="role_turn"
        )
        deadline.throw_if_exceeded()
        if token.is_cancelled():
            raise LiveLoopError(_bilingual("turn was cancelled", "نوبت لغو شد"))
        if not live:
            briefing["live"] = False
            briefing["live_reason"] = _bilingual(
                "local briefing; live hosted turn was not requested",
                "خلاصهٔ محلی؛ نوبت زنده درخواست نشد",
            )
            return briefing
        if os.environ.get("DREAM_ALLOW_NETWORK", "").strip().lower() not in _LIVE_ON:
            raise LiveLoopSecurityError(
                _bilingual(
                    "live role turns need DREAM_ALLOW_NETWORK and a configured key",
                    "نوبت زنده نیاز به DREAM_ALLOW_NETWORK و کلید پیکربندی‌شده دارد",
                )
            )
        key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DREAM_LIVELOOP_KEY") or ""
        if not key or key.startswith("sk_EXAMPLE"):
            raise LiveLoopSecurityError(
                _bilingual(
                    "live role turns refuse to run without a real owner key",
                    "نوبت زنده بدون کلید واقعی مالک اجرا نمی‌شود",
                )
            )
        raise LiveLoopSecurityError(
            _bilingual(
                "live hosted completion is not wired in this cut; use the chat pane",
                "تکمیل میزبان در این برش سیم‌کشی نشده؛ از پنل چت استفاده کنید",
            )
        )

    def role_catalog(self, space_id: str) -> dict[str, Any]:
        record = self.spaces.get(space_id)
        ceiling = record.get("ceiling") or "guarded"
        roles = []
        for role in record.get("roles") or []:
            try:
                full = get_role(role["role_id"])
            except KeyError:
                continue
            roles.append(
                {
                    **full,
                    "effective_ceiling": clamp_ceiling(ceiling, full["risk_ceiling"]),
                }
            )
        return {"space_id": space_id, "ceiling": ceiling, "roles": roles}


_service: LiveLoopService | None = None
_lock = threading.Lock()


def get_service() -> LiveLoopService:
    global _service
    with _lock:
        if _service is None:
            _service = LiveLoopService()
        return _service


def reset_service(service: LiveLoopService | None = None) -> LiveLoopService | None:
    global _service
    with _lock:
        _service = service
        return _service
