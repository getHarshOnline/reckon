"""
Tests for Reckon Pareto frontier module.

Tests the Pareto frontier computation, uncertainty handling,
frontier stability, and operating point selection.
"""

import pytest

from reckon.metrics.pareto import (
    ParetoPoint,
    ParetoPointWithUncertainty,
    ParetoFrontierResult,
    FrontierStability,
    compute_pareto_frontier,
    compute_pareto_frontier_2d,
    compute_frontier_stability,
    select_operating_point,
    is_dominated,
)


class TestParetoPoint:
    """Tests for ParetoPoint dataclass."""

    def test_create_pareto_point(self):
        """Test basic ParetoPoint creation."""
        point = ParetoPoint(x=0.2, y=0.8, label="test")
        assert point.x == 0.2
        assert point.y == 0.8
        assert point.label == "test"
        assert not point.is_pareto

    def test_to_dict(self):
        """Test serialization to dictionary."""
        point = ParetoPoint(
            x=0.2, y=0.8, label="test", x_metric="cost", y_metric="quality"
        )
        d = point.to_dict()
        assert d["x"] == 0.2
        assert d["y"] == 0.8
        assert d["x_metric"] == "cost"
        assert d["y_metric"] == "quality"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        d = {"x": 0.3, "y": 0.7, "label": "from_dict", "is_pareto": True}
        point = ParetoPoint.from_dict(d)
        assert point.x == 0.3
        assert point.y == 0.7
        assert point.label == "from_dict"
        assert point.is_pareto


class TestParetoPointWithUncertainty:
    """Tests for ParetoPointWithUncertainty dataclass."""

    def test_create_with_uncertainty(self):
        """Test creation with uncertainty values."""
        point = ParetoPointWithUncertainty(
            x=0.2, y=0.8,
            x_mean=0.2, x_std=0.05,
            y_mean=0.8, y_std=0.1,
            trial_count=5,
        )
        assert point.x == 0.2
        assert point.x_std == 0.05
        assert point.y_std == 0.1
        assert point.trial_count == 5

    def test_from_trials(self):
        """Test creation from trial data."""
        x_values = [0.18, 0.20, 0.22, 0.19, 0.21]
        y_values = [0.75, 0.80, 0.85, 0.78, 0.82]

        point = ParetoPointWithUncertainty.from_trials(
            x_values=x_values,
            y_values=y_values,
            label="trial_point",
            x_metric="overhead",
            y_metric="performance",
        )

        assert point.trial_count == 5
        assert abs(point.x_mean - 0.2) < 0.01
        assert abs(point.y_mean - 0.8) < 0.01
        assert point.x_std > 0  # Should have some std
        assert point.y_std > 0
        assert point.x_metric == "overhead"
        assert point.y_metric == "performance"

    def test_from_trials_empty_raises(self):
        """Test that empty trials raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            ParetoPointWithUncertainty.from_trials([], [])

    def test_to_dict_includes_uncertainty(self):
        """Test that to_dict includes uncertainty fields."""
        point = ParetoPointWithUncertainty(
            x=0.2, y=0.8,
            x_std=0.05, y_std=0.1,
            trial_count=3,
        )
        d = point.to_dict()
        assert "x_std" in d
        assert "y_std" in d
        assert "trial_count" in d
        assert d["trial_count"] == 3


class TestIsDominated:
    """Tests for dominance checking."""

    def test_dominated(self):
        """Test that a point is dominated by a better point."""
        p = ParetoPoint(x=0.5, y=0.5)
        q = ParetoPoint(x=0.3, y=0.7)  # Lower x, higher y
        assert is_dominated(p, q)

    def test_not_dominated_better_x(self):
        """Test non-dominance when p has better x."""
        p = ParetoPoint(x=0.2, y=0.5)
        q = ParetoPoint(x=0.4, y=0.6)
        assert not is_dominated(p, q)

    def test_not_dominated_better_y(self):
        """Test non-dominance when p has better y."""
        p = ParetoPoint(x=0.4, y=0.8)
        q = ParetoPoint(x=0.3, y=0.6)
        assert not is_dominated(p, q)


class TestComputeParetoFrontier2D:
    """Tests for 2D Pareto frontier computation."""

    def test_empty_input(self):
        """Test with empty point list."""
        result = compute_pareto_frontier_2d([])
        assert result.n_frontier == 0
        assert result.n_dominated == 0

    def test_single_point(self):
        """Test with single point."""
        points = [ParetoPoint(x=0.5, y=0.5, label="only")]
        result = compute_pareto_frontier_2d(points)
        assert result.n_frontier == 1
        assert result.frontier_points[0].label == "only"
        assert result.frontier_points[0].is_pareto

    def test_all_pareto(self):
        """Test when all points are Pareto-optimal."""
        points = [
            ParetoPoint(x=0.2, y=0.5, label="low_cost"),
            ParetoPoint(x=0.5, y=0.8, label="high_quality"),
        ]
        result = compute_pareto_frontier_2d(points)
        assert result.n_frontier == 2
        assert result.n_dominated == 0

    def test_mixed_frontier(self):
        """Test with mix of frontier and dominated points."""
        points = [
            ParetoPoint(x=0.2, y=0.6, label="a"),  # Pareto
            ParetoPoint(x=0.4, y=0.8, label="b"),  # Pareto
            ParetoPoint(x=0.3, y=0.5, label="c"),  # Dominated by a
            ParetoPoint(x=0.5, y=0.7, label="d"),  # Dominated by b
        ]
        result = compute_pareto_frontier_2d(points)
        assert result.n_frontier == 2
        assert result.n_dominated == 2

        frontier_labels = {p.label for p in result.frontier_points}
        assert frontier_labels == {"a", "b"}

    def test_frontier_sorted_by_x(self):
        """Test that frontier points are sorted by x."""
        points = [
            ParetoPoint(x=0.5, y=0.9, label="high_x"),
            ParetoPoint(x=0.1, y=0.5, label="low_x"),
            ParetoPoint(x=0.3, y=0.7, label="mid_x"),
        ]
        result = compute_pareto_frontier_2d(points)

        x_values = [p.x for p in result.frontier_points]
        assert x_values == sorted(x_values)


class TestFrontierStability:
    """Tests for frontier stability computation."""

    def test_identical_frontiers(self):
        """Test stability with identical frontiers."""
        points1 = [
            ParetoPoint(x=0.2, y=0.6, label="a"),
            ParetoPoint(x=0.4, y=0.8, label="b"),
        ]
        points2 = [
            ParetoPoint(x=0.21, y=0.59, label="a"),  # Same labels
            ParetoPoint(x=0.39, y=0.81, label="b"),
        ]

        f1 = compute_pareto_frontier_2d(points1)
        f2 = compute_pareto_frontier_2d(points2)

        stability = compute_frontier_stability([f1, f2])
        assert stability.jaccard_index == 1.0
        assert stability.churn_rate == 0.0

    def test_different_frontiers(self):
        """Test stability with different frontiers."""
        points1 = [
            ParetoPoint(x=0.2, y=0.6, label="a"),
            ParetoPoint(x=0.4, y=0.8, label="b"),
        ]
        points2 = [
            ParetoPoint(x=0.2, y=0.6, label="a"),
            ParetoPoint(x=0.5, y=0.9, label="c"),  # Different label
        ]

        f1 = compute_pareto_frontier_2d(points1)
        f2 = compute_pareto_frontier_2d(points2)

        stability = compute_frontier_stability([f1, f2])
        # Jaccard: intersection={a}, union={a,b,c} -> 1/3
        assert 0.3 < stability.jaccard_index < 0.4
        assert stability.churn_rate > 0

    def test_requires_two_frontiers(self):
        """Test that at least 2 frontiers are required."""
        points = [ParetoPoint(x=0.2, y=0.6, label="a")]
        f1 = compute_pareto_frontier_2d(points)

        with pytest.raises(ValueError, match="At least 2"):
            compute_frontier_stability([f1])

    def test_stability_gate_threshold(self):
        """Test stability gate: jaccard >= 0.7 for fixed seeds."""
        # Create multiple frontiers with high overlap (simulating fixed seeds)
        base_points = [
            ParetoPoint(x=0.1, y=0.5, label="a"),
            ParetoPoint(x=0.2, y=0.6, label="b"),
            ParetoPoint(x=0.3, y=0.7, label="c"),
            ParetoPoint(x=0.4, y=0.8, label="d"),
        ]

        frontiers = []
        for _ in range(3):
            # Add slight variation but same labels (simulating seed variation)
            varied = [
                ParetoPoint(x=p.x + 0.01, y=p.y + 0.01, label=p.label)
                for p in base_points
            ]
            frontiers.append(compute_pareto_frontier_2d(varied))

        stability = compute_frontier_stability(frontiers)
        # With same labels, should have perfect Jaccard
        assert stability.jaccard_index >= 0.7


class TestSelectOperatingPoint:
    """Tests for operating point selection."""

    @pytest.fixture
    def sample_frontier(self):
        """Create a sample frontier for testing."""
        points = [
            ParetoPoint(x=0.1, y=0.4, label="low_cost"),
            ParetoPoint(x=0.2, y=0.6, label="budget_cap_point"),
            ParetoPoint(x=0.3, y=0.75, label="knee"),
            ParetoPoint(x=0.5, y=0.85, label="mid"),
            ParetoPoint(x=0.8, y=0.9, label="high_quality"),
        ]
        return compute_pareto_frontier_2d(points)

    def test_budget_cap_within_limit(self, sample_frontier):
        """Test budget_cap returns point within limit."""
        point = select_operating_point(
            sample_frontier, "budget_cap", budget_cap=0.25
        )
        assert point.x <= 0.25
        # Should be the highest y within budget: x=0.2, y=0.6
        assert point.y == 0.6

    def test_budget_cap_no_points_in_range(self, sample_frontier):
        """Test budget_cap when no points within limit."""
        point = select_operating_point(
            sample_frontier, "budget_cap", budget_cap=0.05
        )
        # Should return minimum x point when none within budget
        assert point.x == 0.1

    def test_budget_cap_requires_cap(self, sample_frontier):
        """Test that budget_cap requires budget_cap parameter."""
        with pytest.raises(ValueError, match="budget_cap required"):
            select_operating_point(sample_frontier, "budget_cap")

    def test_utility_weighted(self, sample_frontier):
        """Test utility_weighted selection."""
        # With high y weight, should prefer high y
        point = select_operating_point(
            sample_frontier, "utility_weighted", utility_weights=(2.0, 0.5)
        )
        # Higher y points should be preferred
        assert point.y >= 0.75

    def test_knee_detection(self, sample_frontier):
        """Test knee point detection."""
        point = select_operating_point(sample_frontier, "knee")
        # Should find a point in the middle region
        assert 0.1 < point.x < 0.8

    def test_empty_frontier_raises(self):
        """Test that empty frontier raises error."""
        empty = ParetoFrontierResult(
            all_points=[], frontier_points=[], dominated_points=[]
        )
        with pytest.raises(ValueError, match="empty"):
            select_operating_point(empty, "knee")

    def test_invalid_method_raises(self, sample_frontier):
        """Test that invalid method raises error."""
        with pytest.raises(ValueError, match="Unknown method"):
            select_operating_point(sample_frontier, "invalid_method")  # type: ignore


class TestComputeParetoFrontier:
    """Tests for the generic compute_pareto_frontier function."""

    def test_with_callable_extractors(self):
        """Test with custom extractor functions."""
        results = [
            {"overhead": 0.1, "quality": 0.5, "name": "config_a"},
            {"overhead": 0.3, "quality": 0.8, "name": "config_b"},
            {"overhead": 0.2, "quality": 0.6, "name": "config_c"},
        ]

        frontier = compute_pareto_frontier(
            results,
            x_fn=lambda r: r["overhead"],
            y_fn=lambda r: r["quality"],
            label_fn=lambda r: r["name"],
        )

        assert frontier.n_frontier > 0
        # config_a and config_b should be on frontier
        frontier_labels = {p.label for p in frontier.frontier_points}
        assert "config_a" in frontier_labels
        assert "config_b" in frontier_labels
