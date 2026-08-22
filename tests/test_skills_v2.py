"""Stage C — skills v2 runtime: format, registry, catalog, slash, approval.

Existing v1 ``.txt`` behaviour is pinned in ``test_skills.py`` and is not
re-specified here.  This file pins the upgrade: SKILL.md validation,
per-skill bilingual errors, cached bounded scan, progressive-disclosure
catalog, Hermes slash stacking, write-approval fail-closed, and the
version/use ledger.
"""

from __future__ import annotations

import json

import pytest

import cli
from dream import tools
from dream.agent import ApprovalPolicy, Dream, EchoBackend
from dream.memory import MemoryStore, normalize_fa
from dream.skills import (
    apply_slash_invocation,
    authoring_templates,
    delete_skill,
    edit_skill,
    load_skills,
    parse_slash_stack,
    render_skill_catalog,
    save_skill,
    save_skill_md,
    view_skill,
)
from dream.skills.format import (
    DESCRIPTION_MAX_CHARS,
    TEMPLATE_SECTIONS,
    SkillFormatError,
    parse_skill_md,
)
from dream.skills.registry import SKILL_CATALOG_BUDGET_CHARS
from dream.skills.store import reset_ledger_for_tests

# Distinctive body marker used by the token-cost test. Must never appear in
# a catalog line (name + description only).
BODY_MARKER = "UNIQUE_BODY_MARKER_xyzzynotincatalog"

OCR_NAME = "ocr-and-documents"
OCR_DESC = "Extract text and tables from PDFs."
OCR_BODY = (
    f"# ocr-and-documents\n\n"
    f"Read the document and extract the tables.\n\n"
    f"{BODY_MARKER}\n"
)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setenv("DREAM_SKILLS_DB", str(tmp_path / "skills-ledger.db"))
    reset_ledger_for_tests()
    from dream.skills.registry import mark_skills_dirty

    mark_skills_dirty()
    return tmp_path.resolve()


@pytest.fixture()
def store(tmp_path):
    memory = MemoryStore(str(tmp_path / "dream.db"))
    yield memory
    memory.close()


def _write_skill_md(root, name: str, description: str, body: str, folder: str | None = None):
    folder_name = folder if folder is not None else name
    directory = root / "skills" / folder_name
    directory.mkdir(parents=True, exist_ok=True)
    text = f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"
    (directory / "SKILL.md").write_text(text, encoding="utf-8")
    from dream.skills.registry import mark_skills_dirty

    mark_skills_dirty()
    return text


def _ok(payload: dict) -> dict:
    assert payload["status"] == "ok", payload
    return payload["result"]


def _error(payload: dict) -> dict:
    assert payload["status"] == "error", payload
    return payload["error"]


def _contains_both_languages(text: str) -> None:
    assert any("\u0600" <= char <= "\u06ff" for char in text)
    assert any("a" <= char.lower() <= "z" for char in text)


# --------------------------------------------------------------------------
# C-1 Format, templates, per-skill errors, collisions, unsafe names.
# --------------------------------------------------------------------------


def test_valid_skill_md_loads_and_keeps_legacy_txt(workspace):
    save_skill("tea-legacy", "when the user asks about tea brewing", ["boil water"])
    _write_skill_md(workspace, OCR_NAME, OCR_DESC, OCR_BODY)
    loaded, problems = load_skills()
    assert problems == []
    names = sorted(skill.name for skill in loaded)
    assert names == [OCR_NAME, "tea-legacy"]
    v2 = next(skill for skill in loaded if skill.kind == "skill_md")
    assert v2.body == OCR_BODY.strip()
    assert BODY_MARKER in v2.body
    assert v2.slash == OCR_NAME


def test_description_over_sixty_chars_is_a_bilingual_per_skill_error(workspace):
    too_long = "x" * (DESCRIPTION_MAX_CHARS + 1)
    _write_skill_md(workspace, "too-long-desc", too_long, "body text here")
    loaded, problems = load_skills()
    assert loaded == []
    assert len(problems) == 1
    assert problems[0].filename.endswith("SKILL.md")
    _contains_both_languages(problems[0].detail)
    assert str(DESCRIPTION_MAX_CHARS) in problems[0].detail or "60" in problems[0].detail


def test_invalid_skill_md_does_not_drop_the_rest_of_the_registry(workspace):
    _write_skill_md(workspace, OCR_NAME, OCR_DESC, OCR_BODY)
    broken = workspace / "skills" / "broken-skill"
    broken.mkdir(parents=True)
    (broken / "SKILL.md").write_text("this is not frontmatter\n", encoding="utf-8")
    from dream.skills.registry import mark_skills_dirty

    mark_skills_dirty()
    loaded, problems = load_skills()
    assert [skill.name for skill in loaded] == [OCR_NAME]
    assert len(problems) == 1
    _contains_both_languages(problems[0].detail)


def test_name_collision_is_reported_and_second_file_is_not_loaded(workspace):
    _write_skill_md(workspace, OCR_NAME, OCR_DESC, OCR_BODY)
    # A second directory cannot share the same name; folder mismatch is also
    # an error. Collision via a legacy file using the same slash name.
    save_skill(OCR_NAME, "legacy colliding description text here", ["step"])
    loaded, problems = load_skills()
    names = [skill.name for skill in loaded]
    assert names.count(OCR_NAME) == 1
    assert problems
    _contains_both_languages(problems[0].detail)


def test_folder_name_must_match_frontmatter_name(workspace):
    _write_skill_md(
        workspace, "pdf-reader", "Read a PDF when asked to.", "body", folder="other-folder"
    )
    loaded, problems = load_skills()
    assert loaded == []
    assert problems
    _contains_both_languages(problems[0].detail)


def test_unsafe_and_reserved_skill_names_are_rejected(workspace):
    _write_skill_md(workspace, "help", "Reserved slash name must not load.", "body of help")
    loaded, problems = load_skills()
    assert not any(skill.slash == "help" for skill in loaded)
    assert problems
    _contains_both_languages(problems[0].detail)


def test_authoring_templates_parse_and_keep_section_order():
    templates = authoring_templates()
    assert set(templates) == {"en", "fa"}
    english = parse_skill_md(templates["en"])
    persian = parse_skill_md(templates["fa"])
    assert len(english.description) <= DESCRIPTION_MAX_CHARS
    assert len(persian.description) <= DESCRIPTION_MAX_CHARS
    for section in TEMPLATE_SECTIONS:
        assert section in templates["en"]
    # Persian template keeps the same five-section shape (Persian headings).
    assert templates["fa"].count("## ") == 5
    assert any("\u0600" <= char <= "\u06ff" for char in persian.description)


def test_strict_parser_raises_on_empty_body():
    empty = "---\nname: empty-body\ndescription: Has a description and no body.\n---\n\n"
    with pytest.raises(SkillFormatError) as caught:
        parse_skill_md(empty)
    _contains_both_languages(str(caught.value))


# --------------------------------------------------------------------------
# C-2 Progressive disclosure / token-cost (Gate C centerpiece).
# --------------------------------------------------------------------------


class RecordingBackend:
    """Records every system prompt; never calls tools unless asked."""

    def __init__(self):
        self.system_prompts: list[str] = []

    def chat(self, messages, tools=None):
        del tools
        system = str(messages[0].get("content", ""))
        self.system_prompts.append(system)
        user = next(m.get("content", "") for m in reversed(messages) if m.get("role") == "user")
        return {"content": f"Echo: {user}", "tool_calls": []}


def test_body_absent_from_system_prompt_until_skill_view(workspace, store):
    _write_skill_md(workspace, OCR_NAME, OCR_DESC, OCR_BODY)
    backend = RecordingBackend()
    dream = Dream(store, backend)
    turn = dream.run("hello")
    assert backend.system_prompts
    system = backend.system_prompts[0]
    assert BODY_MARKER not in system
    assert OCR_NAME in system
    assert OCR_DESC in system
    assert turn.reply.startswith("Echo:")

    viewed = _ok(json.loads(tools.execute("skill_view", {"name": OCR_NAME})))
    assert BODY_MARKER in viewed["body"]
    # Viewing does not leak the body into a later system prompt either.
    dream.run("still hello")
    assert all(BODY_MARKER not in prompt for prompt in backend.system_prompts)


def test_catalog_stays_within_budget_with_fifty_skills(workspace, store):
    for index in range(50):
        name = f"skill-{index:02d}"
        desc = f"Installed fixture skill number {index:02d}."
        _write_skill_md(workspace, name, desc, f"# {name}\n\n{BODY_MARKER}-{index}\n")
    catalog, injected = render_skill_catalog()
    assert len(injected) == 50
    assert len(catalog) <= SKILL_CATALOG_BUDGET_CHARS
    assert BODY_MARKER not in catalog
    backend = RecordingBackend()
    Dream(store, backend).run("ping")
    system = backend.system_prompts[0]
    assert BODY_MARKER not in system
    assert len([line for line in system.splitlines() if line.startswith("/skill-")]) == 50


def test_skill_view_missing_skill_is_a_bilingual_error(workspace):
    payload = json.loads(tools.execute("skill_view", {"name": "no-such-skill"}))
    error = _error(payload)
    _contains_both_languages(str(error.get("message", "")))


# --------------------------------------------------------------------------
# C-3 Slash parsing with stacking (path-like args, 5-cap).
# --------------------------------------------------------------------------


def test_path_like_argument_is_not_swallowed(workspace):
    _write_skill_md(workspace, OCR_NAME, OCR_DESC, OCR_BODY)
    stack = parse_slash_stack("/ocr-and-documents /tmp/scan.pdf extract the tables")
    assert [skill.name for skill in stack.skills] == [OCR_NAME]
    assert stack.remainder == "/tmp/scan.pdf extract the tables"
    assert stack.raw_tokens == ("/ocr-and-documents",)


def test_five_skill_stack_with_trailing_instruction(workspace):
    names = [f"stack-{index}" for index in range(5)]
    for name in names:
        _write_skill_md(workspace, name, f"Stack fixture {name} description.", f"body of {name}")
    extra = "stack-x"
    _write_skill_md(workspace, extra, "Sixth skill must not be auto-stacked.", "body of sixth")
    message = "/stack-0 /stack-1 /stack-2 /stack-3 /stack-4 then summarise all of them"
    stack = parse_slash_stack(message)
    assert [skill.name for skill in stack.skills] == names
    assert stack.remainder == "then summarise all of them"
    six = parse_slash_stack(
        "/stack-0 /stack-1 /stack-2 /stack-3 /stack-4 /stack-x leftover"
    )
    assert [skill.name for skill in six.skills] == names
    assert six.remainder == "/stack-x leftover"


class CaptureUserBackend(RecordingBackend):
    """Records system prompts and the user message the model actually saw."""

    def __init__(self):
        super().__init__()
        self.users: list[str] = []

    def chat(self, messages, tools=None):
        self.users.append(
            next(m["content"] for m in reversed(messages) if m.get("role") == "user")
        )
        return super().chat(messages, tools)


def test_slash_loads_bodies_into_user_turn_not_system_prompt(workspace, store):
    _write_skill_md(workspace, OCR_NAME, OCR_DESC, OCR_BODY)
    visible, stack = apply_slash_invocation("/ocr-and-documents extract the tables")
    assert stack.invoked
    assert BODY_MARKER in visible
    backend = CaptureUserBackend()
    Dream(store, backend).run("/ocr-and-documents extract the tables")
    assert BODY_MARKER in backend.users[0]
    assert all(BODY_MARKER not in prompt for prompt in backend.system_prompts)


def test_cli_and_agent_share_the_same_slash_parser(workspace, store, capsys):
    _write_skill_md(workspace, OCR_NAME, OCR_DESC, OCR_BODY)
    dream = Dream(store, RecordingBackend())
    assert cli.dispatch_command(
        "/ocr-and-documents /tmp/scan.pdf extract the tables", dream, output=print
    )
    out = capsys.readouterr().out
    assert "extract the tables" in out


def test_unknown_slash_is_still_an_unknown_command(workspace, store, capsys):
    dream = Dream(store, EchoBackend())
    assert cli.dispatch_command("/definitely-not-a-skill", dream, output=print)
    out = capsys.readouterr().out
    assert "Unknown command" in out


# --------------------------------------------------------------------------
# C-4 Versioning, use logs, write-approval fail-closed.
# --------------------------------------------------------------------------


def test_versions_append_and_never_overwrite(workspace):
    from dream.skills.store import get_ledger

    first = save_skill_md(OCR_NAME, OCR_DESC, "first body")
    assert first.endswith("SKILL.md")
    edit_skill(OCR_NAME, OCR_DESC, "second body")
    ledger = get_ledger()
    versions = ledger.versions(OCR_NAME)
    assert [row.version for row in versions] == [1, 2]
    assert versions[0].content != versions[1].content
    assert "first body" in versions[0].content
    assert "second body" in versions[1].content
    # Re-saving identical content is a no-op, not an overwrite.
    edit_skill(OCR_NAME, OCR_DESC, "second body")
    assert [row.version for row in ledger.versions(OCR_NAME)] == [1, 2]


def test_save_skill_md_refuses_to_clobber_without_replace(workspace):
    save_skill_md(OCR_NAME, OCR_DESC, "first body")
    with pytest.raises(ValueError) as caught:
        save_skill_md(OCR_NAME, OCR_DESC, "sneaky overwrite")
    _contains_both_languages(str(caught.value))
    text = (workspace / "skills" / OCR_NAME / "SKILL.md").read_text(encoding="utf-8")
    assert "first body" in text
    assert "sneaky overwrite" not in text


def test_use_log_records_view_and_slash(workspace, store):
    from dream.skills.store import get_ledger

    _write_skill_md(workspace, OCR_NAME, OCR_DESC, OCR_BODY)
    view_skill(OCR_NAME)
    Dream(store, RecordingBackend()).run("/ocr-and-documents go")
    rows = get_ledger().uses(OCR_NAME)
    sources = {row.source for row in rows}
    assert "skill_view" in sources
    assert "slash" in sources
    assert any(row.outcome == "success" for row in rows)
    assert any(row.outcome == "invoked" for row in rows)


def test_write_approval_denial_fails_closed(workspace, store):
    class SaveBackend:
        def chat(self, messages, tools=None):
            del tools
            if messages[-1].get("role") == "tool":
                return {"content": "blocked path", "tool_calls": []}
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "save",
                        "name": "save_skill",
                        "arguments": {
                            "name": "denied-skill",
                            "description": "should not land on disk",
                            "steps": ["one"],
                        },
                    }
                ],
            }

    policy = ApprovalPolicy(
        auto_approve={"safe"},
        always_ask={"guarded", "dangerous"},
        ask=lambda name, arguments: False,
    )
    dream = Dream(store, SaveBackend(), policy)
    turn = dream.run("please save a skill")
    assert turn.tool_calls[0]["allowed"] is False
    assert "denied" in turn.tool_calls[0]["result"]
    loaded, _ = load_skills()
    assert loaded == []
    leftover = list((workspace / "skills").rglob("*")) if (workspace / "skills").exists() else []
    assert leftover == []


def test_delete_skill_removes_file_and_keeps_versions(workspace):
    from dream.skills.store import get_ledger

    save_skill_md(OCR_NAME, OCR_DESC, "keep this in history")
    delete_skill(OCR_NAME)
    loaded, problems = load_skills()
    assert loaded == []
    assert not (workspace / "skills" / OCR_NAME / "SKILL.md").exists()
    versions = get_ledger().versions(OCR_NAME)
    assert versions
    assert "keep this in history" in versions[-1].content
    del problems


def test_normalizer_import_paths_are_one_implementation():
    from dream.skills.registry import normalize_fa as registry_norm

    assert registry_norm is normalize_fa


def test_hand_edit_still_busts_the_registry_cache(workspace):
    _write_skill_md(workspace, OCR_NAME, OCR_DESC, "original body")
    before = view_skill(OCR_NAME)
    assert "original body" in before["body"]
    path = workspace / "skills" / OCR_NAME / "SKILL.md"
    path.write_text(
        f"---\nname: {OCR_NAME}\ndescription: {OCR_DESC}\n---\n\nedited body\n",
        encoding="utf-8",
    )
    after = view_skill(OCR_NAME)
    assert "edited body" in after["body"]
