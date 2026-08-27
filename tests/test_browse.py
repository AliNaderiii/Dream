from __future__ import annotations

from pathlib import Path

import pytest

from dream import tools
from dream.browse.errors import BrowseError, BrowseSecurityError
from dream.browse.service import BrowseService
from dream.browse.store import BrowseStore


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BrowseService:
    monkeypatch.delenv("DREAM_ALLOW_NETWORK", raising=False)
    return BrowseService(store=BrowseStore(tmp_path / "browse.json"))


def test_propose_does_not_fetch_until_allow_once(
    runtime: BrowseService, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tools, "read_page", lambda url: calls.append(url) or "Title\nHello")
    monkeypatch.setattr(
        tools,
        "_open_network_request",
        lambda *_args, **_kwargs: calls.append("open"),
    )
    draft = runtime.propose("https://example.com/notes")
    assert draft["status"] == "APPROVAL_PENDING"
    assert draft["yolo"] is False
    assert draft["chrome_profile"] is False
    assert draft["computer_use"] is False
    assert draft["hosted_fetch"] is False
    assert calls == []
    with pytest.raises(BrowseSecurityError, match="approver"):
        runtime.approve(draft["draft_id"], approved=False)
    assert calls == []
    with pytest.raises(BrowseSecurityError, match="network"):
        runtime.approve(draft["draft_id"], approved=True)
    assert calls == []
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "true")
    fetched = runtime.approve(draft["draft_id"], approved=True)
    assert fetched["status"] == "fetched"
    assert fetched["hosted_fetch"] is True
    assert fetched["excerpt"].startswith("Title")
    assert calls == ["https://example.com/notes"]
    denied = runtime.propose("https://example.com/other")
    gone = runtime.deny(denied["draft_id"])
    assert gone["status"] == "denied"
    assert gone["hosted_fetch"] is False
    assert calls == ["https://example.com/notes"]


def test_follow_only_uses_extracted_public_links(
    runtime: BrowseService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DREAM_ALLOW_NETWORK", "true")
    monkeypatch.setattr(
        tools,
        "read_page",
        lambda url: "Guide\nSee https://example.com/next and http://127.0.0.1/secret",
    )
    draft = runtime.propose("https://example.com/start")
    fetched = runtime.approve(draft["draft_id"], approved=True)
    urls = [item["url"] for item in fetched["links"]]
    assert "https://example.com/next" in urls
    assert all("127.0.0.1" not in item for item in urls)
    with pytest.raises(BrowseSecurityError, match="extracted"):
        runtime.follow(fetched["draft_id"], "https://evil.example/phish")
    nxt = runtime.follow(fetched["draft_id"], "https://example.com/next")
    assert nxt["status"] == "APPROVAL_PENDING"
    with pytest.raises(BrowseError, match="followable"):
        runtime.follow(nxt["draft_id"], "https://example.com/next")
