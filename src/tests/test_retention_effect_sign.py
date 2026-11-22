"""Harmful measured effects do not earn a retention bonus."""

import pytest

from reckon.core.resources import MemoryBudget
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.policies import EvidencePerBytePolicy
from reckon.memory.record import PayloadType


@pytest.mark.parametrize("score_type", ["ablation_delta", "counterfactual_delta"])
def test_harmful_effect_is_pruned_before_beneficial_effect(score_type):
    memory = CausalMemoryManager(MemoryBudget(max_slots=2), EvidencePerBytePolicy(evidence_weight=1))
    harmful = memory.write("harmful", PayloadType.CUE, cost_bytes=5)
    useful = memory.write("useful", PayloadType.CUE, cost_bytes=5)
    memory.update_score(harmful, score_type, -100)
    memory.update_score(useful, score_type, 1)
    memory.update_score(harmful, "influence_proxy", 1000)
    record = memory.get_record(harmful)
    incoming = memory.write("incoming", PayloadType.CUE, cost_bytes=5)
    assert {r.id for r in memory.get_all_records()} == {useful, incoming}
    assert getattr(record.causal_score, score_type) == -100


def test_harmful_effect_does_not_erase_separate_utility():
    memory = CausalMemoryManager(MemoryBudget(max_slots=2), EvidencePerBytePolicy(evidence_weight=0.5))
    high_utility = memory.write("utility", PayloadType.CUE, cost_bytes=5, initial_utility=10)
    effect_only = memory.write("effect", PayloadType.CUE, cost_bytes=5)
    memory.update_score(high_utility, "ablation_delta", -100)
    memory.update_score(effect_only, "ablation_delta", 1)
    incoming = memory.write("incoming", PayloadType.CUE, cost_bytes=5)
    assert {r.id for r in memory.get_all_records()} == {high_utility, incoming}
