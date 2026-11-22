"""
Property-based tests using hypothesis for math operations.
"""

import pytest
import math

try:
    from hypothesis import given, strategies as st, assume, settings
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

from reckon.memory.record import RecordCost, UtilityEstimate, MemoryRecord, PayloadType


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestRecordCostProperties:
    """Property-based tests for RecordCost."""

    @given(st.integers(min_value=1, max_value=10**9))
    def test_valid_bytes_accepted(self, bytes_val):
        """Any positive integer for bytes should be accepted."""
        cost = RecordCost(bytes=bytes_val)
        assert cost.bytes == bytes_val

    @given(st.integers(max_value=0))
    def test_invalid_bytes_rejected(self, bytes_val):
        """Zero or negative bytes should be rejected."""
        with pytest.raises(ValueError):
            RecordCost(bytes=bytes_val)

    @given(st.integers(min_value=1, max_value=10**9))
    def test_valid_slots_accepted(self, slots_val):
        """Any positive integer for slots should be accepted."""
        cost = RecordCost(slots=slots_val)
        assert cost.slots == slots_val

    @given(st.integers(max_value=0))
    def test_invalid_slots_rejected(self, slots_val):
        """Zero or negative slots should be rejected."""
        with pytest.raises(ValueError):
            RecordCost(slots=slots_val)

    @given(st.integers(min_value=0, max_value=10**9))
    def test_valid_tokens_accepted(self, tokens_val):
        """Non-negative tokens should be accepted."""
        cost = RecordCost(tokens=tokens_val)
        assert cost.tokens == tokens_val

    @given(st.integers(max_value=-1))
    def test_invalid_tokens_rejected(self, tokens_val):
        """Negative tokens should be rejected."""
        with pytest.raises(ValueError):
            RecordCost(tokens=tokens_val)


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestUtilityProperties:
    """Property-based tests for UtilityEstimate."""

    @given(st.floats(allow_nan=False, allow_infinity=False))
    def test_update_delta_clamped(self, delta):
        """Delta should always be clamped to [-MAX_DELTA, MAX_DELTA]."""
        ue = UtilityEstimate()
        initial_value = ue.value
        ue.update_utility(delta)

        # The actual change should be at most MAX_DELTA
        actual_change = ue.value - initial_value
        assert abs(actual_change) <= UtilityEstimate.MAX_DELTA + 1e-10

    @given(st.floats(min_value=-1000, max_value=1000))
    def test_update_accumulates(self, delta):
        """Updates should accumulate correctly."""
        ue = UtilityEstimate()
        ue.update_utility(delta)
        assert abs(ue.value - delta) < 1e-10  # Should equal delta (within float precision)

    @given(st.lists(st.floats(min_value=-100, max_value=100), min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_multiple_updates_accumulate(self, deltas):
        """Multiple updates should sum correctly."""
        ue = UtilityEstimate()
        expected = 0.0
        for delta in deltas:
            ue.update_utility(delta)
            expected += delta
        # Allow for floating-point accumulation errors
        assert abs(ue.value - expected) < 1e-6 * len(deltas)

    @given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12))
    def test_normalization_threshold_detection(self, value):
        """Normalization flag should be True when value exceeds threshold."""
        assume(abs(value) > 0)
        ue = UtilityEstimate()
        ue.value = value

        # Small delta to check threshold
        needs_norm = ue.update_utility(0.0)

        expected = abs(ue.value) > UtilityEstimate.NORMALIZATION_THRESHOLD
        assert needs_norm == expected


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestCausalScoreProperties:
    """Property-based tests for CausalScore."""

    @given(st.floats(min_value=-1.0, max_value=1.0))
    def test_valid_ablation_delta_range(self, value):
        """Any value in [-1, 1] should be valid for ablation_delta."""
        from reckon.memory.record import CausalScore
        cs = CausalScore(ablation_delta=value)
        assert cs.ablation_delta == value

    @given(st.floats(min_value=-1.0, max_value=1.0))
    def test_valid_counterfactual_delta_range(self, value):
        """Any value in [-1, 1] should be valid for counterfactual_delta."""
        from reckon.memory.record import CausalScore
        cs = CausalScore(counterfactual_delta=value)
        assert cs.counterfactual_delta == value

    @given(st.floats(min_value=0.0, max_value=1.0))
    def test_valid_influence_proxy_range(self, value):
        """Any value in [0, 1] should be valid for influence_proxy."""
        from reckon.memory.record import CausalScore
        cs = CausalScore(influence_proxy=value)
        assert cs.influence_proxy == value

    @given(st.floats())
    def test_out_of_range_ablation_delta(self, value):
        """Values outside [-1, 1] should be rejected."""
        from reckon.memory.record import CausalScore
        assume(not math.isnan(value))
        assume(value < -1.0 or value > 1.0)
        with pytest.raises(ValueError):
            CausalScore(ablation_delta=value)


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestMemoryRecordProperties:
    """Property-based tests for MemoryRecord."""

    @given(st.integers(min_value=1, max_value=10**6))
    def test_utility_per_cost_positive_bytes(self, bytes_val):
        """utility_per_cost should work for any positive bytes value."""
        record = MemoryRecord(
            id="test",
            timestamp=0,
            payload_type=PayloadType.OBSERVATION,
            payload="data",
            cost=RecordCost(bytes=bytes_val),
        )
        record.utility.value = 100.0
        result = record.utility_per_cost()
        assert result == 100.0 / bytes_val

    @given(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False))
    def test_utility_per_cost_any_utility(self, utility):
        """utility_per_cost should work for any finite utility value."""
        record = MemoryRecord(
            id="test",
            timestamp=0,
            payload_type=PayloadType.OBSERVATION,
            payload="data",
            cost=RecordCost(bytes=10),
        )
        record.utility.value = utility
        result = record.utility_per_cost()
        assert result == utility / 10.0


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestResourceVectorProperties:
    """Property-based tests for ResourceVector."""

    @given(
        st.integers(min_value=0, max_value=10**9) | st.none(),
        st.integers(min_value=0, max_value=10**12) | st.none(),
        st.floats(min_value=0.0, max_value=1.0),
    )
    def test_valid_resource_vector_creation(self, slots, bytes_val, noise):
        """Valid combinations should create ResourceVector."""
        from reckon.core.resources import ResourceVector
        rv = ResourceVector(
            memory_slots=slots,
            memory_bytes=bytes_val,
            noise_floor=noise,
        )
        assert rv.memory_slots == slots
        assert rv.memory_bytes == bytes_val
        assert rv.noise_floor == noise


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestMemoryBudgetProperties:
    """Property-based tests for MemoryBudget."""

    @given(st.integers(min_value=1, max_value=10**6))
    def test_valid_max_slots(self, slots):
        """Any positive integer should be valid for max_slots."""
        from reckon.core.resources import MemoryBudget
        budget = MemoryBudget(max_slots=slots)
        assert budget.max_slots == slots

    @given(st.integers(min_value=1, max_value=10**12))
    def test_valid_max_bytes(self, bytes_val):
        """Any positive integer should be valid for max_bytes."""
        from reckon.core.resources import MemoryBudget
        budget = MemoryBudget(max_slots=100, max_bytes=bytes_val)
        assert budget.max_bytes == bytes_val

    @given(st.integers(min_value=1, max_value=10**6))
    def test_to_resource_vector_preserves_values(self, slots):
        """to_resource_vector should preserve slot values."""
        from reckon.core.resources import MemoryBudget
        budget = MemoryBudget(max_slots=slots)
        rv = budget.to_resource_vector()
        assert rv.memory_slots == slots


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
