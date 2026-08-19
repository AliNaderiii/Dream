"""RPC surface for ``project.*`` and ``approval.list`` (S06).

A project is a folder-like grouping of sessions — never a CRM record — so
the tests pin the semantics that matter: deleting a project ungroups its
sessions without touching them, a session belongs to one project at a time,
and the index survives a sidecar restart like the sessions index does.
"""

from __future__ import annotations

import asyncio
import pathlib
import tempfile
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore


def make_methods(**kwargs: Any) -> BridgeMethods:
    store = MemoryStore(":memory:")
    return BridgeMethods(
        store,
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        projects_path=tempfile.mktemp(suffix=".json"),
        default_provider="echo",
        **kwargs,
    )


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# ============================================================== project.create


def test_create_returns_a_project_with_a_stable_shape() -> None:
    m = make_methods()
    project = m.project_create({"name": "Thesis", "folder": "/home/ali/thesis"})
    assert project["project_id"].startswith("prj_")
    assert project["id"] == project["project_id"]
    assert project["name"] == "Thesis"
    assert project["folder"] == "/home/ali/thesis"
    assert project["session_ids"] == []
    assert project["created_at"] > 0


def test_create_strips_names_and_accepts_a_missing_folder() -> None:
    m = make_methods()
    project = m.project_create({"name": "  Inbox  "})
    assert project["name"] == "Inbox"
    assert project["folder"] is None


@pytest.mark.parametrize("params", [{}, {"name": ""}, {"name": "   "}, {"name": 7}])
def test_create_requires_a_name(params: dict[str, Any]) -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="name"):
        m.project_create(params)


def test_create_rejects_a_blank_folder() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="folder"):
        m.project_create({"name": "P", "folder": "   "})


def test_create_deduplicates_session_ids() -> None:
    m = make_methods()
    session = m.session_create({"title": "kick-off"})
    sid = session["session_id"]
    project = m.project_create({"name": "P", "session_ids": [sid, sid]})
    assert project["session_ids"] == [sid]


def test_create_rejects_malformed_session_ids() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="session_ids"):
        m.project_create({"name": "P", "session_ids": "not-a-list"})
    with pytest.raises(BridgeError, match="session_ids"):
        m.project_create({"name": "P", "session_ids": ["ok", ""]})


# =============================================================== list and get


def test_list_orders_by_recent_activity_and_get_joins_sessions() -> None:
    m = make_methods()
    session = m.session_create({"title": "notes"})
    first = m.project_create({"name": "Old"})
    second = m.project_create({"name": "New"})
    m.project_add_session({"project_id": second["project_id"], "session_id": session["session_id"]})

    listed = m.project_list()["projects"]
    assert [p["name"] for p in listed] == ["New", "Old"]
    assert listed[1]["project_id"] == first["project_id"]

    fetched = m.project_get({"project_id": second["project_id"]})
    assert fetched["session_ids"] == [session["session_id"]]
    assert [s["title"] for s in fetched["sessions"]] == ["notes"]


def test_get_drops_sessions_that_no_longer_exist() -> None:
    m = make_methods()
    session = m.session_create({"title": "temp"})
    project = m.project_create({"name": "P", "session_ids": [session["session_id"]]})
    m.session_delete({"session_id": session["session_id"]})
    fetched = m.project_get({"project_id": project["project_id"]})
    assert fetched["session_ids"] == [session["session_id"]]
    assert fetched["sessions"] == []


@pytest.mark.parametrize(
    "method", ["project_get", "project_update", "project_delete", "project_add_session"]
)
def test_unknown_project_id_is_invalid_params(method: str) -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="no project with id"):
        getattr(m, method)({"project_id": "prj_nope"})


def test_missing_project_id_is_rejected() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="project_id"):
        m.project_get({})


# ===================================================================== update


def test_update_renames_and_changes_the_folder() -> None:
    m = make_methods()
    project = m.project_create({"name": "Draft", "folder": "/tmp/a"})
    updated = m.project_update(
        {"project_id": project["project_id"], "name": "Final", "folder": "/tmp/b"}
    )
    assert updated["name"] == "Final"
    assert updated["folder"] == "/tmp/b"


def test_update_clears_the_folder_with_null_or_blank() -> None:
    m = make_methods()
    project = m.project_create({"name": "P", "folder": "/tmp/a"})
    cleared = m.project_update({"project_id": project["project_id"], "folder": None})
    assert cleared["folder"] is None
    m.project_update({"project_id": project["project_id"], "folder": "/tmp/c"})
    blanked = m.project_update({"project_id": project["project_id"], "folder": "  "})
    assert blanked["folder"] is None


def test_update_rejects_a_blank_name() -> None:
    m = make_methods()
    project = m.project_create({"name": "P"})
    with pytest.raises(BridgeError, match="name"):
        m.project_update({"project_id": project["project_id"], "name": "   "})


# ===================================================================== delete


def test_delete_ungroups_but_keeps_the_sessions() -> None:
    m = make_methods()
    session = m.session_create({"title": "keeper"})
    project = m.project_create({"name": "P", "session_ids": [session["session_id"]]})
    outcome = m.project_delete({"project_id": project["project_id"]})
    assert outcome == {"deleted": True, "project_id": project["project_id"]}
    assert m.project_list()["projects"] == []
    # The session itself is untouched — a folder delete never destroys work.
    assert m.session_get({"session_id": session["session_id"]})["title"] == "keeper"


# ==================================================================== sessions


def test_add_session_moves_it_out_of_any_other_project() -> None:
    m = make_methods()
    session = m.session_create({"title": "shared"})
    sid = session["session_id"]
    first = m.project_create({"name": "First", "session_ids": [sid]})
    second = m.project_create({"name": "Second"})

    m.project_add_session({"project_id": second["project_id"], "session_id": sid})
    assert m.project_get({"project_id": second["project_id"]})["session_ids"] == [sid]
    assert m.project_get({"project_id": first["project_id"]})["session_ids"] == []


def test_add_session_is_idempotent() -> None:
    m = make_methods()
    session = m.session_create({"title": "s"})
    project = m.project_create({"name": "P"})
    for _ in range(2):
        m.project_add_session(
            {"project_id": project["project_id"], "session_id": session["session_id"]}
        )
    assert m.project_get({"project_id": project["project_id"]})["session_ids"] == [
        session["session_id"]
    ]


def test_add_session_requires_a_known_session() -> None:
    m = make_methods()
    project = m.project_create({"name": "P"})
    with pytest.raises(BridgeError, match="no session with id"):
        m.project_add_session({"project_id": project["project_id"], "session_id": "sess_nope"})
    with pytest.raises(BridgeError, match="session_id"):
        m.project_add_session({"project_id": project["project_id"], "session_id": ""})


def test_remove_session_leaves_the_session_alive() -> None:
    m = make_methods()
    session = m.session_create({"title": "s"})
    project = m.project_create({"name": "P", "session_ids": [session["session_id"]]})
    updated = m.project_remove_session(
        {"project_id": project["project_id"], "session_id": session["session_id"]}
    )
    assert updated["session_ids"] == []
    assert m.session_get({"session_id": session["session_id"]}) is not None
    # Removing an absent session is a quiet no-op, not an error.
    again = m.project_remove_session(
        {"project_id": project["project_id"], "session_id": session["session_id"]}
    )
    assert again["session_ids"] == []


# ================================================================ persistence


def test_projects_persist_across_a_restart() -> None:
    base = pathlib.Path(tempfile.mkdtemp())
    sessions = str(base / "sessions.json")
    providers = str(base / "providers.json")
    projects = str(base / "projects.json")

    first = BridgeMethods(
        MemoryStore(str(base / "bridge.db")),
        sessions_path=sessions,
        providers_path=providers,
        projects_path=projects,
    )
    session = first.session_create({"title": "kept"})
    created = first.project_create(
        {
            "name": "Persistent",
            "folder": "/work/persistent",
            "session_ids": [session["session_id"]],
        }
    )
    first.shutdown()

    second = BridgeMethods(
        MemoryStore(str(base / "bridge.db")),
        sessions_path=sessions,
        providers_path=providers,
        projects_path=projects,
    )
    fetched = second.project_get({"project_id": created["project_id"]})
    assert fetched["name"] == "Persistent"
    assert fetched["folder"] == "/work/persistent"
    assert fetched["session_ids"] == [session["session_id"]]
    second.shutdown()


# ================================================================ approval.list


def test_approval_list_shows_pending_schedule_approvals() -> None:
    m = make_methods()
    created = m.schedule_create(
        {
            "name": "Risky",
            "prompt": "delete everything",
            "cron_expression": "0 3 * * *",
            "require_approval": True,
        }
    )

    async def scenario() -> Any:
        task = asyncio.get_event_loop().create_task(
            m.schedule_run_now({"schedule_id": created["schedule_id"]})
        )
        for _ in range(200):
            pending = m.approval_list()["approvals"]
            if pending:
                break
            await asyncio.sleep(0.01)
        approvals = m.approval_list()["approvals"]
        assert len(approvals) == 1
        assert approvals[0]["name"] == "schedule.execute"
        assert approvals[0]["resolved"] is False
        m.schedule_approve({"approval_id": approvals[0]["approval_id"], "allowed": True})
        outcome = await task
        return approvals[0], outcome

    approval, outcome = run(scenario())
    assert outcome["run"]["status"] == "success"
    # Resolved approvals leave the queue unless explicitly requested.
    assert m.approval_list()["approvals"] == []
    resolved = m.approval_list({"include_resolved": True})["approvals"]
    assert [a["approval_id"] for a in resolved] == [approval["approval_id"]]
    assert resolved[0]["resolved"] is True
    assert resolved[0]["decision"] is True


def test_approval_list_is_empty_when_nothing_is_pending() -> None:
    m = make_methods()
    assert m.approval_list() == {"approvals": []}


# ============================================================== handler table


def test_every_s06_method_is_routable() -> None:
    m = make_methods()
    expected = {
        "project.create",
        "project.list",
        "project.get",
        "project.update",
        "project.delete",
        "project.add_session",
        "project.remove_session",
        "approval.list",
    }
    assert expected <= set(m.handlers)
