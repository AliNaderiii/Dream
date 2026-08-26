from __future__ import annotations

from pathlib import Path

import pytest

from dream.bridge import methods_space
from dream.bridge.errors import INVALID_PARAMS, BridgeError
from dream.bridge.extensions import Registry
from dream.space.service import SpaceService
from dream.space.store import SpaceStore
from dream.workspace.service import WorkspaceService
from dream.workspace.service import reset_service as reset_workspace


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SpaceService:
    monkeypatch.setenv("DREAM_SPACE_STORE", str(tmp_path / "spaces.json"))
    monkeypatch.setenv("DREAM_INJECTION_QUARANTINE", str(tmp_path / "quarantine"))
    monkeypatch.delenv("DREAM_ALLOW_NETWORK", raising=False)
    workspace = WorkspaceService(
        registry_path=tmp_path / "ws.json", projects_path=tmp_path / "proj.json"
    )
    reset_workspace(workspace)
    service = SpaceService(SpaceStore(tmp_path / "spaces.json"))
    methods_space.reset_service(service)
    return service


def test_create_list_get_archive(runtime: SpaceService) -> None:
    created = runtime.create("Studio", language="fa")
    assert created["copied"] is False
    listed = runtime.list()
    assert listed["count"] == 1
    fetched = runtime.get(created["space_id"])
    assert fetched["name"] == "Studio"
    assert fetched["language"] == "fa"
    assert len(fetched["roles"]) == 5
    archived = runtime.archive(created["space_id"])
    assert archived["archived"] is True
    assert runtime.list()["count"] == 0


def test_attach_folder_in_place(runtime: SpaceService, tmp_path: Path) -> None:
    folder = tmp_path / "desk"
    folder.mkdir()
    (folder / "notes.md").write_text("hello", encoding="utf-8")
    space = runtime.create("Desk")
    attached = runtime.attach_folder(space["space_id"], str(folder))
    assert attached["copied"] is False
    assert attached["imported_in_place"] is True
    assert Path(attached["root"]["path"]) == folder.resolve()


def test_attach_refuses_parent_traversal(runtime: SpaceService) -> None:
    space = runtime.create("Nope")
    with pytest.raises(Exception, match="traversal"):
        runtime.attach_folder(space["space_id"], "../etc")


def test_instruction_and_local_ask(runtime: SpaceService, tmp_path: Path) -> None:
    doc = tmp_path / "how.md"
    doc.write_text("# How\nAlways confirm before sending mail.\n", encoding="utf-8")
    space = runtime.create("Mail")
    runtime.set_instruction(space["space_id"], path=str(doc))
    answer = runtime.ask(space["space_id"], "secretary", "What is the review point?")
    assert answer["hosted"] is False
    assert "confirm before sending" in answer["answer"]
    assert answer["role"]["effective_ceiling"] == "safe"


def test_nl_draft_pending_until_approve(runtime: SpaceService) -> None:
    space = runtime.create("Rhythm")
    draft = runtime.propose_draft(space["space_id"], "every day at 9 AM")
    assert draft["status"] == "APPROVAL_PENDING"
    assert draft["cron"] == "0 9 * * *"
    assert draft["fired"] is False
    with pytest.raises(Exception, match="not approved"):
        runtime.run_draft(draft["draft_id"], approved=True)
    approved = runtime.approve_draft(draft["draft_id"])
    assert approved["status"] == "APPROVED"
    ran = runtime.run_draft(draft["draft_id"], approved=True)
    assert ran["fired"] is False
    assert ran["spawned"] is False


def test_deny_stays_idle(runtime: SpaceService) -> None:
    space = runtime.create("Idle")
    draft = runtime.propose_draft(space["space_id"], "every monday at 10:30")
    denied = runtime.deny_draft(draft["draft_id"])
    assert denied["status"] == "DENIED"
    with pytest.raises(Exception, match="idle"):
        runtime.approve_draft(draft["draft_id"])
    with pytest.raises(Exception, match="not approved"):
        runtime.run_draft(draft["draft_id"], approved=True)


def test_persian_schedule_draft(runtime: SpaceService) -> None:
    space = runtime.create("صبح", language="fa")
    draft = runtime.propose_draft(space["space_id"], "هر روز ساعت ۹ صبح")
    assert draft["cron"] == "0 9 * * *"
    assert draft["status"] == "APPROVAL_PENDING"


def test_bridge_handlers_and_discovery(runtime: SpaceService) -> None:
    created = methods_space.space_create({"name": "Via RPC"})
    listed = methods_space.space_list({})
    assert any(row["space_id"] == created["space_id"] for row in listed["spaces"])
    catalog = methods_space.space_catalog({})
    assert catalog["count"] == 5
    with pytest.raises(BridgeError) as raised:
        methods_space.space_create({"name": ""})
    assert raised.value.code == INVALID_PARAMS
    handlers = Registry.merged_handlers()
    assert "space.create" in handlers
    assert "space.approve_draft" in handlers
