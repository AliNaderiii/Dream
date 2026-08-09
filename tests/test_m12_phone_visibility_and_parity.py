"""Pins M12: phone skill visibility, interface parity, and search vs dispatch.

What this pins and what evidence justified it:

- Defect one (skills invisible on phone): measured on a fresh clone of merged
  main today with one real skill saved. Terminal /skills lists the skill and
  its file name while phone /skills replies "This command is not available in
  Telegram." Same for /skill QUERY and phone /help never mentions skills.
  The phone allowlist held ten entries while the terminal knew fourteen; six
  terminal commands were unreachable. The owner can already teach a procedure
  by talking on the phone (save_skill/use_skill are registered in the phone
  conversation) but cannot see, search, or check what was learned. These tests
  pin that /skills and /skill must be reachable from the phone and list/search
  the same file-backed skills the terminal sees, with Persian replies readable
  on the phone.

- Defect two (two lists drift silently): the terminal keeps KNOWN_COMMANDS,
  the phone keeps a separate CHAT_COMMANDS frozenset and a third hand-written
  CHAT_HELP string. Nothing compared them; the forget command existed in the
  terminal for several milestones before being patched into the phone, caught
  by the owner not the suite. These tests pin that the phone help line must
  agree with the phone allowlist and that the terminal and phone command sets
  must not drift; a test must fail when they disagree. A single source of
  truth with generated help satisfies the principal engineer's veto; if the
  lists stay separate the test is the enforcement.

- Defect three (search vs dispatch are not the same question): with one skill
  saved (renewing car insurance) terminal /skill bime returned "No skill
  matches" while /skill bime mashin and tamdid bime found it. Widened to five
  realistic skills, every single-word query (bime, chay, qatar, tamdid)
  returned nothing. The cause is deliberate: the matcher requires a fraction
  of the skill's own words (1/3) and a floor of two shared stems so one
  generic word can never summon a procedure the assistant then follows. That
  bar is correct for dispatch (use_skill) where a false positive means the
  wrong procedure is followed, but wrong for search (/skill QUERY) where the
  owner typed the word and reads the result; a false negative means he
  concludes the skill was never saved. These tests pin that the single-word
  queries find their genuine skills through the phone and terminal search
  path while the dispatch bar does not move (use_skill stays strict).

Break-and-restore is required: every new test was observed failing against
deliberate breaks and green after checkout (messages in PR).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import cli
from dream import tools as dream_tools
from dream.memory import MemoryStore
from dream.telegram import TelegramBot

OWNER = 4242

# Persian literals as backslash-u escapes (repo convention).
# Gloss: تمدید بیمه ماشین
BIME_MASHIN_NAME = "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"  # noqa: E501
BIME_MASHIN_DESC = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f \u0628\u06cc\u0645\u0647 "
    "\u0645\u0627\u0634\u06cc\u0646 \u0631\u0627 \u062a\u0645\u062f\u06cc\u062f \u06a9\u0646\u062f"
)
# Gloss: بیمه
BIME_QUERY = "\u0628\u06cc\u0645\u0647"
# Gloss: چای دم کردن
CHAY_NAME = "\u0686\u0627\u06cc \u062f\u0645 \u06a9\u0631\u062f\u0646"
CHAY_DESC = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f \u0686\u0627\u06cc "
    "\u062f\u0631\u0633\u062a \u06a9\u0646\u062f"
)
# Gloss: چای
CHAY_QUERY = "\u0686\u0627\u06cc"
# Gloss: سفر به قطر
QATAR_NAME = "\u0633\u0641\u0631 \u0628\u0647 \u0642\u0637\u0631"
QATAR_DESC = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f \u0628\u0647 \u0642\u0637\u0631 "
    "\u0633\u0641\u0631 \u06a9\u0646\u062f"
)
QATAR_QUERY = "\u0642\u0637\u0631"
# Gloss: تمدید
TAMDID_QUERY = "\u062a\u0645\u062f\u06cc\u062f"
# Gloss: پرداخت قسط
QESR_NAME = "\u067e\u0631\u062f\u0627\u062e\u062a \u0642\u0633\u0637"
QESR_DESC = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f \u0642\u0633\u0637 "
    "\u0648\u0627\u0645 \u0631\u0627 \u067e\u0631\u062f\u0627\u062e\u062a \u06a9\u0646\u062f"
)
# Gloss: تمدید بیمه موتور
BIME_MOTOR_NAME = "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0648\u062a\u0648\u0631"  # noqa: E501
BIME_MOTOR_DESC = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f \u0628\u06cc\u0645\u0647 "
    "\u0645\u0648\u062a\u0648\u0631 \u0631\u0627 \u062a\u0645\u062f\u06cc\u062f \u06a9\u0646\u062f"
)
# Gloss: پیامک تبریک تولد
SMS_BDAY_NAME = "\u067e\u06cc\u0627\u0645\u06a9 \u062a\u0628\u0631\u06cc\u06a9 \u062a\u0648\u0644\u062f"  # noqa: E501
SMS_BDAY_DESC = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f \u0628\u0631\u0627\u06cc "
    "\u062a\u0648\u0644\u062f \u062f\u0648\u0633\u062a\u0634 "
    "\u067e\u06cc\u0627\u0645\u06a9 \u062a\u0628\u0631\u06cc\u06a9 \u0628\u0646\u0648\u06cc\u0633\u062f"  # noqa: E501
)
SMS_NDAY_NAME = "\u067e\u06cc\u0627\u0645\u06a9 \u062a\u0628\u0631\u06cc\u06a9 \u0633\u0627\u0644 \u0646\u0648"  # noqa: E501
SMS_NDAY_DESC = (
    "\u0648\u0642\u062a\u06cc \u06a9\u0627\u0631\u0628\u0631 "
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u062f \u0628\u0631\u0627\u06cc "
    "\u0633\u0627\u0644 \u0646\u0648 \u0628\u0647 \u062e\u0627\u0646\u0648\u0627\u062f\u0647 "
    "\u067e\u06cc\u0627\u0645\u06a9 \u062a\u0628\u0631\u06cc\u06a9 \u0628\u0641\u0631\u0633\u062a\u062f"  # noqa: E501
)
BDAY_QUERY = (
    "\u0628\u0631\u0627\u06cc \u062a\u0648\u0644\u062f "
    "\u0631\u0641\u06cc\u0642\u0645 \u0686\u06cc \u0628\u0646\u0648\u06cc\u0633\u0645\u061f"
)
NDAY_QUERY = (
    "\u062a\u0628\u0631\u06cc\u06a9 \u0633\u0627\u0644 \u0646\u0648 "
    "\u0628\u0647 \u0641\u0627\u0645\u06cc\u0644\u0645 \u0686\u06cc \u0628\u06af\u0645\u061f"
)
DOLLAR_QUERY = (
    "\u0642\u06cc\u0645\u062a \u062f\u0644\u0627\u0631 "
    "\u0627\u0645\u0631\u0648\u0632 \u0686\u0642\u062f\u0631 \u0627\u0633\u062a\u061f"
)


def _fake_token() -> str:
    return "123456789:" + "A_b-c" * 7


def _update(update_id: int, chat_id: int, text: str, *, user_id: int | None = None):
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id if user_id is None else user_id},
            "text": text,
        },
    }


class FakeTransport:
    def __init__(self):
        self.sent: list[tuple[int, str, float]] = []
        self.actions: list[tuple[int, str, float]] = []
        self.poll_calls: list[dict] = []

    def get_updates(self, *, offset, allowed_updates, poll_timeout, http_timeout):
        self.poll_calls.append(
            {
                "offset": offset,
                "allowed_updates": tuple(allowed_updates),
                "poll_timeout": poll_timeout,
                "http_timeout": http_timeout,
            }
        )
        return []

    def send_message(self, *, chat_id, text, http_timeout):
        self.sent.append((chat_id, text, http_timeout))

    def send_chat_action(self, *, chat_id, action, http_timeout):
        self.actions.append((chat_id, action, http_timeout))


def _make_bot(store: MemoryStore, transport: FakeTransport) -> TelegramBot:
    return TelegramBot(
        _fake_token(),
        store,
        transport=transport,
        allowed_user=OWNER,
        backend_factory=lambda: SimpleNamespace(
            run=lambda msg: SimpleNamespace(reply="dummy")
        ),
        output=lambda x: None,
    )


# ---------------------------------------------------------------------------
# Defect one: phone can list and search skills
# ---------------------------------------------------------------------------


def test_phone_lists_saved_skill(tmp_path):
    tmp = tmp_path / "ws_list"
    tmp.mkdir()
    dream_tools.WORKSPACE_ROOT = tmp.resolve()
    db = str(tmp_path / "list.db")
    transport = FakeTransport()
    with MemoryStore(db) as store:
        from dream import skills as skills_module

        skills_module.save_skill(
            BIME_MASHIN_NAME,
            BIME_MASHIN_DESC,
            ["\u0645\u0631\u062d\u0644\u0647 1", "\u0645\u0631\u062d\u0644\u0647 2"],
        )
        bot = _make_bot(store, transport)
        bot.process_updates([_update(1, OWNER, "/skills")])
        assert transport.sent, "phone should have replied"
        reply = transport.sent[-1][1]
        assert BIME_MASHIN_NAME in reply
        assert "skills/" in reply


def test_phone_finds_skill_by_persian_single_word(tmp_path):
    tmp = tmp_path / "ws_find"
    tmp.mkdir()
    dream_tools.WORKSPACE_ROOT = tmp.resolve()
    db = str(tmp_path / "find.db")
    transport = FakeTransport()
    with MemoryStore(db) as store:
        from dream import skills as skills_module

        skills_module.save_skill(
            BIME_MASHIN_NAME,
            BIME_MASHIN_DESC,
            ["\u0645\u0631\u062d\u0644\u0647 1", "\u0645\u0631\u062d\u0644\u0647 2"],
        )
        bot = _make_bot(store, transport)
        bot.process_updates([_update(2, OWNER, f"/skill {BIME_QUERY}")])
        assert transport.sent
        reply = transport.sent[-1][1]
        assert "not available" not in reply.lower()
        assert "No skill matches" not in reply
        assert BIME_MASHIN_NAME in reply


def test_terminal_and_phone_share_skill_file(tmp_path):
    """Phone listing after terminal save sees same file."""
    tmp = tmp_path / "ws_shared"
    tmp.mkdir()
    dream_tools.WORKSPACE_ROOT = tmp.resolve()
    db = str(tmp_path / "shared.db")
    transport = FakeTransport()
    with MemoryStore(db) as store:
        from dream import skills as skills_module
        from dream.agent import Dream, EchoBackend

        dream = Dream(store, EchoBackend())
        skills_module.save_skill(
            CHAY_NAME,
            CHAY_DESC,
            ["\u06a9\u062a\u0631\u06cc \u0631\u0627 \u067e\u0631 \u06a9\u0646"],
        )
        cli_out: list[str] = []
        cli.dispatch_command("/skills", dream, cli_out.append)
        terminal_text = "\n".join(cli_out)
        assert CHAY_NAME in terminal_text

        bot = _make_bot(store, transport)
        bot.process_updates([_update(3, OWNER, "/skills")])
        phone_reply = transport.sent[-1][1]
        assert CHAY_NAME in phone_reply


# ---------------------------------------------------------------------------
# Defect two: parity - help vs allowlist and terminal vs phone
# ---------------------------------------------------------------------------


def test_phone_help_agrees_with_allowlist():
    from dream.telegram import CHAT_COMMANDS, CHAT_HELP

    help_cmds = set(re.findall(r"/[a-z\\-]+", CHAT_HELP.lower()))
    from cli import _COMMAND_ALIASES  # type: ignore

    canonical_in_help = {_COMMAND_ALIASES.get(cmd, cmd) for cmd in help_cmds}
    canonical_allow = {_COMMAND_ALIASES.get(cmd, cmd) for cmd in CHAT_COMMANDS}
    assert (
        canonical_in_help == canonical_allow | {"/help"}
        or canonical_in_help == canonical_allow
    ), f"help {help_cmds} vs allow {CHAT_COMMANDS}"


def test_phone_help_mentions_skills():
    from dream.telegram import CHAT_HELP

    assert "/skills" in CHAT_HELP
    assert "/skill" in CHAT_HELP


def test_terminal_and_phone_parity():
    from cli import _PHONE_POLICY, KNOWN_COMMANDS  # type: ignore
    from dream.telegram import CHAT_COMMANDS

    for cmd in KNOWN_COMMANDS:
        assert cmd in _PHONE_POLICY, f"{cmd} missing phone policy (drift)"
    from cli import _COMMAND_ALIASES  # type: ignore

    allowed_canonical = {
        cmd for cmd, (allowed, _) in _PHONE_POLICY.items() if allowed
    }
    expected = set(allowed_canonical) | {
        alias for alias, canon in _COMMAND_ALIASES.items() if canon in allowed_canonical
    }
    assert CHAT_COMMANDS == expected, f"CHAT {CHAT_COMMANDS} vs {expected}"


def test_six_unreachable_commands_have_explicit_decision():
    """The six commands unreachable before M12 must each have a decision."""
    from cli import _PHONE_POLICY  # type: ignore

    six = ["/dedupe", "/pin", "/skill", "/skills", "/stats", "/tools"]
    for cmd in six:
        assert cmd in _PHONE_POLICY
        allowed, reason = _PHONE_POLICY[cmd]
        assert isinstance(allowed, bool)
        assert isinstance(reason, str) and len(reason.strip()) > 10


# ---------------------------------------------------------------------------
# Defect three: permissive search vs strict dispatch
# ---------------------------------------------------------------------------


def test_single_word_search_finds_skill_while_dispatch_stays_strict(tmp_path):
    tmp = tmp_path / "ws_search"
    tmp.mkdir()
    dream_tools.WORKSPACE_ROOT = tmp.resolve()
    from dream import skills as skills_module

    for p in (tmp / "skills").glob("*"):
        p.unlink()
    skills_module.save_skill(BIME_MASHIN_NAME, BIME_MASHIN_DESC, ["a"])
    skills_module.save_skill(BIME_MOTOR_NAME, BIME_MOTOR_DESC, ["a"])
    skills_module.save_skill(CHAY_NAME, CHAY_DESC, ["a"])
    skills_module.save_skill(QATAR_NAME, QATAR_DESC, ["a"])
    skills_module.save_skill(QESR_NAME, QESR_DESC, ["a"])

    assert skills_module.find_skill(BIME_QUERY) is None
    assert skills_module.find_skill(CHAY_QUERY) is None
    assert skills_module.find_skill(QATAR_QUERY) is None
    assert skills_module.find_skill(TAMDID_QUERY) is None

    bime_hits = skills_module.score_skills(BIME_QUERY, permissive=True)
    assert len([s for s in bime_hits if BIME_QUERY in s.name]) >= 2
    chay_hits = skills_module.score_skills(CHAY_QUERY, permissive=True)
    assert any(CHAY_QUERY in s.name for s in chay_hits)
    qatar_hits = skills_module.score_skills(QATAR_QUERY, permissive=True)
    assert any(QATAR_QUERY in s.name for s in qatar_hits)
    tamdid_hits = skills_module.score_skills(TAMDID_QUERY, permissive=True)
    assert len(tamdid_hits) >= 2


def test_dispatch_bar_did_not_move(tmp_path):
    """Strict bar unchanged: two-word genuine still needs both, unrelated none."""
    tmp = tmp_path / "ws_bar"
    tmp.mkdir()
    dream_tools.WORKSPACE_ROOT = tmp.resolve()
    from dream import skills as skills_module

    skills_module.save_skill(SMS_BDAY_NAME, SMS_BDAY_DESC, ["a"])
    skills_module.save_skill(SMS_NDAY_NAME, SMS_NDAY_DESC, ["a"])
    from dream.skills import find_skill, score_skills

    bday = find_skill(BDAY_QUERY)
    assert bday is not None and bday.name == SMS_BDAY_NAME
    nday = find_skill(NDAY_QUERY)
    assert nday is not None and nday.name == SMS_NDAY_NAME
    bday_scores = score_skills(BDAY_QUERY)
    assert not any(s.name == SMS_NDAY_NAME for s in bday_scores)
    assert find_skill(DOLLAR_QUERY) is None
