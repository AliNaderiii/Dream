"""S00 commercial kernel: plans, pricing, and the JSON usage ledger.

Pins the acceptance criteria for the commercial kernel:

- Seven plans: local, guest, daily, individual_monthly, individual_yearly,
  team, company. Currency is always IRR.
- Only free plans carry a numeric price (0). Paid-plan prices are null with
  the honest note "TBD after cost measurement".
- The guest ledger blocks the 21st turn with a Persian quota sentence.
- The local plan needs no ledger file.
- Metered plans fail closed on a corrupt ledger: a broken file refuses turns
  instead of silently granting unlimited usage.
- /plan /usage /route are known commands and read-only allowed on the phone.
"""

from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path

import pytest

import cli
from dream.agent import Dream, EchoBackend
from dream.commerce import (
    DEFAULT_LEDGER_PATH,
    GUEST_DAILY_LIMIT,
    PLANS,
    Ledger,
    LedgerConfigurationError,
    LedgerCorruptionError,
    LedgerError,
    LedgerWriteError,
    QuotaExceeded,
    active_plan,
    ledger_attached,
    usage_text,
)
from dream.memory import MemoryStore

# Any Persian letter: \u0600-\u06FF.
PERSIAN = re.compile(r"[\u0600-\u06FF]")
# Gloss: نوبت (turn)
TURN_WORD = "\u0646\u0648\u0628\u062a"

EXPECTED_PLANS = {
    "local",
    "guest",
    "daily",
    "individual_monthly",
    "individual_yearly",
    "team",
    "company",
}

FREE_PLANS = {"local", "guest"}
PAID_PLANS = EXPECTED_PLANS - FREE_PLANS


def _seed(path: str, count: int, plan: str = "guest", now: datetime | None = None) -> Ledger:
    """Write ``count`` consumed entries into a fresh ledger."""
    ledger = Ledger(path=path, plan=plan)
    for _ in range(count):
        ledger.consume(now=now)
    return ledger


def _make_dream(store: MemoryStore) -> Dream:
    return Dream(store, EchoBackend())


# ---------------------------------------------------------------------------
# Plans and pricing
# ---------------------------------------------------------------------------


def test_seven_plans_exist_and_currency_is_irr():
    assert set(PLANS) == EXPECTED_PLANS
    for plan in PLANS.values():
        assert plan.currency == "IRR"


def test_no_irr_numeric_price_except_zero_for_free_plans():
    for plan_id, plan in PLANS.items():
        expected = 0 if plan_id in FREE_PLANS else None
        assert plan.price == expected, (
            f"{plan_id} must carry price={expected!r} "
            f"({'0 for free plans' if plan_id in FREE_PLANS else 'None (TBD) for paid plans'}), "
            f"got {plan.price!r}"
        )


def test_paid_plan_prices_are_tbd_after_cost_measurement():
    for plan_id in PAID_PLANS:
        assert "TBD after cost measurement" in PLANS[plan_id].price_note


def test_local_plan_is_unlimited_free_and_not_metered():
    plan = PLANS["local"]
    assert plan.price == 0
    assert plan.metered is False
    assert plan.daily_limit is None
    assert plan.monthly_limit is None
    assert plan.yearly_limit is None


def test_guest_plan_has_twenty_turn_daily_quota():
    assert GUEST_DAILY_LIMIT == 20
    assert PLANS["guest"].daily_limit == 20
    assert PLANS["guest"].metered is True


def test_all_paid_plans_are_metered():
    for plan_id in PAID_PLANS:
        assert PLANS[plan_id].metered is True, f"{plan_id} must be metered"


# ---------------------------------------------------------------------------
# Ledger attachment and the local exemption
# ---------------------------------------------------------------------------


def test_local_plan_does_not_require_a_ledger_file(monkeypatch):
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    monkeypatch.delenv("DREAM_LEDGER", raising=False)
    assert ledger_attached() is False
    assert Ledger.from_env() is None


def test_local_plan_runs_without_any_ledger(monkeypatch, tmp_path):
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    monkeypatch.delenv("DREAM_LEDGER", raising=False)
    with MemoryStore(str(tmp_path / "local.db")) as store:
        turn = _make_dream(store).run("What is 12 x 3?")
    assert turn.tool_calls == []
    assert turn.reply  # a real reply, not a quota refusal


def test_metered_plan_attaches_a_ledger_without_explicit_path(monkeypatch):
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.delenv("DREAM_LEDGER", raising=False)
    assert ledger_attached() is True
    ledger = Ledger.from_env()
    assert ledger is not None
    assert ledger.plan_id == "guest"
    assert str(ledger.path).endswith("data/dream-ledger.json")


def test_explicit_ledger_attaches_even_with_local_plan(monkeypatch):
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    monkeypatch.setenv("DREAM_LEDGER", "data/some-ledger.json")
    assert ledger_attached() is True
    assert Ledger.from_env() is not None


def test_local_plan_with_explicit_ledger_records_but_never_blocks(monkeypatch, tmp_path):
    ledger_path = str(tmp_path / "local.json")
    monkeypatch.setenv("DREAM_PLAN", "local")
    monkeypatch.setenv("DREAM_LEDGER", ledger_path)
    ledger = Ledger.from_env()
    assert ledger is not None
    now = datetime(2026, 8, 19, 10, 0, 0)
    for _ in range(50):  # far beyond any guest quota; must never block
        ledger.consume(now=now)
    info = ledger.usage(now=now)
    assert info["limit"] is None
    assert info["used"] == 50


# ---------------------------------------------------------------------------
# Guest quota: the 21st turn is blocked with a Persian sentence
# ---------------------------------------------------------------------------


def test_guest_ledger_blocks_the_21st_turn(tmp_path):
    now = datetime(2026, 8, 19, 12, 0, 0)
    ledger = _seed(str(tmp_path / "guest.json"), GUEST_DAILY_LIMIT, plan="guest", now=now)
    assert ledger.remaining(now=now) == 0
    with pytest.raises(QuotaExceeded) as excinfo:
        ledger.consume(now=now)
    assert PERSIAN.search(str(excinfo.value))
    assert TURN_WORD in str(excinfo.value)


def test_guest_20th_turn_is_allowed_21st_is_refused(tmp_path):
    now = datetime(2026, 8, 19, 12, 0, 0)
    ledger = Ledger(path=str(tmp_path / "guest.json"), plan="guest")
    for _ in range(GUEST_DAILY_LIMIT):
        ledger.consume(now=now)
    assert ledger.usage(now=now)["used"] == GUEST_DAILY_LIMIT
    with pytest.raises(QuotaExceeded):
        ledger.consume(now=now)
    # Nothing was appended by the refused turn.
    assert ledger.usage(now=now)["used"] == GUEST_DAILY_LIMIT


def test_guest_21st_turn_blocked_end_to_end(tmp_path, monkeypatch):
    ledger_path = str(tmp_path / "guest-e2e.json")
    _seed(ledger_path, GUEST_DAILY_LIMIT, plan="guest")
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", ledger_path)
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        turn = _make_dream(store).run("What time is it?")
    assert turn.tool_calls == []
    assert turn.memories_created == []
    assert PERSIAN.search(turn.reply)
    assert TURN_WORD in turn.reply


def test_guest_quota_resets_on_a_new_day(tmp_path):
    day_one = datetime(2026, 8, 19, 23, 0, 0)
    day_two = datetime(2026, 8, 20, 0, 30, 0)
    ledger = _seed(str(tmp_path / "guest.json"), GUEST_DAILY_LIMIT, plan="guest", now=day_one)
    with pytest.raises(QuotaExceeded):
        ledger.consume(now=day_one)
    ledger.consume(now=day_two)  # new day: quota starts fresh
    assert ledger.usage(now=day_two)["used"] == 1


# ---------------------------------------------------------------------------
# Fail-closed on corruption and misconfiguration
# ---------------------------------------------------------------------------


def test_corrupt_ledger_fails_closed_for_metered_plan(tmp_path, monkeypatch):
    ledger_path = tmp_path / "broken.json"
    ledger_path.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    ledger = Ledger.from_env()
    assert ledger is not None
    with pytest.raises(LedgerCorruptionError) as excinfo:
        ledger.consume()
    assert PERSIAN.search(str(excinfo.value))
    # The corrupt file is untouched: a refused turn writes nothing.
    assert ledger_path.read_text(encoding="utf-8") == "{ this is not json"


def test_corrupt_ledger_refuses_turns_through_dream(tmp_path, monkeypatch):
    ledger_path = tmp_path / "broken-e2e.json"
    ledger_path.write_text("[]", encoding="utf-8")  # valid JSON, wrong shape
    monkeypatch.setenv("DREAM_PLAN", "daily")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        turn = _make_dream(store).run("hello")
    assert turn.tool_calls == []
    assert PERSIAN.search(turn.reply)


def test_ledger_with_malformed_entries_fails_closed(tmp_path):
    ledger_path = tmp_path / "entries.json"
    ledger_path.write_text(
        json.dumps({"version": 1, "plan": "guest", "entries": [{"ts": 123}]}),
        encoding="utf-8",
    )
    with pytest.raises(LedgerCorruptionError):
        Ledger(path=str(ledger_path), plan="guest").consume()


def test_unknown_plan_is_a_configuration_error(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_PLAN", "banana")
    with pytest.raises(LedgerConfigurationError):
        active_plan()
    with pytest.raises(LedgerConfigurationError):
        Ledger(path=str(tmp_path / "x.json"))
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        turn = _make_dream(store).run("hello")
    assert turn.tool_calls == []
    assert PERSIAN.search(turn.reply)


def test_missing_ledger_file_is_not_corruption(tmp_path):
    ledger = Ledger(path=str(tmp_path / "fresh.json"), plan="guest")
    assert ledger.consume() == 1  # a brand-new ledger starts empty, not broken


def test_ledger_persists_across_reloads(tmp_path):
    ledger_path = str(tmp_path / "persist.json")
    _seed(ledger_path, 5, plan="guest")
    fresh = Ledger(path=ledger_path, plan="guest")
    assert fresh.usage()["used"] == 5


def test_usage_summary_shape(tmp_path):
    now = datetime(2026, 8, 19, 12, 0, 0)
    ledger = _seed(str(tmp_path / "usage.json"), 3, plan="guest", now=now)
    info = ledger.usage(now=now)
    assert info["plan"] == "guest"
    assert info["currency"] == "IRR"
    assert info["price"] == 0
    assert info["window"] == "day"
    assert info["used"] == 3
    assert info["limit"] == GUEST_DAILY_LIMIT


# ---------------------------------------------------------------------------
# CLI surface: flags and slash commands
# ---------------------------------------------------------------------------


def test_plan_usage_route_are_known_commands():
    for command in ("/plan", "/usage", "/route"):
        assert command in cli.KNOWN_COMMANDS
        assert command in cli._HELP_FRAGMENTS  # type: ignore[attr-defined]


def test_plan_usage_route_are_read_only_allowed_on_the_phone():
    from cli import _PHONE_POLICY, PHONE_COMMANDS  # type: ignore[attr-defined]

    for command in ("/plan", "/usage", "/route"):
        assert command in PHONE_COMMANDS, f"{command} must be phone-reachable"
        allowed, reason = _PHONE_POLICY[command]
        assert allowed is True, f"{command} must be allowed on the phone"
        assert len(reason.strip()) > 10


def test_cli_plan_flag_exits_zero(monkeypatch, capsys):
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    assert cli.main(["--plan"]) == 0
    out = capsys.readouterr().out
    assert "Plan: local" in out
    assert "Currency: IRR" in out
    assert "Price: 0" in out


def test_cli_plan_flag_shows_tbd_price_for_paid_plan(monkeypatch, capsys):
    monkeypatch.setenv("DREAM_PLAN", "team")
    assert cli.main(["--plan"]) == 0
    out = capsys.readouterr().out
    assert "Plan: team" in out
    assert "TBD after cost measurement" in out
    assert "Price: 0" not in out


def test_cli_usage_flag_exits_zero(monkeypatch, tmp_path, capsys):
    ledger_path = str(tmp_path / "usage-flag.json")
    _seed(ledger_path, 4, plan="guest")
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", ledger_path)
    assert cli.main(["--usage"]) == 0
    out = capsys.readouterr().out
    assert "Plan: guest" in out
    assert "4 of 20 turns used" in out


def test_cli_usage_flag_without_ledger(monkeypatch, capsys):
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    monkeypatch.delenv("DREAM_LEDGER", raising=False)
    assert cli.main(["--usage"]) == 0
    assert "No usage ledger attached" in capsys.readouterr().out


def test_slash_plan_usage_route_dispatch(tmp_path, monkeypatch):
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    monkeypatch.delenv("DREAM_LEDGER", raising=False)
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = _make_dream(store)
        plan_lines: list[str] = []
        assert cli.dispatch_command("/plan", dream, plan_lines.append) is True
        assert any("Currency: IRR" in line for line in plan_lines)
        usage_lines: list[str] = []
        assert cli.dispatch_command("/usage", dream, usage_lines.append) is True
        assert any("No usage ledger attached" in line for line in usage_lines)
        route_lines: list[str] = []
        assert cli.dispatch_command("/route", dream, route_lines.append) is True
        assert any("Route:" in line for line in route_lines)


def test_env_example_documents_plan_and_ledger():
    example = Path(__file__).resolve().parent.parent / ".env.example"
    text = example.read_text(encoding="utf-8")
    assert "DREAM_PLAN=" in text
    assert "DREAM_LEDGER=" in text


def test_usage_text_reports_corruption_not_crash(tmp_path, monkeypatch):
    ledger_path = tmp_path / "broken.txt"
    ledger_path.write_text("{", encoding="utf-8")
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    text = usage_text()
    assert PERSIAN.search(text)


# ---------------------------------------------------------------------------
# S01: atomic writes
# ---------------------------------------------------------------------------


def _chmod_is_enforced(path: Path) -> bool:
    """True when the sandbox actually honours the permission bits.

    Running as root (some CI images) makes a 0o000 file readable anyway, so
    the permission-based tests skip themselves instead of lying.
    """
    try:
        if path.is_dir():
            probe = path / "probe.tmp"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
        else:
            path.read_text(encoding="utf-8")
    except OSError:
        return True
    return False


def test_consume_writes_atomically_and_leaves_no_temp_files(tmp_path):
    ledger_dir = tmp_path / "atomic"
    ledger_dir.mkdir()
    ledger = Ledger(path=str(ledger_dir / "ledger.json"), plan="guest")
    for _ in range(3):
        ledger.consume()
    # A torn write would leave a .tmp sibling behind.
    assert [entry.name for entry in ledger_dir.iterdir()] == ["ledger.json"]


def test_consume_uses_replace_so_readers_never_see_a_partial_file(tmp_path, monkeypatch):
    """The payload is fully written to a temp file before it is moved in."""
    ledger_path = tmp_path / "replace.json"
    ledger = Ledger(path=str(ledger_path), plan="guest")
    ledger.consume()
    seen: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src, dst, *args, **kwargs):
        source = Path(src)
        # At replace time the temp file already holds the complete ledger.
        payload = json.loads(source.read_text(encoding="utf-8"))
        seen.append((str(src), str(dst)))
        assert len(payload["entries"]) == 2
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr("dream.commerce.os.replace", spy)
    ledger.consume()
    assert len(seen) == 1
    src, dst = seen[0]
    assert dst == str(ledger_path)
    assert src != str(ledger_path)
    assert Path(src).parent == ledger_path.parent  # same filesystem: rename is atomic


def test_failed_write_keeps_the_previous_ledger_intact(tmp_path, monkeypatch):
    ledger_path = tmp_path / "intact.json"
    ledger = Ledger(path=str(ledger_path), plan="guest")
    ledger.consume()
    before = ledger_path.read_text(encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("dream.commerce.os.replace", boom)
    with pytest.raises(LedgerWriteError):
        ledger.consume()
    # Old content survives untouched and no temp file is left behind.
    assert ledger_path.read_text(encoding="utf-8") == before
    assert [entry.name for entry in tmp_path.iterdir()] == ["intact.json"]


def test_unrecorded_turn_is_not_counted_as_used(tmp_path, monkeypatch):
    ledger_path = tmp_path / "notcounted.json"
    ledger = Ledger(path=str(ledger_path), plan="guest")
    ledger.consume()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("dream.commerce.os.replace", boom)
    with pytest.raises(LedgerWriteError):
        ledger.consume()
    monkeypatch.undo()
    assert ledger.usage()["used"] == 1


def test_unwritable_ledger_directory_fails_closed(tmp_path):
    ledger_dir = tmp_path / "readonly"
    ledger_dir.mkdir()
    ledger_path = ledger_dir / "ledger.json"
    Ledger(path=str(ledger_path), plan="guest").consume()
    ledger_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        if not _chmod_is_enforced(ledger_dir):
            pytest.skip("filesystem does not enforce directory permissions here")
        ledger = Ledger(path=str(ledger_path), plan="guest")
        with pytest.raises(LedgerWriteError) as excinfo:
            ledger.consume()
        assert PERSIAN.search(str(excinfo.value))
        assert isinstance(excinfo.value, LedgerError)  # Dream refuses the turn
    finally:
        ledger_dir.chmod(stat.S_IRWXU)


def test_unwritable_ledger_refuses_the_turn_through_dream(tmp_path, monkeypatch):
    ledger_dir = tmp_path / "ro-e2e"
    ledger_dir.mkdir()
    ledger_path = ledger_dir / "ledger.json"
    Ledger(path=str(ledger_path), plan="daily").consume()
    ledger_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        if not _chmod_is_enforced(ledger_dir):
            pytest.skip("filesystem does not enforce directory permissions here")
        monkeypatch.setenv("DREAM_PLAN", "daily")
        monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
        with MemoryStore(str(tmp_path / "dream.db")) as store:
            turn = _make_dream(store).run("hello")
        assert turn.tool_calls == []
        assert turn.memories_created == []
        assert PERSIAN.search(turn.reply)
    finally:
        ledger_dir.chmod(stat.S_IRWXU)


# ---------------------------------------------------------------------------
# S01: fail-closed reads — every flavour of corruption
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("empty", ""),
        ("whitespace", "   \n"),
        ("truncated", '{"version": 1, "plan": "guest", "entries": [{"ts": "2026-'),
        ("json_list", "[]"),
        ("json_string", '"entries"'),
        ("json_null", "null"),
        ("entries_not_a_list", '{"version": 1, "entries": {}}'),
        ("entries_missing", '{"version": 1, "plan": "guest"}'),
        ("entry_not_a_dict", '{"version": 1, "entries": ["2026-08-19"]}'),
        ("entry_without_ts", '{"version": 1, "entries": [{"when": "2026-08-19"}]}'),
        ("entry_ts_not_a_string", '{"version": 1, "entries": [{"ts": 1755600000}]}'),
        ("entry_ts_unparsable", '{"version": 1, "entries": [{"ts": "yesterday"}]}'),
    ],
)
def test_every_corrupt_shape_denies_the_turn(tmp_path, name, content):
    ledger_path = tmp_path / f"{name}.json"
    ledger_path.write_text(content, encoding="utf-8")
    ledger = Ledger(path=str(ledger_path), plan="guest")
    with pytest.raises(LedgerCorruptionError) as excinfo:
        ledger.consume()
    assert PERSIAN.search(str(excinfo.value))
    # Fail closed: the refused turn wrote nothing.
    assert ledger_path.read_text(encoding="utf-8") == content


def test_non_utf8_ledger_is_corruption_not_a_crash(tmp_path):
    ledger_path = tmp_path / "binary.json"
    ledger_path.write_bytes(b"\xff\xfe\x00\x01 not text")
    with pytest.raises(LedgerCorruptionError):
        Ledger(path=str(ledger_path), plan="guest").consume()


def test_ledger_path_that_is_a_directory_is_corruption(tmp_path):
    ledger_path = tmp_path / "ledger-as-dir.json"
    ledger_path.mkdir()
    with pytest.raises(LedgerCorruptionError):
        Ledger(path=str(ledger_path), plan="guest").consume()


def test_unreadable_ledger_file_is_corruption(tmp_path):
    ledger_path = tmp_path / "unreadable.json"
    Ledger(path=str(ledger_path), plan="guest").consume()
    ledger_path.chmod(0o000)
    try:
        if not _chmod_is_enforced(ledger_path):
            pytest.skip("filesystem does not enforce file permissions here")
        with pytest.raises(LedgerCorruptionError):
            Ledger(path=str(ledger_path), plan="guest").consume()
    finally:
        ledger_path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_corrupt_ledger_denies_even_with_quota_left(tmp_path):
    """Corruption is not "assume zero used": it is a refusal."""
    ledger_path = tmp_path / "corrupt-with-room.json"
    ledger_path.write_text("{ broken", encoding="utf-8")
    ledger = Ledger(path=str(ledger_path), plan="company")  # 20000-turn plan
    with pytest.raises(LedgerCorruptionError):
        ledger.consume()
    with pytest.raises(LedgerCorruptionError):
        ledger.usage()
    with pytest.raises(LedgerCorruptionError):
        ledger.remaining()


def test_corrupt_ledger_denies_every_metered_plan(tmp_path):
    for plan_id in sorted(PAID_PLANS | {"guest"}):
        ledger_path = tmp_path / f"corrupt-{plan_id}.json"
        ledger_path.write_text("{ broken", encoding="utf-8")
        with pytest.raises(LedgerCorruptionError):
            Ledger(path=str(ledger_path), plan=plan_id).consume()


def test_corruption_appearing_mid_session_still_denies(tmp_path):
    """A ledger that goes bad between turns is re-read, not trusted from cache."""
    ledger_path = tmp_path / "goes-bad.json"
    ledger = Ledger(path=str(ledger_path), plan="guest")
    ledger.consume()
    ledger_path.write_text("{ corrupted by something else", encoding="utf-8")
    with pytest.raises(LedgerCorruptionError):
        ledger.consume()


# ---------------------------------------------------------------------------
# S01: environment fallbacks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["guest", "GUEST", "  Guest  ", "gUeSt\n"])
def test_plan_name_is_case_and_whitespace_insensitive(monkeypatch, raw):
    monkeypatch.setenv("DREAM_PLAN", raw)
    assert active_plan().id == "guest"
    assert ledger_attached() is True
    assert Ledger().plan_id == "guest"


@pytest.mark.parametrize("raw", ["", "   ", "local", "  LOCAL  "])
def test_blank_or_local_plan_means_local_and_no_ledger(monkeypatch, raw):
    monkeypatch.setenv("DREAM_PLAN", raw)
    monkeypatch.delenv("DREAM_LEDGER", raising=False)
    assert active_plan().id == "local"
    assert ledger_attached() is False
    assert Ledger.from_env() is None


def test_blank_ledger_env_does_not_attach_a_ledger(monkeypatch):
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    monkeypatch.setenv("DREAM_LEDGER", "   ")
    assert ledger_attached() is False
    assert Ledger.from_env() is None


def test_blank_ledger_env_falls_back_to_the_default_path(monkeypatch):
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", "  ")
    assert Path(Ledger().path) == Path(DEFAULT_LEDGER_PATH)


def test_explicit_path_argument_beats_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_LEDGER", str(tmp_path / "from-env.json"))
    chosen = tmp_path / "explicit.json"
    assert Ledger(path=str(chosen), plan="guest").path == chosen


def test_explicit_plan_argument_beats_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_PLAN", "guest")
    ledger = Ledger(path=str(tmp_path / "x.json"), plan="team")
    assert ledger.plan_id == "team"


def test_unknown_plan_in_env_denies_instead_of_defaulting(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_PLAN", "enterprise-plus")
    monkeypatch.setenv("DREAM_LEDGER", str(tmp_path / "x.json"))
    # A typo must never be silently downgraded to local (free unlimited).
    assert ledger_attached() is True
    with pytest.raises(LedgerConfigurationError):
        Ledger.from_env()


# ---------------------------------------------------------------------------
# S01: concurrency — two ledger objects over one file
# ---------------------------------------------------------------------------


def test_two_ledgers_on_one_file_do_not_lose_entries(tmp_path):
    ledger_path = str(tmp_path / "shared.json")
    first = Ledger(path=ledger_path, plan="guest")
    second = Ledger(path=ledger_path, plan="guest")
    for _ in range(5):
        first.consume()
        second.consume()  # interleaved: each read-modify-write re-reads disk
    payload = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 10
    assert first.usage()["used"] == 10
    assert second.usage()["used"] == 10


def test_quota_is_shared_across_ledger_objects(tmp_path):
    ledger_path = str(tmp_path / "shared-quota.json")
    now = datetime(2026, 8, 19, 9, 0, 0)
    first = Ledger(path=ledger_path, plan="guest")
    second = Ledger(path=ledger_path, plan="guest")
    for _ in range(GUEST_DAILY_LIMIT):
        first.consume(now=now)
    # The second object was created before those turns; it must still refuse.
    with pytest.raises(QuotaExceeded):
        second.consume(now=now)


# ---------------------------------------------------------------------------
# S01: the meter is opt-in, and it never records secrets
# ---------------------------------------------------------------------------


def test_default_dream_has_no_attached_meter(monkeypatch, tmp_path):
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    monkeypatch.delenv("DREAM_LEDGER", raising=False)
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)  # the default ledger path is relative to cwd
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, EchoBackend())
        assert dream.ledger is None
        assert dream.ledger_attached is False
        assert dream.run("hello").reply  # a real reply, not a refusal
    # Running a local turn creates no ledger file anywhere.
    assert not (workdir / DEFAULT_LEDGER_PATH).exists()
    assert list(workdir.rglob("*.json")) == []


def test_dream_attaches_a_meter_for_a_metered_plan(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(tmp_path / "attached.json"))
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, EchoBackend())
        assert dream.ledger_attached is True
        assert dream.ledger is not None
        dream.run("hello")
        assert dream.ledger.usage()["used"] == 1


def test_dream_attaches_a_meter_when_only_the_ledger_env_is_set(monkeypatch, tmp_path):
    monkeypatch.delenv("DREAM_PLAN", raising=False)
    monkeypatch.setenv("DREAM_LEDGER", str(tmp_path / "explicit.json"))
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, EchoBackend())
        assert dream.ledger_attached is True


def test_misconfigured_plan_still_counts_as_attached(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_PLAN", "banana")
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, EchoBackend())
        assert dream.ledger_attached is True  # fail-closed: the gate stays on
        assert PERSIAN.search(dream.run("hello").reply)


def test_ledger_records_timestamps_only_and_no_secrets(tmp_path, monkeypatch):
    ledger_path = tmp_path / "no-secrets.json"
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-value")
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        _make_dream(store).run("my password is hunter2")
    text = ledger_path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert set(payload) == {"version", "plan", "entries"}
    for entry in payload["entries"]:
        assert set(entry) == {"ts"}
    assert "sk-super-secret-value" not in text
    assert "hunter2" not in text


def test_usage_readout_never_leaks_the_ledger_path(tmp_path, monkeypatch):
    """/usage is phone-reachable: it must not disclose filesystem paths."""
    ledger_path = tmp_path / "secret-place" / "ledger.json"
    ledger_path.parent.mkdir()
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    Ledger.from_env().consume()
    text = usage_text()
    assert "Plan: guest" in text
    assert str(ledger_path) not in text
    assert "secret-place" not in text
    info = Ledger.from_env().usage()
    assert "path" not in info
    assert str(ledger_path) not in json.dumps(info)


def test_corrupt_ledger_message_does_not_leak_the_path(tmp_path, monkeypatch):
    ledger_path = tmp_path / "private-dir" / "broken.json"
    ledger_path.parent.mkdir()
    ledger_path.write_text("{ broken", encoding="utf-8")
    monkeypatch.setenv("DREAM_PLAN", "guest")
    monkeypatch.setenv("DREAM_LEDGER", str(ledger_path))
    text = usage_text()
    assert PERSIAN.search(text)
    assert "private-dir" not in text
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        reply = _make_dream(store).run("hi").reply
    assert "private-dir" not in reply
