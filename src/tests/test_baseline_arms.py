"""Memory controls and independent retention rankings in the experiment matrix."""

from dataclasses import replace

import pytest

from reckon.core.resources import MemoryBudget
from reckon.experiments import Experiment, compare_experiments, run_experiment
from reckon.memory import CausalMemoryManager, ImportancePolicy, PayloadType, RandomPolicy


@pytest.mark.parametrize("task", ["keydoor", "bandit", "continual", "tutor"])
def test_no_memory_and_full_memory_controls(task):
    base = Experiment(task=task, episodes=2, budget_slots=1, budget_bytes=1)
    none = run_experiment(replace(base, policy="none"))
    full = run_experiment(replace(base, policy="full"))
    assert none["usage"]["final_slots"] == 0
    assert none["usage"]["baseline_discards"] == none["usage"]["writes"]
    assert none["usage"]["policy_prunes"] == 0
    assert none["usage"]["peak_slots"] == 1
    assert full["usage"]["policy_prunes"] == 0
    assert full["usage"]["baseline_discards"] == 0
    assert full["effective_budget"]["max_bytes"] is None
    assert full["usage"]["peak_slots"] <= full["effective_budget"]["max_slots"]
    if task == "keydoor":
        assert not any(ep["key_retrieved"] for ep in none["result"]["raw_data"]["episodes"])
        assert all(ep["key_retrieved"] for ep in full["result"]["raw_data"]["episodes"])


def test_random_policy_replays_without_reusing_record_ids():
    def retained(seed):
        memory = CausalMemoryManager(MemoryBudget(max_slots=3, max_bytes=12), RandomPolicy(seed))
        for i in range(20):
            memory.write(i, PayloadType.CUE, cost_bytes=4)
        return [record.payload for record in memory.get_all_records()]

    assert retained(42) == retained(42)
    assert retained(42) != retained(43)


def test_keydoor_uses_retrieved_color_and_counts_empty_queries():
    base = Experiment(task="keydoor", episodes=30, seed=42)
    none = run_experiment(replace(base, policy="none"))
    full = run_experiment(replace(base, policy="full"))
    empty_episodes = none["result"]["raw_data"]["episodes"]
    full_episodes = full["result"]["raw_data"]["episodes"]
    assert {ep["key_color"] for ep in full_episodes} == {"red", "blue", "green"}
    assert {ep["correct_door"] for ep in full_episodes if ep["key_color"] == "green"} == {
        (3, 1),
        (3, 3),
    }
    for empty, retained in zip(empty_episodes, full_episodes):
        assert empty["key_color"] == retained["key_color"]
        assert empty["correct_door"] == retained["correct_door"]
        assert empty["success"] == (empty["correct_door"] == (3, 1))
        expected = retained["key_color"] != "green" or retained["correct_door"] == (3, 1)
        assert retained["success"] == expected
        assert empty["reads"] == retained["reads"] == 1
    assert none["result"]["raw_data"]["total_reads"] == 30
    assert none["result"]["diagnostics"]["key_retrievals_per_query"] == 0
    assert full["result"]["diagnostics"]["key_retrievals_per_query"] == 1
    assert (
        full["result"]["performance"]["success_rate"]
        > none["result"]["performance"]["success_rate"]
    )


def test_importance_uses_explicit_weight_not_learned_utility():
    memory = CausalMemoryManager(MemoryBudget(max_slots=2, max_bytes=10), ImportancePolicy())
    important = memory.write(
        "important", PayloadType.CUE, cost_bytes=5, metadata={"importance": 10}
    )
    learned = memory.write("learned", PayloadType.CUE, cost_bytes=5, initial_utility=100)
    incoming = memory.write("incoming", PayloadType.CUE, cost_bytes=5)
    assert {record.id for record in memory.get_all_records()} == {important, incoming}
    assert memory.get_record(learned) is None


def test_invalid_importance_refuses_before_pruning():
    memory = CausalMemoryManager(MemoryBudget(max_slots=1), ImportancePolicy())
    original = memory.write("original", PayloadType.CUE, metadata={"importance": float("nan")})
    with pytest.raises(ValueError, match="importance"):
        memory.write("incoming", PayloadType.CUE)
    assert memory.get_record(original) is not None


def test_controls_are_not_repeated_for_every_budget():
    result = compare_experiments(
        [Experiment(episodes=2)], ["none", "full", "random", "importance"], [1, 2], [42, 43]
    )
    assert len(result["rows"]) == 6
    assert [row["budget_slots"] for row in result["rows"][:2]] == [None, None]
    for row in result["rows"]:
        assert row["learn_utility"] is True
        assert row["reset_memory"] is False
        assert len(row["runs"]) == 2
