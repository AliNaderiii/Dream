"""Named specialized agents: one job, one grant set, one risk ceiling.

These are catalog entries, not a new agent runtime. Council stays three-role
and opt-in in ``dream/council.py``. A role cannot widen grants above the
Space ceiling.
"""

from __future__ import annotations

from typing import Any

ROLES: dict[str, dict[str, Any]] = {
    "secretary": {
        "role_id": "secretary",
        "name_en": "Secretary",
        "name_fa": "منشی",
        "job_en": "Keep notes, recall profile facts, and answer scheduling questions.",
        "job_fa": "یادداشت، بازیابی نمایه، و پرسش‌های زمان‌بندی.",
        "tools": ("get_datetime", "remember_fact", "list_notes"),
        "risk_ceiling": "safe",
    },
    "research": {
        "role_id": "research",
        "name_en": "Research",
        "name_fa": "پژوهش",
        "job_en": (
            "Plan and summarise local research; "
            "no live web unless the owner enabled network."
        ),
        "job_fa": "برنامه و خلاصهٔ پژوهش محلی؛ وب زنده فقط با اجازهٔ شبکه.",
        "tools": ("get_datetime", "read_note", "list_notes"),
        "risk_ceiling": "guarded",
    },
    "data": {
        "role_id": "data",
        "name_en": "Data",
        "name_fa": "داده",
        "job_en": "Describe local tables honestly. Never evaluate model-authored code.",
        "job_fa": "توصیف صادقانهٔ جدول‌های محلی. هرگز کد مدل را اجرا نکن.",
        "tools": ("list_notes", "read_note", "calculate"),
        "risk_ceiling": "guarded",
    },
    "desk": {
        "role_id": "desk",
        "name_en": "Desk",
        "name_fa": "میزکار",
        "job_en": "Read files that are already attached to this Space. Never copy folders.",
        "job_fa": "خواندن فایل‌های پیوست همین فضا. هرگز پوشه را کپی نکن.",
        "tools": ("list_notes", "read_note"),
        "risk_ceiling": "safe",
    },
    "security": {
        "role_id": "security",
        "name_en": "Security",
        "name_fa": "امنیت",
        "job_en": "Audit drafts and refuse dangerous shell. Read-only.",
        "job_fa": "ممیزی پیشنویس‌ها و رد پوستهٔ خطرناک. فقط خواندنی.",
        "tools": ("get_datetime",),
        "risk_ceiling": "safe",
    },
}

CEILING_RANK = {"safe": 0, "guarded": 1, "dangerous": 2}


def list_roles() -> list[dict[str, Any]]:
    return [dict(row) for row in ROLES.values()]


def get_role(role_id: str) -> dict[str, Any]:
    key = (role_id or "").strip().lower()
    if key not in ROLES:
        raise KeyError(key)
    return dict(ROLES[key])


def clamp_ceiling(space_ceiling: str, role_ceiling: str) -> str:
    space_rank = CEILING_RANK.get(space_ceiling, 0)
    role_rank = CEILING_RANK.get(role_ceiling, 0)
    allowed = min(space_rank, role_rank)
    for name, rank in CEILING_RANK.items():
        if rank == allowed:
            return name
    return "safe"
