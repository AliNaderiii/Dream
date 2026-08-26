from __future__ import annotations

from pathlib import Path

import pytest

from dream.bridge import methods_liveloop
from dream.bridge.errors import INVALID_PARAMS, BridgeError
from dream.bridge.extensions import Registry
from dream.liveloop.honesty import snapshot
from dream.liveloop.service import LiveLoopService
from dream.memory import MemoryStore
from dream.scheduler import get_schedule
from dream.space.service import SpaceService
from dream.space.store import SpaceStore


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LiveLoopService:
    monkeypatch.setenv("DREAM_SPACE_STORE", str(tmp_path / "spaces.json"))
    monkeypatch.setenv("DREAM_LIVELOOP_DB", str(tmp_path / "loop.db"))
    monkeypatch.delenv("DREAM_ALLOW_NETWORK", raising=False)
    spaces = SpaceService(SpaceStore(tmp_path / "spaces.json"))
    store = MemoryStore(str(tmp_path / "loop.db"))
    return LiveLoopService(spaces=spaces, store=store)


def test_honesty_flags_echo_bar_versus_hosted_pane() -> None:
    honest = snapshot(bar_provider="echo", pane_provider="echo")
    assert honest["mismatch"] is False
    split = snapshot(
        bar_provider="Echo (offline)",
        pane_provider="vllm-605bde5f",
        pane_model="qwen3.6-35b",
    )
    assert split["mismatch"] is True
    assert split["honest"] is False
    assert "not the pane" in split["note_en"]


def test_arm_approved_draft(runtime: LiveLoopService, tmp_path: Path) -> None:
    doc = tmp_path / "how.md"
    doc.write_text("Stay local.\n", encoding="utf-8")
    space = runtime.spaces.create("Studio")
    runtime.spaces.set_instruction(space["space_id"], path=str(doc))
    draft = runtime.spaces.propose_draft(space["space_id"], "every day at 9 AM")
    runtime.spaces.approve_draft(draft["draft_id"])
    armed = runtime.arm_draft(draft["draft_id"], approved=True)
    assert armed["armed"] is True
    assert armed["spawned"] is False
    assert armed["require_approval"] is True
    assert armed["schedule"]["cron_expression"] == "0 9 * * *"
    stored = get_schedule(runtime.store, armed["schedule"]["schedule_id"])
    assert stored is not None
    assert stored.require_approval is True


def test_arm_refuses_unapproved_and_dangerous(runtime: LiveLoopService) -> None:
    space = runtime.spaces.create("No")
    pending = runtime.spaces.propose_draft(space["space_id"], "every day at 8 AM")
    with pytest.raises(Exception, match="not approved"):
        runtime.arm_draft(pending["draft_id"], approved=True)
    bad = runtime.spaces.propose_draft(space["space_id"], "every day at 9 AM !rm -rf /")
    runtime.spaces.approve_draft(bad["draft_id"])
    with pytest.raises(Exception, match="never scheduled"):
        runtime.arm_draft(bad["draft_id"], approved=True)


def test_role_turn_local_and_live_fail_closed(runtime: LiveLoopService, tmp_path: Path) -> None:
    doc = tmp_path / "how.md"
    doc.write_text("Outcome: a brief.\nConstraints: never send mail.\n", encoding="utf-8")
    space = runtime.spaces.create("Mail")
    runtime.spaces.set_instruction(space["space_id"], path=str(doc))
    turn = runtime.role_turn(space["space_id"], "secretary", "What is the constraint?")
    assert turn["live"] is False
    assert turn["hosted"] is False
    assert "never send mail" in turn["answer"]
    with pytest.raises(Exception, match="DREAM_ALLOW_NETWORK"):
        runtime.role_turn(space["space_id"], "secretary", "Go live", live=True)


def test_bridge_handlers(runtime: LiveLoopService, monkeypatch: pytest.MonkeyPatch) -> None:
    from dream.liveloop import service as module

    monkeypatch.setattr(module, "_service", runtime)
    methods_liveloop.reset_service(runtime)
    shot = methods_liveloop.liveloop_route_snapshot(
        {"bar_provider": "echo", "pane_provider": "earth"}
    )
    assert shot["mismatch"] is True
    with pytest.raises(BridgeError) as raised:
        methods_liveloop.liveloop_arm_draft({"draft_id": "missing", "approved": True})
    assert raised.value.code == INVALID_PARAMS
    assert "liveloop.arm_draft" in Registry.merged_handlers()
