"""
Tests for Reckon Credit Assignment.

Tests EpisodeContext tracking, credit policies, and utility updates.
"""

import json
import math
import time

import pytest

from reckon.core.episode_context import (
    EpisodeContext,
    get_current_context,
    set_current_context,
    clear_current_context,
)
from reckon.core.credit import (
    CreditPolicy,
    CreditAssignment,
    compute_credit,
    update_utility,
)
from reckon.core.resources import MemoryBudget
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.record import PayloadType


class TestEpisodeContext:
    """Tests for EpisodeContext."""

    def test_create_context(self):
        """Test basic context creation."""
        ctx = EpisodeContext(episode_id="ep_001")
        assert ctx.episode_id == "ep_001"
        assert ctx.step == 0
        assert len(ctx.id) > 0  # UUID generated
        assert ctx.retrieved_record_ids == []

    def test_context_manager(self):
        """Test context manager protocol."""
        ctx = EpisodeContext(episode_id="ep_001")

        # Before entering context
        assert get_current_context() is None

        with ctx:
            # Inside context
            assert get_current_context() is ctx

        # After exiting context
        assert get_current_context() is None

    def test_context_tracks_records(self):
        """Test that context tracks retrieved records."""
        ctx = EpisodeContext(episode_id="ep_001")

        ctx.add_retrieved_record("r1")
        ctx.add_retrieved_record("r2")

        assert ctx.retrieved_record_ids == ["r1", "r2"]

    def test_add_record_is_idempotent(self):
        """Test that adding same record twice doesn't duplicate."""
        ctx = EpisodeContext(episode_id="ep_001")

        ctx.add_retrieved_record("r1")
        ctx.add_retrieved_record("r1")

        assert ctx.retrieved_record_ids == ["r1"]

    def test_advance_step_clears_records(self):
        """Test that advancing step clears retrieved records."""
        ctx = EpisodeContext(episode_id="ep_001")

        ctx.add_retrieved_record("r1")
        assert ctx.step == 0

        ctx.advance_step()

        assert ctx.step == 1
        assert ctx.retrieved_record_ids == []

    def test_context_expiry(self):
        """Test context expiry detection."""
        # Create context with very short TTL
        ctx = EpisodeContext(episode_id="ep_001", ttl_ms=1)

        # Wait for expiry
        time.sleep(0.01)

        assert ctx.is_expired()

    def test_context_not_expired(self):
        """Test that fresh context is not expired."""
        ctx = EpisodeContext(episode_id="ep_001", ttl_ms=300000)
        assert not ctx.is_expired()

    def test_nested_contexts(self):
        """Test nested context managers."""
        ctx1 = EpisodeContext(episode_id="ep_001")
        ctx2 = EpisodeContext(episode_id="ep_002")

        with ctx1:
            assert get_current_context() is ctx1

            with ctx2:
                assert get_current_context() is ctx2

            # Back to ctx1 after exiting ctx2
            assert get_current_context() is ctx1

        assert get_current_context() is None


class TestCreditPolicy:
    """Tests for credit policies."""

    def test_simple_policy_equal_credit(self):
        """Test SIMPLE policy distributes equal credit."""
        credits = compute_credit(
            record_ids=["r1", "r2", "r3"],
            outcome=1.0,
            policy=CreditPolicy.SIMPLE,
        )

        assert len(credits) == 3

        # Each should get 1/3
        for c in credits:
            assert abs(c.credit - 1 / 3) < 0.001

    def test_credit_sum_is_one(self):
        """Test that credit sum equals 1.0."""
        credits = compute_credit(
            record_ids=["r1", "r2", "r3", "r4"],
            outcome=1.0,
            policy=CreditPolicy.SIMPLE,
        )

        credit_sum = sum(c.credit for c in credits)
        assert abs(credit_sum - 1.0) < 0.001

    def test_none_policy_returns_empty(self):
        """Test NONE policy returns no credits."""
        credits = compute_credit(
            record_ids=["r1", "r2"],
            outcome=1.0,
            policy=CreditPolicy.NONE,
        )

        assert credits == []

    def test_shaped_policy_weights_by_utility(self):
        """At scale 2, the weights are log(3/2), log(2) and log(3)."""
        utilities = {"negative": -2 * math.log(2), "zero": 0.0, "positive": 2 * math.log(2)}

        credits = compute_credit(
            record_ids=["negative", "zero", "positive"],
            outcome=-1.0,
            policy=CreditPolicy.SHAPED,
            utilities=utilities,
            shaped_scale=2.0,
        )

        assert [c.record_id for c in credits] == list(utilities)
        assert [c.credit for c in credits] == pytest.approx(
            [math.log(1.5) / math.log(9), math.log(2) / math.log(9), 0.5]
        )

    def test_shaped_policy_normalizes_large_finite_weights(self):
        credits = compute_credit(
            ["r1", "r2"], 1.0, CreditPolicy.SHAPED, {"r1": 1.6e308, "r2": 8e307}
        )
        assert [c.credit for c in credits] == pytest.approx([2 / 3, 1 / 3])

    @pytest.mark.parametrize("utility", [math.nan, math.inf, -math.inf, -1000.0])
    def test_shaped_policy_rejects_invalid_or_unrepresentable_credit(self, utility):
        with pytest.raises(ValueError, match="SHAPED credit"):
            compute_credit(["r1", "r2"], 1.0, CreditPolicy.SHAPED, {"r1": utility, "r2": 0.0})

    def test_shaped_policy_rejects_all_underflow(self):
        with pytest.raises(ValueError, match="underflowed"):
            compute_credit(["r1"], 1.0, CreditPolicy.SHAPED, {"r1": -1000.0})

    def test_shaped_policy_rejects_underflow_during_normalization(self):
        with pytest.raises(ValueError, match="underflowed"):
            compute_credit(["r1", "r2"], 1.0, CreditPolicy.SHAPED, {"r1": -500.0, "r2": 1e308})

    def test_shaped_policy_remains_monotone_near_zero(self):
        low, high = compute_credit(
            ["r1", "r2"], 1.0, CreditPolicy.SHAPED, {"r1": -1e-12, "r2": 1e-12}
        )
        assert low.credit < 0.5 < high.credit
        assert math.fsum([low.credit, high.credit]) == pytest.approx(1.0)

    @pytest.mark.parametrize("scale", [0.0, -1.0, math.inf, math.nan])
    def test_shaped_policy_rejects_invalid_scale(self, scale):
        with pytest.raises(ValueError, match="positive scale"):
            compute_credit(["r1"], 1.0, CreditPolicy.SHAPED, shaped_scale=scale)

    def test_shaped_policy_rejects_nonfinite_outcome(self):
        with pytest.raises(ValueError, match="finite outcome"):
            compute_credit(["r1"], math.nan, CreditPolicy.SHAPED)

    def test_shaped_policy_empty_retrieval_is_noop(self):
        assert compute_credit([], 1.0, CreditPolicy.SHAPED) == []

    def test_shaped_policy_fallback_without_utilities(self):
        """Test SHAPED policy falls back to equal credit without utilities."""
        credits = compute_credit(
            record_ids=["r1", "r2"],
            outcome=1.0,
            policy=CreditPolicy.SHAPED,
            utilities=None,
        )

        # Should fall back to equal credit
        for c in credits:
            assert abs(c.credit - 0.5) < 0.001

    def test_ablation_policy_weights_by_delta(self):
        """Test ABLATION policy weights by measured ablation deltas."""
        ablation_deltas = {"r1": 0.8, "r2": 0.2}

        credits = compute_credit(
            record_ids=["r1", "r2"],
            outcome=1.0,
            policy=CreditPolicy.ABLATION,
            ablation_deltas=ablation_deltas,
        )

        credit_dict = {c.record_id: c.credit for c in credits}
        assert abs(credit_dict["r1"] - 0.8) < 0.001
        assert abs(credit_dict["r2"] - 0.2) < 0.001

    def test_empty_record_ids(self):
        """Test with empty record IDs."""
        credits = compute_credit(
            record_ids=[],
            outcome=1.0,
            policy=CreditPolicy.SIMPLE,
        )

        assert credits == []

    @pytest.mark.parametrize("scores", [{"r1": -2.0, "r2": 0.0}, {"r1": -2.0}])
    def test_measured_nonpositive_effects_do_not_get_fallback_credit(self, scores):
        credits = compute_credit(["r1", "r2"], 1.0, CreditPolicy.ABLATION, ablation_deltas=scores)
        assert [credit.credit for credit in credits] == [0.0, 0.0]

    def test_unmeasured_records_keep_explicit_equal_credit_fallback(self):
        credits = compute_credit(["r1", "r2"], 1.0, CreditPolicy.ABLATION)
        assert [credit.credit for credit in credits] == [0.5, 0.5]

    @pytest.mark.parametrize(
        "policy", [CreditPolicy.SIMPLE, CreditPolicy.SHAPED, CreditPolicy.ABLATION]
    )
    def test_active_credit_rejects_nonfinite_outcomes(self, policy):
        with pytest.raises(ValueError, match="finite outcome"):
            compute_credit(["r1"], math.inf, policy)

    def test_ablation_credit_rejects_nonfinite_measurement(self):
        with pytest.raises(ValueError, match="finite measured"):
            compute_credit(["r1"], 1.0, CreditPolicy.ABLATION, ablation_deltas={"r1": math.nan})


class TestUtilityUpdate:
    """Tests for utility update function."""

    def test_documented_update_example(self):
        """Keep the public EMA example numerically correct."""
        result = update_utility(0.5, credit=0.33, outcome=1.0)

        assert result == pytest.approx(0.483)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"current_utility": math.nan},
            {"credit": math.inf},
            {"eta": 0.0},
            {"eta": 1.1},
            {"u_min": 2.0, "u_max": 1.0},
        ],
    )
    def test_invalid_update_is_rejected(self, kwargs):
        arguments = {"current_utility": 0.5, "credit": 0.5, "outcome": 1.0}
        arguments.update(kwargs)
        with pytest.raises(ValueError):
            update_utility(**arguments)

    def test_basic_update(self):
        """Test basic EMA utility update."""
        # u <- (1 - eta) * u + eta * credit * outcome
        # 0.5 <- 0.9 * 0.5 + 0.1 * 0.5 * 1.0 = 0.45 + 0.05 = 0.5
        result = update_utility(
            current_utility=0.5,
            credit=0.5,
            outcome=1.0,
            eta=0.1,
        )

        assert abs(result - 0.5) < 0.001

    def test_positive_outcome_increases_utility(self):
        """Test that positive outcome can increase utility."""
        result = update_utility(
            current_utility=0.3,
            credit=1.0,
            outcome=1.0,
            eta=0.1,
        )

        # 0.9 * 0.3 + 0.1 * 1.0 * 1.0 = 0.27 + 0.1 = 0.37
        assert result > 0.3

    def test_clamping_to_max(self):
        """Test that utility is clamped to u_max."""
        result = update_utility(
            current_utility=0.95,
            credit=1.0,
            outcome=1.0,
            eta=0.5,
            u_max=1.0,
        )

        # Would be 0.5 * 0.95 + 0.5 * 1.0 = 0.975, but should clamp
        assert result <= 1.0

    def test_clamping_to_min(self):
        """Test that utility is clamped to u_min."""
        result = update_utility(
            current_utility=0.1,
            credit=0.0,
            outcome=-1.0,
            eta=0.5,
            u_min=0.0,
        )

        assert result >= 0.0


class TestManagerRetrieveObserve:
    """Tests for CausalMemoryManager retrieve() and observe()."""

    @pytest.fixture
    def manager(self):
        """Create a test memory manager."""
        budget = MemoryBudget(max_slots=100, max_bytes=10000)
        return CausalMemoryManager(budget, episode_id="test_ep")

    def test_invalid_later_utility_does_not_partially_update_earlier_record(self, manager):
        ids = [
            manager.write(payload={"x": value}, payload_type=PayloadType.OBSERVATION)
            for value in range(2)
        ]
        first, second = [manager.get_record(rid) for rid in ids]
        first.utility.value = 0.5
        second.utility.value = math.nan
        with EpisodeContext(episode_id="test"):
            manager.retrieve(record_ids=ids)
            with pytest.raises(ValueError, match="finite inputs"):
                manager.observe(1.0)
        assert first.utility.value == 0.5

    def test_ablation_observe_preserves_deltas_and_records_literal_policy(self, manager):
        deltas = [-2.0, 1.0, 3.0]
        ids = [
            manager.write(
                payload={"x": i}, payload_type=PayloadType.OBSERVATION, initial_utility=0.5
            )
            for i in range(3)
        ]
        for rid, delta in zip(ids, deltas):
            manager.get_record(rid).causal_score.ablation_delta = delta
        with EpisodeContext(episode_id="test"):
            manager.retrieve(record_ids=ids)
            credits = manager.observe(1.0, policy=CreditPolicy.ABLATION)
        by_id = {item.record_id: item for item in credits}
        for rid, delta, weight in zip(ids, deltas, [0.0, 0.25, 0.75]):
            assert by_id[rid].credit == pytest.approx(weight)
            assert by_id[rid].to_dict()["policy"] == "ablation"
            assert CreditAssignment.from_dict(by_id[rid].to_dict()) == by_id[rid]
            record = manager.get_record(rid)
            assert record.causal_score.ablation_delta == delta
            assert record.utility.value == pytest.approx(0.45 + 0.1 * weight)
        updates = [
            event for event in manager.get_event_log() if event["op_type"] == "update_score"
        ]
        assert {event["record_id"] for event in updates} == set(ids)
        assert {json.loads(event["details"])["signal_source"] for event in updates} == {
            "observe:ablation"
        }
        assert not hasattr(CreditPolicy, "CAUSAL")
        with pytest.raises(ValueError):
            CreditPolicy("causal")

    def test_retrieve_tracks_in_context(self, manager):
        """Test that retrieve tracks records in context."""
        # Write some records
        r1 = manager.write(payload={"x": 1}, payload_type=PayloadType.OBSERVATION)
        r2 = manager.write(payload={"x": 2}, payload_type=PayloadType.OBSERVATION)

        with EpisodeContext(episode_id="test") as ctx:
            hits = manager.retrieve(record_ids=[r1, r2])

            assert len(hits) == 2
            assert set(ctx.retrieved_record_ids) == {r1, r2}

    def test_observe_distributes_credit(self, manager):
        """Test that observe distributes credit."""
        # Write some records
        r1 = manager.write(payload={"x": 1}, payload_type=PayloadType.OBSERVATION)
        r2 = manager.write(payload={"x": 2}, payload_type=PayloadType.OBSERVATION)

        with EpisodeContext(episode_id="test") as ctx:
            manager.retrieve(record_ids=[r1, r2])
            credits = manager.observe(outcome=1.0, policy=CreditPolicy.SIMPLE)

            assert len(credits) == 2
            credit_sum = sum(c.credit for c in credits)
            assert abs(credit_sum - 1.0) < 0.001

    def test_observe_updates_utility(self, manager):
        """Test that observe updates record utility."""
        # Write record with known initial utility
        r1 = manager.write(
            payload={"x": 1},
            payload_type=PayloadType.OBSERVATION,
            initial_utility=0.0,
        )

        with EpisodeContext(episode_id="test") as ctx:
            manager.retrieve(record_ids=[r1])
            manager.observe(outcome=1.0, policy=CreditPolicy.SIMPLE)

        # Check utility was updated
        record = manager.get_record(r1)
        assert record is not None
        assert record.utility.value > 0.0

    def test_observe_without_context_returns_empty(self, manager):
        """Test that observe without context returns empty."""
        r1 = manager.write(payload={"x": 1}, payload_type=PayloadType.OBSERVATION)

        # Don't use EpisodeContext
        credits = manager.observe(outcome=1.0)

        assert credits == []

    def test_observe_with_empty_context_returns_empty(self, manager):
        """Test that observe with empty context returns empty."""
        with EpisodeContext(episode_id="test") as ctx:
            # Don't retrieve anything
            credits = manager.observe(outcome=1.0)

            assert credits == []

    def test_utility_is_clamped_per_observe(self, manager):
        """Test that credit sum is clamped per observe call."""
        # Write multiple records
        r1 = manager.write(payload={"x": 1}, payload_type=PayloadType.OBSERVATION)
        r2 = manager.write(payload={"x": 2}, payload_type=PayloadType.OBSERVATION)
        r3 = manager.write(payload={"x": 3}, payload_type=PayloadType.OBSERVATION)

        with EpisodeContext(episode_id="test") as ctx:
            manager.retrieve(record_ids=[r1, r2, r3])
            credits = manager.observe(outcome=1.0, policy=CreditPolicy.SIMPLE)

            # Credit sum should be exactly 1.0
            credit_sum = sum(c.credit for c in credits)
            assert abs(credit_sum - 1.0) < 0.001

    def test_context_lifecycle_in_process(self, manager):
        """Test in-process implicit context works."""
        r1 = manager.write(payload={"x": 1}, payload_type=PayloadType.OBSERVATION)

        # This tests the "in-process SDK" mode from the spec
        with EpisodeContext(episode_id="test"):
            manager.retrieve(record_ids=[r1])
            credits = manager.observe(outcome=1.0)

            assert len(credits) == 1
