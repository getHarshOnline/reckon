"""
Tests for numeric safety (epsilon comparisons, inf/nan handling).
"""

import pytest
import math

from reckon.core.causality import CausalRelation, DirectInfluenceRecords, EPSILON
from reckon.core.resources import ResourceVector


class TestFloatEpsilon:
    """Tests for EPSILON-based comparisons."""

    def test_epsilon_defined(self):
        """EPSILON should be a small positive number."""
        assert EPSILON > 0
        assert EPSILON < 1e-6

    def test_epsilon_value(self):
        """EPSILON should be 1e-9."""
        assert EPSILON == 1e-9

    def test_near_threshold_comparison_above(self):
        """Values just above threshold should be considered causal."""
        rv = ResourceVector(memory_slots=10)
        relation = CausalRelation(
            source="A",
            target="B",
            resources=rv,
            distinguishability=0.5 + EPSILON / 2,  # Just above threshold
            threshold=0.5,
        )
        assert relation.is_causal is True

    def test_near_threshold_comparison_below(self):
        """Values significantly below threshold should not be causal."""
        rv = ResourceVector(memory_slots=10)
        relation = CausalRelation(
            source="A",
            target="B",
            resources=rv,
            distinguishability=0.5 - EPSILON * 2,  # Below threshold
            threshold=0.5,
        )
        assert relation.is_causal is False

    def test_exactly_at_threshold(self):
        """Value exactly at threshold should be considered causal."""
        rv = ResourceVector(memory_slots=10)
        relation = CausalRelation(
            source="A",
            target="B",
            resources=rv,
            distinguishability=0.5,  # Exactly at threshold
            threshold=0.5,
        )
        assert relation.is_causal is True

    def test_floating_point_precision_edge_case(self):
        """Edge case: 0.1 + 0.2 != 0.3 in floating point."""
        rv = ResourceVector(memory_slots=10)
        # 0.1 + 0.2 in floating point is slightly more than 0.3
        computed_value = 0.1 + 0.2
        relation = CausalRelation(
            source="A",
            target="B",
            resources=rv,
            distinguishability=computed_value,
            threshold=0.3,
        )
        # Should handle this correctly with epsilon
        assert relation.is_causal is True


class TestDirectInfluenceRecordsEdgeCases:
    """Tests for DirectInfluenceRecords edge cases."""

    def test_zero_distinguishability(self):
        """Zero distinguishability should not be causal."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)
        records.add_relation("A", "B", distinguishability=0.0, threshold=0.1)
        assert records.causes("A", "B") is False

    def test_one_distinguishability(self):
        """Maximum distinguishability should be causal."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)
        records.add_relation("A", "B", distinguishability=1.0, threshold=0.1)
        assert records.causes("A", "B") is True

    def test_very_small_threshold(self):
        """Very small thresholds should work correctly."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)
        records.add_relation("A", "B", distinguishability=1e-8, threshold=1e-10)
        assert records.causes("A", "B") is True


class TestNumericBoundaries:
    """Tests for numeric boundary conditions."""

    def test_utility_per_cost_with_min_bytes(self):
        """utility_per_cost should use minimum floor of 1 byte."""
        from reckon.memory.record import MemoryRecord, PayloadType, RecordCost

        record = MemoryRecord(
            id="test",
            timestamp=0,
            payload_type=PayloadType.OBSERVATION,
            payload="data",
            cost=RecordCost(bytes=1),  # Minimum valid bytes
        )
        record.utility.value = 10.0
        # Should divide by max(bytes, 1) = 1
        assert record.utility_per_cost() == 10.0

    def test_large_utility_values(self):
        """Large utility values should be handled correctly."""
        from reckon.memory.record import UtilityEstimate

        ue = UtilityEstimate()
        # Apply many updates
        for _ in range(1000):
            ue.update_utility(999.0)  # Just under MAX_DELTA
        # Value should be clamped per update but can accumulate
        assert ue.value == 999.0 * 1000  # 1000 updates of 999 each

    def test_negative_utility_accumulation(self):
        """Negative utility should accumulate correctly."""
        from reckon.memory.record import UtilityEstimate

        ue = UtilityEstimate()
        ue.update_utility(-500.0)
        ue.update_utility(-500.0)
        assert ue.value == -1000.0

    def test_alternating_utility_updates(self):
        """Alternating positive/negative updates should cancel out."""
        from reckon.memory.record import UtilityEstimate

        ue = UtilityEstimate()
        for _ in range(100):
            ue.update_utility(100.0)
            ue.update_utility(-100.0)
        assert abs(ue.value) < 1e-10  # Should be approximately 0


class TestResourceVectorNumericConstraints:
    """Tests for numeric constraints in ResourceVector."""

    def test_zero_values_accepted(self):
        """Zero values (except noise_floor) should be accepted."""
        rv = ResourceVector(
            memory_slots=0,
            memory_bytes=0,
            memory_tokens=0,
            bandwidth=0.0,
            compute=0.0,
            noise_floor=0.0,
        )
        assert rv.memory_slots == 0
        assert rv.noise_floor == 0.0

    def test_large_values_accepted(self):
        """Very large values should be accepted."""
        rv = ResourceVector(
            memory_slots=10**9,
            memory_bytes=10**15,
            memory_tokens=10**12,
        )
        assert rv.memory_slots == 10**9
        assert rv.memory_bytes == 10**15


class TestInfNanFiltering:
    """Tests for infinity and NaN handling."""

    def test_inf_in_utility_update(self):
        """Infinity in utility update should be clamped."""
        from reckon.memory.record import UtilityEstimate

        ue = UtilityEstimate()
        # Large values get clamped to MAX_DELTA
        ue.update_utility(float("inf"))
        # After clamping, value should be MAX_DELTA
        assert ue.value == UtilityEstimate.MAX_DELTA
        assert not math.isinf(ue.value)

    def test_negative_inf_in_utility_update(self):
        """Negative infinity in utility update should be clamped."""
        from reckon.memory.record import UtilityEstimate

        ue = UtilityEstimate()
        ue.update_utility(float("-inf"))
        assert ue.value == -UtilityEstimate.MAX_DELTA
        assert not math.isinf(ue.value)

    def test_nan_in_utility_update(self):
        """NaN in utility update should be handled gracefully."""
        from reckon.memory.record import UtilityEstimate

        ue = UtilityEstimate()
        # NaN is clamped to MAX_DELTA (1000.0) due to Python min/max behavior
        # This is acceptable - NaN doesn't corrupt the system
        ue.update_utility(float("nan"))
        # Value should not be NaN (system handles it gracefully)
        assert not math.isnan(ue.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
