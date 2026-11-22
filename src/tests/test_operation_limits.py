"""Operation budgets refuse calls before storage, access or event mutation."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from reckon.core.resources import MemoryBudget
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.record import PayloadType


def write(memory, payload="cue"):
    return memory.write(payload, PayloadType.CUE, cost_bytes=1)


def test_write_window_is_sliding_and_refusal_does_not_prune():
    memory = CausalMemoryManager(
        MemoryBudget(max_slots=1, max_write_ops_per_window=2, window_size=3)
    )
    write(memory)
    memory.set_step(1)
    retained = write(memory)
    before = memory.get_event_log()
    assert len(before) == 3  # Two writes and one policy prune.
    memory.set_step(2)
    with pytest.raises(RuntimeError, match="write rate"):
        write(memory)
    assert memory.get_record(retained) is not None
    assert memory.current_usage_bytes == memory.current_usage_slots == 1
    assert memory.get_event_log() == []
    memory.set_step(3)  # Only the step-zero write has expired.
    retained = write(memory)
    with pytest.raises(RuntimeError, match="write rate"):
        write(memory)
    assert memory.get_record(retained) is not None
    memory.set_step(4)
    write(memory)


def test_empty_reads_count_and_refusals_do_not_touch_records_or_call_interventions():
    memory = CausalMemoryManager(MemoryBudget(max_read_ops_per_window=1, window_size=2))
    record_id = write(memory)
    assert memory.read(record_ids=["missing"]) == []
    memory.get_event_log()
    called = []
    with memory.before_read(lambda records: called.append(records)):
        with pytest.raises(RuntimeError, match="read rate"):
            memory.retrieve(record_ids=[record_id])
    assert called == []
    assert memory.get_record(record_id).utility.use_count == 0
    assert memory.get_event_log() == []
    memory.set_step(2)
    assert [r.id for r in memory.retrieve(record_ids=[record_id])] == [record_id]
    assert memory.get_record(record_id).utility.use_count == 1


def test_failed_calls_release_their_reservations():
    memory = CausalMemoryManager(
        MemoryBudget(max_read_ops_per_window=1, max_write_ops_per_window=1)
    )
    with pytest.raises(TypeError):
        memory.write(object(), PayloadType.CUE)
    record_id = write(memory)

    def fail(_records):
        raise ValueError("trial failed")

    with memory.before_read(fail), pytest.raises(ValueError, match="trial failed"):
        memory.read()
    assert memory.read()[0].id == record_id
    with pytest.raises(RuntimeError, match="read rate"):
        memory.read()


def test_carried_episodes_keep_limits_and_full_resets_start_new_windows():
    memory = CausalMemoryManager(MemoryBudget(max_write_ops_per_window=1, window_size=3))
    write(memory)
    memory.set_episode("second", reset_memory=False)
    memory.set_step(0)
    with pytest.raises(RuntimeError, match="write rate"):
        write(memory)
    memory.set_step(2)  # Absolute step three.
    write(memory)
    with pytest.raises(ValueError, match="non-decreasing"):
        memory.set_step(1)
    memory.set_episode("fresh", reset_memory=True)
    assert memory.current_usage_slots == 0
    write(memory)


def test_limits_are_independent_and_concurrent_calls_cannot_overspend():
    memory = CausalMemoryManager(
        MemoryBudget(max_write_ops_per_window=3, max_read_ops_per_window=2)
    )

    def attempt(_):
        try:
            return write(memory)
        except RuntimeError:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(attempt, range(24)))
    assert sum(value is not None for value in outcomes) == 3
    memory.read()
    memory.read()
    with pytest.raises(RuntimeError, match="read rate"):
        memory.read()
    events = memory.get_event_log()
    assert len(events) == 5


def test_in_progress_read_cannot_reset_the_quota_or_reenter_past_its_limit():
    memory = CausalMemoryManager(MemoryBudget(max_read_ops_per_window=1))
    write(memory)

    def intervene(_records):
        with pytest.raises(RuntimeError, match="read rate"):
            memory.read()
        with pytest.raises(RuntimeError, match="timeline"):
            memory.set_episode("bypass")
        with pytest.raises(RuntimeError, match="timeline"):
            memory.set_step(1000)

    with memory.before_read(intervene):
        assert len(memory.read()) == 1
    assert memory.episode_id == ""
    with pytest.raises(RuntimeError, match="read rate"):
        memory.read()


def test_changed_rate_settings_need_validated_full_reset():
    budget = MemoryBudget(max_write_ops_per_window=1)
    memory = CausalMemoryManager(budget)
    record_id = write(memory)
    budget.max_write_ops_per_window = 2
    with pytest.raises(ValueError, match="full episode reset"):
        write(memory)
    budget.window_size = 0
    with pytest.raises(ValueError, match="window_size"):
        memory.set_episode("invalid")
    assert memory.get_record(record_id) is not None
    assert memory.episode_id == ""
    budget.window_size = 100
    memory.set_episode("new")
    write(memory)
    write(memory)
    with pytest.raises(RuntimeError, match="write rate"):
        write(memory)


@pytest.mark.parametrize(
    "name", ["max_read_ops_per_window", "max_write_ops_per_window", "window_size"]
)
@pytest.mark.parametrize("value", [0, -1, 1.5, float("nan"), True])
def test_operation_budgets_are_positive_integers(name, value):
    with pytest.raises(ValueError, match=name):
        MemoryBudget(**{name: value})
