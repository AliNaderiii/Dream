"""Tests for Persian normalisation, stemming and the memory store."""

from __future__ import annotations

import pytest

from dream import tools
from dream.memory import KINDS, MemoryStore, _stem_fa, normalize_fa


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------


def test_arabic_yeh_folds_to_farsi_yeh():
    assert normalize_fa("مي‌خواهم") == normalize_fa("می‌خواهم")


def test_alef_maksura_folds_to_farsi_yeh():
    assert normalize_fa("مصطفى") == normalize_fa("مصطفی")


def test_arabic_kaf_folds_to_keheh():
    assert normalize_fa("كتاب") == normalize_fa("کتاب")


def test_persian_digits_become_ascii():
    assert normalize_fa("۱۲۳") == "123"


def test_arabic_indic_digits_become_ascii():
    assert normalize_fa("٤٥٦") == "456"


def test_diacritics_are_removed():
    assert normalize_fa("مُحَمَّد") == "محمد"


def test_tatweel_is_removed():
    assert normalize_fa("سلــــام") == "سلام"


def test_hamza_forms_fold_to_alef():
    assert normalize_fa("أإآ") == "ااا"


def test_teh_marbuta_folds_to_heh():
    assert normalize_fa("مدرسة") == normalize_fa("مدرسه")


def test_whitespace_is_collapsed_and_stripped():
    assert normalize_fa("  سلام\t\n  دنیا  ") == "سلام دنیا"


def test_zwnj_becomes_a_space():
    assert normalize_fa("می‌خواهم") == "می خواهم"


def test_empty_input():
    assert normalize_fa("") == ""


# --------------------------------------------------------------------------
# Stemming
# --------------------------------------------------------------------------


def test_stem_strips_possessive_mim():
    assert _stem_fa("استارتاپم") == "استارتاپ"


def test_stem_strips_plural_ha():
    assert _stem_fa("کتابها") == "کتاب"


def test_stem_keeps_short_tokens_intact():
    assert _stem_fa("کتم") == "کتم"


def test_stem_leaves_unsuffixed_token_alone():
    assert _stem_fa("استارتاپ") == "استارتاپ"


# --------------------------------------------------------------------------
# Store: write and read
# --------------------------------------------------------------------------


def test_write_and_read_back(store):
    m = store.remember("اسم من علی است", kind="semantic", tags=["نام"], importance=0.9)
    again = store.get(m.id)
    assert again is not None
    assert again.content == "اسم من علی است"
    assert again.kind == "semantic"
    assert again.tags == ["نام"]
    assert again.importance == pytest.approx(0.9)


def test_all_three_kinds_are_stored_and_counted(store):
    store.remember("قهوه تلخ دوست دارم", kind="semantic")
    store.remember("امروز به دندانپزشک رفتم", kind="episodic")
    store.remember("همیشه اول فارسی جواب بده", kind="procedural")
    stats = store.stats()
    assert stats["total"] == 3
    assert stats["by_kind"] == dict.fromkeys(KINDS, 1)


def test_unknown_kind_is_rejected(store):
    with pytest.raises(ValueError):
        store.remember("چیزی", kind="nonsense")


def test_duplicate_boosts_importance_instead_of_inserting(store):
    first = store.remember("من در تهران زندگی می‌کنم", importance=0.5)
    second = store.remember("من در تهران زندگی می‌کنم", importance=0.5)
    assert second.id == first.id
    assert second.importance > first.importance
    assert len(store.all()) == 1


# --------------------------------------------------------------------------
# Recall
# --------------------------------------------------------------------------


def test_exact_term_recall(store):
    store.remember("استارتاپ من درباره هوش مصنوعی است")
    hits = store.recall("استارتاپ")
    assert hits and "استارتاپ" in hits[0].content


def test_recall_with_arabic_spelling_finds_persian_storage(store):
    store.remember("می‌خواهم کتاب بخوانم")
    hits = store.recall("مي‌خواهم كتاب")
    assert hits, "Arabic-form query must reach Persian-form storage"


def test_recall_with_possessive_suffix(store):
    store.remember("استارتاپ من درباره هوش مصنوعی است")
    hits = store.recall("استارتاپم")
    assert hits, "stemming must let استارتاپم match stored استارتاپ"
    assert "استارتاپ" in hits[0].content


def test_kinds_filter(store):
    store.remember("قهوه دوست دارم", kind="semantic")
    store.remember("امروز قهوه خوردم", kind="episodic")
    hits = store.recall("قهوه", kinds=["episodic"])
    assert hits
    assert all(m.kind == "episodic" for m in hits)


def test_scores_are_within_bounds(store):
    store.remember("پروژه دریم یک دستیار شخصی است", importance=0.8)
    store.remember("زبان مورد علاقه من پایتون است", importance=0.4)
    hits = store.recall("پروژه پایتون")
    assert hits
    for m in hits:
        assert 0.0 <= m.score <= 1.0
    assert hits == sorted(hits, key=lambda m: m.score, reverse=True)


def test_reinforcement_increments_use_count(store):
    m = store.remember("گربه من اسمش پشمک است")
    assert m.use_count == 0
    store.recall("پشمک", reinforce=True)
    assert store.get(m.id).use_count == 1


def test_reinforce_false_leaves_use_count_alone(store):
    m = store.remember("گربه من اسمش پشمک است")
    store.recall("پشمک", reinforce=False)
    assert store.get(m.id).use_count == 0


def test_forget_removes_memory_from_recall(store):
    m = store.remember("رمز وای‌فای خانه ۱۲۳۴۵۶ است")
    assert store.recall("وای‌فای")
    assert store.forget(m.id) is True
    assert store.recall("وای‌فای") == []
    assert store.get(m.id).archived is True


def test_hard_forget_deletes_the_row(store):
    m = store.remember("یک راز کاملا موقت")
    assert store.forget(m.id, hard=True) is True
    assert store.get(m.id) is None
    assert store.recall("راز") == []


def test_recall_of_missing_term_returns_nothing(store):
    store.remember("قهوه تلخ دوست دارم")
    assert store.recall("هلیکوپتر") == []


def test_recall_respects_limit(store):
    for i in range(5):
        store.remember(f"یادداشت شماره {i} درباره قهوه")
    assert len(store.recall("قهوه", limit=2)) == 2


# --------------------------------------------------------------------------
# Journal
# --------------------------------------------------------------------------


def test_journal_append_and_read_back(store):
    store.log("user", "سلام", session_id="s1")
    store.log("assistant", "سلام! چطور می‌توانم کمک کنم؟", session_id="s1")
    entries = store.recent_journal(session_id="s1")
    assert [e["role"] for e in entries] == ["user", "assistant"]
    assert entries[0]["content"] == "سلام"
    assert store.stats()["journal"] == 2


def test_journal_is_separate_from_memories(store):
    store.log("user", "استارتاپ من چطور است؟")
    assert store.all() == []
    assert store.recall("استارتاپ") == []


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------


def test_tool_registry_is_populated():
    assert {
        "calculate",
        "read_note",
        "write_note",
        "run_shell",
        "send_email",
    } <= tools.REGISTRY.keys()


def test_schema_types_are_derived_from_hints():
    properties = tools.REGISTRY["write_note"].schema["properties"]
    assert properties["filename"]["type"] == "string"
    assert properties["content"]["type"] == "string"
    assert tools.REGISTRY["run_shell"].schema["properties"]["timeout"]["type"] == "integer"


def test_schema_required_excludes_parameters_with_defaults():
    schema = tools.REGISTRY["run_shell"].schema
    assert "command" in schema["required"]
    assert "timeout" not in schema["required"]


def test_schema_includes_param_docstring_text():
    schema = tools.REGISTRY["read_note"].schema
    assert schema["properties"]["filename"]["description"] == "Relative path of the note to read."


def test_calculate_ascii_digits():
    assert tools.calculate("2 * (3 + 4)") == 14


def test_calculate_extended_arabic_indic_digits():
    assert tools.calculate("۱۲ + ۳") == 15


def test_calculate_multiplication_sign():
    assert tools.calculate("6 × 7") == 42


def test_calculate_rejects_code():
    with pytest.raises(ValueError):
        tools.calculate("__import__('os').system('echo unsafe')")


def test_execute_unknown_tool_returns_structured_error():
    result = tools.execute("not_a_tool", {})
    assert '"error"' in result
    assert "unknown_tool" in result


def test_safe_path_rejects_workspace_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    with pytest.raises(PermissionError):
        tools._safe_path("../outside.txt")


def test_write_then_read_note_preserves_non_ascii(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    text = "سلام، دنیا — unchanged"
    tools.write_note("notes/فارسی.txt", text)
    assert tools.read_note("notes/فارسی.txt") == text


def test_provider_schema_formats_are_well_formed():
    openai = tools.openai_schemas()
    anthropic = tools.anthropic_schemas()
    assert all(item["type"] == "function" and "parameters" in item["function"] for item in openai)
    assert all("name" in item and item["input_schema"]["type"] == "object" for item in anthropic)


def test_dangerous_tools_are_recorded_as_dangerous():
    assert tools.REGISTRY["run_shell"].risk == "dangerous"
    assert tools.REGISTRY["send_email"].risk == "dangerous"


def test_execute_blocks_dangerous_tool_without_approval():
    result = tools.execute("run_shell", {"command": "this must never run"})
    assert "approval_required" in result


def test_execute_logs_guarded_tool(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    with caplog.at_level("INFO", logger="dream.tools"):
        tools.execute("write_note", {"filename": "note.txt", "content": "logged"})
    assert "executing guarded tool: write_note" in caplog.text
