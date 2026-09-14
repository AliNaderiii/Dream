"""Unit tests for Tree-of-Thought search, MCTS rollout, and metacognitive reflection."""

import pytest

from dream.reasoning.engine import ReasoningEngine
from dream.reasoning.types import NodeStatus, ReasoningStrategy


@pytest.fixture
def reasoning_engine():
    engine = ReasoningEngine()
    engine.reset()
    yield engine
    engine.reset()


def test_tree_initialization(reasoning_engine):
    traj, root_id = reasoning_engine.create_thought_tree(
        goal="بهینه‌سازی شبکه عامل‌های چندگانه",
        strategy=ReasoningStrategy.TREE_OF_THOUGHT,
    )
    assert traj.trajectory_id.startswith("traj-")
    assert root_id == traj.root_node_id
    assert root_id in traj.nodes
    assert traj.nodes[root_id].status == NodeStatus.SELECTED


def test_branch_expansion_and_evaluation(reasoning_engine):
    traj, root_id = reasoning_engine.create_thought_tree("طراحی معماری خط‌لوله داده")
    branches = [
        "گزینه ۱: استفاده از بافر حلقوی درون‌حافظه‌ای",
        "گزینه ۲: استفاده از معماری پیام‌رسانی رویدادمحور توزیع‌شده",
        "گزینه ۳: ساختار داده مبتنی بر گراف زمانی",
    ]

    children = reasoning_engine.expand_node(traj.trajectory_id, root_id, branches)
    assert len(children) == 3

    # Evaluate each child
    for child in children:
        eval_node = reasoning_engine.evaluate_node(
            trajectory_id=traj.trajectory_id,
            node_id=child.node_id,
            score=0.85,
            rationale="انسجام منطقی بالا و تطابق با نیازهای کارایی",
        )
        assert eval_node.score == 0.85
        assert eval_node.status == NodeStatus.EVALUATED


def test_mcts_search_step_and_backprop(reasoning_engine):
    traj, _root_id = reasoning_engine.create_thought_tree("تحلیل راهبردی داده")

    step_res = reasoning_engine.mcts_search_step(traj.trajectory_id)
    assert step_res["trajectory_id"] == traj.trajectory_id
    assert step_res["new_nodes_count"] >= 2
    assert len(step_res["evaluated_nodes"]) >= 2


def test_step_critique_and_hallucination_detection(reasoning_engine):
    traj, root_id = reasoning_engine.create_thought_tree("مسئله تحلیل منطق")
    children = reasoning_engine.expand_node(
        traj.trajectory_id,
        root_id,
        ["فرضیه اول با شرح و بسط منطقی دقیق برای ارزیابی سامانه هوشمند."],
    )
    critique_res = reasoning_engine.step_critique(
        trajectory_id=traj.trajectory_id,
        node_id=children[0].node_id,
    )
    assert critique_res["node_id"] == children[0].node_id
    assert 0.0 <= critique_res["score"] <= 1.0
    assert "coherence_score" in critique_res["critique"]


def test_backtrack_and_prune(reasoning_engine):
    traj, root_id = reasoning_engine.create_thought_tree("مسئله بهینه‌سازی")
    children = reasoning_engine.expand_node(
        traj.trajectory_id,
        root_id,
        ["شاخه مناسب", "شاخه نامناسب با نمره پایین"],
    )
    reasoning_engine.evaluate_node(traj.trajectory_id, children[0].node_id, 0.9)
    reasoning_engine.evaluate_node(traj.trajectory_id, children[1].node_id, 0.1)

    prune_res = reasoning_engine.backtrack_and_prune(
        trajectory_id=traj.trajectory_id,
        min_threshold=0.35,
    )
    assert prune_res["pruned_nodes_count"] == 1
    assert prune_res["active_nodes_count"] >= 1


def test_synthesize_solution(reasoning_engine):
    traj, root_id = reasoning_engine.create_thought_tree("طراحی الگوریتم جستجو")
    children = reasoning_engine.expand_node(
        traj.trajectory_id,
        root_id,
        ["استفاده از جستجوی فضایی MCTS با تابع ارزیابی ترکیبی"],
    )
    reasoning_engine.evaluate_node(traj.trajectory_id, children[0].node_id, 0.95)

    solution = reasoning_engine.synthesize_solution(traj.trajectory_id)
    assert solution["trajectory_id"] == traj.trajectory_id
    assert solution["confidence"] >= 0.9
    assert len(solution["steps"]) >= 1
    assert "MCTS" in solution["final_answer"]
