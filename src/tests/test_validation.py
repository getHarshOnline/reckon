"""
Tests for validation logic in core and memory modules.
"""

import pytest

from reckon.core.resources import ResourceVector, MemoryBudget
from reckon.memory.record import RecordCost, CausalScore, UtilityEstimate


class TestResourceVectorValidation:
    """Tests for ResourceVector validation."""

    def test_negative_noise_floor_rejected(self):
        """Negative noise_floor should raise ValueError."""
        with pytest.raises(ValueError, match="noise_floor"):
            ResourceVector(noise_floor=-1.0)

    def test_zero_noise_floor_accepted(self):
        """Zero noise_floor is valid."""
        rv = ResourceVector(noise_floor=0.0)
        assert rv.noise_floor == 0.0

    def test_valid_resource_vector(self):
        """Valid resource vector should be created."""
        rv = ResourceVector(noise_floor=0.01)
        assert rv.noise_floor == 0.01

    def test_negative_memory_slots_rejected(self):
        """Negative memory_slots should raise ValueError."""
        with pytest.raises(ValueError, match="memory_slots"):
            ResourceVector(memory_slots=-1)

    def test_negative_memory_bytes_rejected(self):
        """Negative memory_bytes should raise ValueError."""
        with pytest.raises(ValueError, match="memory_bytes"):
            ResourceVector(memory_bytes=-1)

    def test_negative_memory_tokens_rejected(self):
        """Negative memory_tokens should raise ValueError."""
        with pytest.raises(ValueError, match="memory_tokens"):
            ResourceVector(memory_tokens=-1)

    def test_negative_bandwidth_rejected(self):
        """Negative bandwidth should raise ValueError."""
        with pytest.raises(ValueError, match="bandwidth"):
            ResourceVector(bandwidth=-1.0)

    def test_negative_compute_rejected(self):
        """Negative compute should raise ValueError."""
        with pytest.raises(ValueError, match="compute"):
            ResourceVector(compute=-1.0)


class TestMemoryBudgetValidation:
    """Tests for MemoryBudget validation."""

    def test_zero_max_bytes_rejected(self):
        """Zero max_bytes should raise ValueError."""
        with pytest.raises(ValueError, match="max_bytes"):
            MemoryBudget(max_slots=100, max_bytes=0)

    def test_zero_max_slots_rejected(self):
        """Zero max_slots should raise ValueError."""
        with pytest.raises(ValueError, match="max_slots"):
            MemoryBudget(max_slots=0)

    def test_negative_max_slots_rejected(self):
        """Negative max_slots should raise ValueError."""
        with pytest.raises(ValueError, match="max_slots"):
            MemoryBudget(max_slots=-1)

    def test_negative_max_bytes_rejected(self):
        """Negative max_bytes should raise ValueError."""
        with pytest.raises(ValueError, match="max_bytes"):
            MemoryBudget(max_slots=100, max_bytes=-1)

    def test_valid_budget(self):
        """Valid budget should be created."""
        budget = MemoryBudget(max_slots=100, max_bytes=10000)
        assert budget.max_slots == 100
        assert budget.max_bytes == 10000

    def test_none_max_bytes_accepted(self):
        """None max_bytes is valid (unlimited)."""
        budget = MemoryBudget(max_slots=100, max_bytes=None)
        assert budget.max_bytes is None

    def test_zero_window_size_rejected(self):
        """Zero window_size should raise ValueError."""
        with pytest.raises(ValueError, match="window_size"):
            MemoryBudget(max_slots=100, window_size=0)


class TestRecordCostValidation:
    """Tests for RecordCost validation."""

    def test_zero_bytes_rejected(self):
        """Zero bytes should raise ValueError."""
        with pytest.raises(ValueError, match="byte"):
            RecordCost(bytes=0)

    def test_negative_bytes_rejected(self):
        """Negative bytes should raise ValueError."""
        with pytest.raises(ValueError, match="byte"):
            RecordCost(bytes=-1)

    def test_default_bytes_is_one(self):
        """Default bytes should be 1."""
        cost = RecordCost()
        assert cost.bytes == 1

    def test_zero_slots_rejected(self):
        """Zero slots should raise ValueError."""
        with pytest.raises(ValueError, match="slot"):
            RecordCost(slots=0)

    def test_negative_slots_rejected(self):
        """Negative slots should raise ValueError."""
        with pytest.raises(ValueError, match="slot"):
            RecordCost(slots=-1)

    def test_negative_tokens_rejected(self):
        """Negative tokens should raise ValueError."""
        with pytest.raises(ValueError, match="token"):
            RecordCost(tokens=-1)

    def test_zero_tokens_accepted(self):
        """Zero tokens is valid."""
        cost = RecordCost(bytes=10, tokens=0)
        assert cost.tokens == 0


class TestCausalScoreValidation:
    """Tests for CausalScore validation."""

    def test_ablation_delta_above_range(self):
        """ablation_delta > 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="ablation_delta"):
            CausalScore(ablation_delta=1.5)

    def test_ablation_delta_below_range(self):
        """ablation_delta < -1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="ablation_delta"):
            CausalScore(ablation_delta=-1.5)

    def test_counterfactual_delta_above_range(self):
        """counterfactual_delta > 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="counterfactual_delta"):
            CausalScore(counterfactual_delta=1.5)

    def test_counterfactual_delta_below_range(self):
        """counterfactual_delta < -1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="counterfactual_delta"):
            CausalScore(counterfactual_delta=-1.5)

    def test_influence_proxy_negative_rejected(self):
        """Negative influence_proxy should raise ValueError."""
        with pytest.raises(ValueError, match="influence_proxy"):
            CausalScore(influence_proxy=-0.1)

    def test_influence_proxy_above_range(self):
        """influence_proxy > 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="influence_proxy"):
            CausalScore(influence_proxy=1.5)

    def test_valid_scores(self):
        """Valid causal scores should be created."""
        cs = CausalScore(ablation_delta=0.5, counterfactual_delta=-0.3, influence_proxy=0.8)
        assert cs.ablation_delta == 0.5
        assert cs.counterfactual_delta == -0.3
        assert cs.influence_proxy == 0.8

    def test_none_scores_accepted(self):
        """None scores are valid (not yet evaluated)."""
        cs = CausalScore()
        assert cs.ablation_delta is None
        assert cs.counterfactual_delta is None
        assert cs.influence_proxy is None

    def test_boundary_values_accepted(self):
        """Boundary values (-1, 0, 1) should be accepted."""
        cs = CausalScore(ablation_delta=-1.0, counterfactual_delta=1.0, influence_proxy=0.0)
        assert cs.ablation_delta == -1.0
        assert cs.counterfactual_delta == 1.0
        assert cs.influence_proxy == 0.0


class TestUtilityEstimate:
    """Tests for UtilityEstimate."""

    def test_update_clamps_positive_delta(self):
        """Large positive delta should be clamped to MAX_DELTA."""
        ue = UtilityEstimate()
        ue.update_utility(5000.0)  # Should clamp to 1000
        assert ue.value == 1000.0

    def test_update_clamps_negative_delta(self):
        """Large negative delta should be clamped to -MAX_DELTA."""
        ue = UtilityEstimate()
        ue.update_utility(-5000.0)  # Should clamp to -1000
        assert ue.value == -1000.0

    def test_update_returns_normalization_flag_when_threshold_exceeded(self):
        """Should return True when value exceeds threshold."""
        ue = UtilityEstimate()
        ue.value = 1e6 - 500
        needs_norm = ue.update_utility(1000.0)
        assert needs_norm is True

    def test_update_returns_false_when_below_threshold(self):
        """Should return False when value is below threshold."""
        ue = UtilityEstimate()
        needs_norm = ue.update_utility(100.0)
        assert needs_norm is False

    def test_max_delta_constant(self):
        """MAX_DELTA constant should be 1000."""
        assert UtilityEstimate.MAX_DELTA == 1000.0

    def test_normalization_threshold_constant(self):
        """NORMALIZATION_THRESHOLD constant should be 1e6."""
        assert UtilityEstimate.NORMALIZATION_THRESHOLD == 1e6

    def test_small_delta_not_clamped(self):
        """Small delta within bounds should not be clamped."""
        ue = UtilityEstimate()
        ue.update_utility(50.0)
        assert ue.value == 50.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
