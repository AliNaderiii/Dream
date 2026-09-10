"""Tests for advanced context compression, tool observation pruning, and budget tracking."""

from dream.compression import (
    ContextCompressionEngine,
    estimate_tokens,
    extract_persian_timeline,
    generate_structured_summary,
    prune_tool_observations,
    split_for_compaction,
    usage,
)


def test_tool_observation_pruner():
    """Verify tool observations in older turns are pruned while recent ones are kept."""
    messages = [
        {"role": "user", "content": "جستجو کن"},
        {"role": "assistant", "content": "در حال جستجو..."},
        {"role": "tool", "name": "search_web", "content": "x" * 1200},
        {"role": "assistant", "content": "اینم نتایج."},
        # Recent turn (should NOT be pruned)
        {"role": "user", "content": "فایل رو بخون"},
        {"role": "assistant", "content": "در حال خواندن..."},
        {"role": "tool", "name": "read_note", "content": "y" * 1500},
        {"role": "assistant", "content": "متن فایل آماده است."},
    ]

    pruned, count, saved = prune_tool_observations(messages, keep_recent_turns=1, max_chars=400)
    assert count == 1
    assert saved > 500

    # The older tool output must be compacted
    assert "[Tool 'search_web' output summary:" in pruned[2]["content"]
    assert len(pruned[2]["content"]) < 600

    # The recent tool output must remain untouched
    assert pruned[6]["content"] == "y" * 1500


def test_persian_timeline_extraction():
    """Verify extraction of Jalali dates and temporal phrasing from dropped turns."""
    dropped = [
        {"role": "user", "content": "جلسه برای فردا ساعت ۱۴:۳۰ تنظیم شود"},
        {"role": "assistant", "content": "در تاریخ 1403/06/21 ثبت شد."},
        {"role": "user", "content": "هفته آینده یادآوری کن."},
    ]

    timeline = extract_persian_timeline(dropped)
    assert "1403/06/21" in timeline
    assert "فردا" in timeline
    assert "ساعت ۱۴:۳۰" in timeline
    assert "هفته آینده" in timeline


def test_structured_summary_generation():
    """Verify multi-section bilingual summary containing metadata and timeline."""
    dropped = [
        {"role": "user", "content": "پروژه دریم را بررسی کن"},
        {"role": "tool", "name": "read_note", "content": "مستندات پروژه دریم"},
        {"role": "assistant", "content": "بررسی شد در تاریخ 1403/07/01."},
    ]

    summary = generate_structured_summary(dropped, reason="threshold")
    assert "[Context compacted / فشرده‌سازی شد]" in summary
    assert "preserved_tool_results='مستندات پروژه دریم'" in summary
    assert "1403/07/01" in summary
    assert "پروژه دریم را بررسی کن" in summary


def test_context_compression_engine_pipeline():
    """Verify the two-stage compression engine behavior."""
    engine = ContextCompressionEngine(default_window=1000, default_threshold=0.5)

    messages = [
        {"role": "user", "content": "تسکو شروع کن"},
        {"role": "tool", "name": "search_web", "content": "a" * 800},
        {"role": "assistant", "content": "انجام شد."},
        {"role": "user", "content": "مرحله دوم"},
        {"role": "assistant", "content": "در حال انجام."},
    ]

    # Test token assessment
    budget = engine.assess_budget(system_prompt="تو یک دستیار هوشمندی", messages=messages)
    assert budget.total_window == 1000
    assert budget.history_tokens > 200

    # Test optimization
    optimized, result = engine.optimize_messages(
        messages, window=500, threshold=0.4, keep_messages=2
    )
    assert result.pruned_tools_count >= 1
    assert len(optimized) <= len(messages)


def test_backward_compatibility_with_compaction_module():
    """Verify all existing compaction utilities work identically."""
    history = [
        {"role": "user", "content": "سلام"},
        {"role": "assistant", "content": "درود"},
        {"role": "user", "content": "حالت چطوره؟"},
        {"role": "assistant", "content": "عالی"},
    ]

    tokens = estimate_tokens(history)
    assert tokens > 0

    u = usage(history, window=4000)
    assert u.window == 4000
    assert u.tokens == tokens
    assert u.ratio < 0.1

    dropped, kept = split_for_compaction(history, preserve=2)
    assert len(dropped) == 2
    assert len(kept) == 2
