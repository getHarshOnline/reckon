"""Notebook ablations remove real records and keep both arms' costs."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "notebooks"))
from _utils.adapters.conversation import run_conversation_episode
from _utils.adapters.record_probe import AdapterProbeConfig, evaluate_adapter_record
from reckon.core.resources import MemoryBudget
from reckon.memory import CausalMemoryManager, FIFOPolicy, PayloadType
from reckon.measured_retention import MeasuredRetentionPolicy, RetentionProbeConfig


def test_conversation_probe_removes_a_real_constraint_before_its_read():
    result = evaluate_adapter_record(
        AdapterProbeConfig("conversation"),
        "first_constraint",
        lambda record: "constraint" in record.tags,
        n_trials=4,
    )
    evaluation = result["evaluation"]
    assert evaluation["delta"] > 0
    assert result["probe_episodes"] == len(result["arms"]) == 8
    assert result["probe_elapsed_s"] >= sum(arm["elapsed_s"] for arm in result["arms"])
    assert result["reference_policy"] == {"name": "FIFOPolicy", "parameters": {}}
    for index, trial in enumerate(evaluation["trials"]):
        baseline, removed = result["arms"][2 * index : 2 * index + 2]
        assert baseline["seed"] == removed["seed"] == trial["seed"]
        assert trial["baseline"]["target_sha256"] == trial["intervention"]["target_sha256"]
        assert not trial["baseline"]["removed"]
        assert trial["intervention"]["removed"]
        target = trial["intervention"]["record_id"]
        assert any(
            event["op_type"] == "prune" and event["record_id"] == target
            for event in removed["result"]["events"]
        )
        assert not any(target in turn["retrieved_ids"] for turn in removed["result"]["transcript"])
        assert baseline["usage"]["prunes"] == 0
        assert removed["usage"]["prunes"] == 1
        assert baseline["usage"]["peak_slots"] > 0
        assert baseline["usage"]["peak_bytes"] > 0


def test_missing_target_is_not_a_zero_effect():
    with pytest.raises(ValueError, match="never reached"):
        evaluate_adapter_record(
            AdapterProbeConfig("conversation", budget_slots=1),
            "first_constraint",
            lambda record: "constraint" in record.tags,
            n_trials=2,
        )


def test_probe_requires_independent_policies():
    policy = FIFOPolicy()
    with pytest.raises(ValueError, match="fresh policy"):
        evaluate_adapter_record(
            AdapterProbeConfig("conversation"),
            "cue",
            lambda record: True,
            policy_factory=lambda: policy,
        )


def test_probe_rejects_measured_retention_before_running_any_episode(monkeypatch):
    from _utils.adapters.record_probe import AdapterProbeTask

    def unexpected(*args, **kwargs):
        pytest.fail("A rejected reference must not launch an episode or snapshot")

    monkeypatch.setattr(AdapterProbeTask, "run", unexpected)

    class DerivedMeasuredPolicy(MeasuredRetentionPolicy):
        pass

    for policy_type in (MeasuredRetentionPolicy, DerivedMeasuredPolicy):
        policy = policy_type(
            RetentionProbeConfig(),
            snapshot_factory=unexpected,
            task_factory=unexpected,
            reference_factory=FIFOPolicy,
            metric="mean_return",
            main_seed=42,
            learn_utility=True,
        )
        with pytest.raises(ValueError, match="non-probing reference"):
            evaluate_adapter_record(
                AdapterProbeConfig("conversation"),
                "cue",
                lambda record: True,
                policy_factory=lambda: policy,
            )
        assert not policy.batches


def test_injected_memory_is_validated_without_losing_its_contents():
    policy = FIFOPolicy()
    memory = CausalMemoryManager(MemoryBudget(max_slots=100, max_bytes=50000), policy)
    marker = memory.write("existing", PayloadType.CUE)
    with pytest.raises(ValueError, match="initially empty"):
        run_conversation_episode(policy, 100, 42, memory=memory)
    assert memory.get_record(marker) is not None
    with pytest.raises(ValueError, match="budget and policy"):
        run_conversation_episode(policy, 1, 42, memory=memory)


def test_minigrid_probe_reads_the_actual_initial_object():
    pytest.importorskip("minigrid")
    result = evaluate_adapter_record(
        AdapterProbeConfig("minigrid", max_steps=100),
        "initial_object",
        lambda record: "initial_cue" in record.tags,
        n_trials=2,
    )
    assert result["probe_episodes"] == 4
    for baseline, removed in zip(result["arms"][::2], result["arms"][1::2]):
        assert baseline["result"]["cue_retrieved_at_fork"]
        assert not removed["result"]["cue_retrieved_at_fork"]
        assert not baseline["result"]["demo_mode"]
        assert not removed["result"]["demo_mode"]


def test_textworld_probe_refuses_prerecorded_fallback(monkeypatch):
    from _utils.adapters import textworld_adapter

    monkeypatch.setattr(textworld_adapter, "check_available", lambda: False)
    with pytest.raises(RuntimeError, match="actual game dependency"):
        evaluate_adapter_record(
            AdapterProbeConfig("textworld", max_steps=10),
            "first_action",
            lambda record: "action" in record.tags,
            n_trials=2,
        )
