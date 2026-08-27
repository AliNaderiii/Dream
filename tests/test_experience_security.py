from __future__ import annotations

from pathlib import Path

import pytest

from dream import tools
from dream.bots.service import BotService
from dream.bots.store import BotStore
from dream.experience.service import ExperienceService
from dream.experience.store import ExperienceStore
from dream.space.service import SpaceService
from dream.space.store import SpaceStore


def test_deny_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setenv("DREAM_SKILLS_DB", str(tmp_path / "skills-ledger.db"))
    spaces = SpaceService(SpaceStore(tmp_path / "spaces.json"))
    bots = BotService(
        store=BotStore(tmp_path / "bots.json"),
        spaces=spaces,
        memory_path=str(tmp_path / "mem.db"),
    )
    space = spaces.create("Safe")
    bot = bots.create(space["space_id"], "Guard", role_id="security")
    bots.set_instruction(bot["bot_id"], "Audit only.")
    service = ExperienceService(store=ExperienceStore(tmp_path / "exp.json"), bots=bots)
    draft = service.capture(bot["bot_id"], "What was refused?")
    denied = service.deny(draft["draft_id"])
    assert denied["status"] == "denied"
    skills = tmp_path / "skills"
    assert not skills.exists() or list(skills.glob("*.md")) == []
