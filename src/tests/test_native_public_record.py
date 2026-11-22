"""Real manager values through native storage, explicit encoding and the viewer."""

import json
from copy import deepcopy
from dataclasses import asdict, is_dataclass, replace
from types import SimpleNamespace

import pytest

from reckon import _rust
from reckon.core.resources import MemoryBudget
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.policies import FIFOPolicy
from reckon.memory.record import PayloadType, RecordCost


def stored_record(tokens=None):
    manager = CausalMemoryManager(MemoryBudget(max_slots=2), episode_id="native-public")
    shared = ["second", "first", "second"]
    payload = SimpleNamespace(values=[1, 2])
    marker = object()
    identity = manager.write(
        payload,
        PayloadType.CUE,
        tags=shared,
        input_ids=shared,
        source_op="observe",
        cost_bytes=9,
        cost_tokens=tokens,
        metadata={"marker": marker},
    )
    record = manager.get_record(identity)
    assert isinstance(record, _rust.MemoryRecord)
    assert isinstance(record.cost, _rust.RecordCost)
    assert record.payload is payload
    assert record.metadata["marker"] is marker
    assert record.tags is record.provenance.input_ids is shared
    record.compressed = True
    record.encoding = "producer-codec"
    record.created_at_step = 0
    record.utility.value = -0.25
    record.utility.uncertainty = 0.75
    record.causal_score.ablation_delta = 0.0
    record.causal_score.counterfactual_delta = -0.5
    record.causal_score.last_evaluated = 7
    return manager, record


def snapshots():
    documents = []
    for tokens in [None, 0, 2**63 - 1]:
        manager, record = stored_record(tokens)
        assert manager.get_all_records()[0] is record
        documents.append(json.loads(record.snapshot_json(b"\x00\xffopaque", b"\xff\x00metadata")))
    return documents


def test_native_values_keep_dataclass_copying_and_cycles_without_shared_trial_mutations():
    import pickle

    manager, record = stored_record()
    assert is_dataclass(record)
    assert replace(record, cost=RecordCost(bytes=3)).payload is record.payload
    record.metadata["self"] = record
    copied = deepcopy(record)
    assert copied.metadata["self"] is copied
    assert copied.tags is copied.provenance.input_ids
    assert copied.tags is not record.tags
    restored = pickle.loads(pickle.dumps(record))
    assert isinstance(restored, _rust.MemoryRecord)
    assert restored.metadata["self"] is restored
    assert restored.tags is restored.provenance.input_ids
    assert restored.cost.tokens is None
    copied.payload.values.append(3)
    assert record.payload.values == [1, 2]
    trial = manager.fork_for_trial(FIFOPolicy())
    trial_record = trial.get_record(record.id)
    assert trial_record.metadata["self"] is trial_record
    assert trial_record is not record
    trial.prune(record.id)
    assert trial.get_all_records() == []
    assert manager.get_record(record.id) is record
    manager.set_episode("reset", reset_memory=True)
    assert manager.get_all_records() == []


def test_mutable_cost_does_not_change_admitted_accounting_or_unknown_tokens():
    manager, record = stored_record(0)
    record.cost.bytes = 999
    record.cost.tokens = None
    assert manager.current_usage_bytes == 9
    assert manager.current_usage_tokens == 0
    assert json.loads(record.snapshot_json(b"", b""))["cost"]["tokens"] is None


@pytest.mark.parametrize("method", ["insert", "insert_record"])
def test_byte_replacement_refuses_live_objects_without_changing_either_view(method):
    manager, record = stored_record(3)
    store = manager._store
    admitted = store.get(record.id).to_wire()
    live = record.snapshot_json(b"payload", b"metadata")
    events = manager.get_event_log_jsonl()
    usage = (store.current_bytes, store.current_tokens, len(store))
    ranking = store.select_for_pruning(store.current_bytes)
    byte_store = _rust.RecordStore()
    byte_store.insert(record.id, 99, "replacement", "action", b"other", 4, 7)
    replacement = byte_store.get(record.id)
    with pytest.raises(ValueError, match="object-backed"):
        if method == "insert":
            store.insert(record.id, 99, "replacement", "action", b"other", 4, 7)
        else:
            store.insert_record(replacement)
    assert manager.get_record(record.id) is record
    assert record.snapshot_json(b"payload", b"metadata") == live
    assert store.get(record.id).to_wire() == admitted
    assert (store.current_bytes, store.current_tokens, len(store)) == usage
    assert store.select_for_pruning(store.current_bytes) == ranking
    assert manager.get_event_log_jsonl() == events
    assert store.touch_object(record.id, 12)
    assert record.utility.use_count == store.get(record.id).use_count == 1
    assert record.utility.last_used == store.get(record.id).last_used == 12


def test_invalid_native_field_is_refused_before_any_budget_removal():
    manager = CausalMemoryManager(MemoryBudget(max_slots=1))
    identity = manager.write("kept", PayloadType.CUE)
    before = manager.get_event_log_jsonl()
    with pytest.raises(TypeError):
        manager.write("invalid", PayloadType.CUE, tags=[object()])
    assert manager.get_record(identity) is not None
    assert manager.current_usage_slots == 1
    assert manager.get_event_log_jsonl() == before


def test_snapshot_keeps_unknown_zero_and_large_counts_without_rewriting_old_wire():
    documents = snapshots()
    assert [item["cost"]["tokens"] for item in documents] == [None, "0", str(2**63 - 1)]
    manager, record = stored_record()
    with pytest.raises(ValueError, match="unknown token count"):
        record.snapshot_wire(b"opaque", b"metadata")
    record.cost.tokens = 0
    wire = record.snapshot_wire(b"opaque", b"metadata")
    stored = _rust.Record.from_wire(wire)
    assert stored.cost_tokens == 0
    assert stored.to_wire() == wire
    assert manager.current_usage_tokens is None


def test_public_access_count_overflow_changes_neither_native_view():
    manager, record = stored_record()
    record.utility.use_count = 2**31 - 1
    before = asdict(record.utility)
    admitted = manager._store.get(record.id).to_wire()
    with pytest.raises(OverflowError, match="use count"):
        manager.read(record_ids=[record.id])
    assert asdict(record.utility) == before
    assert manager._store.get(record.id).to_wire() == admitted
    with pytest.raises(OverflowError, match="native integer range"):
        record.update_utility(1.0, 51)
    assert asdict(record.utility) == before


def test_json_refuses_nonfinite_numbers_without_replacing_measurements():
    _, record = stored_record()
    record.causal_score.influence_proxy = float("inf")
    with pytest.raises(ValueError, match="finite"):
        record.snapshot_json(b"", b"")
    assert record.causal_score.influence_proxy == float("inf")


def test_opaque_cycles_are_collectable_after_the_manager_is_released():
    import gc
    import weakref

    manager, record = stored_record()
    record.metadata["manager"] = manager
    record.provenance.input_ids.append(record)
    observed = weakref.ref(record)
    del manager, record
    gc.collect()
    assert observed() is None


def test_generated_schema_validates_actual_snapshots_and_refuses_wrong_field_types():
    jsonschema = pytest.importorskip(
        "jsonschema", reason="Install the dev extra for schema validation"
    )
    schema = json.loads(_rust.record_schema())
    for value in snapshots():
        jsonschema.validate(value, schema)
    _, record = stored_record()
    record.provenance = None
    absent = json.loads(record.snapshot_json(b"payload", b"metadata"))
    assert absent["provenance"] is None
    jsonschema.validate(absent, schema)
    del absent["provenance"]
    jsonschema.validate(absent, schema)
    for field, bad in [("timestamp", 42), ("payload", [256]), ("payloadType", "not-a-kind")]:
        value = snapshots()[0]
        value[field] = bad
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(value, schema)
    value = snapshots()[0]
    value["cost"]["tokens"] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(value, schema)
    value = snapshots()[0]
    value["invented"] = "not declared"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(value, schema)


if __name__ == "__main__":
    print(json.dumps(snapshots()))
