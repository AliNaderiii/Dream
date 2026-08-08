"""Tests for teaching the model when a procedure is a skill, not a fact.

What this pins:

- The M4 ``contribute_prompt`` hook is wired: the skills subsystem supplies
  its own usage line through ``SkillPromptProvider`` and that line reaches
  the system prompt of a real turn (previously the hook had never been
  called and the prompt contained zero mention of skills).
- The measured M9 failure is inverted on the owner's own two-message
  transcript. Before this milestone the same input produced two
  ``remember_fact`` tool calls plus one extraction row (three durable rows,
  zero skills — reproduced by the red run). After it, the same input, fed to
  a scripted backend whose tool choices follow the system prompt, ends in
  exactly one skill file of three steps, the model writes zero memory rows,
  and a later added step extends the same file instead of creating a second
  skill.
- A fact-shaped statement still becomes a memory row, not a skill.
- A how-to request consults the stored skill through ``use_skill`` and the
  reply carries the stored steps; an unrelated request triggers no skill
  lookup at all.

Evidence that justified them: no live provider answered in this environment
(``OPENAI_API_KEY`` unset, no Ollama), so the model is a scripted
``PromptFollowingBackend`` that uses a tool only when the system prompt names
it — the measured M9 principle. The transcript test was observed red against
unchanged source (3 rows, 0 skills, reproducing the owner's transcript) and
green after the source change; every test in this file was additionally
observed red against a deliberate one-line break and green again after
``git checkout`` restored the source (break-and-restore log is in the PR).
"""

from __future__ import annotations

import re

import pytest

import dream.skills as skills
from dream import tools
from dream.agent import Dream
from dream.memory import MemoryStore

# Persian strings are written as backslash-u escapes (repository convention).
# Gloss: یاد بگیر: برای تمدید بیمه ماشین اول بیمه‌نامه قبلی را پیدا می‌کنم
MSG_1 = (
    "\u06cc\u0627\u062f \u0628\u06af\u06cc\u0631: "
    "\u0628\u0631\u0627\u06cc \u062a\u0645\u062f\u06cc\u062f "
    "\u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646 "
    "\u0627\u0648\u0644 \u0628\u06cc\u0645\u0647\u200c\u0646\u0627\u0645\u0647 "
    "\u0642\u0628\u0644\u06cc \u0631\u0627 \u067e\u06cc\u062f\u0627 "
    "\u0645\u06cc\u200c\u06a9\u0646\u0645"
)
# Gloss: بعد کارت ماشین را برمی‌دارم، بعد میرم نمایندگی
MSG_2 = (
    "\u0628\u0639\u062f \u06a9\u0627\u0631\u062a \u0645\u0627\u0634\u06cc\u0646 "
    "\u0631\u0627 \u0628\u0631\u0645\u06cc\u200c\u062f\u0627\u0631\u0645\u060c "
    "\u0628\u0639\u062f \u0645\u06cc\u0631\u0645 \u0646\u0645\u0627\u06cc\u0646\u062f\u06af\u06cc"
)
# Gloss: بعد فرم تمدید را پر می‌کنم
MSG_3 = (
    "\u0628\u0639\u062f \u0641\u0631\u0645 \u062a\u0645\u062f\u06cc\u062f "
    "\u0631\u0627 \u067e\u0631 \u0645\u06cc\u200c\u06a9\u0646\u0645"
)
# Gloss: تمديد بيمه ماشين — the name the scripted model derives from MSG_1
SKILL_NAME = (
    "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"
)
# Gloss: بیمه‌نامه قبلی را پیدا می‌کنم
STEP_1 = (
    "\u0628\u06cc\u0645\u0647\u200c\u0646\u0627\u0645\u0647 "
    "\u0642\u0628\u0644\u06cc \u0631\u0627 \u067e\u06cc\u062f\u0627 "
    "\u0645\u06cc\u200c\u06a9\u0646\u0645"
)
# Gloss: کارت ماشین را برمی‌دارم
STEP_2 = (
    "\u06a9\u0627\u0631\u062a \u0645\u0627\u0634\u06cc\u0646 \u0631\u0627 "
    "\u0628\u0631\u0645\u06cc\u200c\u062f\u0627\u0631\u0645"
)
# Gloss: میرم نمایندگی
STEP_3 = "\u0645\u06cc\u0631\u0645 \u0646\u0645\u0627\u06cc\u0646\u062f\u06af\u06cc"
# Gloss: فرم تمدید را پر می‌کنم
STEP_4 = (
    "\u0641\u0631\u0645 \u062a\u0645\u062f\u06cc\u062f \u0631\u0627 "
    "\u067e\u0631 \u0645\u06cc\u200c\u06a9\u0646\u0645"
)
# Gloss: اسم کامل من سارا رادمنش است
FACT_MSG = (
    "\u0627\u0633\u0645 \u06a9\u0627\u0645\u0644 \u0645\u0646 "
    "\u0633\u0627\u0631\u0627 \u0631\u0627\u062f\u0645\u0646\u0634 "
    "\u0627\u0633\u062a"
)
# Gloss: چطور بیمه ماشین را تمدید کنم؟
HOWTO_MSG = (
    "\u0686\u0637\u0648\u0631 \u0628\u06cc\u0645\u0647 "
    "\u0645\u0627\u0634\u06cc\u0646 \u0631\u0627 \u062a\u0645\u062f\u06cc\u062f "
    "\u06a9\u0646\u0645\u061f"
)
# Gloss: قیمت دلار امروز چقدر است؟
DOLLAR_MSG = (
    "\u0642\u06cc\u0645\u062a \u062f\u0644\u0627\u0631 "
    "\u0627\u0645\u0631\u0648\u0632 \u0686\u0642\u062f\u0631 "
    "\u0627\u0633\u062a\u061f"
)
# Gloss: کاربر در حال تمدید بیمه ماشین است — the unchanged extraction pass's
# durable-fact output for MSG_1 (emulating the measured M9 transcript, where
# the pass stored one row alongside the model's two remember_fact rows).
EXTRACT_FACT = (
    "\u06a9\u0627\u0631\u0628\u0631 \u062f\u0631 \u062d\u0627\u0644 "
    "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 "
    "\u0645\u0627\u0634\u06cc\u0646 \u0627\u0633\u062a"
)
# Gloss: استخراج — marker of the extraction pass's system prompt
EXTRACT_MARK = "\u0627\u0633\u062a\u062e\u0631\u0627\u062c"
# Gloss: اسم کامل من | دوست دارم | هستم
FACT_CUES = (
    "\u0627\u0633\u0645 \u06a9\u0627\u0645\u0644 \u0645\u0646",
    "\u062f\u0648\u0633\u062a \u062f\u0627\u0631\u0645",
    "\u0647\u0633\u062a\u0645",
)
# Gloss: چطور | چجوری | طرز | یادم بده
HOWTO_CUES = (
    "\u0686\u0637\u0648\u0631",
    "\u0686\u062c\u0648\u0631\u06cc",
    "\u0637\u0631\u0632",
    "\u06cc\u0627\u062f\u0645 \u0628\u062f\u0647",
)
# Gloss: یاد بگیر | اول | بعد | سپس | قدم | مرحله
TEACH_CUES = (
    "\u06cc\u0627\u062f \u0628\u06af\u06cc\u0631",
    "\u0627\u0648\u0644",
    "\u0628\u0639\u062f",
    "\u0633\u067e\u0633",
    "\u0642\u062f\u0645",
    "\u0645\u0631\u062d\u0644\u0647",
)
# Gloss: پاسخ:  |  نتیجه:
REPLY_PREFIX = "\u067e\u0627\u0633\u062e: "
RESULT_PREFIX = "\u0646\u062a\u06cc\u062c\u0647: "
# Gloss: وقتی کاربر بخواهد {name} را انجام دهد یا روشش را بپرسد
DESC_PRE = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0628\u062e\u0648\u0627\u0647\u062f "
)
DESC_POST = (
    " \u0631\u0627 \u0627\u0646\u062c\u0627\u0645 \u062f\u0647\u062f "
    "\u06cc\u0627 \u0631\u0648\u0634\u0634 \u0631\u0627 "
    "\u0628\u067e\u0631\u0633\u062f"
)


class PromptFollowingBackend:
    """Deterministic model stand-in whose tool choices follow the system prompt.

    It uses a tool only when the system prompt names it — the measured M9
    principle this milestone exists to fix. On a prompt that does not name
    the skills tools, teaching-shaped messages reach for ``remember_fact``
    (the measured M9 behaviour, reproduced by the red run of the transcript
    test). On a prompt that does, step-shaped messages are gathered across
    turns into one ``save_skill`` call under one name, fact statements reach
    for ``remember_fact``, and how-to requests reach for ``use_skill``.
    Extraction requests (a system prompt naming ``استخراج``, no tools) return
    scripted durable-fact JSON, identical before and after the source change.
    """

    _STEP_SPLIT = re.compile("|".join(TEACH_CUES[1:]))
    _PREAMBLE = re.compile("^" + TEACH_CUES[0] + "[:\u060c]? *")
    _NAME_RE = re.compile(
        "\u0628\u0631\u0627\u06cc +(.+?) *$"  # برای ...
    )
    _TRAILING = re.compile("[\u060c.;:]+$")  # ، . ؛ :

    def __init__(self) -> None:
        self.system_prompts: list[str] = []
        self._steps: list[str] = []
        self._name: str | None = None
        self._calls = 0

    def chat(self, messages, tools=None):
        system = str(messages[0].get("content", ""))
        if tools is None and EXTRACT_MARK in system:
            text = str(messages[-1]["content"])
            return {"content": self._extraction_json(text), "tool_calls": []}
        if tools is not None:
            self.system_prompts.append(system)
        if messages[-1].get("role") == "tool":
            return {"content": RESULT_PREFIX + str(messages[-1]["content"]), "tool_calls": []}
        user = next(m["content"] for m in reversed(messages) if m.get("role") == "user")
        skills_named = "save_skill" in system and "use_skill" in system
        if any(cue in user for cue in FACT_CUES):
            return self._call("remember_fact", {"content": user})
        if any(cue in user for cue in HOWTO_CUES):
            if skills_named:
                return self._call("use_skill", {"query": user})
            return {"content": REPLY_PREFIX + user, "tool_calls": []}
        if any(cue in user for cue in TEACH_CUES):
            if skills_named:
                self._gather(user)
                return self._call(
                    "save_skill",
                    {
                        "name": self._name,
                        "description": DESC_PRE + str(self._name) + DESC_POST,
                        "steps": list(self._steps),
                    },
                )
            return self._call("remember_fact", {"content": user})
        return {"content": REPLY_PREFIX + user, "tool_calls": []}

    def _call(self, name: str, arguments: dict) -> dict:
        self._calls += 1
        return {
            "content": None,
            "tool_calls": [
                {"id": f"call-{self._calls}", "name": name, "arguments": arguments}
            ],
        }

    def _extraction_json(self, user: str) -> str:
        if user == MSG_1:
            return (
                '[{"content": "' + EXTRACT_FACT
                + '", "kind": "episodic", "importance": 0.7}]'
            )
        if user == FACT_MSG:
            return '[{"content": "' + FACT_MSG + '", "kind": "semantic", "importance": 0.9}]'
        return "[]"

    def _gather(self, user: str) -> None:
        fragments = [fragment.strip() for fragment in self._STEP_SPLIT.split(user)]
        fragments = [fragment for fragment in fragments if fragment]
        preamble = ""
        if not self._STEP_SPLIT.match(user):
            preamble = self._PREAMBLE.sub("", fragments.pop(0)).strip(" :\u060c")
            match = self._NAME_RE.search(preamble)
            if match:
                self._name = match.group(1).strip(" \u060c")
        steps = [self._TRAILING.sub("", fragment) for fragment in fragments]
        self._steps.extend(step for step in steps if step)
        if not self._name:
            self._name = " ".join((preamble or user).split()[:3])


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    return tmp_path.resolve()


@pytest.fixture()
def store(tmp_path):
    memory_store = MemoryStore(str(tmp_path / "dream.db"))
    yield memory_store
    memory_store.close()


def test_skills_usage_line_reaches_the_system_prompt(workspace, store):
    backend = PromptFollowingBackend()

    Dream(store, backend).run(MSG_1)

    assert backend.system_prompts
    system = backend.system_prompts[0]
    assert skills.SKILLS_USAGE in system
    assert "save_skill" in system
    assert "use_skill" in system


def test_two_message_teaching_ends_as_one_skill_of_three_steps(workspace, store):
    """The owner's two-message transcript: one skill of three steps, no
    procedural memory rows written by the model (the extraction pass's one
    durable-fact row is unchanged and out of scope)."""
    backend = PromptFollowingBackend()
    dream = Dream(store, backend)

    first = dream.run(MSG_1)
    second = dream.run(MSG_2)

    loaded, problems = skills.load_skills()
    assert problems == []
    assert len(loaded) == 1
    assert loaded[0].name == SKILL_NAME
    assert list(loaded[0].steps) == [STEP_1, STEP_2, STEP_3]

    assert [call["name"] for call in first.tool_calls] == ["save_skill"]
    assert [call["name"] for call in second.tool_calls] == ["save_skill"]
    first_args = first.tool_calls[0]["arguments"]
    second_args = second.tool_calls[0]["arguments"]
    assert first_args["name"] == second_args["name"] == SKILL_NAME
    assert first_args["steps"] == [STEP_1]
    assert second_args["steps"] == [STEP_1, STEP_2, STEP_3]

    # Memory rows: before the milestone the same input stored three rows
    # (two remember_fact calls plus one extraction row). After it the model
    # writes none; only the unchanged extraction pass stores its one
    # durable-fact row.
    created = first.memories_created + second.memories_created
    assert [memory.content for memory in created] == [EXTRACT_FACT]
    assert all(memory.source == "extraction" for memory in created)


def test_later_step_extends_the_same_skill_not_a_second_one(workspace, store):
    backend = PromptFollowingBackend()
    dream = Dream(store, backend)

    dream.run(MSG_1)
    dream.run(MSG_2)
    third = dream.run(MSG_3)

    loaded, problems = skills.load_skills()
    assert problems == []
    assert len(loaded) == 1
    assert loaded[0].name == SKILL_NAME
    assert list(loaded[0].steps) == [STEP_1, STEP_2, STEP_3, STEP_4]
    assert third.tool_calls[0]["arguments"]["steps"] == [STEP_1, STEP_2, STEP_3, STEP_4]


def test_fact_statement_still_becomes_a_memory_row(workspace, store):
    backend = PromptFollowingBackend()
    dream = Dream(store, backend)

    turn = dream.run(FACT_MSG)

    assert [call["name"] for call in turn.tool_calls] == ["remember_fact"]
    assert [memory.content for memory in turn.memories_created] == [FACT_MSG]
    assert skills.load_skills()[0] == []


def test_how_to_request_consults_the_stored_skill(workspace, store):
    backend = PromptFollowingBackend()
    dream = Dream(store, backend)
    dream.run(MSG_1)
    dream.run(MSG_2)

    turn = dream.run(HOWTO_MSG)

    assert [call["name"] for call in turn.tool_calls] == ["use_skill"]
    result = turn.tool_calls[0]["result"]
    assert '"match"' in result
    assert STEP_3 in result
    assert STEP_3 in turn.reply


def test_unrelated_request_does_not_consult_skills(workspace, store):
    backend = PromptFollowingBackend()
    dream = Dream(store, backend)
    dream.run(MSG_1)
    dream.run(MSG_2)

    turn = dream.run(DOLLAR_MSG)

    assert turn.tool_calls == []
    assert turn.reply == REPLY_PREFIX + DOLLAR_MSG


def test_skill_prompt_provider_honours_the_budget():
    provider = skills.SkillPromptProvider()

    block, items = provider.contribute_prompt("", 10_000)
    assert block == skills.SKILLS_USAGE
    assert items == []

    block, items = provider.contribute_prompt("", len(skills.SKILLS_USAGE) - 1)
    assert block == ""
    assert items == []
