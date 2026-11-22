"""Storage limits and accounting survive mixed operations under every built-in policy."""

import pytest
from hypothesis import given, settings, strategies as st

from reckon.core.resources import MemoryBudget
from reckon.experiments import POLICIES
from reckon.memory import CausalMemoryManager, FIFOPolicy
from reckon.memory.record import PayloadType


@pytest.mark.parametrize("reason", [None, "\ud800"])
@pytest.mark.parametrize("operation", ["admission", "manual"])
def test_invalid_prune_log_reason_is_refused_before_removal(reason, operation):
    class InvalidReasonPolicy(FIFOPolicy):
        def reason(self):
            return reason

    memory = CausalMemoryManager(MemoryBudget(max_slots=1), InvalidReasonPolicy())
    original = memory.write("original", PayloadType.CUE, cost_bytes=1)
    memory.get_event_log()
    with pytest.raises((TypeError, UnicodeEncodeError)):
        if operation == "manual":
            memory.prune(original, reason=reason)
        else:
            memory.write("incoming", PayloadType.CUE)
    assert [r.id for r in memory.get_all_records()] == [original]
    assert memory.current_usage_bytes == 1
    assert memory.get_event_log() == []


@pytest.mark.parametrize("cost", [1.5, 2**63])
def test_unrepresentable_cost_is_refused_before_existing_records_are_pruned(cost):
    memory = CausalMemoryManager(MemoryBudget(max_slots=1))
    original = memory.write("original", PayloadType.CUE, cost_bytes=1)
    memory.get_event_log()
    with pytest.raises((TypeError, OverflowError)):
        memory.write("invalid", PayloadType.CUE, cost_bytes=cost)
    assert [record.id for record in memory.get_all_records()] == [original]
    assert memory.current_usage_bytes == 1
    assert memory.get_event_log() == []


def test_total_byte_overflow_is_refused_before_insertion():
    memory = CausalMemoryManager(MemoryBudget(max_slots=2))
    original = memory.write("large accounting cost", PayloadType.CUE, cost_bytes=2**63 - 1)
    memory.get_event_log()
    with pytest.raises(OverflowError, match="byte total"):
        memory.write("one more byte", PayloadType.CUE, cost_bytes=1)
    assert [r.id for r in memory.get_all_records()] == [original]
    assert memory.current_usage_bytes == 2**63 - 1
    assert memory.get_event_log() == []


def test_slot_pruning_can_make_the_final_byte_total_representable():
    memory = CausalMemoryManager(MemoryBudget(max_slots=1))
    memory.write("old", PayloadType.CUE, cost_bytes=2**63 - 1)
    incoming = memory.write("new", PayloadType.CUE, cost_bytes=2**63 - 1)
    assert [r.id for r in memory.get_all_records()] == [incoming]
    assert memory.current_usage_bytes == 2**63 - 1


@pytest.mark.parametrize("step", [1.5, 2**63, -(2**63) - 1])
def test_invalid_step_leaves_the_previous_timeline_position_usable(step):
    memory = CausalMemoryManager(MemoryBudget(max_slots=1))
    memory.set_step(3)
    with pytest.raises((TypeError, OverflowError)):
        memory.set_step(step)
    incoming = memory.write("valid", PayloadType.CUE)
    assert memory.get_record(incoming).timestamp == 3
    assert memory.get_event_log()[-1]["timestamp"] == 3


@pytest.mark.parametrize("case", ["overflow", "invalid_type", "invalid_utf8"])
def test_invalid_episode_transition_preserves_records_and_episode(case):
    memory = CausalMemoryManager(MemoryBudget(max_slots=1), episode_id="original")
    original = memory.write("kept", PayloadType.CUE, cost_bytes=1)
    memory.set_step(2**63 - 1)
    memory.get_event_log()
    with pytest.raises((TypeError, OverflowError, UnicodeEncodeError)):
        if case == "invalid_type":
            memory.set_episode(123)
        elif case == "invalid_utf8":
            memory.set_episode("\ud800")
        else:
            memory.set_episode("too late", reset_memory=False)
    assert memory.episode_id == "original"
    assert [r.id for r in memory.get_all_records()] == [original]
    assert memory.current_usage_bytes == 1
    assert memory.get_event_log() == []


@pytest.mark.parametrize(
    "policy", ["fifo", "lru", "utility", "evidence_per_byte", "random", "importance", "diversity"]
)
@given(
    slots=st.integers(1, 8),
    byte_limit=st.integers(1, 40),
    operations=st.lists(
        st.tuples(
            st.sampled_from(["write", "write", "remove", "score", "episode"]),
            st.integers(-50, 50),
            st.integers(-20, 20),
            st.sampled_from([PayloadType.ACTION, PayloadType.CUE, PayloadType.TRACE]),
        ),
        min_size=1,
        max_size=40,
    ),
)
@settings(max_examples=60, deadline=None)
def test_mixed_operations_preserve_both_limits_and_exact_accounting(
    policy, slots, byte_limit, operations
):
    memory = CausalMemoryManager(
        MemoryBudget(max_slots=slots, max_bytes=byte_limit), POLICIES[policy]()
    )
    for step, (operation, cost, score, kind) in enumerate(operations):
        memory.set_step(step)
        records = memory.get_all_records()
        memory.get_event_log()
        if operation == "write":
            before = {record.id: record.to_dict() for record in records}
            if cost > byte_limit:
                with pytest.raises(ValueError, match="byte budget"):
                    memory.write("oversized", kind, cost_bytes=cost)
                assert {r.id: r.to_dict() for r in memory.get_all_records()} == before
                assert memory.get_event_log() == []
            else:
                incoming = memory.write(
                    str(step),
                    kind,
                    cost_bytes=cost,
                    initial_utility=score,
                    metadata={"importance": score},
                )
                assert memory.get_record(incoming) is not None
        elif operation == "episode":
            memory.set_episode(str(step), reset_memory=cost % 2 == 0)
        elif records:
            selected = records[cost % len(records)].id
            if operation == "remove":
                assert memory.prune(selected)
                assert not memory.prune(selected)
            else:
                assert memory.update_score(selected, "utility", score)

        remaining = memory.get_all_records()
        assert memory.current_usage_slots == len(remaining) <= slots
        assert memory.current_usage_bytes == sum(r.cost.bytes for r in remaining) <= byte_limit
        assert len({r.id for r in remaining}) == len(remaining)
