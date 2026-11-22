"""The measured arm must execute isolated interventions and count their whole price."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
import numpy as np

from reckon.core.episode_context import EpisodeContext
from reckon.core.resources import MemoryBudget
from reckon.experiments import Experiment, compare_experiments, run_experiment
from reckon.cli import main
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.policies import FIFOPolicy
from reckon.memory.record import PayloadType
from reckon.measured_retention import MeasuredRetentionPolicy, RetentionProbeConfig
from reckon.metrics import MemoryEfficiencyMetrics, PerformanceMetrics
from reckon.metrics.probe import ProbeConfig
from reckon.metrics.tests.fdr import FDRMethod
from reckon.tasks.base import BaseTask, TaskResult
from reckon.tasks.task_c_continual import (
    ContinualConfig,
    ContinualClassificationTask,
    ContinualTask,
)


def probe_config(episodes=1):
    return RetentionProbeConfig(
        episodes_per_arm=episodes,
        sampling=ProbeConfig(
            n_trials=4,
            min_trials=2,
            max_trials=8,
            n_permutations=100,
            adaptive_sampling=False,
            seed=1000,
            fdr_method=FDRMethod.BONFERRONI,
        ),
    )


class RetainedCueTask(BaseTask):
    @property
    def name(self):
        return "Retained cue"

    @property
    def description(self):
        return "Use the supplied retained values in each fresh episode"

    def run(self, cmm, num_episodes, seed, *, reset_memory=False, learn_utility=True):
        assert reset_memory is False
        outcomes = []
        for episode in range(num_episodes):
            cmm.set_episode(str(episode), reset_memory=False)
            with EpisodeContext(episode_id=str(episode)):
                records = cmm.retrieve(query={"tags": ["value"]})
                outcome = sum(record.payload["value"] for record in records) + seed / 10000
                outcomes.append(outcome)
                if learn_utility:
                    cmm.observe(outcome)
        return TaskResult(
            PerformanceMetrics(mean_return=sum(outcomes) / len(outcomes)),
            MemoryEfficiencyMetrics(),
            {},
        )


def test_trial_copy_preserves_native_state_and_isolates_records_logs_and_windows():
    memory = CausalMemoryManager(MemoryBudget(max_slots=3, max_write_ops_per_window=1))
    kept = memory.write({"value": [1]}, PayloadType.CUE, cost_tokens=8, metadata={"x": [1]})
    memory.update_score(kept, "utility", 0.7)
    memory.set_step(3)
    memory.retrieve()
    original = memory.get_record(kept)
    assert original is not None
    # Admission's native costs remain independent of returned metadata.
    original.cost.tokens = 999
    with memory.subscribe_events() as source_events:
        while not source_events.empty():
            source_events.get_nowait()
        trial = memory.fork_for_trial(FIFOPolicy())
        assert trial.get_event_log() == []
        copied = trial.get_record(kept)
        assert copied is not None
        assert copied.to_dict() == original.to_dict()
        assert trial.current_usage_tokens == 8
        copied_native, original_native = trial._store.get(kept), memory._store.get(kept)
        assert copied_native is not None and original_native is not None
        assert copied_native.use_count == original_native.use_count
        copied.payload["value"].append(2)
        copied.metadata["x"].append(2)
        trial.update_score(kept, "utility", 0.1)
        trial.write("new", PayloadType.CUE)
        assert source_events.empty()
    assert original.payload == {"value": [1]}
    assert original.metadata == {"x": [1]}
    assert original.utility.value == 0.7
    assert memory.current_usage_slots == 1
    with pytest.raises(RuntimeError, match="rate limit"):
        memory.write("denied", PayloadType.CUE)


def test_measured_prune_uses_signed_paired_effects_and_full_multi_episode_cost():
    memory = CausalMemoryManager(MemoryBudget(max_slots=3))
    ids = [
        memory.write({"value": value}, PayloadType.CUE, tags=["value"], cost_bytes=1)
        for value in (5, -3, 0)
    ]
    original = [record.to_dict() for record in memory.get_all_records()]
    policy = MeasuredRetentionPolicy(
        probe_config(2),
        lambda: memory.fork_for_trial(FIFOPolicy()),
        RetainedCueTask,
        FIFOPolicy,
        "mean_return",
        42,
        True,
    )
    memory.retention_policy = policy
    memory.get_event_log()
    incoming = memory.write({"value": 0}, PayloadType.CUE, cost_bytes=1)
    assert [r.id for r in memory.get_all_records()] == [ids[0], ids[2], incoming]
    batch = policy.batches[0]
    assert batch["selected"] == [ids[1]]
    assert batch["records"] == original
    assert batch["probe_calls"] == 24
    assert batch["probe_episodes"] == 48
    assert policy.episodes == 48
    assert 0 < batch["probe_wall_time_s"] <= policy.elapsed_s
    for row, value in zip(batch["evidence"], (5, -3, 0)):
        assert row["delta"] == pytest.approx(value)
        assert row["probe_episodes"] == 16
        assert row["trial_elapsed_s"] > 0
        for pair in row["trials"]:
            before, after = pair["baseline"], pair["intervention"]
            assert before["seed"] == after["seed"]
            assert before["outcome"] - after["outcome"] == pytest.approx(value)
            assert before["removed_record_id"] is None
            assert after["removed_record_id"] == row["record_id"]
            assert after["initial_record_reads"].get(row["record_id"], 0) == 0
            assert before["initial_record_reads"][row["record_id"]] == 2
            assert before["memory_events"]["coverage"] == "complete_trial_subscription"
    retained = memory.get_record(ids[0])
    assert retained is not None
    assert retained.utility.value == 0
    assert retained.causal_score.ablation_delta is None
    assert [event["op_type"] for event in memory.get_event_log()] == ["prune", "write"]
    json.dumps(batch, allow_nan=False)


def test_continual_probe_measures_a_carried_record_before_any_new_write(monkeypatch):
    def fixed_dataset(env, config, rng):
        # The zero training vector changes only the bias. The retained example
        # supplies the positive weight required by the distinct test point.
        env.train_data = [[(np.array([0.0, 0.0]), 0)]]
        env.test_data = [[(np.array([0.0, 1.0]), 1)]]

    monkeypatch.setattr(ContinualClassificationTask, "__init__", fixed_dataset)
    memory = CausalMemoryManager(MemoryBudget(max_slots=1))
    marker = memory.write(
        {"x": [0.0, 1.0], "y": 1, "task": 0}, PayloadType.REPRESENTATION, tags=["replay_sample"]
    )
    policy = MeasuredRetentionPolicy(
        probe_config(),
        lambda: memory.fork_for_trial(FIFOPolicy()),
        lambda: ContinualTask(ContinualConfig(num_tasks=1, replay_fraction=1)),
        FIFOPolicy,
        "mean_accuracy",
        42,
        True,
    )
    memory.retention_policy = policy
    memory.write("incoming", PayloadType.CUE)
    evidence = policy.batches[0]["evidence"][0]
    assert evidence["record_id"] == marker
    assert evidence["delta"] == 1
    assert evidence["probe_episodes"] == 8
    for pair in evidence["trials"]:
        assert pair["baseline"]["initial_record_reads"] == {marker: 1}
        assert pair["intervention"]["initial_record_reads"] == {}
        assert pair["baseline"]["outcome"] == 1
        assert pair["intervention"]["outcome"] == 0


@pytest.mark.parametrize(
    "task,environment",
    [
        ("keydoor", {}),
        ("bandit", {"num_arms": 2, "num_modes": 2, "indicator_probability": 0.02}),
        ("continual", {"num_tasks": 3, "samples_per_task": 20, "test_samples_per_task": 3}),
        (
            "tutor",
            {
                "num_concepts": 2,
                "num_sessions": 1,
                "questions_per_session": 3,
                "misconception_probability": 1.0,
                "hint_success_probability": 1.0,
            },
        ),
    ],
)
def test_all_builtin_tasks_run_measured_arm_with_real_pruning(task, environment):
    result = run_experiment(
        Experiment(
            task=task,
            environment=environment,
            policy="measured",
            budget_slots=1,
            episodes=2,
            retention_probe=probe_config(),
        )
    )
    usage = result["usage"]
    assert result["measured_retention_effects"]
    assert usage["policy_prunes"] > 0
    assert usage["probe_episodes"] > 0
    assert usage["total_episodes"] == 2 + usage["probe_episodes"]
    assert 0 < usage["probe_elapsed_s"] < usage["elapsed_s"]
    assert usage["task_elapsed_s"] + usage["probe_elapsed_s"] == pytest.approx(usage["elapsed_s"])
    assert usage["peak_slots"] == 1
    json.dumps(result, allow_nan=False)


def test_comparison_aggregates_costs_and_no_pruning_does_not_claim_measurements():
    config = Experiment(episodes=2, retention_probe=probe_config())
    rows = compare_experiments([config], ["fifo", "measured"], [1], [41, 42])["rows"]
    assert rows[0]["probe_episodes"] == 0
    measured = rows[1]
    assert measured["probe_episodes"] == sum(
        run["usage"]["probe_episodes"] for run in measured["runs"]
    )
    assert measured["probe_elapsed_s"] == sum(
        run["usage"]["probe_elapsed_s"] for run in measured["runs"]
    )
    assert measured["total_episodes"] == 4 + measured["probe_episodes"]
    untouched = run_experiment(replace(config, policy="measured", budget_slots=10))
    assert untouched["retention_probes"] == []
    assert untouched["measured_retention_effects"] is False


def test_probe_errors_leave_live_records_and_events_unchanged():
    memory = CausalMemoryManager(MemoryBudget(max_slots=1))
    kept = memory.write(1, PayloadType.CUE)
    config = probe_config()
    config.sampling.seed = 42
    memory.retention_policy = MeasuredRetentionPolicy(
        config,
        lambda: memory.fork_for_trial(FIFOPolicy()),
        RetainedCueTask,
        FIFOPolicy,
        "mean_return",
        42,
        True,
    )
    memory.get_event_log()
    with pytest.raises(ValueError, match="overlaps"):
        memory.write(2, PayloadType.CUE)
    assert [r.id for r in memory.get_all_records()] == [kept]
    assert memory.get_event_log() == []


def test_measured_arm_requires_an_explicit_supported_probe_declaration():
    with pytest.raises(ValueError, match="explicit retention_probe"):
        run_experiment(Experiment(policy="measured"))
    config = probe_config()
    config.reference_policy = "measured"
    with pytest.raises(ValueError, match="non-probing"):
        run_experiment(Experiment(policy="measured", retention_probe=config))
    with pytest.raises(ValueError, match="Unsupported"):
        RetentionProbeConfig.from_dict({"unused": True})


def test_declared_cli_example_preserves_adaptive_sampling_and_distinct_batch_seeds(capsys):
    path = Path(__file__).parents[2] / "experiments/configs/measured_keydoor.yaml"
    assert main(["run", "--config", str(path), "--output", "json"]) == 0
    result = json.loads(capsys.readouterr().out)
    batches = result["retention_probes"]
    assert len(batches) == 2
    assert [batch["sampling"]["seed"] for batch in batches] == [1000, 1008]
    assert all(batch["sampling"]["adaptive_sampling"] for batch in batches)
    assert all(batch["sampling"]["fdr_method"] == "bonferroni" for batch in batches)
    assert all(row["n_trials"] == 2 for batch in batches for row in batch["evidence"])
    assert result["usage"]["probe_episodes"] == 8
    assert result["usage"]["total_episodes"] == 11
