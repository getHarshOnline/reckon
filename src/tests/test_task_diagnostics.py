"""Task results name the quantity their counters actually measure."""

from statistics import mean

import pytest

from reckon.core.resources import MemoryBudget
from reckon.memory import CausalMemoryManager
from reckon.tasks import ContinualTask, TutorTask
from reckon.tasks.task_c_continual import ContinualConfig
from reckon.tasks.task_d_tutor import TutorConfig


def test_continual_accuracy_per_write_is_not_reward_per_occupied_slot():
    memory = CausalMemoryManager(MemoryBudget(max_slots=2))
    result = ContinualTask(ContinualConfig(
        num_tasks=3, samples_per_task=30, test_samples_per_task=15,
    )).run(memory, num_episodes=3, seed=42)
    episodes = result.raw_data["episodes"]
    expected = mean(ep["mean_accuracy"] / max(ep["total_writes"], 1) for ep in episodes)
    assert result.diagnostics["mean_episode_accuracy_per_write"] == pytest.approx(expected)
    assert expected != pytest.approx(result.performance.mean_accuracy / memory.current_usage_slots)
    assert result.diagnostics["one_minus_mean_forgetting"] == pytest.approx(
        1 - mean(ep["forgetting"] for ep in episodes)
    )
    assert result.memory.reads_per_write == pytest.approx(
        sum(ep["total_reads"] for ep in episodes) / max(sum(ep["total_writes"] for ep in episodes), 1)
    )
    assert "causal" not in result.to_dict()
    assert "reward_per_slot" not in result.to_dict()["memory"]


def test_tutor_keeps_episode_and_pooled_hint_read_fractions_distinct():
    memory = CausalMemoryManager(MemoryBudget(max_slots=4))
    result = TutorTask(TutorConfig(
        num_concepts=6, num_sessions=1, questions_per_session=6,
        misconception_probability=1, hint_success_probability=0.3,
    )).run(memory, num_episodes=8, seed=42)
    episodes = result.raw_data["episodes"]
    episode_mean = mean(ep["useful_reads"] / max(ep["total_reads"], 1) for ep in episodes)
    pooled = sum(ep["useful_reads"] for ep in episodes) / max(
        sum(ep["total_reads"] for ep in episodes), 1
    )
    assert episode_mean != pytest.approx(pooled)
    assert result.diagnostics["mean_episode_effective_hint_read_fraction"] == pytest.approx(episode_mean)
    assert result.diagnostics["pooled_effective_hint_read_fraction"] == pytest.approx(pooled)
    assert result.diagnostics["mean_misconception_clearance"] == pytest.approx(
        mean(ep["improvement_rate"] for ep in episodes)
    )
    assert set(result.to_dict()) == {"performance", "memory", "diagnostics", "raw_data"}
