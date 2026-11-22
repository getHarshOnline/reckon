"""
Tests for Reckon core module.
"""

import pytest

from reckon.core.resources import ResourceVector, MemoryBudget
from reckon.core.causality import DirectInfluenceRecords, DistinguishabilityMeasure


class TestResourceVector:
    """Tests for ResourceVector."""

    def test_create_resource_vector(self):
        """Test basic resource vector creation."""
        rv = ResourceVector(
            memory_slots=100,
            memory_bytes=10000,
            noise_floor=0.01,
        )
        assert rv.memory_slots == 100
        assert rv.memory_bytes == 10000
        assert rv.noise_floor == 0.01

    def test_is_satisfied(self):
        """Test budget satisfaction check."""
        budget = ResourceVector(memory_slots=100, memory_bytes=1000)
        usage = ResourceVector(memory_slots=50, memory_bytes=500)

        assert budget.is_satisfied(usage)

        over_usage = ResourceVector(memory_slots=150, memory_bytes=500)
        assert not budget.is_satisfied(over_usage)


class TestMemoryBudget:
    """Tests for MemoryBudget."""

    def test_create_budget(self):
        """Test budget creation."""
        budget = MemoryBudget(max_slots=100, max_bytes=10000)
        assert budget.max_slots == 100
        assert budget.max_bytes == 10000

    def test_to_resource_vector(self):
        """Test conversion to ResourceVector."""
        budget = MemoryBudget(max_slots=50, max_bytes=5000, max_tokens=1000)
        rv = budget.to_resource_vector()

        assert rv.memory_slots == 50
        assert rv.memory_bytes == 5000
        assert rv.memory_tokens == 1000


class TestDirectInfluenceRecords:
    """Tests for DirectInfluenceRecords."""

    def test_add_and_check_relation(self):
        """Test adding and checking causal relations."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        records.add_relation(
            source="cue_A",
            target="reward_B",
            distinguishability=0.8,
            threshold=0.1,
        )

        assert records.causes("cue_A", "reward_B")
        assert not records.causes("reward_B", "cue_A")

    def test_upstream_downstream(self):
        """Test getting upstream and downstream events."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        records.add_relation("A", "B", 0.5)
        records.add_relation("A", "C", 0.5)
        records.add_relation("D", "B", 0.5)

        downstream = records.downstream_of("A")
        assert "B" in downstream
        assert "C" in downstream

        upstream = records.upstream_of("B")
        assert "A" in upstream
        assert "D" in upstream


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
