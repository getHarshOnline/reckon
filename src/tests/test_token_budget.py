"""Declared token costs share the actual policy order and native accounting."""

import pytest
from hypothesis import given, settings, strategies as st

from reckon._rust import RecordStore
from reckon.core.resources import MemoryBudget
from reckon.experiments import POLICIES
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.policies import FIFOPolicy
from reckon.memory.record import PayloadType


def write(memory, tokens, *, size=1):
    return memory.write("cue", PayloadType.CUE, cost_bytes=size, cost_tokens=tokens)


@pytest.mark.parametrize(
    "policy", ["fifo", "lru", "utility", "evidence_per_byte", "random", "importance", "diversity"]
)
@given(
    slots=st.integers(1, 5),
    byte_limit=st.integers(1, 20),
    token_limit=st.integers(1, 20),
    operations=st.lists(
        st.tuples(st.integers(0, 4), st.integers(1, 20), st.integers(0, 20)), max_size=40
    ),
)
@settings(max_examples=40, deadline=None)
def test_every_policy_preserves_all_three_limits_through_mixed_operations(
    policy, slots, byte_limit, token_limit, operations
):
    memory = CausalMemoryManager(
        MemoryBudget(max_slots=slots, max_bytes=byte_limit, max_tokens=token_limit),
        POLICIES[policy](),
    )
    for step, (operation, size, tokens) in enumerate(operations):
        memory.set_step(step)
        records = memory.get_all_records()
        if operation < 2:
            if size > byte_limit or tokens > token_limit:
                before = [r.id for r in records]
                with pytest.raises(ValueError):
                    write(memory, tokens, size=size)
                assert [r.id for r in memory.get_all_records()] == before
            else:
                write(memory, tokens, size=size)
        elif operation == 2 and records:
            memory.prune(records[0].id)
        elif operation == 3:
            memory.retrieve()
        else:
            memory.set_episode(str(step), reset_memory=bool(tokens % 2))
        records = memory.get_all_records()
        assert memory.current_usage_slots == len(records) <= slots
        assert memory.current_usage_bytes == sum(r.cost.bytes for r in records) <= byte_limit
        assert memory.current_usage_tokens == sum(r.cost.tokens for r in records) <= token_limit


def test_zero_and_missing_counts_remain_distinct_and_enabling_a_limit_requires_complete_counts():
    budget = MemoryBudget()
    memory = CausalMemoryManager(budget)
    uncounted = write(memory, None)
    zero = write(memory, 0)
    assert "tokens" not in memory.get_record(uncounted).to_dict()["cost"]
    assert memory.get_record(zero).to_dict()["cost"]["tokens"] == 0
    assert memory.get_record(zero).cost.tokens == 0
    assert memory.current_usage_tokens is None
    budget.max_tokens = 2
    with pytest.raises(ValueError, match="requires counts"):
        write(memory, 1)
    memory.prune(uncounted)
    assert memory.current_usage_tokens == 0
    write(memory, 2)
    assert memory.current_usage_tokens == 2
    memory.set_episode("carried", reset_memory=False)
    assert memory.current_usage_tokens == 2
    memory.set_episode("fresh")
    assert memory.current_usage_tokens == 0


@pytest.mark.parametrize("tokens", [None, -1, 1.5, True, float("nan"), 2**63, 11])
def test_invalid_or_oversized_token_cost_never_evicts_existing_records(tokens):
    memory = CausalMemoryManager(MemoryBudget(max_slots=1, max_tokens=10))
    kept = write(memory, 4)
    memory.get_event_log()
    with pytest.raises((ValueError, OverflowError)):
        write(memory, tokens)
    assert [r.id for r in memory.get_all_records()] == [kept]
    assert memory.current_usage_tokens == 4
    assert memory.get_event_log() == []


def test_combined_pressure_keeps_the_policy_order_and_validates_native_costs():
    memory = CausalMemoryManager(MemoryBudget(max_slots=3, max_bytes=10, max_tokens=10))
    first = write(memory, 0, size=7)
    second = write(memory, 4)
    third = write(memory, 6)
    # Changing returned metadata cannot fake freed tokens or change admission costs.
    memory.get_record(first).cost.tokens = 100
    memory.get_record(second).cost.bytes = 100
    memory.get_event_log()
    incoming = write(memory, 5, size=2)
    assert [r.id for r in memory.get_all_records()] == [incoming]
    assert [e["record_id"] for e in memory.get_event_log() if e["op_type"] == "prune"] == [
        first,
        second,
        third,
    ]
    assert (memory.current_usage_bytes, memory.current_usage_tokens) == (2, 5)


def test_custom_policy_cannot_claim_token_savings_by_mutating_its_input():
    class Incomplete(FIFOPolicy):
        def select_for_pruning(self, records, overflow_bytes, overflow_slots=0, overflow_tokens=0):
            records[0].cost.tokens = 100
            return [records[0].id]

    memory = CausalMemoryManager(MemoryBudget(max_tokens=10), Incomplete())
    first = write(memory, 1)
    second = write(memory, 9)
    memory.get_event_log()
    with pytest.raises(ValueError, match="required bytes and slots and tokens"):
        write(memory, 5)
    assert [r.id for r in memory.get_all_records()] == [first, second]
    assert memory.current_usage_tokens == 10
    assert memory.get_record(first).cost.tokens == 1
    assert memory.get_event_log() == []


def test_total_overflow_refuses_before_pruning_but_valid_removal_can_make_it_fit():
    memory = CausalMemoryManager(MemoryBudget(max_slots=2))
    kept = write(memory, 2**63 - 1)
    memory.get_event_log()
    with pytest.raises(OverflowError, match="token total"):
        write(memory, 1)
    assert memory.get_record(kept) is not None
    assert memory.get_event_log() == []
    memory.budget.max_slots = 1
    write(memory, 2**63 - 1)
    assert memory.get_record(kept) is None
    assert memory.current_usage_tokens == 2**63 - 1


def test_native_binding_preserves_token_costs_and_refuses_invalid_replacements():
    store = RecordStore()
    store.insert("a", 0, "trial", "cue", b"a", 1, 2**63 - 1)
    with pytest.raises(OverflowError, match="token total"):
        store.insert("b", 0, "trial", "cue", b"b", 1, 1)
    with pytest.raises(ValueError, match="token cost"):
        store.insert("a", 0, "trial", "cue", b"changed", 9, -1)
    assert store.get("a").cost_tokens == store.current_tokens == 2**63 - 1
    assert store.current_bytes == 1
    store.insert("a", 0, "trial", "cue", b"a", 1, 2)
    assert store.current_tokens == 2
    store.remove("a")
    assert store.current_tokens == 0
