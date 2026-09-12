"""Unit and integration tests for Metacognitive Reasoning, Trees & Tree-of-Thought."""

from __future__ import annotations

import pytest

from dream.reasoning import (
    MetacognitiveEvaluator,
    NodeStatus,
    ReasoningEngine,
    ReasoningStrategy,
    StrategyTree,
    handle_reasoning_slash_command,
    reasoning_create_thought_tree,
    reasoning_evaluate_node,
    reasoning_expand_node,
    reasoning_get_best_path,
    reasoning_get_status,
    reset_global_reasoning_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_reasoning_engine() -> None:
    reset_global_reasoning_engine()
    yield
    reset_global_reasoning_engine()


def test_toolset_includes_reasoning() -> None:
    """Verify reasoning toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("reasoning")
    assert ts is not None
    assert "reasoning_create_thought_tree" in ts.tools
    assert "reasoning_solve_goal" in ts.tools
    assert "reasoning_evaluate_node" in ts.tools
    assert "reasoning" in BUILTIN_TOOLSETS


def test_thought_tree_expansion_and_uct_scoring() -> None:
    """Verify tree initialization, node expansion, and UCT calculation."""
    tree = StrategyTree()
    root = tree.initialize_root(goal="بهینه‌سازی مصرف رم در عامل هوشمند")

    children = tree.expand_node(
        parent_id=root.node_id,
        child_thoughts=[
            "فرضیه ۱: استفاده از کشینگ LRU و آزادسازی بافرهای متنی",
            "فرضیه ۲: فشرده‌سازی بردارهای حافظه معنایی",
        ],
    )
    assert len(children) == 2
    assert root.status == NodeStatus.EXPANDED
    assert len(root.children_ids) == 2

    # Verify UCT score
    uct_score = tree.calculate_uct(children[0], parent_visits=1)
    assert uct_score > 0.0


def test_tree_backpropagation_and_pruning() -> None:
    """Verify score backpropagation and dead-end branch pruning."""
    tree = StrategyTree()
    root = tree.initialize_root(goal="طراحی پایگاه داده توزیع‌شده")

    children = tree.expand_node(
        parent_id=root.node_id,
        child_thoughts=["راهکار ضعیف", "راهکار قوی و مقیاس‌پذیر"],
    )

    # Evaluate child 0 with low score
    tree.evaluate_node(children[0].node_id, score=0.1, rationale="غیرعملی")
    # Evaluate child 1 with high score
    tree.evaluate_node(children[1].node_id, score=0.9, rationale="مقیاس‌پذیر و مناسب")

    # Prune low-scoring branch
    pruned = tree.prune_low_value_branches(min_score_threshold=0.3)
    assert pruned == 1
    assert children[0].status == NodeStatus.PRUNED

    # Extract best trajectory
    best_path = tree.extract_best_trajectory()
    assert len(best_path) == 2
    assert best_path[-1].node_id == children[1].node_id


def test_metacognitive_evaluator_and_loop_detection() -> None:
    """Verify self-critique scoring and loop/repetition detection."""
    evaluator = MetacognitiveEvaluator()

    # Coherent step
    thought_text = (
        "با توجه به داده‌های ورودی، ابتدا باید اعتبارسنجی طرح انجام شود "
        "و سپس تراکنش ثبت گردد."
    )
    eval1 = evaluator.evaluate_thought_step(
        thought_text=thought_text,
        depth=2,
    )
    assert eval1.coherence_score >= 0.8
    assert eval1.suggested_action in ("continue_exploration", "ready_for_conclusion")

    # Repetitive circular step
    eval2 = evaluator.evaluate_thought_step(
        thought_text="اعتبارسنجی طرح باید انجام شود",
        depth=3,
        context_history=["اعتبارسنجی طرح باید انجام شود"],
    )
    assert eval2.hallucination_risk > 0.5
    assert eval2.suggested_action == "backtrack"


def test_reasoning_engine_solve_goal_with_tree() -> None:
    """Verify end-to-end goal solving and report generation."""
    engine = ReasoningEngine()
    traj, summary = engine.solve_goal_with_tree(
        goal="انتخاب الگوریتم رمزنگاری برای پیام‌رسان امن",
        hypotheses=[
            "استفاده از پروتکل Signal و الگوریتم Double Ratchet",
            "استفاده از رمزنگاری ساده متقارن بدون چرخش کلید",
        ],
    )

    assert traj.strategy == ReasoningStrategy.TREE_OF_THOUGHT
    assert len(traj.selected_path) >= 2
    assert traj.confidence > 0.0
    assert "Double Ratchet" in traj.final_answer
    assert "Tree-of-Thought Report" in summary


def test_reasoning_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /think & /reasoning slash commands."""
    # Tool: create thought tree
    res_init = reasoning_create_thought_tree("کاهش زمان پاسخ‌دهی پایگاه داده")
    assert res_init["success"] is True
    tid = res_init["trajectory"]["trajectory_id"]
    root_id = res_init["root_node_id"]

    # Tool: expand & evaluate
    res_exp = reasoning_expand_node(
        trajectory_id=tid,
        parent_node_id=root_id,
        thoughts=["ایجاد ایندکس B-Tree روی ستون‌های پرکاربرد"],
    )
    assert res_exp["success"] is True
    child_id = res_exp["nodes"][0]["node_id"]

    res_eval = reasoning_evaluate_node(
        trajectory_id=tid,
        node_id=child_id,
        score=0.92,
        rationale="بسیار موثر در کاهش زمان کوئری‌ها",
    )
    assert res_eval["success"] is True
    assert res_eval["node"]["score"] == 0.92

    # Tool: get best path & status
    res_path = reasoning_get_best_path(tid)
    assert res_path["success"] is True

    res_st = reasoning_get_status()
    assert res_st["success"] is True
    assert res_st["total_trajectories"] >= 1

    # Slash: /think
    slash_think = handle_reasoning_slash_command("/think بهبود بازدهی سیستم")
    assert "Tree-of-Thought Report" in slash_think

    # Slash: /reasoning status
    slash_st = handle_reasoning_slash_command("/reasoning status")
    assert "وضعیت موتور استدلال" in slash_st

    # Slash: /reasoning reset
    slash_reset = handle_reasoning_slash_command("/reasoning reset")
    assert "بازنشانی شد" in slash_reset
