"""Create named Space bots with isolated memory. YOLO is refused."""

from __future__ import annotations

import os
import threading
import uuid
from typing import Any

from dream.bots.avatars import HUES, SHAPES, normalize_avatar
from dream.bots.errors import BotError, BotSecurityError
from dream.bots.store import BotStore, get_store, now, reset_store
from dream.memory import MemoryStore
from dream.security.injection import scan_text
from dream.space.catalog import get_role
from dream.space.service import SpaceService
from dream.space.service import get_service as space_service

_DOC_CAP = 8_000
_MEMORY_DB = os.environ.get("DREAM_BOTS_MEMORY_DB", "data/bots-memory.db")
_SERVICE: BotService | None = None
_LOCK = threading.Lock()


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


def _memory_text(row: Any) -> str:
    if isinstance(row, dict):
        value = row.get("content")
    else:
        value = getattr(row, "content", "")
    return value.strip() if isinstance(value, str) else ""


def _new_id() -> str:
    return f"bot_{uuid.uuid4().hex[:12]}"


class BotService:
    """Roster of persistent specialists bound to a Space."""

    def __init__(
        self,
        store: BotStore | None = None,
        spaces: SpaceService | None = None,
        memory_path: str | None = None,
    ) -> None:
        self.store = store or get_store()
        self.spaces = spaces or space_service()
        self.memory_path = memory_path or _MEMORY_DB

    def create(
        self,
        space_id: str,
        name: str,
        *,
        role_id: str = "secretary",
        model: str = "echo",
        shape: str | None = None,
        hue: str | None = None,
        yolo: bool = False,
    ) -> dict[str, Any]:
        if yolo:
            raise BotSecurityError(
                _bilingual(
                    "YOLO and Always Allow are refused for Space bots",
                    "YOLO و Always Allow برای بات‌های فضا رد است",
                )
            )
        space = self.spaces.get(space_id)
        title = (name or "").strip()
        if not title or len(title) > 80:
            raise BotError(
                _bilingual(
                    "name must be a non-empty string of at most 80 characters",
                    "نام باید رشته‌ای غیرخالی حداکثر ۸۰ نویسه باشد",
                )
            )
        try:
            role = get_role(role_id)
        except KeyError as exc:
            raise BotError(
                _bilingual(f"unknown role {role_id!r}", f"نقش ناشناخته {role_id!r}")
            ) from exc
        model_id = (model or "echo").strip()
        if not model_id or len(model_id) > 80 or "://" in model_id:
            raise BotSecurityError(
                _bilingual(
                    "model must be a short local id, not a URL",
                    "مدل باید شناسهٔ کوتاه محلی باشد، نه نشانی",
                )
            )
        stamp = now()
        record = {
            "bot_id": _new_id(),
            "space_id": space["space_id"],
            "name": title,
            "role_id": role["role_id"],
            "model": model_id,
            "avatar": normalize_avatar(shape, hue),
            "instruction": None,
            "memory_user": "",
            "yolo": False,
            "archived": False,
            "created_at": stamp,
            "updated_at": stamp,
        }
        record["memory_user"] = f"bot:{record['bot_id']}"
        return self.store.put(record)

    def list(self, space_id: str) -> dict[str, Any]:
        self.spaces.get(space_id)
        rows = self.store.list(space_id)
        return {"bots": rows, "count": len(rows), "shapes": list(SHAPES), "hues": list(HUES)}

    def get(self, bot_id: str) -> dict[str, Any]:
        return self.store.get(bot_id)

    def set_instruction(self, bot_id: str, text: str) -> dict[str, Any]:
        record = self.store.get(bot_id)
        body = (text or "").strip()
        if not body or len(body) > _DOC_CAP:
            raise BotError(
                _bilingual(
                    "instruction must be a non-empty string of at most 8000 characters",
                    "دستور باید رشته‌ای غیرخالی حداکثر ۸۰۰۰ نویسه باشد",
                )
            )
        report = scan_text(body)
        override = [
            finding for finding in report.findings if finding.kind == "instruction_override"
        ]
        if override:
            from dream.security.injection import guard_untrusted

            guard_untrusted(body, source=f"bot-instruction:{bot_id}")
            raise BotSecurityError(
                _bilingual(
                    "instruction looks like a prompt injection and was quarantined",
                    "دستور شبیه تزریق پرامپت است و قرنطینه شد",
                )
            )
        record["instruction"] = {
            "text": report.sanitized[:_DOC_CAP],
            "findings": [finding.kind for finding in report.findings],
        }
        record["updated_at"] = now()
        return self.store.put(record)

    def remember(self, bot_id: str, content: str) -> dict[str, Any]:
        record = self.store.get(bot_id)
        fact = (content or "").strip()
        if not fact or len(fact) > 2_000:
            raise BotError(
                _bilingual(
                    "memory must be a non-empty string of at most 2000 characters",
                    "حافظه باید رشته‌ای غیرخالی حداکثر ۲۰۰۰ نویسه باشد",
                )
            )
        memory = self._memory(record)
        entry = memory.remember(fact, kind="semantic")
        entry_id = entry.get("id") if isinstance(entry, dict) else getattr(entry, "id", None)
        return {
            "bot_id": bot_id,
            "memory_user": record["memory_user"],
            "stored": True,
            "id": entry_id,
        }

    def recall(self, bot_id: str, query: str) -> dict[str, Any]:
        record = self.store.get(bot_id)
        q = (query or "").strip()
        if not q or len(q) > 400:
            raise BotError(
                _bilingual(
                    "query must be a non-empty string of at most 400 characters",
                    "پرسش باید رشته‌ای غیرخالی حداکثر ۴۰۰ نویسه باشد",
                )
            )
        rows = self._memory(record).recall(q, limit=5)
        lines = [_memory_text(row) for row in rows]
        lines = [line for line in lines if line]
        return {"bot_id": bot_id, "memory_user": record["memory_user"], "hits": lines}

    def ask(self, bot_id: str, question: str) -> dict[str, Any]:
        record = self.store.get(bot_id)
        prompt = (question or "").strip()
        if not prompt or len(prompt) > 4_000:
            raise BotError(
                _bilingual(
                    "question must be a non-empty string of at most 4000 characters",
                    "پرسش باید رشته‌ای غیرخالی حداکثر ۴۰۰۰ نویسه باشد",
                )
            )
        instruction = ((record.get("instruction") or {}).get("text") or "").strip()
        if not instruction:
            raise BotError(
                _bilingual("this bot has no instruction yet", "این بات هنوز دستور ندارد")
            )
        role = get_role(record["role_id"])
        facts = [_memory_text(row) for row in self._memory(record).recall(prompt, limit=3)]
        facts = [item for item in facts if item]
        excerpt = "\n".join(line for line in instruction.splitlines() if line.strip())[:800]
        answer = (
            f"{record['name']} ({role['name_en']}) · model {record['model']}\n"
            "YOLO is off. This is a local briefing; no hosted model was called.\n"
            f"Question: {prompt}\n"
            f"Instruction:\n{excerpt}"
        )
        if facts:
            answer += "\nIsolated memory:\n" + "\n".join(f"- {item}" for item in facts)
        return {
            "bot_id": bot_id,
            "space_id": record["space_id"],
            "role_id": record["role_id"],
            "model": record["model"],
            "yolo": False,
            "hosted": False,
            "answer": answer,
        }

    def _memory(self, record: dict[str, Any]) -> MemoryStore:
        return MemoryStore(self.memory_path, user=str(record["memory_user"]))


def get_service() -> BotService:
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:
            _SERVICE = BotService()
        return _SERVICE


def reset_service(service: BotService | None = None) -> BotService | None:
    global _SERVICE
    with _LOCK:
        _SERVICE = service
        if service is None:
            reset_store(None)
        return _SERVICE
