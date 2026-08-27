"""Stage a skill from a bot turn. Writes only after owner approval."""

from __future__ import annotations

import re
import threading
import uuid
from typing import Any

from dream.bots.errors import BotError
from dream.bots.service import BotService
from dream.bots.service import get_service as bot_service
from dream.experience.errors import ExperienceError, ExperienceSecurityError
from dream.experience.store import ExperienceStore, now
from dream.security.injection import scan_text
from dream.skills import save_skill_md

_SERVICE: ExperienceService | None = None
_LOCK = threading.Lock()


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return (slug or "session-procedure")[:64]


class ExperienceService:
    def __init__(
        self,
        store: ExperienceStore | None = None,
        bots: BotService | None = None,
    ) -> None:
        self.store = store or ExperienceStore()
        self.bots = bots or bot_service()

    def capture(
        self,
        bot_id: str,
        question: str,
        *,
        yolo: bool = False,
    ) -> dict[str, Any]:
        if yolo:
            raise ExperienceSecurityError(
                _bilingual(
                    "YOLO cannot auto-write skills from experience",
                    "YOLO نمی‌تواند مهارت را از تجربه خودکار بنویسد",
                )
            )
        try:
            bot = self.bots.get(bot_id)
        except BotError as exc:
            raise ExperienceError(str(exc)) from exc
        prompt = (question or "").strip()
        if not prompt or len(prompt) > 4_000:
            raise ExperienceError(
                _bilingual(
                    "question must be a non-empty string of at most 4000 characters",
                    "پرسش باید رشته‌ای غیرخالی حداکثر ۴۰۰۰ نویسه باشد",
                )
            )
        briefing = self.bots.ask(bot_id, prompt)
        excerpt = str(briefing.get("answer") or "")[:800]
        body = (
            "## Purpose\n\n"
            f"Reusable steps for {bot['name']}.\n\n"
            "## Instructions\n\n"
            "1. Restate the goal in one sentence.\n"
            "2. Stay inside the bot instruction.\n"
            "3. Never send mail or run YOLO.\n\n"
            f"## Source question\n\n{prompt}\n\n"
            f"## Briefing\n\n{excerpt}\n"
        )
        report = scan_text(body)
        if any(finding.kind == "instruction_override" for finding in report.findings):
            raise ExperienceSecurityError(
                _bilingual(
                    "experience text looks like a prompt injection",
                    "متن تجربه شبیه تزریق پرامپت است",
                )
            )
        record = {
            "draft_id": f"exp_{uuid.uuid4().hex[:12]}",
            "bot_id": bot_id,
            "name": _slug(bot["name"]),
            "description": f"Procedure captured from {bot['name']}.",
            "body": report.sanitized,
            "status": "APPROVAL_PENDING",
            "yolo": False,
            "created_at": now(),
        }
        return self.store.put(record)

    def list(self, bot_id: str | None = None) -> dict[str, Any]:
        rows = self.store.list(bot_id)
        return {"drafts": rows, "count": len(rows)}

    def approve(self, draft_id: str, *, approved: bool = False) -> dict[str, Any]:
        if not approved:
            raise ExperienceSecurityError(
                _bilingual("missing approver — refuse", "تأییدکننده نیست — رد شد")
            )
        record = self.store.pop(draft_id)
        filename = save_skill_md(record["name"], record["description"], record["body"])
        return {
            "applied": True,
            "draft_id": draft_id,
            "name": record["name"],
            "filename": filename,
            "status": "created",
        }

    def deny(self, draft_id: str) -> dict[str, Any]:
        record = self.store.pop(draft_id)
        return {"applied": False, "draft_id": draft_id, "name": record["name"], "status": "denied"}


def get_service() -> ExperienceService:
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:
            _SERVICE = ExperienceService()
        return _SERVICE


def reset_service(service: ExperienceService | None = None) -> ExperienceService | None:
    global _SERVICE
    with _LOCK:
        _SERVICE = service
        return _SERVICE
