from __future__ import annotations

from pathlib import Path

import pytest

from dream.bots.errors import BotSecurityError
from dream.bots.service import BotService
from dream.bots.store import BotStore
from dream.space.service import SpaceService
from dream.space.store import SpaceStore


@pytest.fixture()
def runtime(tmp_path: Path) -> BotService:
    spaces = SpaceService(SpaceStore(tmp_path / "spaces.json"))
    return BotService(
        store=BotStore(tmp_path / "bots.json"),
        spaces=spaces,
        memory_path=str(tmp_path / "mem.db"),
    )


def test_roster_isolates_memory_and_refuses_yolo(runtime: BotService) -> None:
    space = runtime.spaces.create("Studio")
    left = runtime.create(space["space_id"], "Scribe", role_id="secretary", hue="teal")
    right = runtime.create(space["space_id"], "Analyst", role_id="research", hue="amber")
    assert left["yolo"] is False
    assert left["memory_user"] != right["memory_user"]
    runtime.set_instruction(left["bot_id"], "Keep notes. Never send mail.")
    runtime.remember(left["bot_id"], "Owner prefers Tehran mornings.")
    hits = runtime.recall(left["bot_id"], "Tehran")
    assert any("Tehran" in item for item in hits["hits"])
    empty = runtime.recall(right["bot_id"], "Tehran")
    assert empty["hits"] == []
    with pytest.raises(BotSecurityError, match="YOLO"):
        runtime.create(space["space_id"], "Chaos", yolo=True)
