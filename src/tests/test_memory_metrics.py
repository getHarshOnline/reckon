"""Memory metrics consume the events emitted by the native manager."""

import pytest

from reckon.core.resources import MemoryBudget
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.record import PayloadType
from reckon.metrics.memory import MemoryEfficiencyMetrics


def test_native_events_supply_counts_and_usage_samples():
    memory = CausalMemoryManager(MemoryBudget(max_slots=3))
    first = memory.write("first", PayloadType.CUE, cost_bytes=5)
    second = memory.write("second", PayloadType.CUE, cost_bytes=10)
    memory.retrieve(record_ids=[first, second])
    memory.retrieve(record_ids=[first])
    memory.retrieve(record_ids=[second])
    memory.prune(second)

    metrics = MemoryEfficiencyMetrics.from_cmm(
        memory,
        {"total_reward": 30, "total_writes": 100, "total_reads": 100, "useful_reads": 2},
    )

    assert metrics.peak_usage_bytes == 15
    assert metrics.average_usage_bytes == 10
    assert metrics.total_reward_per_byte == 2
    assert metrics.total_reward_per_slot == 30
    assert metrics.reads_per_write == 1.5
    assert metrics.useful_reads_per_read == pytest.approx(2 / 3)
    assert memory.get_event_log() == []


def test_reward_scope_is_named_and_absence_is_not_a_measured_zero():
    memory = CausalMemoryManager(MemoryBudget(max_slots=3))
    memory.write("retained", PayloadType.CUE, cost_bytes=5)
    mean = MemoryEfficiencyMetrics.from_cmm(memory, {"mean_return": 10})
    assert mean.mean_return_per_byte == 2
    assert mean.mean_return_per_slot == 10
    assert mean.total_reward_per_byte is None
    total = MemoryEfficiencyMetrics.from_cmm(memory, {"total_reward": 0, "mean_return": 10})
    assert total.total_reward_per_byte == 0
    assert total.total_reward_per_slot == 0
    assert total.mean_return_per_byte is None
    missing = MemoryEfficiencyMetrics.from_cmm(memory, {})
    assert not any("reward" in key or "return" in key for key in missing.to_dict())


def test_no_write_samples_do_not_invent_an_average():
    memory = CausalMemoryManager(MemoryBudget(max_slots=3))
    memory.write("retained", PayloadType.CUE, cost_bytes=5)
    memory.get_event_log()

    metrics = MemoryEfficiencyMetrics.from_cmm(
        memory, {"total_reward": 10, "total_writes": 2, "total_reads": 3}
    )

    assert metrics.peak_usage_bytes == 5
    assert metrics.average_usage_bytes is None
    assert metrics.total_reward_per_byte == 2
    assert metrics.reads_per_write == 1.5
