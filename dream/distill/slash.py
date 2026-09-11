"""Slash command handlers for Dataset Distillation and Autonomous Evals."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.distill.exporter import DatasetDistiller
from dream.distill.tools import get_global_evaluator, get_global_recorder
from dream.distill.types import DistillFormat


def handle_distill_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/distill` slash command (export dataset or show stats)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    recorder = get_global_recorder()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "stats"

    if subcmd in ("stats", "info"):
        traces = recorder.list_trajectories(min_quality=0.0)
        output(cm.bold(f"🧠 Dataset Distillation Engine ({len(traces)} Recorded Traces):"))
        high_q = sum(1 for t in traces if t.quality_score >= 0.8)
        output(f"  • High-Quality Samples (>=0.8): {cm.green(str(high_q))}")
        output(f"  • Total Trajectories:            {len(traces)}")
        return True

    if subcmd == "export":
        fmt = parts[2].lower() if len(parts) > 2 else "openai"
        out_path = parts[3] if len(parts) > 3 else f"dist/distilled_dataset_{fmt}.jsonl"
        traces = recorder.list_trajectories(min_quality=0.5)
        if not traces:
            output(cm.yellow("No recorded trajectories found to export."))
            return True

        res = DatasetDistiller.export_to_file(
            traces=traces,
            output_path=out_path,
            export_format=DistillFormat(fmt),
        )
        if res.get("success"):
            output(cm.green(f"✓ Exported {res.get('samples_count')} samples ({fmt}) to {out_path}"))
        else:
            output(cm.red(f"✗ Export failed: {res.get('error')}"))
        return True

    output(
        cm.bold(
            "Usage / "
            "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
            "\u062f\u0633\u062a\u0648\u0631 /distill:"
        )
    )
    output(
        "  /distill stats                     - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0622\u0645\u0627\u0631 "
        "\u062a\u0631\u0627\u0698\u06a9\u062a\u0648\u0631\u06cc\u200c\u0647\u0627 "
        "/ View dataset stats"
    )
    output(
        "  /distill export [format] [path]    - "
        "\u0627\u0633\u062a\u062e\u0631\u0627\u062c "
        "\u062f\u06cc\u062a\u0627\u0633\u062a "
        "\u0622\u0645\u0648\u0632\u0634\u06cc / Export dataset"
    )
    return True


def handle_eval_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/eval` slash command (run automated benchmark suite)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    from dream.agent import Dream, EchoBackend
    from dream.memory import MemoryStore

    evaluator = get_global_evaluator()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "run"
    cat_filter = parts[2] if len(parts) > 2 else None

    if subcmd in ("run", "benchmark", "test"):
        output(cm.cyan("🚀 Running Dream Autonomous Benchmark Suite..."))
        with MemoryStore(":memory:") as store:
            dream = Dream(store, EchoBackend())
            report = evaluator.evaluate(dream, category_filter=cat_filter)

        pass_pct = int(report.pass_rate * 100)
        output(cm.bold(f"📊 Benchmark Evaluation Report ({report.total_tests} Tests):"))
        rate_str = cm.green(f"{pass_pct}%")
        output(f"  • Pass Rate:     {rate_str} ({report.passed_count}/{report.total_tests})")
        output(f"  • Tool Accuracy: {cm.cyan(f'{report.tool_accuracy * 100:.1f}%')}")
        output(f"  • Avg Latency:   {cm.dim(f'{report.avg_latency_ms:.1f}ms')}")

        for cat, stats in report.category_breakdown.items():
            c_pass = stats.get("passed", 0)
            c_tot = stats.get("total", 0)
            lat = stats.get("avg_latency_ms", 0.0)
            output(f"    - {cat:<15}: {c_pass}/{c_tot} passed ({lat:.1f}ms)")
        return True

    output(
        cm.bold(
            "Usage / "
            "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
            "\u062f\u0633\u062a\u0648\u0631 /eval:"
        )
    )
    output(
        "  /eval run                 - "
        "\u0627\u062c\u0631\u0627\u06cc \u062a\u0645\u0627\u0645 "
        "\u062a\u0633\u062a\u200c\u0647\u0627\u06cc "
        "\u0628\u0646\u0686\u0645\u0627\u0631\u06a9 "
        "/ Run all benchmark tests"
    )
    output(
        "  /eval run <category>      - "
        "\u0627\u062c\u0631\u0627\u06cc \u062f\u0633\u062a\u0647 "
        "\u062e\u0627\u0635 / Run category (persian_nlp, coding)"
    )
    return True
