from __future__ import annotations

from pathlib import Path

import pytest

from dream import tools
from dream.bots.service import BotService
from dream.bots.store import BotStore
from dream.experience.errors import ExperienceSecurityError
from dream.experience.service import ExperienceService
from dream.experience.store import ExperienceStore
from dream.space.service import SpaceService
from dream.space.store import SpaceStore


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ExperienceService:
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setenv("DREAM_SKILLS_DB", str(tmp_path / "skills-ledger.db"))
    spaces = SpaceService(SpaceStore(tmp_path / "spaces.json"))
    bots = BotService(
        store=BotStore(tmp_path / "bots.json"),
        spaces=spaces,
        memory_path=str(tmp_path / "mem.db"),
    )
    space = spaces.create("Studio")
    bot = bots.create(space["space_id"], "Scribe")
    bots.set_instruction(bot["bot_id"], "Keep notes. Never send mail.")
    service = ExperienceService(store=ExperienceStore(tmp_path / "exp.json"), bots=bots)
    service._bot_id = bot["bot_id"]  # type: ignore[attr-defined]
    return service


def test_capture_stays_pending_until_approve(runtime: ExperienceService, tmp_path: Path) -> None:
    bot_id = runtime._bot_id  # type: ignore[attr-defined]
    draft = runtime.capture(bot_id, "How do we file the morning notes?")
    assert draft["status"] == "APPROVAL_PENDING"
    assert draft["yolo"] is False
    before = list(tmp_path.rglob("SKILL.md"))
    with pytest.raises(ExperienceSecurityError, match="approver"):
        runtime.approve(draft["draft_id"], approved=False)
    applied = runtime.approve(draft["draft_id"], approved=True)
    assert applied["applied"] is True
    after = list(tmp_path.rglob("SKILL.md"))
    assert len(after) > len(before)


def test_yolo_cannot_write_skills(runtime: ExperienceService) -> None:
    bot_id = runtime._bot_id  # type: ignore[attr-defined]
    with pytest.raises(ExperienceSecurityError, match="YOLO"):
        runtime.capture(bot_id, "Anything", yolo=True)
