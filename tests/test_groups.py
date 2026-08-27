from __future__ import annotations

from pathlib import Path

import pytest

from dream.bots.service import BotService
from dream.bots.store import BotStore
from dream.groups.errors import GroupError
from dream.groups.service import GroupService
from dream.groups.store import GroupStore
from dream.space.service import SpaceService
from dream.space.store import SpaceStore


@pytest.fixture()
def runtime(tmp_path: Path) -> GroupService:
    spaces = SpaceService(SpaceStore(tmp_path / "spaces.json"))
    bots = BotService(
        store=BotStore(tmp_path / "bots.json"),
        spaces=spaces,
        memory_path=str(tmp_path / "mem.db"),
    )
    space = spaces.create("Studio")
    scribe = bots.create(space["space_id"], "Scribe", role_id="secretary")
    analyst = bots.create(space["space_id"], "Analyst", role_id="research")
    guard = bots.create(space["space_id"], "Guard", role_id="security")
    bots.set_instruction(scribe["bot_id"], "Keep notes. Never send mail.")
    bots.set_instruction(analyst["bot_id"], "Summarise only. Never send mail.")
    bots.set_instruction(guard["bot_id"], "Audit only. Never send mail.")
    service = GroupService(
        store=GroupStore(tmp_path / "groups.json"),
        bots=bots,
        spaces=spaces,
    )
    service._space_id = space["space_id"]  # type: ignore[attr-defined]
    service._roster = [scribe["bot_id"], analyst["bot_id"], guard["bot_id"]]  # type: ignore[attr-defined]
    return service


def test_group_runs_two_bots_and_caps_rounds(runtime: GroupService) -> None:
    space_id = runtime._space_id  # type: ignore[attr-defined]
    ids = runtime._roster[:2]  # type: ignore[attr-defined]
    run = runtime.start(space_id, ids, "How do we file the morning notes?")
    assert run["yolo"] is False
    assert run["hosted"] is False
    assert run["cap"] == 3
    assert run["rounds"] <= 3
    assert run["stopped"] in {"round_cap", "repeat"}
    assert 2 <= len(run["bot_ids"]) <= 6
    assert len(run["transcript"]) <= 3 * len(ids)
    assert all(turn["round"] <= 3 for turn in run["transcript"])
    listed = runtime.list(space_id)
    assert listed["count"] == 1
    assert "transcript" not in listed["groups"][0]
    fetched = runtime.get(run["group_id"])
    assert fetched["group_id"] == run["group_id"]


def test_size_and_round_overrides_are_clamped(runtime: GroupService) -> None:
    space_id = runtime._space_id  # type: ignore[attr-defined]
    ids = runtime._roster  # type: ignore[attr-defined]
    with pytest.raises(GroupError, match="2 to 6"):
        runtime.start(space_id, ids[:1], "Too few")
    with pytest.raises(GroupError, match="2 to 6"):
        runtime.start(
            space_id,
            ids + ["bot_extra_1", "bot_extra_2", "bot_extra_3", "bot_extra_4"],
            "Too many",
        )
    run = runtime.start(space_id, ids[:2], "Cap this", max_rounds=99)
    assert run["rounds"] <= 3
    assert run["cap"] == 3
