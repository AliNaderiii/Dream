from __future__ import annotations

import json

from dream.store.sessions import SessionStore


def test_session_crud_search_and_restore(tmp_path):
    path = tmp_path / "sessions.db"
    store = SessionStore(path)
    session = store.create("Persian research", model_provider="echo")
    store.add_message(session.id, "user", "سلام دنیا")
    store.add_message(session.id, "assistant", "Hello world")
    assert store.get(session.id).message_count == 2
    rows, total = store.list(search="سلام")
    assert total == 1 and rows[0].id == session.id
    store.update(session.id, name="Renamed", is_archived=True)
    assert store.list(archived=True)[0][0].name == "Renamed"
    store.close()

    restored = SessionStore(path)
    assert restored.get(session.id).message_count == 2
    assert [message.role for message in restored.messages(session.id)] == ["user", "assistant"]
    restored.close()


def test_exports_are_valid_and_html_is_escaped(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    session = store.create("Export")
    store.add_message(session.id, "user", "<script>alert(1)</script>")
    body, mime, name = store.export(session.id, "json")
    assert json.loads(body)["version"] == 1
    assert mime == "application/json" and name.endswith(".json")
    markdown, _, _ = store.export(session.id, "markdown")
    assert "## User" in markdown
    page, _, _ = store.export(session.id, "html")
    assert "<script>" not in page and "&lt;script&gt;" in page


def test_delete_cascades_messages(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    session = store.create("Delete me")
    store.add_message(session.id, "user", "hello")
    assert store.delete(session.id)
    assert store.messages(session.id) == []
