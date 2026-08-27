"""Turn-taking group of Space bots. Hard cap of three rounds. No YOLO."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from dream.bots.errors import BotError
from dream.bots.service import BotService
from dream.bots.service import get_service as bot_service
from dream.groups.errors import GroupError, GroupSecurityError
from dream.groups.store import GroupStore, now
from dream.security.injection import scan_text
from dream.space.errors import SpaceError
from dream.space.service import SpaceService
from dream.space.service import get_service as space_service

_MIN_BOTS = 2
_MAX_BOTS = 6
_MAX_ROUNDS = 3
_ANSWER_CAP = 2_000
_SERVICE: GroupService | None = None
_LOCK = threading.Lock()


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


def _normalize_answer(text: str) -> str:
    return " ".join(text.split()).casefold()


def _follow_up(question: str, transcript: list[dict[str, Any]]) -> str:
    tail = transcript[-3:]
    lines = [
        f"- {turn.get('name') or turn.get('bot_id')}: {str(turn.get('answer') or '')[:200]}"
        for turn in tail
    ]
    blob = f"{question}\n\nEarlier:\n" + "\n".join(lines)
    return blob[:4_000]


class GroupService:
    def __init__(
        self,
        store: GroupStore | None = None,
        bots: BotService | None = None,
        spaces: SpaceService | None = None,
    ) -> None:
        self.store = store or GroupStore()
        self.bots = bots or bot_service()
        self.spaces = spaces or space_service()

    def start(
        self,
        space_id: str,
        bot_ids: list[str],
        question: str,
        *,
        yolo: bool = False,
        max_rounds: int = _MAX_ROUNDS,
    ) -> dict[str, Any]:
        if yolo:
            raise GroupSecurityError(
                _bilingual(
                    "YOLO cannot run a bot group",
                    "YOLO نمی‌تواند گروه بات را اجرا کند",
                )
            )
        if isinstance(max_rounds, bool) or not isinstance(max_rounds, int):
            raise GroupError(
                _bilingual(
                    "max_rounds must be an integer",
                    "سقف راند باید عدد درست باشد",
                )
            )
        if max_rounds < 1:
            raise GroupError(
                _bilingual(
                    "max_rounds must be at least 1",
                    "سقف راند باید حداقل ۱ باشد",
                )
            )
        cap = min(max_rounds, _MAX_ROUNDS)
        ids = self._ids(bot_ids)
        try:
            space = self.spaces.get(space_id)
        except SpaceError as exc:
            raise GroupError(str(exc)) from exc
        prompt = (question or "").strip()
        if not prompt or len(prompt) > 4_000:
            raise GroupError(
                _bilingual(
                    "question must be a non-empty string of at most 4000 characters",
                    "پرسش باید رشته‌ای غیرخالی حداکثر ۴۰۰۰ نویسه باشد",
                )
            )
        report = scan_text(prompt)
        if any(finding.kind == "instruction_override" for finding in report.findings):
            raise GroupSecurityError(
                _bilingual(
                    "group question looks like a prompt injection",
                    "پرسش گروه شبیه تزریق پرامپت است",
                )
            )
        records: dict[str, dict[str, Any]] = {}
        for bot_id in ids:
            try:
                record = self.bots.get(bot_id)
            except BotError as exc:
                raise GroupError(str(exc)) from exc
            if record.get("space_id") != space["space_id"]:
                raise GroupSecurityError(
                    _bilingual(
                        "bots must belong to the same space",
                        "بات‌ها باید به یک فضا تعلق داشته باشند",
                    )
                )
            records[bot_id] = record
        transcript: list[dict[str, Any]] = []
        previous: dict[str, str] = {}
        stopped = "round_cap"
        rounds_used = 0
        for round_no in range(1, cap + 1):
            rounds_used = round_no
            repeated = False
            for bot_id in ids:
                ask_prompt = prompt if round_no == 1 else _follow_up(prompt, transcript)
                try:
                    briefing = self.bots.ask(bot_id, ask_prompt)
                except BotError as exc:
                    raise GroupError(str(exc)) from exc
                answer = str(briefing.get("answer") or "")[:_ANSWER_CAP]
                turn = {
                    "round": round_no,
                    "bot_id": bot_id,
                    "name": records[bot_id]["name"],
                    "answer": answer,
                    "hosted": False,
                }
                transcript.append(turn)
                norm = _normalize_answer(answer)
                if bot_id in previous and previous[bot_id] == norm:
                    repeated = True
                previous[bot_id] = norm
            if repeated:
                stopped = "repeat"
                break
        record = {
            "group_id": f"grp_{uuid.uuid4().hex[:12]}",
            "space_id": space["space_id"],
            "bot_ids": ids,
            "question": prompt,
            "rounds": rounds_used,
            "cap": _MAX_ROUNDS,
            "stopped": stopped,
            "yolo": False,
            "hosted": False,
            "transcript": transcript,
            "created_at": now(),
        }
        return self.store.put(record)

    def get(self, group_id: str) -> dict[str, Any]:
        return self.store.get(group_id)

    def list(self, space_id: str) -> dict[str, Any]:
        try:
            self.spaces.get(space_id)
        except SpaceError as exc:
            raise GroupError(str(exc)) from exc
        rows = []
        for row in self.store.list(space_id):
            item = dict(row)
            item.pop("transcript", None)
            rows.append(item)
        return {"groups": rows, "count": len(rows)}

    def _ids(self, bot_ids: list[str]) -> list[str]:
        if not isinstance(bot_ids, list):
            raise GroupError(
                _bilingual(
                    "bot_ids must be a list of 2 to 6 bot ids",
                    "شناسه بات‌ها باید فهرست ۲ تا ۶ مورد باشد",
                )
            )
        cleaned: list[str] = []
        for item in bot_ids:
            if not isinstance(item, str) or not item.strip() or len(item) > 80:
                raise GroupError(
                    _bilingual(
                        "bot_ids must be a list of 2 to 6 bot ids",
                        "شناسه بات‌ها باید فهرست ۲ تا ۶ مورد باشد",
                    )
                )
            cleaned.append(item.strip())
        if len(cleaned) < _MIN_BOTS or len(cleaned) > _MAX_BOTS:
            raise GroupError(
                _bilingual(
                    "bot_ids must be a list of 2 to 6 bot ids",
                    "شناسه بات‌ها باید فهرست ۲ تا ۶ مورد باشد",
                )
            )
        if len(set(cleaned)) != len(cleaned):
            raise GroupSecurityError(
                _bilingual(
                    "duplicate bot ids are refused",
                    "شناسه تکراری بات رد است",
                )
            )
        return cleaned


def get_service() -> GroupService:
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:
            _SERVICE = GroupService()
        return _SERVICE


def reset_service(service: GroupService | None = None) -> GroupService | None:
    global _SERVICE
    with _LOCK:
        _SERVICE = service
        return _SERVICE
