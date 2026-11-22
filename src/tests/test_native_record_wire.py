"""A generated Python producer through native storage and back to its contract."""

import pytest

pytest.importorskip("betterproto2", reason="Requires the optional wire runtime.")
from reckon._rust import Record, RecordStore
from reckon.generated.reckon import (
    CausalScore,
    MemoryRecord,
    PayloadType,
    RecordCost,
    RecordOrigin,
    UtilityEstimate,
)


def complete_record(timestamp=42):
    """Use nondefaults and opaque bytes so a compact projection cannot pass."""
    return MemoryRecord(
        id="wire-cue",
        timestamp=timestamp,
        episode_id="native-roundtrip",
        payload_type=PayloadType.CUE,
        payload=b"\x00\xff\x80opaque",
        compressed=True,
        encoding="producer-codec",
        cost=RecordCost(bytes=9, tokens=0, slots=1),
        tags=["second", "first", "second"],
        provenance=RecordOrigin(source_op="observe", input_ids=["b", "a"], hash="supplied"),
        utility=UtilityEstimate(value=-0.25, uncertainty=0.75, last_used=-1, use_count=0),
        causal_score=CausalScore(
            ablation_delta=0.0, counterfactual_delta=-0.5, influence_proxy=None, last_evaluated=7
        ),
        metadata=b"\xff\x00metadata",
        created_at_step=0,
        created_at_sequence=None,
    )


@pytest.mark.parametrize("timestamp", [0, 42, -(2**63), 2**63 - 1])
def test_generated_python_native_store_roundtrip(timestamp):
    original = complete_record(timestamp)
    store = RecordStore(2)
    store.insert_record(Record.from_wire(bytes(original)))
    stored = store.get(original.id)
    assert stored is not None
    assert stored.timestamp == timestamp
    assert bytes(MemoryRecord.parse(stored.to_wire())) == bytes(original)
    assert store.current_bytes == 9
    fork = store.fork()
    store.update_utility(original.id, 0.5)
    store.touch(original.id, 51)
    expected = complete_record(timestamp)
    expected.utility.value = 0.5
    expected.utility.last_used = 51
    expected.utility.use_count = 1
    assert MemoryRecord.parse(store.remove(original.id).to_wire()) == expected
    assert MemoryRecord.parse(fork.get(original.id).to_wire()) == original


def test_failed_insert_preserves_previous_record_and_accounting():
    original = complete_record()
    store = RecordStore(1)
    store.insert_record(Record.from_wire(bytes(original)))
    invalid = complete_record()
    invalid.cost.bytes = -1
    with pytest.raises(ValueError, match="non-negative"):
        store.insert_record(Record.from_wire(bytes(invalid)))
    assert store.current_bytes == 9
    assert MemoryRecord.parse(store.get(original.id).to_wire()) == original


def test_touch_refuses_imported_maximum_count_without_partial_mutation():
    original = complete_record()
    original.utility.use_count = 2**31 - 1
    store = RecordStore(1)
    store.insert_record(Record.from_wire(bytes(original)))
    before = store.get(original.id).to_wire()
    with pytest.raises(OverflowError, match="use count"):
        store.touch(original.id, 51)
    assert store.get(original.id).to_wire() == before
    assert store.current_bytes == 9
    assert store.touch("missing", 51) is False


def test_missing_messages_and_malformed_wire_are_refused():
    for field in ["cost", "utility", "causal_score"]:
        value = complete_record()
        setattr(value, field, None)
        with pytest.raises(ValueError, match=field):
            Record.from_wire(bytes(value))
    with pytest.raises(ValueError):
        Record.from_wire(b"\xff")


def test_public_manager_keeps_python_objects_mutability_and_unknown_tokens():
    from types import SimpleNamespace
    from reckon.core.resources import MemoryBudget
    from reckon.memory.manager import CausalMemoryManager
    from reckon.memory.record import PayloadType as PublicPayloadType

    payload = SimpleNamespace(values=[1, 2])
    marker = object()
    tags = ["second", "first", "second"]
    manager = CausalMemoryManager(MemoryBudget(max_slots=2))
    identity = manager.write(
        payload, PublicPayloadType.CUSTOM, tags=tags, metadata={"marker": marker}
    )
    stored = manager.get_record(identity)
    assert stored.payload is payload
    assert stored.metadata["marker"] is marker
    assert stored.tags is tags
    assert stored.cost.tokens is None
    assert manager.current_usage_tokens is None
    payload.values.append(3)
    assert manager.get_record(identity).payload.values == [1, 2, 3]


if __name__ == "__main__":
    # The browser check consumes actual native-store output, not a TS fixture.
    import json

    samples = []
    for timestamp in [0, 42, -(2**63), 2**63 - 1]:
        value = complete_record(timestamp)
        value.id = f"wire-{timestamp}"
        if timestamp == 42:
            value.provenance = None
            value.created_at_step = None
            value.created_at_sequence = 0
        native_store = RecordStore(1)
        native_store.insert_record(Record.from_wire(bytes(value)))
        samples.append(list(native_store.get(value.id).to_wire()))
    print(json.dumps(samples))
