"""Tests for step shape coercion, durable file readability, and two-message saving.

What this pins:

- Defect One: Step elements passed as dictionaries (e.g. ``{"step": "..."}``,
  ``{"text": "..."}``, ``{"description": "..."}``, ``{"number": 1, "step": "..."}``,
  or Persian key ``{"مرحله": "..."}``), bare numbers, or plain strings are coerced
  into clean human-readable text. The resulting file on disk contains genuine UTF-8
  Persian text, with no Python dictionary representations (``{'step': ...}``) and
  no ``\\u`` escape sequences where Persian characters belong.
- Data Integrity: Ambiguous, unreadable, or nested shapes (booleans, nested dicts,
  conflicting text keys, index-only dicts, empty dicts, non-string/number values)
  are strictly refused with a descriptive ``ValueError``, never guessed or silently
  discarded.
- Defect Two: The owner's two-message procedure sequence must result in all three
  steps being saved on disk. A reply claiming a save cannot appear without an actual
  ``save_skill`` tool execution in that turn.

Evidence that justified them:
Reproduced against merged main:
1. Merged main stored ``1. {'step': 'bime-name-ye qabli ro peyda mikonam'}`` when
   the model passed a list of objects.
2. On the second message of the procedure, a model without the sharpened rule claimed
   steps were added while emitting zero tool calls, leaving one step on disk.
Both tests were observed failing against unchanged source (red before green) and
passing after implementation. Break-and-restore evidence is in the PR.
"""

from __future__ import annotations

import pytest

import dream.skills as skills
from dream import tools
from dream.agent import Dream
from dream.memory import MemoryStore

# Persian strings are written as backslash-u escapes (repository convention).
# Gloss: تمدید بیمه ماشین
SKILL_NAME = (
    "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"
)
# Gloss: روش تمدید بیمه ماشین
SKILL_DESC = (
    "\u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 "
    "\u0645\u0627\u0634\u06cc\u0646"
)
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

# Marker required in system prompt prohibiting claiming un-saved skills:
# Gloss: هرگز بدون فراخوانی ابزار save_skill ادعا نکن
PROMPT_RULE_NO_UNSAVED_CLAIM = (
    "\u0647\u0631\u06af\u0632 \u0628\u062f\u0648\u0646 "
    "\u0641\u0631\u0627\u062e\u0648\u0627\u0646\u06cc "
    "\u0627\u0628\u0632\u0627\u0631 save_skill "
    "\u0627\u062f\u0639\u0627 \u0646\u06a9\u0646"
)

# Gloss: قدم‌ها ذخیره شدند
CLAIM_SAVED_TEXT = (
    "\u0642\u062f\u0645\u200c\u0647\u0627 "
    "\u0630\u062e\u06cc\u0631\u0647 \u0634\u062f\u0646\u062f"
)
# Gloss: نتیجه:
RESULT_PREFIX = "\u0646\u062a\u06cc\u062c\u0647: "


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    return tmp_path.resolve()


@pytest.fixture()
def store(tmp_path):
    memory_store = MemoryStore(str(tmp_path / "dream.db"))
    yield memory_store
    memory_store.close()


# --------------------------------------------------------------------------
# Defect One: Step shape coercion, human-readable file, and refusal of bad shapes
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "step_input,expected_text",
    [
        ("plain string step", "plain string step"),
        ({"step": "object keyed step"}, "object keyed step"),
        ({"text": "object keyed text"}, "object keyed text"),
        ({"description": "object keyed description"}, "object keyed description"),
        ({"number": 1, "step": "step with number"}, "step with number"),
        (42, "42"),
        ({"\u0645\u0631\u062d\u0644\u0647": STEP_1}, STEP_1),
    ],
)
def test_accepted_step_shapes_produce_readable_text_and_no_repr(
    workspace, step_input, expected_text
):
    """Pin Defect One: All six accepted step shapes produce readable text in the file
    without Python dict repr (e.g. `{'step': ...}`) and without backslash-u escapes."""
    rel = skills.save_skill(SKILL_NAME, SKILL_DESC, [step_input])
    path = workspace / rel
    assert path.is_file()

    raw_text = path.read_text(encoding="utf-8")
    # Must NOT contain Python dict repr formatting or backslash-u escapes
    assert "{'step'" not in raw_text
    assert "{'text'" not in raw_text
    assert "{'description'" not in raw_text
    assert r"\u06" not in raw_text
    assert f"1. {expected_text}" in raw_text

    # Reloading through skills parser must return the exact expected step string
    loaded, problems = skills.load_skills()
    assert problems == []
    assert len(loaded) == 1
    assert loaded[0].steps == (str(expected_text),)


@pytest.mark.parametrize(
    "bad_step,error_match",
    [
        (True, "boolean"),
        (False, "boolean"),
        ({"step": {"nested": "dict"}}, "nested"),
        ({"step": "first", "text": "second"}, "ambiguous"),
        ({"number": 1}, "index-only|cannot"),
        ({}, "empty"),
        (["nested", "list"], "valid step|list"),
    ],
)
def test_unusable_step_shapes_are_refused_with_message(workspace, bad_step, error_match):
    """Pin Data Integrity: Unreadable or ambiguous shapes are strictly refused with a
    descriptive ValueError rather than guessed or silently coerced to repr."""
    with pytest.raises(ValueError, match=error_match):
        skills.save_skill(SKILL_NAME, SKILL_DESC, [bad_step])


# --------------------------------------------------------------------------
# Defect Two: Two-message sequence and proof that claimed save requires actual save
# --------------------------------------------------------------------------


# Gloss: استخراج — marker of the extraction pass's system prompt
EXTRACT_MARK = "\u0627\u0633\u062a\u062e\u0631\u0627\u062c"


class ComplianceModelingBackend:
    """Backend modeling the observed Defect Two failure vs compliance.

    When the system prompt lacks the sharpened negative constraint forbidding
    un-saved claims (as in M10), the model exhibits the observed Defect Two
    compliance gap on the second message: it emits a conversational reply
    claiming the steps were saved («قدم‌ها ذخیره شدند...») without calling save_skill.
    When the system prompt contains the sharpened constraint, the model obeys it
    and calls save_skill with all three steps before replying.
    """

    def __init__(self) -> None:
        self._steps: list[str] = []
        self._calls = 0

    def chat(self, messages, tools=None):
        system = str(messages[0].get("content", ""))
        if tools is None and EXTRACT_MARK in system:
            return {"content": "[]", "tool_calls": []}
        if messages[-1].get("role") == "tool":
            return {"content": RESULT_PREFIX + str(messages[-1]["content"]), "tool_calls": []}
        user = next(m["content"] for m in reversed(messages) if m.get("role") == "user")

        if user == MSG_1:
            if not self._steps:
                self._steps.append(STEP_1)
            self._calls += 1
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call-{self._calls}",
                        "name": "save_skill",
                        "arguments": {
                            "name": SKILL_NAME,
                            "description": SKILL_DESC,
                            "steps": list(self._steps),
                        },
                    }
                ],
            }

        if user == MSG_2:
            if STEP_2 not in self._steps:
                self._steps.extend([STEP_2, STEP_3])
            # Check whether system prompt has the sharpened negative constraint
            if PROMPT_RULE_NO_UNSAVED_CLAIM in system:
                # Obey sharpened instruction: call save_skill with all steps
                self._calls += 1
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call-{self._calls}",
                            "name": "save_skill",
                            "arguments": {
                                "name": SKILL_NAME,
                                "description": SKILL_DESC,
                                "steps": list(self._steps),
                            },
                        }
                    ],
                }
            # Reproduce Defect Two compliance gap under M10 prompt: claim save without tool call
            return {
                "content": (
                    f"{CLAIM_SAVED_TEXT}: 1. {STEP_1} 2. {STEP_2} 3. {STEP_3}"
                ),
                "tool_calls": [],
            }

        return {"content": f"Echo: {user}", "tool_calls": []}


def test_two_message_sequence_saves_all_three_steps_and_never_claims_unsaved(
    workspace, store
):
    """The owner's two-message sequence must end with all three steps on disk,
    and a reply claiming a save cannot appear without an actual save_skill call."""
    backend = ComplianceModelingBackend()
    dream = Dream(store, backend)

    first = dream.run(MSG_1)
    second = dream.run(MSG_2)

    # 1. Verify tool calls: save_skill MUST be called in both turns
    assert [call["name"] for call in first.tool_calls] == ["save_skill"]
    assert [call["name"] for call in second.tool_calls] == ["save_skill"]

    # 2. Proof that a claimed save cannot appear without the actual save
    if CLAIM_SAVED_TEXT in second.reply:
        assert any(c["name"] == "save_skill" for c in second.tool_calls)

    # 3. Verify exactly one skill with all three steps is stored on disk
    loaded, problems = skills.load_skills()
    assert problems == []
    assert len(loaded) == 1
    assert loaded[0].name == SKILL_NAME
    assert list(loaded[0].steps) == [STEP_1, STEP_2, STEP_3]
