"""
Tests for the Causal Memory Manager.
"""

import json

import pytest

from reckon.core.resources import MemoryBudget
from reckon.memory.record import MemoryRecord, PayloadType, RecordOrigin
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.policies import (
    FIFOPolicy,
    LRUPolicy,
    UtilityPolicy,
    EvidencePerBytePolicy,
    RetentionPolicy,
)


class TestMemoryRecord:
    """Tests for MemoryRecord."""

    def test_create_record(self):
        """Test basic record creation."""
        record = MemoryRecord(
            id="test-1",
            timestamp=0,
            payload_type=PayloadType.OBSERVATION,
            payload={"x": 1, "y": 2},
        )
        assert record.id == "test-1"
        assert record.timestamp == 0
        assert record.payload_type == PayloadType.OBSERVATION
        assert record.provenance.hash  # Should auto-generate

    def test_utility_per_cost(self):
        """Test utility per cost calculation."""
        record = MemoryRecord(
            id="test-1",
            timestamp=0,
            payload_type=PayloadType.CUE,
            payload="key",
        )
        record.utility.value = 10.0
        record.cost.bytes = 5

        assert record.utility_per_cost() == 2.0


class TestCausalMemoryManager:
    """Tests for CausalMemoryManager."""

    def test_record_origin_survives_trial_copy_without_sharing_mutable_inputs(self):
        memory = CausalMemoryManager(MemoryBudget(max_slots=2))
        record_id = memory.write(
            "cue", PayloadType.CUE, source_op="summarize", input_ids=["a", "b"]
        )
        original = memory.get_record(record_id)
        assert isinstance(original.provenance, RecordOrigin)
        document = original.to_dict()["provenance"]
        assert document == {
            "source_op": "summarize", "input_ids": ["a", "b"],
            "hash": original.provenance.hash,
        }
        assert len(document["hash"]) == 16
        trial = memory.fork_for_trial(FIFOPolicy())
        copied = trial.get_record(record_id)
        assert copied.to_dict()["provenance"] == document
        copied.provenance.input_ids.append("trial-only")
        assert original.provenance.input_ids == ["a", "b"]

    def test_write_and_read(self):
        """Test basic write and read operations."""
        budget = MemoryBudget(max_slots=10, max_bytes=1000)
        cmm = CausalMemoryManager(budget, episode_id="ep1")

        record_id = cmm.write(
            payload={"obs": "hello"},
            payload_type=PayloadType.OBSERVATION,
            tags=["cue"],
        )

        assert record_id is not None
        assert cmm.current_usage_slots == 1

        hits = cmm.read(query={"tags": ["cue"]})
        assert len(hits) == 1
        assert hits[0].id == record_id

    def test_budget_enforcement_fifo(self):
        """Test that FIFO policy prunes oldest records."""
        budget = MemoryBudget(max_slots=3)
        cmm = CausalMemoryManager(budget, retention_policy=FIFOPolicy())

        ids = []
        for i in range(5):
            cmm.set_step(i)
            rid = cmm.write(
                payload=f"data-{i}",
                payload_type=PayloadType.OBSERVATION,
            )
            ids.append(rid)

        # Should have pruned oldest records
        assert cmm.current_usage_slots == 3
        # First two should be pruned
        assert cmm.get_record(ids[0]) is None
        assert cmm.get_record(ids[1]) is None
        # Last three should remain
        assert cmm.get_record(ids[2]) is not None

    def test_event_logging(self):
        """Test that events are logged correctly."""
        budget = MemoryBudget(max_slots=10)
        cmm = CausalMemoryManager(budget)

        cmm.write(
            payload="test",
            payload_type=PayloadType.CUE,
        )
        cmm.read(query={"tags": []})

        events = cmm.get_event_log()
        assert len(events) == 2
        # Events are returned as dicts from Rust logger with op_type key
        assert events[0]["op_type"] == "write"
        assert events[1]["op_type"] == "read"

    def test_update_score(self):
        """Test causal score updates."""
        budget = MemoryBudget(max_slots=10)
        cmm = CausalMemoryManager(budget)

        rid = cmm.write(
            payload="test",
            payload_type=PayloadType.CUE,
        )

        success = cmm.update_score(
            record_id=rid,
            score_type="ablation_delta",
            value=0.5,
            signal_source="test_probe",
        )

        assert success
        record = cmm.get_record(rid)
        assert record.causal_score.ablation_delta == 0.5


@pytest.mark.parametrize(
    "policy,removed_index",
    [
        (FIFOPolicy(), 0),
        (LRUPolicy(), 1),
        (UtilityPolicy(), 1),
        (EvidencePerBytePolicy(), 1),
    ],
)
@pytest.mark.parametrize("max_slots,max_bytes", [(2, None), (10, 20), (2, 20)])
def test_selected_policy_controls_byte_and_slot_pruning(
    policy, removed_index, max_slots, max_bytes
):
    """Different rankings remain different under each kind of memory pressure."""
    memory = CausalMemoryManager(MemoryBudget(max_slots=max_slots, max_bytes=max_bytes), policy)
    memory.set_step(1)
    old = memory.write("old", PayloadType.CUE, cost_bytes=5, initial_utility=100)
    memory.set_step(2)
    recent = memory.write("recent", PayloadType.CUE, cost_bytes=10, initial_utility=0)
    memory.set_step(3)
    memory.retrieve(record_ids=[old])
    memory.get_event_log()
    memory.set_step(4)
    new = memory.write("incoming", PayloadType.CUE, cost_bytes=10)

    removed = [old, recent][removed_index]
    retained = [old, recent][1 - removed_index]
    assert memory.get_record(removed) is None
    assert {r.id for r in memory.get_all_records()} == {retained, new}
    assert memory.current_usage_slots <= max_slots
    if max_bytes is not None:
        assert memory.current_usage_bytes <= max_bytes
    prunes = [e for e in memory.get_event_log() if e["op_type"] == "prune"]
    assert len(prunes) == 1
    assert prunes[0]["record_id"] == removed
    assert json.loads(prunes[0]["details"])["reason"] == policy.reason()


def test_oversized_write_leaves_records_and_log_unchanged():
    memory = CausalMemoryManager(MemoryBudget(max_slots=2, max_bytes=10))
    retained = memory.write("existing", PayloadType.CUE, cost_bytes=5)
    memory.get_event_log()
    with pytest.raises(ValueError, match="exceeds the byte budget"):
        memory.write("too large", PayloadType.CUE, cost_bytes=11)
    assert [r.id for r in memory.get_all_records()] == [retained]
    assert memory.current_usage_bytes == 5
    assert memory.get_event_log() == []


class IncompletePolicy(RetentionPolicy):
    def select_for_pruning(self, records, overflow_bytes, overflow_slots=0, overflow_tokens=0):
        return []

    def reason(self):
        return "incomplete"


def test_policy_cannot_silently_fall_back_to_a_different_ranking():
    memory = CausalMemoryManager(MemoryBudget(max_slots=1), IncompletePolicy())
    retained = memory.write("existing", PayloadType.CUE)
    memory.get_event_log()
    with pytest.raises(ValueError, match="required bytes and slots"):
        memory.write("incoming", PayloadType.CUE)
    assert [r.id for r in memory.get_all_records()] == [retained]
    assert memory.get_event_log() == []


def test_fifo_frees_enough_bytes_even_when_one_slot_would_suffice():
    memory = CausalMemoryManager(MemoryBudget(max_slots=2, max_bytes=18), FIFOPolicy())
    memory.set_step(1)
    first = memory.write("first", PayloadType.CUE, cost_bytes=5)
    memory.set_step(2)
    second = memory.write("second", PayloadType.CUE, cost_bytes=10)
    memory.set_step(3)
    incoming = memory.write("incoming", PayloadType.CUE, cost_bytes=10)
    assert [r.id for r in memory.get_all_records()] == [incoming]
    pruned = [e["record_id"] for e in memory.get_event_log() if e["op_type"] == "prune"]
    assert pruned == [first, second]
    assert memory.current_usage_bytes == 10


@pytest.mark.parametrize("policy", [FIFOPolicy(), LRUPolicy()])
def test_carried_memory_keeps_scores_events_and_run_order(policy):
    memory = CausalMemoryManager(MemoryBudget(max_slots=2), policy)
    memory.set_episode("first")
    memory.set_step(100)
    old = memory.write("old", PayloadType.CUE, initial_utility=10)
    memory.retrieve(record_ids=[old])

    memory.set_episode("second", reset_memory=False)
    memory.set_step(0)
    recent = memory.write("recent", PayloadType.CUE)
    assert memory.get_record(old).utility.value == 10
    memory.retrieve(record_ids=[recent])
    incoming = memory.write("incoming", PayloadType.CUE)

    assert {r.id for r in memory.get_all_records()} == {recent, incoming}
    events = memory.get_event_log()
    assert [e["event_id"] for e in events] == sorted({e["event_id"] for e in events})
    writes = [e for e in events if e["op_type"] == "write"]
    assert [e["episode_id"] for e in writes] == ["first", "second", "second"]
    assert writes[0]["timestamp"] < writes[1]["timestamp"]


def test_explicit_episode_reset_discards_memory_and_previous_events():
    memory = CausalMemoryManager(MemoryBudget(max_slots=2))
    memory.set_step(100)
    memory.write("old", PayloadType.CUE)
    memory.set_episode("fresh", reset_memory=True)
    assert memory.get_all_records() == []
    assert memory.current_usage_bytes == 0
    assert memory.get_event_log() == []
    record_id = memory.write("new", PayloadType.CUE)
    assert memory.get_record(record_id).timestamp == 0
