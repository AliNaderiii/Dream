"""Pin the atomic, oldest-first cleanup pass that protects stored memories.

The pass exists because the near-duplicate write check was added after dirty
stores already existed; these tests cover the measured merge cases and guards.
"""

import json

import pytest

import cli
import dream.memory as memory_module
from dream.memory import MemoryStore, normalize_fa

FACTS = [
    "\u06a9\u0627\u0631\u0628\u0631 \u06cc\u06a9 \u062e\u0648\u062f\u0631\u0648 \u067e\u0631\u0627\u06cc\u062f \u0633\u0641\u06cc\u062f \u062f\u0627\u0631\u062f",  # noqa: E501
    "\u06a9\u0627\u0631\u0628\u0631 \u062e\u0648\u062f\u0631\u0648 \u067e\u0631\u0627\u06cc\u062f \u0633\u0641\u06cc\u062f \u062f\u0627\u0631\u062f",  # noqa: E501
    "\u06a9\u0627\u0631\u0628\u0631 \u062e\u0648\u062f\u0631\u0648 \u067e\u0631\u0627\u06cc\u062f \u062f\u0627\u0631\u062f",  # noqa: E501
    "\u06a9\u0627\u0631\u0628\u0631 \u0631\u0648\u06cc \u06cc\u06a9 \u0627\u0633\u062a\u0627\u0631\u062a\u0627\u067e \u0641\u06cc\u0646\u200c\u062a\u06a9 \u06a9\u0627\u0631 \u0645\u06cc\u200c\u06a9\u0646\u062f",  # noqa: E501
    "\u06a9\u0627\u0631\u0628\u0631 \u0631\u0648\u06cc \u0627\u0633\u062a\u0627\u0631\u062a\u0627\u067e \u0641\u06cc\u0646\u200c\u062a\u06a9 \u06a9\u0627\u0631 \u0645\u06cc\u200c\u06a9\u0646\u062f",  # noqa: E501
    "\u0633\u0646 \u06a9\u0627\u0631\u0628\u0631 \u06f3\u06f0 \u0633\u0627\u0644 \u0627\u0633\u062a",  # noqa: E501
    "\u0639\u0645\u0631 \u06a9\u0627\u0631\u0628\u0631 \u06f3\u06f0 \u0627\u0633\u062a",
    "\u06a9\u0627\u0631\u0628\u0631 \u062f\u0631 \u062a\u0647\u0631\u0627\u0646 \u0632\u0646\u062f\u06af\u06cc \u0645\u06cc\u200c\u06a9\u0646\u062f",  # noqa: E501
    "\u06a9\u0627\u0631\u0628\u0631 \u067e\u0627\u06cc\u062a\u0648\u0646 \u0628\u0644\u062f \u0627\u0633\u062a",  # noqa: E501
]


def seed(store, text, kind="semantic", importance=.5, pinned=False, archived=False, tags=(), user=None):  # noqa: E501
    now = len(store.all(include_archived=True)) + 1
    store.conn.execute(
        """INSERT INTO memories
        (user_id, kind, content, norm, tags, importance, created_at, last_used_at,
         use_count, source, archived, pinned) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?)""",
        (user or store.user_id, kind, text, normalize_fa(text), json.dumps(list(tags)), importance,
         now, now, archived, pinned),
    )
    store.conn.commit()


def seeded():
    store = MemoryStore(":memory:")
    for fact in FACTS:
        seed(store, fact)
    return store


def test_nine_facts_dry_run_confirm_and_repeat():
    store = seeded()
    assert len(store.all()) == 9
    assert store.cleanup_duplicates()["merged"] == 3
    assert len(store.all()) == 9
    assert store.cleanup_duplicates(False)["merged"] == 3
    assert len(store.all()) == 6
    assert store.cleanup_duplicates(False)["merged"] == 0
    assert len(store.all()) == 6


def test_pairs_and_details():
    result = seeded().cleanup_duplicates()
    assert result["pairs"] == [(2, 1), (5, 4), (7, 6)]
    assert (result["examined"], result["merged"], result["remaining"]) == (9, 3, 6)
    assert len(result["details"]) == 3
    assert all(detail[2] and detail[3] for detail in result["details"])


def test_default_dry_run_and_no_changes():
    store = seeded()
    before = list(store.conn.execute("SELECT id, importance FROM memories"))
    store.cleanup_duplicates()
    assert before == list(store.conn.execute("SELECT id, importance FROM memories"))


@pytest.mark.parametrize("kind", ["episodic", "procedural"])
def test_nonsemantic_rows_ignored(kind):
    store = MemoryStore(":memory:")
    seed(store, FACTS[0], kind=kind)
    seed(store, FACTS[1], kind=kind)
    assert store.cleanup_duplicates()["merged"] == 0


def test_pinned_archived_and_other_user_rows_ignored():
    store = MemoryStore(":memory:")
    seed(store, FACTS[0], pinned=True)
    seed(store, FACTS[1])
    seed(store, FACTS[0], archived=True)
    seed(store, FACTS[1], archived=True)
    seed(store, FACTS[0], user="other")
    seed(store, FACTS[1], user="other")
    assert store.cleanup_duplicates()["merged"] == 0
    assert len(store.all()) == 2


def test_importance_tags_last_used_and_no_superseded_by():
    store = MemoryStore(":memory:")
    seed(store, FACTS[0], importance=.9, tags=("old",))
    seed(store, FACTS[1], importance=.2, tags=("new",))
    before = store.get(1).last_used_at
    store.cleanup_duplicates(False)
    row = store.get(1)
    assert row.importance == 1.0 and set(row.tags) == {"old", "new"}
    assert row.last_used_at > before and row.superseded_by is None
    store = MemoryStore(":memory:")
    seed(store, FACTS[0], importance=.2)
    seed(store, FACTS[1], importance=.9)
    assert store.cleanup_duplicates(False)["merged"] == 1
    assert store.get(1).importance == 1.0


def test_contradiction_empty_and_single():
    store = MemoryStore(":memory:")
    seed(store, "user has a white car")
    seed(store, "user has a black car")
    assert store.cleanup_duplicates()["merged"] == 0
    assert MemoryStore(":memory:").cleanup_duplicates()["merged"] == 0
    one = MemoryStore(":memory:")
    seed(one, "one fact")
    assert one.cleanup_duplicates()["merged"] == 0


def test_deterministic_for_fixed_insertion_order():
    outcomes = set()
    for _ in range(20):
        store = seeded()
        store.cleanup_duplicates(False)
        outcomes.add(tuple(memory.id for memory in store.all()))
    assert len(outcomes) == 1


def test_atomicity(monkeypatch):
    store = seeded()
    before = list(store.conn.execute("SELECT id, importance FROM memories"))
    original = memory_module._is_duplicate
    calls = 0

    def fail_after_a_few(*args):
        nonlocal calls
        calls += 1
        if calls > 2:
            raise RuntimeError("forced")
        return original(*args)

    monkeypatch.setattr(memory_module, "_is_duplicate", fail_after_a_few)
    with pytest.raises(RuntimeError):
        store.cleanup_duplicates(False)
    assert before == list(store.conn.execute("SELECT id, importance FROM memories"))


def _feeding_input(lines):
    iterator = iter(lines)

    def read(_prompt=""):
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    return read


@pytest.mark.parametrize("quiet", [False, True])
def test_quiet_suppresses_diagnostics_not_command_replies(tmp_path, monkeypatch, capsys, quiet):
    store_path = tmp_path / ("quiet.db" if quiet else "loud.db")
    with MemoryStore(str(store_path)) as store:
        seed(store, "one visible fact")
    commands = ["/mems", "/help", "/stats", "/unknown", "/dedupe", "/exit"]
    monkeypatch.setattr("builtins.input", _feeding_input(commands))
    arguments = ["--db", str(store_path)] + (["--quiet"] if quiet else [])
    assert cli.main(arguments) == 0
    output = capsys.readouterr().out
    assert "one visible fact" in output
    assert "/dedupe [confirm]" in output
    assert "{\"" in output
    assert "Unknown command: /unknown" in output
    assert ("[dedupe]" in output) is (not quiet)


def test_cli_dedupe_wording_help_and_quiet(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", _feeding_input(["/dedupe", "/dedupe confirm", "/help", "/exit"]))  # noqa: E501
    assert cli.main(["--db", str(tmp_path / "one.db")]) == 0
    output = capsys.readouterr().out
    assert "would remain" in output and "add the confirm argument" in output
    assert "0 merged, 0 remain" in output
    assert "/dedupe [confirm]" in output and "/dedupe" in cli.KNOWN_COMMANDS
    monkeypatch.setattr("builtins.input", _feeding_input(["/dedupe", "/exit"]))
    assert cli.main(["--quiet", "--db", str(tmp_path / "two.db")]) == 0
    assert "[dedupe]" not in capsys.readouterr().out
