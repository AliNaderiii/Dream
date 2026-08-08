"""Tests for file-backed skills: format, matching, safety, and resilience.

What this pins:

- A skill is a hand-readable ``.txt`` file inside the workspace root, written
  through the existing ``_safe_path`` boundary helper; names containing a path
  separator, a parent reference, or an absolute path are refused.
- A skill written in one session is found and used in a second session with a
  separate store and a separate conversation instance (no in-process cache).
- Hand edits to a skill file take effect on the next use with no rebuild.
- Persian matching reuses ``normalize_fa``, the stemmer, and the synonym
  index: three different phrasings find one skill, an unrelated request finds
  nothing, a near-miss pair routes to the right skill, and Arabic-yeh/ZWNJ
  spellings behave like their canonical forms.
- A skill that names a dangerous tool does not approve it: ``run_shell``
  still requires human approval when a skill's steps mention it.
- An empty skills directory, a malformed file, and a file mangled into
  non-UTF-8 bytes are all skipped-and-reported, never fatal.
- The store gains no skills table (skills are files, not rows).

Evidence that justified them: the milestone brief requires each pinned
behaviour with measurements; every test here was additionally observed red
against a deliberate one-line source break and green again after
``git checkout`` restored the source (break-and-restore log is in the PR).
"""

from __future__ import annotations

import json

import pytest

import cli
from dream import tools
from dream.agent import ApprovalPolicy, Dream, EchoBackend
from dream.memory import MemoryStore

# Persian strings are written as backslash-u escapes (repository convention).
# Gloss: چای دم کردن
TEA_SKILL_NAME = "\u0686\u0627\u06cc \u062f\u0645 \u06a9\u0631\u062f\u0646"
# Gloss: وقتی کاربر می‌خواهد چای درست کند یا طرز تهیه چای را بپرسد
TEA_SKILL_DESCRIPTION = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f \u0686\u0627\u06cc "
    "\u062f\u0631\u0633\u062a \u06a9\u0646\u062f \u06cc\u0627 \u0637\u0631\u0632 "
    "\u062a\u0647\u06cc\u0647 \u0686\u0627\u06cc \u0631\u0627 "
    "\u0628\u067e\u0631\u0633\u062f"
)
TEA_SKILL_STEPS = [
    # ۱. کتری را با آب تازه پر کن و روی شعله بگذار
    "\u06a9\u062a\u0631\u06cc \u0631\u0627 \u0628\u0627 \u0622\u0628 "
    "\u062a\u0627\u0632\u0647 \u067e\u0631 \u06a9\u0646 \u0648 "
    "\u0631\u0648\u06cc \u0634\u0639\u0644\u0647 \u0628\u06af\u0630\u0627\u0631",
    # ۲. وقتی آب جوش آمد چای خشک را در قوری بریز
    "\u0648\u0642\u062a\u06cc \u0622\u0628 \u062c\u0648\u0634 \u0622\u0645\u062f"
    " \u0686\u0627\u06cc \u062e\u0634\u06a9 \u0631\u0627 \u062f\u0631 "
    "\u0642\u0648\u0631\u06cc \u0628\u0631\u06cc\u0632",
    # ۳. روی شعله ملایم ده دقیقه دم بده
    "\u0631\u0648\u06cc \u0634\u0639\u0644\u0647 \u0645\u0644\u0627\u06cc\u0645"
    " \u062f\u0647 \u062f\u0642\u06cc\u0642\u0647 \u062f\u0645 \u0628\u062f\u0647",
]

# Three genuinely different phrasings of one request:
#   «چطور چای دم کنم؟»      — how do I brew tea?
#   «طرز تهیه چای را بگو»   — tell me how to make tea
#   «می‌خوام چای درست کنم»  — I want to make tea
TEA_QUERY_HOW = "\u0686\u0637\u0648\u0631 \u0686\u0627\u06cc \u062f\u0645 \u06a9\u0646\u0645\u061f"
TEA_QUERY_RECIPE = (
    "\u0637\u0631\u0632 \u062a\u0647\u06cc\u0647 \u0686\u0627\u06cc \u0631\u0627 \u0628\u06af\u0648"
)
TEA_QUERY_WANT = (
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0645 \u0686\u0627\u06cc "
    "\u062f\u0631\u0633\u062a \u06a9\u0646\u0645"
)
# Unrelated: «قیمت دلار امروز چقدر است؟» — what is today's dollar price?
DOLLAR_QUERY = (
    "\u0642\u06cc\u0645\u062a \u062f\u0644\u0627\u0631 \u0627\u0645\u0631\u0648\u0632 "
    "\u0686\u0642\u062f\u0631 \u0627\u0633\u062a\u061f"
)

# Near-miss pair: two skills whose descriptions differ only in the occasion.
# Birthday:  پیامک تبریک تولد | New year: پیامک تبریک سال نو
SMS_BIRTHDAY_NAME = (
    "\u067e\u06cc\u0627\u0645\u06a9 \u062a\u0628\u0631\u06cc\u06a9 \u062a\u0648\u0644\u062f"
)
SMS_BIRTHDAY_DESCRIPTION = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f"
    " \u0628\u0631\u0627\u06cc \u062a\u0648\u0644\u062f "
    "\u062f\u0648\u0633\u062a\u0634"
    " \u067e\u06cc\u0627\u0645\u06a9 \u062a\u0628\u0631\u06cc\u06a9 "
    "\u0628\u0646\u0648\u06cc\u0633\u062f"
)
SMS_NEWYEAR_NAME = (
    "\u067e\u06cc\u0627\u0645\u06a9 \u062a\u0628\u0631\u06cc\u06a9 \u0633\u0627\u0644 \u0646\u0648"
)
SMS_NEWYEAR_DESCRIPTION = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f"
    " \u0628\u0631\u0627\u06cc \u0633\u0627\u0644 \u0646\u0648 "
    "\u0628\u0647 \u062e\u0627\u0646\u0648\u0627\u062f\u0647"
    " \u067e\u06cc\u0627\u0645\u06a9 \u062a\u0628\u0631\u06cc\u06a9 "
    "\u0628\u0641\u0631\u0633\u062a\u062f"
)
# Birthday request without the word پیامک: «برای تولد رفیقم چی بنویسم؟»
BIRTHDAY_REQUEST = (
    "\u0628\u0631\u0627\u06cc \u062a\u0648\u0644\u062f \u0631\u0641\u06cc\u0642\u0645"
    " \u0686\u06cc \u0628\u0646\u0648\u06cc\u0633\u0645\u061f"
)
# New-year request: «تبریک سال نو به فامیلم چی بگم؟»
NEWYEAR_REQUEST = (
    "\u062a\u0628\u0631\u06cc\u06a9 \u0633\u0627\u0644 \u0646\u0648 \u0628\u0647"
    " \u0641\u0627\u0645\u06cc\u0644\u0645 \u0686\u06cc \u0628\u06af\u0645\u061f"
)

# Arabic-yeh spelling of «می‌خوام چای درست کنم» with Arabic digit-less shapes:
# مي‌خوام چاي درست کنم — byte-level different, same words after normalisation.
TEA_QUERY_ARABIC_SPELLING = (
    "\u0645\u064a\u200c\u062e\u0648\u0627\u0645 \u0686\u0627\u064a "
    "\u062f\u0631\u0633\u062a \u06a9\u0646\u0645"
)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """Point the workspace boundary helper at a fresh temporary directory."""
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    return tmp_path


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


def _save_tea_skill() -> dict:
    payload = json.loads(
        tools.execute(
            "save_skill",
            {
                "name": TEA_SKILL_NAME,
                "description": TEA_SKILL_DESCRIPTION,
                "steps": TEA_SKILL_STEPS,
            },
        )
    )
    assert payload["status"] == "ok", payload
    return payload["result"]


def _use_skill(query: str) -> dict:
    payload = json.loads(tools.execute("use_skill", {"query": query}))
    assert payload["status"] == "ok", payload
    return payload["result"]


# --------------------------------------------------------------------------
# Cross-session reuse: written in one session, found and used in the next.
# Written first in this milestone and observed failing against unchanged
# source before any implementation existed.
# --------------------------------------------------------------------------


class UseSkillBackend:
    """Backend that asks for a skill once, then answers with what came back."""

    def __init__(self, query: str):
        self.query = query
        self.seen_tool_result = ""

    def chat(self, messages, tools=None):
        del tools
        if messages[-1]["role"] == "tool":
            self.seen_tool_result = messages[-1]["content"]
            return {"content": "\u0628\u062e\u0634.", "tool_calls": []}  # «بخش.»
        return {
            "content": None,
            "tool_calls": [
                {"id": "use-skill", "name": "use_skill", "arguments": {"query": self.query}}
            ],
        }


def test_skill_written_in_one_session_is_found_and_used_in_the_next(workspace, tmp_path):
    # Session one: a Dream with its own store saves the skill to the workspace.
    store_one = MemoryStore(str(tmp_path / "one.db"))
    dream_one = Dream(store_one, EchoBackend())
    del dream_one  # the conversation instance itself is session state
    result = _save_tea_skill()
    assert result["filename"].startswith("skills/")
    store_one.close()

    # Session two: completely separate store and conversation instances, and a
    # freshly imported view of the files; only the workspace directory is shared.
    from dream import skills as skills_module

    store_two = MemoryStore(str(tmp_path / "two.db"))
    backend = UseSkillBackend(TEA_QUERY_HOW)
    dream_two = Dream(store_two, backend)
    found = skills_module.find_skill(TEA_QUERY_HOW)
    assert found is not None
    assert found.name == TEA_SKILL_NAME
    turn = dream_two.run(TEA_QUERY_HOW)
    assert turn.tool_calls[0]["name"] == "use_skill"
    assert TEA_SKILL_STEPS[0] in backend.seen_tool_result
    store_two.close()


# --------------------------------------------------------------------------
# Format: the file is plain readable text and the write returns its path.
# --------------------------------------------------------------------------


def test_saved_skill_file_is_human_readable(workspace):
    result = _save_tea_skill()
    path = workspace / result["filename"]
    text = path.read_text(encoding="utf-8")
    assert text == (
        f"name: {TEA_SKILL_NAME}\n"
        f"description: {TEA_SKILL_DESCRIPTION}\n"
        "steps:\n"
        f"1. {TEA_SKILL_STEPS[0]}\n"
        f"2. {TEA_SKILL_STEPS[1]}\n"
        f"3. {TEA_SKILL_STEPS[2]}\n"
    )
    reloaded = _use_skill(TEA_QUERY_RECIPE)
    assert reloaded["match"]["steps"] == TEA_SKILL_STEPS


def test_hand_edit_takes_effect_on_next_use(workspace):
    result = _save_tea_skill()
    path = workspace / result["filename"]
    text = path.read_text(encoding="utf-8")
    # The owner corrects step one in a text editor; ten minutes becomes five.
    # «ده دقیقه» -> «پنج دقیقه»
    edited = text.replace(
        "\u062f\u0647 \u062f\u0642\u06cc\u0642\u0647",
        "\u067e\u0646\u062c \u062f\u0642\u06cc\u0642\u0647",
    )
    assert edited != text
    path.write_text(edited, encoding="utf-8")
    found = _use_skill(TEA_QUERY_HOW)
    assert any(
        "\u067e\u0646\u062c \u062f\u0642\u06cc\u0642\u0647" in step
        for step in found["match"]["steps"]
    )


# --------------------------------------------------------------------------
# Persian matching: paraphrase tolerance, rejection, near-miss routing.
# --------------------------------------------------------------------------


def test_three_persian_phrasings_find_the_same_skill(workspace):
    _save_tea_skill()
    for query in (TEA_QUERY_HOW, TEA_QUERY_RECIPE, TEA_QUERY_WANT):
        found = _use_skill(query)
        assert found["match"] is not None, query
        assert found["match"]["name"] == TEA_SKILL_NAME
        assert found["match"]["steps"] == TEA_SKILL_STEPS


def test_unrelated_request_finds_nothing(workspace):
    _save_tea_skill()
    assert _use_skill(DOLLAR_QUERY)["match"] is None


def test_near_miss_pair_routes_to_the_right_skill(workspace):
    for name, description in (
        (SMS_BIRTHDAY_NAME, SMS_BIRTHDAY_DESCRIPTION),
        (SMS_NEWYEAR_NAME, SMS_NEWYEAR_DESCRIPTION),
    ):
        payload = json.loads(
            tools.execute(
                "save_skill",
                {"name": name, "description": description, "steps": ["\u0645\u062a\u0646"]},
            )
        )
        assert payload["status"] == "ok", payload
    from dream import skills as skills_module

    birthday = skills_module.find_skill(BIRTHDAY_REQUEST)
    assert birthday is not None and birthday.name == SMS_BIRTHDAY_NAME
    newyear = skills_module.find_skill(NEWYEAR_REQUEST)
    assert newyear is not None and newyear.name == SMS_NEWYEAR_NAME
    # The wrong skill must not merely rank lower: it must not clear the bar.
    birthday_scores = skills_module.score_skills(BIRTHDAY_REQUEST)
    newyear_scores = skills_module.score_skills(NEWYEAR_REQUEST)
    assert not any(s.name == SMS_NEWYEAR_NAME for s in birthday_scores)
    assert not any(s.name == SMS_BIRTHDAY_NAME for s in newyear_scores)


def test_arabic_spellings_match_the_same_skill(workspace):
    _save_tea_skill()
    found = _use_skill(TEA_QUERY_ARABIC_SPELLING)
    assert found["match"] is not None
    assert found["match"]["name"] == TEA_SKILL_NAME


# --------------------------------------------------------------------------
# Boundary: the three name refusals, through the tool boundary.
# --------------------------------------------------------------------------


def test_skill_name_escaping_the_workspace_is_refused(workspace):
    for bad_name in (
        "a/b",  # path separator
        "a\\b",  # Windows path separator
        "..",  # parent directory reference
        "../tea",  # parent reference with a stem
        "/etc/passwd",  # absolute POSIX path
        "C:/evil",  # absolute Windows path
    ):
        payload = json.loads(
            tools.execute(
                "save_skill",
                {"name": bad_name, "description": "x", "steps": ["y"]},
            )
        )
        assert payload["status"] == "error", bad_name
    assert list(workspace.rglob("*")) == []


# --------------------------------------------------------------------------
# Safety: following a skill never widens approval.
# --------------------------------------------------------------------------


class SkillThenShellBackend:
    """Reads the skill as instructed, then tries the dangerous step it named."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        del tools
        if messages[-1]["role"] == "tool":
            if self.calls == 1:
                self.calls += 1
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "shell",
                            "name": "run_shell",
                            "arguments": {"command": "echo must-not-run"},
                        }
                    ],
                }
            # «انجام نشد.» — it was not done.
            refused = "\u0627\u0646\u062c\u0627\u0645 \u0646\u0634\u062f."
            return {"content": refused, "tool_calls": []}
        self.calls += 1
        return {
            "content": None,
            "tool_calls": [
                {"id": "use", "name": "use_skill", "arguments": {"query": TEA_QUERY_HOW}}
            ],
        }


def test_dangerous_tool_named_in_skill_still_needs_approval(workspace, store):
    # A skill whose steps literally tell the assistant to use run_shell.
    payload = json.loads(
        tools.execute(
            "save_skill",
            {
                "name": TEA_SKILL_NAME,
                "description": TEA_SKILL_DESCRIPTION,
                "steps": ["use run_shell to boil the kettle"],
            },
        )
    )
    assert payload["status"] == "ok", payload
    dream = Dream(store, SkillThenShellBackend(), ApprovalPolicy())
    turn = dream.run(TEA_QUERY_HOW)
    shell_call = next(c for c in turn.tool_calls if c["name"] == "run_shell")
    assert shell_call["allowed"] is False
    assert "dangerous tool denied" in shell_call["result"]


# --------------------------------------------------------------------------
# Resilience: empty directory, malformed file, mangled bytes — never fatal.
# --------------------------------------------------------------------------


def test_empty_skill_directory_is_not_an_error(workspace):
    payload = json.loads(tools.execute("list_skills", {}))
    assert payload["status"] == "ok"
    assert payload["result"] == {"skills": [], "problems": []}
    assert _use_skill(TEA_QUERY_HOW)["match"] is None


def test_malformed_skill_file_is_skipped_and_reported(workspace):
    _save_tea_skill()
    broken = workspace / "skills" / "broken.txt"
    broken.write_text("this file has no name, description or steps\n", encoding="utf-8")
    payload = json.loads(tools.execute("list_skills", {}))
    result = payload["result"]
    assert [s["name"] for s in result["skills"]] == [TEA_SKILL_NAME]
    assert len(result["problems"]) == 1
    assert result["problems"][0]["filename"] == "skills/broken.txt"
    # The good skill keeps working when a broken one sits beside it.
    assert _use_skill(TEA_QUERY_HOW)["match"]["name"] == TEA_SKILL_NAME


def test_hand_mangled_bytes_are_skipped_and_reported(workspace):
    _save_tea_skill()
    mangled = workspace / "skills" / "mangled.txt"
    mangled.write_bytes(b"name: caf\xe9\n")  # latin-1, not valid UTF-8
    payload = json.loads(tools.execute("list_skills", {}))
    result = payload["result"]
    assert [s["name"] for s in result["skills"]] == [TEA_SKILL_NAME]
    assert len(result["problems"]) == 1
    assert "mangled" in result["problems"][0]["filename"]
    assert _use_skill(TEA_QUERY_HOW)["match"]["name"] == TEA_SKILL_NAME


# --------------------------------------------------------------------------
# Writing again updates in place; the store never learns about skills.
# --------------------------------------------------------------------------


def test_saving_the_same_name_updates_the_file(workspace):
    first = _save_tea_skill()
    assert first["status"] == "created"
    payload = json.loads(
        tools.execute(
            "save_skill",
            {
                "name": TEA_SKILL_NAME,
                "description": TEA_SKILL_DESCRIPTION,
                "steps": TEA_SKILL_STEPS[:1],
            },
        )
    )
    assert payload["result"]["status"] == "updated"
    listed = json.loads(tools.execute("list_skills", {}))["result"]
    assert len(listed["skills"]) == 1
    assert listed["skills"][0]["steps"] == TEA_SKILL_STEPS[:1]


def test_store_gains_no_skills_table(workspace, store):
    _save_tea_skill()
    tables = {
        row[0]
        for row in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert not any("skill" in table for table in tables)
    assert tools.execute("search_memory", {"query": "skills"}) is not None
    assert isinstance(store, MemoryStore)


# --------------------------------------------------------------------------
# CLI: /skills lists, /skill QUERY prints the matched card.
# --------------------------------------------------------------------------


def test_cli_skill_commands(workspace, store, capsys):
    _save_tea_skill()
    dream = Dream(store, EchoBackend())
    assert cli.dispatch_command("/skills", dream, output=print)
    out = capsys.readouterr().out
    assert TEA_SKILL_NAME in out
    assert cli.dispatch_command(f"/skill {TEA_QUERY_RECIPE}", dream, output=print)
    out = capsys.readouterr().out
    assert TEA_SKILL_STEPS[0] in out
    capsys.readouterr()
    assert cli.dispatch_command(f"/skill {DOLLAR_QUERY}", dream, output=print)
    out = capsys.readouterr().out
    assert TEA_SKILL_NAME not in out
