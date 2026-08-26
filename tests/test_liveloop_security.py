from __future__ import annotations

from pathlib import Path

import pytest

from dream.liveloop.errors import LiveLoopSecurityError
from dream.liveloop.service import LiveLoopService
from dream.memory import MemoryStore
from dream.space.service import SpaceService
from dream.space.store import SpaceStore


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LiveLoopService:
    monkeypatch.setenv("DREAM_SPACE_STORE", str(tmp_path / "spaces.json"))
    monkeypatch.setenv("DREAM_LIVELOOP_DB", str(tmp_path / "loop.db"))
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk_EXAMPLE_not_a_real_key")
    spaces = SpaceService(SpaceStore(tmp_path / "spaces.json"))
    return LiveLoopService(spaces=spaces, store=MemoryStore(str(tmp_path / "loop.db")))


def test_live_turn_refuses_example_key(runtime: LiveLoopService, tmp_path: Path) -> None:
    doc = tmp_path / "how.md"
    doc.write_text("Be brief.\n", encoding="utf-8")
    space = runtime.spaces.create("Safe")
    runtime.spaces.set_instruction(space["space_id"], path=str(doc))
    with pytest.raises(LiveLoopSecurityError, match="real owner key"):
        runtime.role_turn(space["space_id"], "security", "Status?", live=True)


def test_arm_without_approver_flag(runtime: LiveLoopService) -> None:
    space = runtime.spaces.create("X")
    draft = runtime.spaces.propose_draft(space["space_id"], "every monday at 10:30")
    runtime.spaces.approve_draft(draft["draft_id"])
    with pytest.raises(LiveLoopSecurityError, match="missing approver"):
        runtime.arm_draft(draft["draft_id"], approved=False)
