"""Company workroom: seats, HITL drafts, no send, no YOLO."""

from __future__ import annotations

from dream.workroom.service import WorkroomService, get_service, reset_service

__all__ = ["WorkroomService", "get_service", "reset_service"]
