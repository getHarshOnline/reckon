"""Configuration must change the executed task and comparisons retain every seed."""

import json
from pathlib import Path
from statistics import stdev

import pytest

from reckon.cli import main
from reckon.experiments import Experiment, compare_experiments, load_experiment, run_experiment


def test_run_applies_configuration_and_explicit_overrides(tmp_path, capsys):
    path = tmp_path / "experiment.yaml"
    path.write_text(
        "task: bandit\nenvironment:\n  num_arms: 2\n  num_modes: 2\n"
        "  mode_switch_interval: 7\nbudget:\n  max_slots: 3\n"
        "retention_policy: fifo\nexperiment:\n  num_episodes: 2\n  seed: 7\n"
        "  reset_memory: true\n  learn_utility: false\n"
    )
    assert (
        main(["run", "--config", str(path), "--policy", "evidence_per_byte",
              "--evidence-weight", "0.75", "--seed", "19", "--output", "json"])
        == 0
    )
    actual = json.loads(capsys.readouterr().out)
    expected = run_experiment(
        Experiment(
            task="bandit",
            environment={"num_arms": 2, "num_modes": 2, "mode_switch_interval": 7},
            budget_slots=3,
            policy="evidence_per_byte",
            evidence_weight=0.75,
            episodes=2,
            seed=19,
            reset_memory=True,
            learn_utility=False,
        )
    )
    assert actual["configuration"] == expected["configuration"]
    assert actual["result"] == expected["result"]
    assert actual["score_source"] == "fixed_initial_utility"
    assert actual["usage"]["peak_slots"] <= 3
    assert actual["usage"]["elapsed_s"] > 0


@pytest.mark.parametrize(
    "source",
    [
        "task: keydoor\ncausal_weight: 0.5",
        "task: keydoor\nretention_policy: causal",
        "task: keydoor\nagent: {type: baseline}",
        "task: keydoor\nenvironment: {grid_size: 10}",
        "task: bandit\nenvironment: {mode_switch_prob: 0.1}",
        "task: tutor\nexperiment: {learn_utility: 'false'}",
        "task: continual\nbudget: {max_tokens: 100}",
        "task: bandit\nenvironment: {reward_std: .nan}",
        "task: bandit\nenvironment: {num_modes: 1}",
        "task: continual\nenvironment: {feature_dim: 1}",
        "task: continual\nenvironment: {feature_dim: 3}",
        "!!python/object:invalid.Class {}",
        "task: keydoor\ntask: bandit",
        "task: keydoor\nbudget: {max_slots: 1, max_slots: 10}",
    ],
)
def test_unused_or_invalid_settings_are_refused(tmp_path, source):
    path = tmp_path / "invalid.yaml"
    path.write_text(source)
    with pytest.raises(ValueError):
        load_experiment(str(path))


def test_comparison_runs_full_matrix_with_paired_seeds():
    report = compare_experiments(
        [Experiment(task="keydoor", episodes=3)], ["fifo", "utility"], [1, 2], [7, 8, 9]
    )
    assert len(report["rows"]) == 4
    for row in report["rows"]:
        assert [run["configuration"]["seed"] for run in row["runs"]] == [7, 8, 9]
        values = [run["result"]["performance"]["success_rate"] for run in row["runs"]]
        assert row["mean"] == sum(values) / 3
        assert row["stdev"] == stdev(values)
        assert row["probe_episodes"] == 0
        assert row["probe_elapsed_s"] == 0
        assert all(run["usage"]["peak_slots"] <= row["budget_slots"] for run in row["runs"])
        assert all(run["usage"]["policy_prunes"] > 0 for run in row["runs"])
        assert row["elapsed_s"] > 0


def test_single_seed_spread_is_unavailable_and_repeated_seeds_fail():
    row = compare_experiments([Experiment(episodes=1)], ["fifo"], [1], [42])["rows"][0]
    assert row["stdev"] is None
    with pytest.raises(ValueError, match="distinct"):
        compare_experiments([Experiment()], ["fifo"], [1], [42, 42])


def test_saved_examples_execute_their_declared_settings():
    root = Path(__file__).resolve().parents[2]
    for name in ("task_a_keydoor.yaml", "task_b_bandit.yaml"):
        config = load_experiment(str(root / "experiments" / "configs" / name))
        result = run_experiment(config)
        assert result["configuration"]["task"] == config.task
        assert result["result"]["raw_data"]["learn_utility"] == config.learn_utility
        assert result["usage"]["peak_bytes"] <= config.budget_bytes


def test_compare_cli_returns_one_json_document(capsys):
    assert (
        main(
            [
                "compare",
                "--tasks",
                "keydoor",
                "--policies",
                "fifo",
                "lru",
                "--budget-slots",
                "1",
                "--seeds",
                "42",
                "43",
                "--episodes",
                "2",
                "--output",
                "json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert len(report["rows"]) == 2
    assert report["seeds"] == [42, 43]
