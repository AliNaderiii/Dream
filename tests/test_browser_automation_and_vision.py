"""Tests for Multi-Provider Browser Automation, DOM Parsing & Vision subsystem."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dream.browser import (
    BrowserBackendType,
    BrowserEngine,
    DOMParser,
    browser_click,
    browser_close,
    browser_extract_content,
    browser_get_status,
    browser_navigate,
    browser_screenshot,
    browser_type,
    get_browser_tools,
    handle_browser_command,
    reset_global_browser_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_dom_parser_cleaning_and_elements():
    parser = DOMParser()
    sample_html = """
    <html>
      <head><script>alert('xss');</script><style>.hidden{display:none;}</style></head>
      <body>
        <h1>Documentation Portal</h1>
        <p>Welcome to the <b>Dream</b> developer platform.</p>
        <a href="https://example.com/docs">Read Docs</a>
        <button id="btn_submit">Submit Feedback</button>
        <input name="search_q" type="text" placeholder="Search..." />
      </body>
    </html>
    """

    cleaned = parser.clean_html(sample_html)
    assert "<script>" not in cleaned
    assert "<style>" not in cleaned
    assert "Documentation Portal" in cleaned

    md = parser.html_to_semantic_markdown(sample_html)
    assert "# Documentation Portal" in md
    assert "Welcome to the Dream developer platform." in md

    elements = parser.extract_interactive_elements(sample_html)
    assert len(elements) == 3

    tags = [e.tag_name for e in elements]
    assert "a" in tags
    assert "button" in tags
    assert "input" in tags


def test_browser_engine_navigation_and_actions():
    engine = BrowserEngine(backend_type=BrowserBackendType.MOCK)
    assert engine.is_active is True

    snapshot = engine.navigate("https://python.org")
    assert snapshot.status_code == 200
    assert "Python.org" in snapshot.title
    assert len(snapshot.elements) >= 3

    # Click action
    click_res = engine.click("button")
    assert click_res["success"] is True

    # Type action
    type_res = engine.type_text("input[name='q']", "fastapi")
    assert type_res["success"] is True

    # Extract content
    snap2 = engine.extract_content()
    assert snap2.url == "https://python.org"


def test_browser_screenshot_and_close():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = BrowserEngine(backend_type=BrowserBackendType.MOCK)
        engine.navigate("https://example.com")

        shot_path = Path(tmpdir) / "test_shot.png"
        res_path = engine.take_screenshot(str(shot_path))
        assert Path(res_path).exists()
        assert Path(res_path).stat().st_size > 0

        assert engine.close() is True
        assert engine.is_active is False


def test_browser_security_blocklist():
    engine = BrowserEngine(blocklist={"malware.example", "bad-site.org"})
    blocked_snap = engine.navigate("https://malware.example/login")
    assert blocked_snap.status_code == 403
    assert "Blocked by Security Policy" in blocked_snap.title


def test_browser_tools_and_slash():
    reset_global_browser_engine()
    tools = get_browser_tools()
    assert len(tools) == 7

    nav_data = browser_navigate("https://docs.dream.ai")
    assert nav_data["status_code"] == 200

    clk = browser_click("button")
    assert clk["success"] is True

    typ = browser_type("input", "hello")
    assert typ["success"] is True

    ext = browser_extract_content()
    assert "docs.dream.ai" in ext["url"]

    stat = browser_get_status()
    assert stat["is_active"] is True

    with tempfile.TemporaryDirectory() as tmpdir:
        sp = str(Path(tmpdir) / "shot.png")
        shot_res = browser_screenshot(sp)
        assert shot_res["success"] is True
        assert Path(shot_res["screenshot_path"]).exists()

    cls_res = browser_close()
    assert cls_res["success"] is True

    # Slash command tests
    lines = []
    handle_browser_command("/browser status", output=lines.append)
    assert any("BROWSER" in line or "MOCK" in line for line in lines)

    lines.clear()
    handle_browser_command("/browser open https://example.com", output=lines.append)
    assert any("example.com" in line for line in lines)

    reset_global_browser_engine()


def test_toolset_includes_browser():
    assert "browser" in BUILTIN_TOOLSETS
    toolset = get_toolset("browser")
    assert toolset is not None
    assert len(toolset.tools) >= 7
    assert "browser_navigate" in toolset.tools
    assert "browser_screenshot" in toolset.tools
