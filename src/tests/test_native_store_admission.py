"""Direct binding callers must receive refusal before native accounting changes."""

import pytest

from reckon._rust import RecordStore


def snapshot(store):
    return (
        store.current_bytes,
        sorted((key, store.get(key).cost_bytes, store.get(key).utility) for key in store.ids()),
        store.select_for_pruning(2**63 - 1),
    )


@pytest.mark.parametrize("target", ["new", "a"])
def test_negative_native_insert_preserves_records_and_priority(target):
    store = RecordStore(max_slots=2)
    store.insert("a", 0, "trial", "cue", b"a", 1)
    store.insert("b", 0, "trial", "cue", b"b", 2)
    store.update_utility("a", 0.75)
    before = snapshot(store)

    with pytest.raises(ValueError, match="non-negative"):
        store.insert(target, 1, "trial", "cue", b"invalid", -1)

    assert snapshot(store) == before


@pytest.mark.parametrize("target,cost", [("new", 1), ("b", 2)])
def test_native_total_overflow_preserves_records_and_priority(target, cost):
    store = RecordStore(max_slots=2)
    store.insert("a", 0, "trial", "cue", b"a", 2**63 - 2)
    store.insert("b", 0, "trial", "cue", b"b", 1)
    before = snapshot(store)

    with pytest.raises(OverflowError, match="byte total"):
        store.insert(target, 1, "trial", "cue", b"invalid", cost)

    assert snapshot(store) == before


def test_native_replacement_deducts_old_cost_before_checking_total():
    store = RecordStore(max_slots=1)
    store.insert("a", 0, "trial", "cue", b"a", 2**63 - 1)
    store.insert("a", 1, "trial", "cue", b"replacement", 2**63 - 1)
    assert store.current_bytes == 2**63 - 1
    assert len(store) == 1
    store.insert("a", 2, "trial", "cue", b"zero", 0)
    assert store.current_bytes == 0
    assert store.remove("a") is not None
    assert store.current_bytes == 0
