"""Company workroom. Drafts never send. YOLO and computer-use are refused."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from dream.security.injection import scan_text
from dream.space.errors import SpaceError
from dream.space.service import SpaceService
from dream.space.service import get_service as space_service
from dream.workroom.errors import WorkroomError, WorkroomSecurityError
from dream.workroom.store import WorkroomStore, now

_SEAT_ROLES = ("manager", "specialist", "warehouse", "reviewer")
_MAX_SEATS = 8
_MAX_DRAFTS = 20
_SERVICE: WorkroomService | None = None
_LOCK = threading.Lock()


def _bilingual(en: str, fa: str) -> str:
    return f"{en}\n{fa}"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class WorkroomService:
    def __init__(
        self,
        store: WorkroomStore | None = None,
        spaces: SpaceService | None = None,
    ) -> None:
        self.store = store or WorkroomStore()
        self.spaces = spaces or space_service()

    def create(
        self,
        name: str,
        *,
        space_id: str | None = None,
        yolo: bool = False,
    ) -> dict[str, Any]:
        if yolo:
            raise WorkroomSecurityError(
                _bilingual(
                    "YOLO cannot open a company workroom",
                    "YOLO نمی‌تواند اتاق کار باز کند",
                )
            )
        title = (name or "").strip()
        if not title or len(title) > 80:
            raise WorkroomError(
                _bilingual(
                    "name must be a non-empty string of at most 80 characters",
                    "نام باید رشته‌ای غیرخالی حداکثر ۸۰ نویسه باشد",
                )
            )
        bound = ""
        if space_id:
            try:
                bound = self.spaces.get(space_id)["space_id"]
            except SpaceError as exc:
                raise WorkroomError(str(exc)) from exc
        stamp = now()
        room_id = _new_id("wrm")
        record = {
            "room_id": room_id,
            "name": title,
            "space_id": bound,
            "mode": "company",
            "memory_user": f"workroom:{room_id}",
            "yolo": False,
            "chrome_profile": False,
            "computer_use": False,
            "sends": False,
            "created_at": stamp,
            "updated_at": stamp,
        }
        return self.store.put_room(record)

    def list(self) -> dict[str, Any]:
        rows = self.store.list_rooms()
        return {"rooms": rows, "count": len(rows), "roles": list(_SEAT_ROLES)}

    def get(self, room_id: str) -> dict[str, Any]:
        room = self.store.get_room(room_id)
        seats = self.store.list_seats(room_id)
        room["seats"] = seats
        room["vip_seats"] = sum(1 for seat in seats if seat.get("vip"))
        return room

    def add_seat(
        self,
        room_id: str,
        name: str,
        *,
        role_id: str = "specialist",
        vip: bool = False,
        yolo: bool = False,
    ) -> dict[str, Any]:
        if yolo:
            raise WorkroomSecurityError(
                _bilingual(
                    "YOLO cannot add workroom seats",
                    "YOLO نمی‌تواند صندلی اتاق کار اضافه کند",
                )
            )
        room = self.store.get_room(room_id)
        title = (name or "").strip()
        if not title or len(title) > 80:
            raise WorkroomError(
                _bilingual(
                    "seat name must be a non-empty string of at most 80 characters",
                    "نام صندلی باید رشته‌ای غیرخالی حداکثر ۸۰ نویسه باشد",
                )
            )
        role = (role_id or "specialist").strip().lower()
        if role not in _SEAT_ROLES:
            raise WorkroomError(
                _bilingual(f"unknown seat role {role!r}", f"نقش صندلی ناشناخته {role!r}")
            )
        if len(self.store.list_seats(room_id)) >= _MAX_SEATS:
            raise WorkroomError(
                _bilingual("seat limit reached (8).", "سقف صندلی پر شد (۸).")
            )
        stamp = now()
        seat_id = _new_id("seat")
        record = {
            "seat_id": seat_id,
            "room_id": room["room_id"],
            "name": title,
            "role_id": role,
            "vip": bool(vip),
            "memory_user": f"workroom:{room['room_id']}:seat:{seat_id}",
            "yolo": False,
            "chrome_profile": False,
            "computer_use": False,
            "can_send": False,
            "created_at": stamp,
        }
        saved = self.store.put_seat(record)
        room["updated_at"] = stamp
        self.store.put_room(room)
        return saved

    def list_seats(self, room_id: str) -> dict[str, Any]:
        self.store.get_room(room_id)
        rows = self.store.list_seats(room_id)
        vip_seats = sum(1 for row in rows if row.get("vip"))
        return {"seats": rows, "count": len(rows), "vip_seats": vip_seats}

    def draft(self, room_id: str, body: str, *, yolo: bool = False) -> dict[str, Any]:
        if yolo:
            raise WorkroomSecurityError(
                _bilingual(
                    "YOLO cannot write workroom drafts",
                    "YOLO نمی‌تواند پیشنویس اتاق کار بنویسد",
                )
            )
        self.store.get_room(room_id)
        text = (body or "").strip()
        if not text or len(text) > 4_000:
            raise WorkroomError(
                _bilingual(
                    "draft must be a non-empty string of at most 4000 characters",
                    "پیشنویس باید رشته‌ای غیرخالی حداکثر ۴۰۰۰ نویسه باشد",
                )
            )
        report = scan_text(text)
        if any(finding.kind == "instruction_override" for finding in report.findings):
            raise WorkroomSecurityError(
                _bilingual(
                    "draft looks like a prompt injection",
                    "پیشنویس شبیه تزریق پرامپت است",
                )
            )
        if len(self.store.list_drafts(room_id)) >= _MAX_DRAFTS:
            raise WorkroomError(
                _bilingual("workroom draft limit reached (20).", "سقف پیشنویس اتاق کار پر شد (۲۰).")
            )
        record = {
            "draft_id": _new_id("wrd"),
            "room_id": room_id,
            "body": report.sanitized[:4_000],
            "status": "APPROVAL_PENDING",
            "sent": False,
            "yolo": False,
            "chrome_profile": False,
            "computer_use": False,
            "created_at": now(),
        }
        return self.store.put_draft(record)

    def list_drafts(self, room_id: str) -> dict[str, Any]:
        self.store.get_room(room_id)
        rows = self.store.list_drafts(room_id)
        return {"drafts": rows, "count": len(rows)}

    def approve(self, draft_id: str, *, approved: bool = False) -> dict[str, Any]:
        if not approved:
            raise WorkroomSecurityError(
                _bilingual("missing approver — refuse", "تأییدکننده نیست — رد شد")
            )
        record = self.store.get_draft(draft_id)
        if record.get("status") != "APPROVAL_PENDING":
            raise WorkroomError(
                _bilingual(
                    "this draft is no longer pending",
                    "این پیشنویس دیگر در انتظار نیست",
                )
            )
        record["status"] = "ready"
        record["sent"] = False
        record["yolo"] = False
        return self.store.put_draft(record)

    def deny(self, draft_id: str) -> dict[str, Any]:
        self.store.pop_draft(draft_id)
        return {
            "applied": False,
            "draft_id": draft_id,
            "status": "denied",
            "sent": False,
            "yolo": False,
            "computer_use": False,
            "chrome_profile": False,
        }


def get_service() -> WorkroomService:
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:
            _SERVICE = WorkroomService()
        return _SERVICE


def reset_service(service: WorkroomService | None = None) -> WorkroomService | None:
    global _SERVICE
    with _LOCK:
        _SERVICE = service
        return _SERVICE
