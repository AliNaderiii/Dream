"""Tests for Persian normalisation, stemming and the memory store."""

from __future__ import annotations

import io
import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError

import pytest

import cli
import doctor
from dream import tools
from dream.agent import (
    _MEMORIES_OPEN,
    DEFAULT_USER_AGENT,
    ApprovalPolicy,
    Dream,
    EchoBackend,
    OpenAIBackend,
)
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


# --------------------------------------------------------------------------
# Agent runtime
# --------------------------------------------------------------------------


def test_approval_policy_auto_approves_safe_and_guarded():
    policy = ApprovalPolicy()
    assert policy.allows("calculate", {})[0] is True
    assert policy.allows("write_note", {})[0] is True


def test_approval_policy_blocks_dangerous_without_approver():
    assert ApprovalPolicy().allows("run_shell", {"command": "echo no"})[0] is False


def test_approval_policy_allows_dangerous_with_approver():
    policy = ApprovalPolicy(ask=lambda name, arguments: True)
    assert policy.allows("run_shell", {"command": "echo yes"})[0] is True


def test_approval_policy_respects_denial():
    policy = ApprovalPolicy(ask=lambda name, arguments: False)
    assert policy.allows("run_shell", {"command": "echo no"})[0] is False


def test_approval_policy_uses_registry_risk_not_arguments():
    policy = ApprovalPolicy()
    assert policy.allows("run_shell", {"risk": "safe"})[0] is False


def test_dream_registers_store_memory_tools(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        Dream(store, EchoBackend())
        assert {"remember_fact", "search_memory", "forget_memory"} <= tools.REGISTRY.keys()
        tools.execute("remember_fact", {"content": "bound to this store"})
        assert store.recall("bound")


def test_agent_invokes_datetime_tool(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        turn = Dream(store, EchoBackend()).run("What time is it?")
        assert turn.tool_calls[0]["name"] == "get_datetime"
        assert "Result:" in turn.reply


def test_agent_invokes_calculate_tool(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        turn = Dream(store, EchoBackend()).run("What is 12 × 3?")
        assert turn.tool_calls[0]["name"] == "calculate"
        assert "36" in turn.reply


def test_recalled_memory_is_injected_into_backend_messages(tmp_path):
    class CaptureBackend(EchoBackend):
        def __init__(self):
            self.messages = []

        def chat(self, messages, tools=None):
            if tools is not None:
                self.messages = messages
            return {"content": "done", "tool_calls": []}

    with MemoryStore(str(tmp_path / "dream.db")) as store:
        store.remember("My favorite drink is coffee")
        backend = CaptureBackend()
        Dream(store, backend).run("What is my favorite drink?")
        assert "My favorite drink is coffee" in backend.messages[0]["content"]
        assert _MEMORIES_OPEN in backend.messages[0]["content"]
        assert "RECALLED MEMORIES" not in backend.messages[0]["content"]


def test_agent_journal_records_user_and_assistant(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        Dream(store, EchoBackend()).run("hello")
        assert [entry["role"] for entry in store.recent_journal()] == ["user", "assistant"]


def test_reset_session_keeps_durable_memory(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        store.remember("persistent fact")
        dream = Dream(store, EchoBackend())
        dream.run("hello")
        dream.reset_session()
        assert dream.history == []
        assert store.recall("persistent")


def test_dangerous_shell_is_blocked_end_to_end(tmp_path):
    class ShellBackend:
        def __init__(self):
            self.tool_result = ""

        def chat(self, messages, tools=None):
            if messages[-1]["role"] == "tool":
                self.tool_result = messages[-1]["content"]
                return {"content": "I cannot run that.", "tool_calls": []}
            return {
                "content": None,
                "tool_calls": [
                    {"id": "shell", "name": "run_shell", "arguments": {"command": "exit 99"}}
                ],
            }

    with MemoryStore(str(tmp_path / "dream.db")) as store:
        backend = ShellBackend()
        turn = Dream(store, backend, ApprovalPolicy()).run("run a command")
        assert turn.tool_calls[0]["allowed"] is False
        assert '"blocked": true' in backend.tool_result
        assert "denied" in backend.tool_result


# --------------------------------------------------------------------------
# User-facing entry points
# --------------------------------------------------------------------------


def test_demo_runs_offline_end_to_end(tmp_path):
    output = []
    cli.run_demo(str(tmp_path / "demo.db"), output.append)
    joined = "\n".join(output)
    assert "1. Seeding" in joined
    assert "5. Approval gate" in joined
    assert '"blocked": true' in joined


def test_all_slash_commands_dispatch(tmp_path):
    output = []
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        memory = store.remember("command test")
        dream = Dream(store, EchoBackend())
        for command in ("/mem command", "/mems", "/stats", "/tools", "/reset", "/help", "/unknown"):
            assert cli.dispatch_command(command, dream, output.append) is True
        assert cli.dispatch_command(f"/forget {memory.id}", dream, output.append) is True
        assert cli.dispatch_command("/exit", dream, output.append) is False
    assert any("Unknown command" in line for line in output)


def test_forget_non_numeric_argument_is_graceful(tmp_path):
    output = []
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        assert cli.dispatch_command("/forget nope", Dream(store, EchoBackend()), output.append)
    assert output == ["Usage: /forget ID — ID must be a number."]


def test_colour_is_suppressed_for_non_tty():
    class PlainStream:
        def isatty(self):
            return False

    assert cli._style("hello", "31", PlainStream()) == "hello"


def test_doctor_offline_checks_pass():
    output = []
    assert doctor.run_checks(output=output.append)
    assert all(line.startswith("PASS") for line in output)


def test_doctor_fails_when_registry_is_empty(monkeypatch):
    output = []
    monkeypatch.setattr(doctor, "REGISTRY", {})
    assert doctor.run_checks(output=output.append) is False
    assert any(line.startswith("FAIL Tool registry") for line in output)


def test_doctor_masks_api_key(monkeypatch):
    output = []
    key = "sk-very-secret-key-value"
    monkeypatch.setenv("OPENAI_API_KEY", key)
    assert doctor.run_checks(output=output.append)
    assert key not in "\n".join(output)


def test_cli_yolo_is_not_default_and_warns(tmp_path, monkeypatch, capsys):
    assert cli.build_parser().parse_args([]).yolo is False
    monkeypatch.setattr("builtins.input", lambda prompt: (_ for _ in ()).throw(EOFError))
    assert cli.main(["--yolo", "--db", str(tmp_path / "yolo.db")]) == 0
    assert "WARNING: --yolo auto-approves dangerous tools." in capsys.readouterr().out


# --------------------------------------------------------------------------
# Chat-completions wire format
# --------------------------------------------------------------------------


class _FakeResponse:
    """Stand-in for the file-like object ``urlopen`` returns on success."""

    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def _http_error(code: int, body: str) -> HTTPError:
    """Build an HTTPError carrying a readable response body, as urllib does."""
    return HTTPError(
        "http://model.test/v1/chat/completions",
        code,
        "Bad Request",
        {},
        io.BytesIO(body.encode("utf-8")),
    )


def _reply(content: str | None = None, tool_calls: list[dict] | None = None) -> dict:
    """Build a chat-completions response body."""
    message: dict = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


class StrictChatServer:
    """A mock endpoint that rejects malformed assistant tool calls.

    It applies the validation a real chat-completions server applies: every
    tool call must carry ``"type": "function"``, must nest ``name`` and
    ``arguments`` under ``function``, and ``arguments`` must be a JSON string.
    """

    def __init__(self, *replies: dict) -> None:
        self.replies = list(replies)
        self.requests: list[dict] = []

    def __call__(self, request, timeout: int | None = None) -> _FakeResponse:
        payload = json.loads(request.data.decode("utf-8"))
        self.requests.append(payload)
        for message in payload["messages"]:
            for call in message.get("tool_calls") or []:
                self._validate(call)
        return _FakeResponse(self.replies.pop(0))

    @staticmethod
    def _validate(call: dict) -> None:
        if call.get("type") != "function":
            raise _http_error(400, '{"error": {"message": "tool_calls.0.type must be function"}}')
        function = call.get("function")
        if not isinstance(function, dict) or not function.get("name"):
            raise _http_error(400, '{"error": {"message": "tool_calls.0.function is missing"}}')
        if not isinstance(function.get("arguments"), str):
            raise _http_error(
                400, '{"error": {"message": "tool_calls.0.function.arguments must be a string"}}'
            )
        if not call.get("id"):
            raise _http_error(400, '{"error": {"message": "tool_calls.0.id must not be empty"}}')


def _assistant_tool_message(history: list[dict]) -> dict:
    return next(message for message in history if message.get("tool_calls"))


def test_assistant_tool_call_is_written_in_wire_format(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, EchoBackend())
        dream.run("What time is it?")
        call = _assistant_tool_message(dream.history)["tool_calls"][0]
        assert call["type"] == "function"
        assert isinstance(call["function"], dict)
        assert call["function"]["name"] == "get_datetime"
        assert "name" not in call


def test_assistant_tool_call_arguments_are_a_json_string(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, EchoBackend())
        dream.run("What is 12 × 3?")
        arguments = _assistant_tool_message(dream.history)["tool_calls"][0]["function"]["arguments"]
        assert isinstance(arguments, str), "arguments must be a JSON string, not an object"
        assert json.loads(arguments) == {"expression": "12 × 3"}


def test_tool_result_is_linked_to_the_tool_call_id(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, EchoBackend())
        dream.run("What time is it?")
        call = _assistant_tool_message(dream.history)["tool_calls"][0]
        result = next(message for message in dream.history if message.get("role") == "tool")
        assert call["id"]
        assert result["tool_call_id"] == call["id"]


def test_second_turn_replays_history_the_server_accepts(tmp_path, monkeypatch):
    server = StrictChatServer(
        _reply(
            tool_calls=[{"id": "call_1", "function": {"name": "get_datetime", "arguments": "{}"}}]
        ),
        _reply("It is noon."),
        _reply("[]"),
        _reply("Anything else?"),
        _reply("[]"),
    )
    monkeypatch.setattr("dream.agent.urlopen", server)
    backend = OpenAIBackend(model="test-model", api_key="", base_url="http://model.test/v1")
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        dream = Dream(store, backend)
        first = dream.run("What time is it?")
        second = dream.run("And in Tehran?")

    assert first.reply == "It is noon."
    assert second.reply == "Anything else?", "the second turn must not fail on replayed history"
    assert len(server.requests) == 5
    replayed = _assistant_tool_message(server.requests[3]["messages"])["tool_calls"][0]
    assert replayed["type"] == "function"
    assert replayed["function"]["name"] == "get_datetime"
    assert isinstance(replayed["function"]["arguments"], str)


def test_mock_server_rejects_dreams_internal_tool_call_shape(monkeypatch):
    """The guard above has teeth: the pre-fix shape is refused with HTTP 400."""
    server = StrictChatServer(_reply("unreachable"))
    monkeypatch.setattr("dream.agent.urlopen", server)
    backend = OpenAIBackend(model="test-model", api_key="", base_url="http://model.test/v1")
    malformed = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_1", "name": "get_datetime", "arguments": {}}],
    }
    response = backend.chat([{"role": "user", "content": "hi"}, malformed])
    assert response["tool_calls"] == []
    assert "tool_calls.0.type must be function" in response["content"]


# --------------------------------------------------------------------------
# Schemas for optional parameters
# --------------------------------------------------------------------------


def test_json_type_unwraps_optional_list():
    assert tools._json_type(list | None) == {"type": "array"}


def test_json_type_unwraps_optional_str():
    assert tools._json_type(str | None) == {"type": "string"}


def test_json_type_unwraps_typing_optional():
    # The legacy ``typing.Optional`` spelling must resolve exactly like ``int | None``.
    assert tools._json_type(Optional[int]) == {"type": "integer"}  # noqa: UP045


def test_json_type_keeps_plain_annotations_unchanged():
    assert tools._json_type(list) == {"type": "array"}
    assert tools._json_type(dict | None) == {"type": "object"}


def test_json_type_describes_a_multi_member_union():
    assert tools._json_type(int | str) == {"anyOf": [{"type": "integer"}, {"type": "string"}]}


def test_remember_fact_declares_tags_as_an_array(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        Dream(store, EchoBackend())
        tags = tools.REGISTRY["remember_fact"].schema["properties"]["tags"]
        assert tags["type"] == "array", "tags is list | None; the model must be told it is a list"


# --------------------------------------------------------------------------
# Backend error reporting
# --------------------------------------------------------------------------


def _raise(exc: Exception):
    def fail(request, timeout: int | None = None):
        raise exc

    return fail


def test_http_error_message_includes_the_response_body(monkeypatch):
    body = '{"error": {"message": "invalid_request: tool_calls.0.function.arguments"}}'
    monkeypatch.setattr("dream.agent.urlopen", _raise(_http_error(400, body)))
    backend = OpenAIBackend(model="test-model", api_key="", base_url="http://model.test/v1")
    content = backend.chat([{"role": "user", "content": "hi"}])["content"]
    assert "HTTP 400" in content
    assert "invalid_request: tool_calls.0.function.arguments" in content


def test_error_message_never_contains_the_api_key(monkeypatch):
    key = "sk-very-secret-key-value"
    body = json.dumps({"error": {"message": f"Incorrect API key provided: {key}"}})
    monkeypatch.setattr("dream.agent.urlopen", _raise(_http_error(401, body)))
    backend = OpenAIBackend(model="test-model", api_key=key, base_url="http://model.test/v1")
    content = backend.chat([{"role": "user", "content": "hi"}])["content"]
    assert key not in content
    assert "Incorrect API key provided" in content


def test_bearer_credentials_are_stripped_from_error_bodies(monkeypatch):
    body = "upstream rejected header Authorization: Bearer sk-leaked-token-value"
    monkeypatch.setattr("dream.agent.urlopen", _raise(_http_error(403, body)))
    backend = OpenAIBackend(model="test-model", api_key="", base_url="http://model.test/v1")
    content = backend.chat([{"role": "user", "content": "hi"}])["content"]
    assert "sk-leaked-token-value" not in content


def test_long_error_body_is_truncated(monkeypatch):
    monkeypatch.setattr("dream.agent.urlopen", _raise(_http_error(500, "x" * 5000)))
    backend = OpenAIBackend(model="test-model", api_key="", base_url="http://model.test/v1")
    content = backend.chat([{"role": "user", "content": "hi"}])["content"]
    assert "truncated" in content
    assert len(content) < 700


def test_bodyless_http_error_still_names_the_status(monkeypatch):
    monkeypatch.setattr(
        "dream.agent.urlopen",
        _raise(HTTPError("http://model.test/v1/chat/completions", 502, "Bad Gateway", {}, None)),
    )
    backend = OpenAIBackend(model="test-model", api_key="", base_url="http://model.test/v1")
    assert "HTTP 502 Bad Gateway" in backend.chat([{"role": "user", "content": "hi"}])["content"]


def test_connection_failure_names_the_error_type(monkeypatch):
    monkeypatch.setattr("dream.agent.urlopen", _raise(URLError("connection refused")))
    backend = OpenAIBackend(model="test-model", api_key="", base_url="http://model.test/v1")
    content = backend.chat([{"role": "user", "content": "hi"}])["content"]
    assert "URLError" in content
    assert "connection refused" in content


# --------------------------------------------------------------------------
# Sampling temperature
#
# The payload previously carried no temperature at all, so the server
# applied its own creative default. Conversation is now pinned to 0.3,
# overridable with DREAM_TEMPERATURE; the extraction pass samples colder
# still, because its output must parse as JSON.
# --------------------------------------------------------------------------


def _recorded_payloads(monkeypatch, *replies: dict) -> list[dict]:
    """Run the given canned replies through a recording mock server."""
    server = StrictChatServer(*replies)
    monkeypatch.setattr("dream.agent.urlopen", server)
    return server.requests


def _test_backend() -> OpenAIBackend:
    return OpenAIBackend(model="test-model", api_key="", base_url="http://model.test/v1")


def test_conversational_payload_sends_temperature_0_3_by_default(monkeypatch):
    monkeypatch.delenv("DREAM_TEMPERATURE", raising=False)
    requests = _recorded_payloads(monkeypatch, _reply("hi"))
    _test_backend().chat([{"role": "user", "content": "hi"}], tools=[])
    assert requests[0]["temperature"] == 0.3


def test_dream_temperature_overrides_the_default(monkeypatch):
    monkeypatch.setenv("DREAM_TEMPERATURE", "0.7")
    requests = _recorded_payloads(monkeypatch, _reply("hi"))
    _test_backend().chat([{"role": "user", "content": "hi"}])
    assert requests[0]["temperature"] == 0.7


@pytest.mark.parametrize("raw", ["", "boiling", "0,3", "one point five"])
def test_malformed_dream_temperature_falls_back_without_raising(monkeypatch, raw):
    # A parse failure must yield the default, never an exception mid-turn.
    monkeypatch.setenv("DREAM_TEMPERATURE", raw)
    requests = _recorded_payloads(monkeypatch, _reply("hi"))
    _test_backend().chat([{"role": "user", "content": "hi"}])
    assert requests[0]["temperature"] == 0.3


@pytest.mark.parametrize("raw", ["-0.1", "2.5", "100", "NaN", "inf"])
def test_out_of_range_dream_temperature_falls_back_to_default(monkeypatch, raw):
    monkeypatch.setenv("DREAM_TEMPERATURE", raw)
    requests = _recorded_payloads(monkeypatch, _reply("hi"))
    _test_backend().chat([{"role": "user", "content": "hi"}])
    assert requests[0]["temperature"] == 0.3


@pytest.mark.parametrize(("raw", "expected"), [("0", 0.0), ("2", 2.0)])
def test_in_range_dream_temperature_is_accepted(monkeypatch, raw, expected):
    monkeypatch.setenv("DREAM_TEMPERATURE", raw)
    requests = _recorded_payloads(monkeypatch, _reply("hi"))
    _test_backend().chat([{"role": "user", "content": "hi"}])
    assert requests[0]["temperature"] == expected


def test_extraction_payload_samples_colder_than_conversation(monkeypatch, tmp_path):
    monkeypatch.delenv("DREAM_TEMPERATURE", raising=False)
    requests = _recorded_payloads(monkeypatch, _reply("A quiet day."), _reply("[]"))
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        Dream(store, _test_backend()).run("I had a calm and quiet morning today.")
    assert len(requests) == 2
    conversational, extraction = requests
    assert "tools" in conversational, "the first request is the conversation"
    assert "tools" not in extraction, "the second request is the extraction pass"
    assert conversational["temperature"] == 0.3
    assert extraction["temperature"] == 0.1
    assert extraction["temperature"] < conversational["temperature"]


def test_extraction_temperature_does_not_follow_dream_temperature(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_TEMPERATURE", "1.2")
    requests = _recorded_payloads(monkeypatch, _reply("A quiet day."), _reply("[]"))
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        Dream(store, _test_backend()).run("I had a calm and quiet morning today.")
    conversational, extraction = requests
    assert conversational["temperature"] == 1.2
    assert extraction["temperature"] == 0.1


# --------------------------------------------------------------------------
# User-Agent header
#
# Dream previously sent no User-Agent, so urllib substituted its own default,
# which Cloudflare fronts some providers with and answers 403 before the
# provider ever sees the request. The client now always sends an identifying
# header, overridable through DREAM_USER_AGENT for users behind unusual
# filters. A header value must stay on one line, so unusable overrides fall
# back to the default rather than being forwarded or raising.
# --------------------------------------------------------------------------


class _RecordingClient:
    """Record the outgoing ``Request`` objects and their decoded bodies."""

    def __init__(self, *replies: dict) -> None:
        self.replies = list(replies)
        self.requests: list[Any] = []
        self.payloads: list[dict] = []

    def __call__(self, request, timeout: int | None = None) -> _FakeResponse:
        self.requests.append(request)
        self.payloads.append(json.loads(request.data.decode("utf-8")))
        return _FakeResponse(self.replies.pop(0))


def _recorded_requests(monkeypatch, *replies: dict) -> _RecordingClient:
    """Run the given canned replies through a header-recording mock server."""
    server = _RecordingClient(*replies)
    monkeypatch.setattr("dream.agent.urlopen", server)
    return server


def _user_agent(request: Any) -> str | None:
    """Return a ``Request``'s User-Agent value, matching the header case-insensitively."""
    for name, value in request.header_items():
        if name.lower() == "user-agent":
            return value
    return None


def test_user_agent_header_is_sent_by_default(monkeypatch):
    monkeypatch.delenv("DREAM_USER_AGENT", raising=False)
    server = _recorded_requests(monkeypatch, _reply("hi"))
    _test_backend().chat([{"role": "user", "content": "hi"}])
    assert _user_agent(server.requests[0]) == DEFAULT_USER_AGENT


def test_default_user_agent_is_a_single_line_identifier(monkeypatch):
    monkeypatch.delenv("DREAM_USER_AGENT", raising=False)
    server = _recorded_requests(monkeypatch, _reply("hi"))
    _test_backend().chat([{"role": "user", "content": "hi"}])
    value = _user_agent(server.requests[0])
    assert value
    assert "\n" not in value
    assert "\r" not in value


def test_dream_user_agent_overrides_the_default(monkeypatch):
    monkeypatch.setenv("DREAM_USER_AGENT", "custom-agent/1.0")
    server = _recorded_requests(monkeypatch, _reply("hi"))
    _test_backend().chat([{"role": "user", "content": "hi"}])
    assert _user_agent(server.requests[0]) == "custom-agent/1.0"


@pytest.mark.parametrize("raw", ["", "   ", "\t", "\n", "\r", "spaced\r\ninjection"])
def test_unusable_dream_user_agent_falls_back_without_raising(monkeypatch, raw):
    # An empty, whitespace-only, or line-broken value is never forwarded: a
    # header with a line break is an injection vector, so it must fall back
    # to the default and must not raise.
    monkeypatch.setenv("DREAM_USER_AGENT", raw)
    server = _recorded_requests(monkeypatch, _reply("hi"))
    _test_backend().chat([{"role": "user", "content": "hi"}])
    assert _user_agent(server.requests[0]) == DEFAULT_USER_AGENT


def test_user_agent_is_sent_on_conversation_and_extraction(monkeypatch, tmp_path):
    monkeypatch.delenv("DREAM_USER_AGENT", raising=False)
    server = _recorded_requests(monkeypatch, _reply("A quiet day."), _reply("[]"))
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        Dream(store, _test_backend()).run("I had a calm and quiet morning today.")
    assert len(server.requests) == 2
    for request in server.requests:
        assert _user_agent(request) == DEFAULT_USER_AGENT


def test_user_agent_does_not_change_the_request_body(monkeypatch):
    monkeypatch.delenv("DREAM_USER_AGENT", raising=False)
    server = _recorded_requests(monkeypatch, _reply("hi"))
    messages = [{"role": "user", "content": "hi"}]
    schema = tools.openai_schemas()
    _test_backend().chat(messages, tools=schema)
    payload = server.payloads[0]
    assert payload["model"] == "test-model"
    assert payload["messages"] == messages
    assert payload["tools"] == schema
    assert payload["temperature"] == 0.3
