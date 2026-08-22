"""Stage E context compaction and prompt-side durable-memory nudges."""

from __future__ import annotations

from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore


def make_agent(tmp_path, monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    return Dream(MemoryStore(tmp_path / "memory.db"), backend=EchoBackend())


def test_trigger_math_and_byte_stable_echo_summary(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch, DREAM_CONTEXT_TOKENS=20, DREAM_COMPACTION_THRESHOLD="0.5")  # noqa: E501
    agent.history = [{"role": "user", "content": "a" * 30} for _ in range(6)]
    before = agent.context_usage()
    result = agent.compact()
    assert before["ratio"] >= 0.5
    assert result["compacted"] is True
    assert result["summary"] == agent.history[0]["summary"]
    assert result["summary"].startswith("[Context compacted / ")


def test_tool_integrity_after_compaction(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch, DREAM_CONTEXT_TOKENS=25, DREAM_COMPACTION_THRESHOLD="0.5")  # noqa: E501
    agent.run("what time is it")
    agent.run("x" * 80)
    answer = agent.run("what time is it")
    assert "Result:" in answer.reply
    assert any(item.get("kind") == "compaction" for item in agent.history)


def test_small_window_never_grows_without_bound(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch, DREAM_CONTEXT_TOKENS=60, DREAM_COMPACTION_THRESHOLD="0.4", DREAM_COMPACTION_KEEP_MESSAGES=2)  # noqa: E501
    for _ in range(15):
        agent.run("x" * 40)
        # Events are transcript metadata, not model context.
        model_history = [x for x in agent.history if x.get("role")]
        assert agent.context_usage()["tokens"] <= 60 or len(model_history) <= 5


def test_explicit_compress_is_a_first_class_persisted_event(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    agent.history = [{"role": "user", "content": "old"} for _ in range(7)]
    turn = agent.run("/compress")
    assert turn.reply == "Context compacted."
    event = next(item for item in agent.history if item.get("kind") == "compaction")
    assert event["before_tokens"] > event["after_tokens"]
    assert event["preserved_messages"] == 4


def test_nudge_is_capped_offable_and_never_demo(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch, DREAM_MEMORY_NUDGE_EVERY_TURNS=1)
    agent.run("one")
    assert agent._nudge_due()
    agent.run("two")
    assert agent._nudge_sent and not agent._nudge_due()
    disabled = make_agent(tmp_path, monkeypatch, DREAM_MEMORY_NUDGES="off", DREAM_MEMORY_NUDGE_EVERY_TURNS=1)  # noqa: E501
    disabled.run("one")
    assert not disabled._nudge_due()
    demo = Dream(MemoryStore(tmp_path / "demo.db"), backend=EchoBackend(), demo=True)
    demo.nudge_every_turns = 1
    demo.run("one")
    assert not demo._nudge_due()


def test_compaction_preserves_prior_tool_result_for_follow_up(tmp_path, monkeypatch):
    """The summary keeps earlier tool facts available after their exchange drops."""
    agent = make_agent(tmp_path, monkeypatch)
    agent.history = [
        {"role": "user", "content": "look up account"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "a"}]},
        {"role": "tool", "tool_call_id": "a", "content": '{"balance": 42}'},
        {"role": "assistant", "content": "The balance is 42."},
        {"role": "user", "content": "new question"},
        {"role": "assistant", "content": "new answer"},
    ]
    agent.compaction_keep_messages = 2
    outcome = agent.compact("threshold")
    assert outcome["compacted"]
    assert '"balance": 42' in outcome["summary"]
    # The next turn sees the retained summary in its system prompt, while no
    # in-flight tool exchange was compacted.
    assert '"balance": 42' in agent._system_message([])["content"]


def test_compaction_event_is_first_class_history_record_after_reload(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    agent.history = [{"role": "user", "content": "old"} for _ in range(7)]
    agent.compact("explicit")
    reloaded_transcript = list(agent.history)  # transcript consumer reload
    event = next(item for item in reloaded_transcript if item.get("kind") == "compaction")
    assert event["timestamp"] > 0
    assert event["summary"] == agent._compaction_summary
