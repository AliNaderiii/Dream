from __future__ import annotations

from pathlib import Path

import pytest

from dream.space.service import SpaceService
from dream.space.store import SpaceStore
from dream.workroom.errors import WorkroomError, WorkroomSecurityError
from dream.workroom.service import WorkroomService
from dream.workroom.store import WorkroomStore


@pytest.fixture()
def runtime(tmp_path: Path) -> WorkroomService:
    spaces = SpaceService(SpaceStore(tmp_path / "spaces.json"))
    return WorkroomService(store=WorkroomStore(tmp_path / "workroom.json"), spaces=spaces)


def test_room_isolates_memory_and_never_sends(runtime: WorkroomService) -> None:
    room = runtime.create("Studio Co")
    assert room["mode"] == "company"
    assert room["yolo"] is False
    assert room["chrome_profile"] is False
    assert room["computer_use"] is False
    assert room["sends"] is False
    assert room["memory_user"].startswith("workroom:")
    seat = runtime.add_seat(room["room_id"], "Leila", role_id="manager", vip=True)
    assert seat["vip"] is True
    assert seat["can_send"] is False
    assert seat["memory_user"] != room["memory_user"]
    draft = runtime.draft(room["room_id"], "Please ship the weekly report.")
    assert draft["status"] == "APPROVAL_PENDING"
    assert draft["sent"] is False
    with pytest.raises(WorkroomSecurityError, match="approver"):
        runtime.approve(draft["draft_id"], approved=False)
    ready = runtime.approve(draft["draft_id"], approved=True)
    assert ready["status"] == "ready"
    assert ready["sent"] is False


def test_seat_cap_and_unknown_role(runtime: WorkroomService) -> None:
    room = runtime.create("Cap")
    with pytest.raises(WorkroomError, match="unknown"):
        runtime.add_seat(room["room_id"], "X", role_id="admin")
    for index in range(8):
        runtime.add_seat(room["room_id"], f"Seat {index}")
    with pytest.raises(WorkroomError, match="seat limit"):
        runtime.add_seat(room["room_id"], "Extra")
