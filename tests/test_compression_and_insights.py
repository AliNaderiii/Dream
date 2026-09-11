"""Comprehensive test suite for Multi-Strategy Compaction, Fast Mode, and Insights Subsystem."""

from __future__ import annotations

import json

from dream.compression.fast_mode import (
    FastMode,
    get_fast_mode_controller,
    reset_fast_mode_controller,
)
from dream.compression.slash import handle_compress_command, handle_fast_command
from dream.compression.strategies import (
    CodePreservingStrategy,
    CompressionStrategyType,
    HybridStrategy,
    LossyStrategy,
    compress_messages,
)
from dream.compression.tools import get_insights_report, set_fast_mode
from dream.insights.analyzer import InsightsAnalyzer
from dream.insights.slash import handle_insights_command


def test_lossy_compression_strategy():
    """Verify narrative summarization condensing messages into key requests and timeline."""
    dropped = [
        {"role": "user", "content": "وضعیت آب‌وهوای تهران رو بررسی کن"},
        {"role": "assistant", "content": "در تاریخ 1403/06/25 هوا آفتابی است."},
        {"role": "user", "content": "سپس قیمت دلار رو بگو"},
        {"role": "assistant", "content": "قیمت دلار 60000 تومان است."},
    ]

    strat = LossyStrategy()
    summary = strat.summarize(dropped)
    assert "[Context Compacted (Lossy Strategy)" in summary
    assert "1403/06/25" in summary
    assert "وضعیت آب‌وهوای تهران" in summary


def test_code_preserving_compression_strategy():
    """Verify code blocks, SQL queries, and file paths survive context compaction."""
    code_block = (
        "```python\n"
        "def calculate_fib(n):\n"
        "    return n if n <= 1 else calculate_fib(n-1) + calculate_fib(n-2)\n"
        "```"
    )
    dropped = [
        {"role": "user", "content": "این تابع رو در مسیر /home/user/app.py بنویس:"},
        {
            "role": "assistant",
            "content": code_block,
        },
        {"role": "user", "content": "حالا اسکریپت test.sh رو اجرا کن."},
    ]

    strat = CodePreservingStrategy()
    summary = strat.summarize(dropped)
    assert "Code-Preserving Strategy" in summary
    assert "def calculate_fib(n):" in summary
    assert "/home/user/app.py" in summary or "test.sh" in summary


def test_hybrid_compression_strategy():
    """Verify hybrid strategy combines timeline, pending tasks, and code."""
    dropped = [
        {"role": "user", "content": "لطفاً تسک‌های مربوط به تاریخ 1403/07/10 را آماده کن."},
        {"role": "tool", "name": "weather_plugin", "content": "بارانی"},
        {
            "role": "assistant",
            "content": "```json\n{\"status\": \"ready\"}\n```",
        },
    ]

    strat = HybridStrategy()
    summary = strat.summarize(dropped)
    assert "Hybrid Strategy" in summary
    assert "1403/07/10" in summary
    assert "weather_plugin" in summary
    assert "{\"status\": \"ready\"}" in summary


def test_compress_messages_pipeline():
    """Verify compress_messages end-to-end pipeline."""
    messages = [
        {"role": "user", "content": "قدم اول: سلام"},
        {"role": "assistant", "content": "درود"},
        {"role": "user", "content": "قدم دوم: تحلیل"},
        {"role": "assistant", "content": "انجام شد"},
        {"role": "user", "content": "قدم سوم: نهایی"},
        {"role": "assistant", "content": "پایان"},
    ]

    new_msgs, result = compress_messages(
        messages, strategy=CompressionStrategyType.HYBRID, keep_recent=2
    )
    assert result.compacted is True
    assert result.dropped_messages_count == 4
    assert len(new_msgs) == 3  # 1 summary header + 2 kept messages
    assert new_msgs[0]["role"] == "system"
    assert new_msgs[0]["_compaction_header"] is True


def test_fast_mode_controller_and_gating():
    """Verify Fast Mode states and LLM parameter tuning."""
    reset_fast_mode_controller()
    ctrl = get_fast_mode_controller()

    # Default is AUTO
    assert ctrl.mode == FastMode.AUTO
    p_auto = ctrl.get_execution_params()
    assert p_auto["latency_priority"] == "adaptive"

    # Set to TURBO
    ctrl.set_mode(FastMode.TURBO)
    assert ctrl.mode == FastMode.TURBO
    p_turbo = ctrl.get_execution_params()
    assert p_turbo["prune_cot"] is True
    assert p_turbo["max_tokens"] == 1024

    # Per-session override
    ctrl.set_mode(FastMode.COLD, session_id="deep_reasoning_sess")
    assert ctrl.get_mode("deep_reasoning_sess") == FastMode.COLD
    assert ctrl.get_mode("other_sess") == FastMode.TURBO


def test_insights_analyzer_and_economics():
    """Verify token breakdown, USD/Toman cost estimation, and tool metrics."""
    analyzer = InsightsAnalyzer(exchange_rate_toman=60_000.0)

    messages = [
        {"role": "user", "content": "لطفاً این متن را به فارسی ترجمه کن."},
        {
            "role": "assistant",
            "content": "در حال فراخوانی ابزار...",
            "tool_calls": [{"name": "translate_tool"}],
        },
        {"role": "tool", "name": "translate_tool", "content": "نتیجه ترجمه متن."},
        {"role": "assistant", "content": "متن ترجمه شده خدمت شما."},
    ]

    report = analyzer.analyze_messages(messages, system_prompt="تو یک دستیاری")
    assert report.message_count == 4
    assert report.turn_count == 1
    assert report.tokens.total_tokens > 0
    assert report.cost.usd_cost > 0
    assert report.cost.toman_cost > 0
    assert len(report.tools) == 1
    assert report.tools[0].name == "translate_tool"
    assert report.tools[0].call_count == 1


def test_compression_and_insights_slash_commands():
    """Verify `/compress`, `/fast`, and `/insights` slash commands."""
    messages = [
        {"role": "user", "content": "سلام"},
        {"role": "assistant", "content": "درود"},
        {"role": "user", "content": "تست ۱"},
        {"role": "assistant", "content": "پاسخ ۱"},
        {"role": "user", "content": "تست ۲"},
        {"role": "assistant", "content": "پاسخ ۲"},
    ]

    # /compress
    outputs: list[str] = []
    new_msgs, ok = handle_compress_command("hybrid 2", messages=messages, output=outputs.append)
    assert ok is True
    assert len(new_msgs) == 3
    assert any("فشرده‌سازی کانتکست" in out for out in outputs)

    # /fast
    outputs.clear()
    handle_fast_command("turbo", output=outputs.append)
    assert any("TURBO" in out for out in outputs)

    # /insights
    outputs.clear()
    handle_insights_command("", messages=messages, output=outputs.append)
    assert any("Session Insights" in out or "تحلیل و بینش‌ها" in out for out in outputs)


def test_agent_tools_for_fast_and_insights():
    """Verify tool execution for agent self-configuration."""
    res_fast = set_fast_mode("cold")
    assert "cold" in res_fast

    res_insights = get_insights_report()
    data = json.loads(res_insights)
    assert "tokens" in data
    assert "cost" in data
