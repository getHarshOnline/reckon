"""Kernel-backed laboratory retention preserves rankings and refusal before mutation."""

import math

import pytest

from reckon.core.resources import MemoryBudget
from reckon.experiments import Experiment, compare_experiments
from reckon.memory import CausalMemoryManager, DiversityPolicy, UtilityPolicy
from reckon.memory.record import PayloadType


def test_per_byte_names_reach_the_native_rule_without_old_aliases():
    from reckon import _rust
    from reckon.memory import policies

    policy = policies.EvidencePerBytePolicy(evidence_weight=0.75)
    assert policy.rule == "evidence_per_byte"
    assert policy.reason() == "low_evidence_per_byte"
    assert not hasattr(policies, "CausalPolicy")
    description = _rust.RetentionPolicy.evidence_per_byte(evidence_weight=0.75)
    assert description.name == "EvidencePerByte"
    assert "evidence_per_byte" in repr(description)
    assert not hasattr(_rust.RetentionPolicy, "causal")
    with pytest.raises(ValueError, match="unknown retention rule"):
        _rust.select_retention([], "measured_per_byte", 0)


def test_diversity_meets_both_limits():
    memory = CausalMemoryManager(MemoryBudget(max_slots=6, max_bytes=6), DiversityPolicy(2))
    originals = []
    for kind in [PayloadType.ACTION, PayloadType.CUE]:
        for utility in [0, 1, 2]:
            originals.append(
                memory.write(str(utility), kind, cost_bytes=1, initial_utility=utility)
            )
    incoming = memory.write("large", PayloadType.TRACE, cost_bytes=5)
    remaining = {record.id for record in memory.get_all_records()}
    assert remaining == {originals[5], incoming}
    assert memory.current_usage_bytes == 6
    assert memory.current_usage_slots == 2


def test_diversity_runs_in_the_comparison_matrix():
    report = compare_experiments(
        [Experiment(task="keydoor", episodes=3)], ["diversity"], [1, 2], [5, 6]
    )
    assert len(report["rows"]) == 2
    for row in report["rows"]:
        assert [run["configuration"]["seed"] for run in row["runs"]] == [5, 6]
        assert all(run["usage"]["policy_prunes"] > 0 for run in row["runs"])
        assert all(run["usage"]["peak_slots"] <= row["budget_slots"] for run in row["runs"])
        assert all(
            run["retention_score_source"] == "utility_without_measured_effects"
            for run in row["runs"]
        )


def test_invalid_later_score_refuses_before_pruning_or_logging():
    memory = CausalMemoryManager(MemoryBudget(max_slots=2), UtilityPolicy())
    first = memory.write("finite", PayloadType.CUE, initial_utility=0.0)
    second = memory.write("invalid", PayloadType.CUE, initial_utility=math.nan)
    memory.get_event_log()
    with pytest.raises(ValueError, match="finite"):
        memory.write("new", PayloadType.CUE)
    assert {record.id for record in memory.get_all_records()} == {first, second}
    assert memory.get_event_log() == []
