"""Record summaries distinguish access, caller labels and stored signed scores."""

import json
from pathlib import Path

import pytest

from reckon.core.resources import MemoryBudget
from reckon.memory import CausalMemoryManager, PayloadType
from reckon.metrics import RecordSummaryMetrics


def test_usage_labels_and_stored_deltas_remain_separate():
    memory = CausalMemoryManager(MemoryBudget(max_slots=8))
    ids = [memory.write(str(index), PayloadType.CUE) for index in range(4)]
    memory.retrieve(record_ids=[ids[0]])
    for record_id, delta in zip(ids, [-0.8, 0.2, float("nan"), float("inf")]):
        memory.update_score(record_id, "ablation_delta", delta)
    summary = RecordSummaryMetrics.from_cmm(
        memory,
        {
            "necessary_cues": [ids[1], "absent"],
            "useful_retrievals": 3,
            "total_retrievals": 4,
        },
    )
    assert summary.used_record_fraction == 0.25
    assert summary.necessary_cue_retention == 0.5
    assert summary.useful_retrieval_fraction is None
    assert summary.max_abs_stored_ablation_delta == 0.8
    assert summary.mean_stored_ablation_delta == pytest.approx(-0.3)
    assert set(summary.to_dict()) == {
        "used_record_fraction",
        "necessary_cue_retention",
        "max_abs_stored_ablation_delta",
        "mean_stored_ablation_delta",
        "proxy_only_record_ids",
        "proxy_only_record_count",
    }


def test_retrieval_fallback_has_its_own_name_and_does_not_invent_cue_retention():
    memory = CausalMemoryManager(MemoryBudget(max_slots=1))
    summary = RecordSummaryMetrics.from_cmm(
        memory,
        {
            "total_cues": 0,
            "useful_retrievals": 3,
            "total_retrievals": 4,
        },
    )
    assert summary.to_dict() == {
        "useful_retrieval_fraction": 0.75,
        "proxy_only_record_ids": [],
        "proxy_only_record_count": 0,
    }
    assert RecordSummaryMetrics.from_cmm(memory, {}).to_dict() == {
        "proxy_only_record_ids": [],
        "proxy_only_record_count": 0,
    }
    assert RecordSummaryMetrics().to_dict() == {}


def test_proxy_only_inventory_preserves_presence_and_does_not_drain_events():
    cases = json.loads((Path(__file__).parent / "fixtures/record_score_presence.json").read_text())
    memory = CausalMemoryManager(MemoryBudget(max_slots=len(cases)))
    expected = []
    fields = {
        "ablationDelta": "ablation_delta",
        "counterfactualDelta": "counterfactual_delta",
        "influenceProxy": "influence_proxy",
    }
    for case in cases:
        record_id = memory.write(case["id"], PayloadType.CUE)
        for key, value in case["score"].items():
            if value is not None:
                memory.update_score(record_id, fields[key], value)
        record = memory.get_record(record_id)
        assert record is not None
        assert record.causal_score.is_proxy_only == (case["source"] == "Proxy only")
        if case["source"] == "Proxy only":
            expected.append(record_id)
    events = memory.get_event_log_jsonl()
    summary = RecordSummaryMetrics.from_cmm(memory, {})
    assert summary.proxy_only_record_ids == sorted(expected)
    assert summary.proxy_only_record_count == 2
    assert summary.to_dict()["proxy_only_record_ids"] == sorted(expected)
    assert memory.get_event_log_jsonl() == events
    memory.prune(expected[0])
    assert RecordSummaryMetrics.from_cmm(memory, {}).proxy_only_record_count == 1
