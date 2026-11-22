"""
Pareto Frontier Computation for Memory Quality vs Probe Overhead.

Computes the Pareto frontier showing the tradeoff between memory quality
metrics selected by their producer and probe overhead
(episodes or wall-time spent on causal evaluation).

The accounting rule: Total compute = task episodes + probe episodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import statistics
from typing import List, Optional, Callable, TypeVar, Literal, Tuple

__all__ = [
    "ParetoPoint",
    "ParetoPointWithUncertainty",
    "ParetoFrontierResult",
    "FrontierStability",
    "compute_pareto_frontier",
    "compute_pareto_frontier_2d",
    "compute_frontier_stability",
    "select_operating_point",
    "is_dominated",
]


# These fields are the public record shape, rather than independent object responsibilities.
@dataclass
class ParetoPoint:  # pylint: disable=too-many-instance-attributes
    """
    A point in multi-dimensional objective space.

    Attributes:
        x: X-axis value (cost metric, lower is better)
        y: Y-axis value (quality metric, higher is better)
        label: Human-readable identifier
        config: Configuration that produced this point
        is_pareto: Whether this point is on the Pareto frontier
        metadata: Additional data (policy name, full results, etc.)
        x_metric: Name of the x-axis metric (e.g., "probe_overhead_ratio")
        y_metric: Name of the y-axis metric (e.g., "reward_per_total_episode")
    """

    x: float
    y: float
    label: str = ""
    config: dict = field(default_factory=dict)
    is_pareto: bool = False
    metadata: dict = field(default_factory=dict)
    x_metric: str = ""
    y_metric: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "x": self.x,
            "y": self.y,
            "label": self.label,
            "config": self.config,
            "is_pareto": self.is_pareto,
            "metadata": self.metadata,
            "x_metric": self.x_metric,
            "y_metric": self.y_metric,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ParetoPoint":
        """Create from dictionary."""
        return cls(
            x=data["x"],
            y=data["y"],
            label=data.get("label", ""),
            config=data.get("config", {}),
            is_pareto=data.get("is_pareto", False),
            metadata=data.get("metadata", {}),
            x_metric=data.get("x_metric", ""),
            y_metric=data.get("y_metric", ""),
        )


@dataclass
class ParetoPointWithUncertainty(ParetoPoint):
    """
    A Pareto point with uncertainty estimates from multiple trials.

    Extends ParetoPoint with mean and standard deviation for both axes,
    computed from trial runs. Used for error bar rendering and confidence
    interval visualization.

    Attributes:
        x_mean: Mean of x values across trials (same as x)
        x_std: Standard deviation of x values across trials
        y_mean: Mean of y values across trials (same as y)
        y_std: Standard deviation of y values across trials
        trial_count: Number of trials used to compute statistics
    """

    x_mean: float = 0.0
    x_std: float = 0.0
    y_mean: float = 0.0
    y_std: float = 0.0
    trial_count: int = 1

    def __post_init__(self) -> None:
        """Sync x_mean/y_mean with x/y if not set."""
        if self.x_mean == 0.0 and self.x != 0.0:
            self.x_mean = self.x
        if self.y_mean == 0.0 and self.y != 0.0:
            self.y_mean = self.y

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "x_mean": self.x_mean,
                "x_std": self.x_std,
                "y_mean": self.y_mean,
                "y_std": self.y_std,
                "trial_count": self.trial_count,
            }
        )
        return base

    @classmethod
    def from_dict(cls, data: dict) -> "ParetoPointWithUncertainty":
        """Create from dictionary."""
        return cls(
            x=data["x"],
            y=data["y"],
            label=data.get("label", ""),
            config=data.get("config", {}),
            is_pareto=data.get("is_pareto", False),
            metadata=data.get("metadata", {}),
            x_metric=data.get("x_metric", ""),
            y_metric=data.get("y_metric", ""),
            x_mean=data.get("x_mean", data["x"]),
            x_std=data.get("x_std", 0.0),
            y_mean=data.get("y_mean", data["y"]),
            y_std=data.get("y_std", 0.0),
            trial_count=data.get("trial_count", 1),
        )

    @classmethod
    # The constructor keeps its existing positional trial and metadata arguments.
    def from_trials(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        cls,
        x_values: List[float],
        y_values: List[float],
        label: str = "",
        config: Optional[dict] = None,
        metadata: Optional[dict] = None,
        x_metric: str = "",
        y_metric: str = "",
    ) -> "ParetoPointWithUncertainty":
        """
        Create a ParetoPointWithUncertainty from trial data.

        Args:
            x_values: X-axis values from multiple trials
            y_values: Y-axis values from multiple trials
            label: Human-readable identifier
            config: Configuration that produced this point
            metadata: Additional data
            x_metric: Name of the x-axis metric
            y_metric: Name of the y-axis metric

        Returns:
            ParetoPointWithUncertainty with computed statistics
        """
        n = len(x_values)
        if n == 0:
            raise ValueError("Cannot create ParetoPointWithUncertainty from empty data")

        x_mean = statistics.mean(x_values)
        y_mean = statistics.mean(y_values)
        x_std = statistics.stdev(x_values) if n > 1 else 0.0
        y_std = statistics.stdev(y_values) if n > 1 else 0.0

        return cls(
            x=x_mean,
            y=y_mean,
            label=label,
            config=config or {},
            is_pareto=False,
            metadata=metadata or {},
            x_metric=x_metric,
            y_metric=y_metric,
            x_mean=x_mean,
            x_std=x_std,
            y_mean=y_mean,
            y_std=y_std,
            trial_count=n,
        )


@dataclass
class FrontierStability:
    """
    Measures stability of a Pareto frontier across trial runs.

    Computed by comparing frontiers from different trial runs using
    Jaccard index (set overlap) and churn rate (point changes).

    Attributes:
        jaccard_index: Jaccard similarity between frontier label sets (0-1)
        churn_rate: Fraction of points that changed between runs (0-1)
        reference_frontier: Labels of points on the reference frontier
    """

    jaccard_index: float
    churn_rate: float
    reference_frontier: List[str]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "jaccard_index": self.jaccard_index,
            "churn_rate": self.churn_rate,
            "reference_frontier": self.reference_frontier,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FrontierStability":
        """Create from dictionary."""
        return cls(
            jaccard_index=data["jaccard_index"],
            churn_rate=data["churn_rate"],
            reference_frontier=data.get("reference_frontier", []),
        )


@dataclass
class ParetoFrontierResult:
    """
    Result of Pareto frontier computation.

    Attributes:
        all_points: All input points with is_pareto flag set
        frontier_points: Points on the Pareto frontier (sorted by x)
        dominated_points: Points not on the frontier
        n_frontier: Number of Pareto-optimal points
        n_dominated: Number of dominated points
    """

    all_points: List[ParetoPoint]
    frontier_points: List[ParetoPoint]
    dominated_points: List[ParetoPoint]

    @property
    def n_frontier(self) -> int:
        """Number of Pareto-optimal points."""
        return len(self.frontier_points)

    @property
    def n_dominated(self) -> int:
        """Number of dominated points."""
        return len(self.dominated_points)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "frontier_points": [p.to_dict() for p in self.frontier_points],
            "dominated_points": [p.to_dict() for p in self.dominated_points],
            "n_frontier": self.n_frontier,
            "n_dominated": self.n_dominated,
        }


def is_dominated(p: ParetoPoint, q: ParetoPoint) -> bool:
    """
    Check if point p is dominated by point q.

    For minimizing x (cost) and maximizing y (quality):
    q dominates p iff q.x <= p.x AND q.y >= p.y AND (q.x < p.x OR q.y > p.y)

    Args:
        p: Point to check
        q: Potential dominator

    Returns:
        True if q dominates p
    """
    return q.x <= p.x and q.y >= p.y and (q.x < p.x or q.y > p.y)


def compute_pareto_frontier_2d(
    points: List[ParetoPoint],
) -> ParetoFrontierResult:
    """
    Compute 2D Pareto frontier (minimize x, maximize y).

    Uses a simple O(n^2) algorithm suitable for typical benchmark sizes.
    For large point sets (>1000), consider more efficient algorithms.

    Args:
        points: List of points to analyze

    Returns:
        ParetoFrontierResult with frontier and dominated points
    """
    if not points:
        return ParetoFrontierResult(
            all_points=[],
            frontier_points=[],
            dominated_points=[],
        )

    # Mark Pareto-optimal points
    for i, p in enumerate(points):
        p_is_pareto = True
        for j, q in enumerate(points):
            if i != j and is_dominated(p, q):
                p_is_pareto = False
                break
        p.is_pareto = p_is_pareto

    # Separate frontier and dominated
    frontier = [p for p in points if p.is_pareto]
    dominated = [p for p in points if not p.is_pareto]

    # Sort frontier by x for line plotting
    frontier.sort(key=lambda p: p.x)

    return ParetoFrontierResult(
        all_points=points,
        frontier_points=frontier,
        dominated_points=dominated,
    )


# Type variable for generic result type
T = TypeVar("T")


def compute_pareto_frontier(
    results: List[T],
    x_fn: Callable[[T], float],
    y_fn: Callable[[T], float],
    label_fn: Optional[Callable[[T], str]] = None,
    config_fn: Optional[Callable[[T], dict]] = None,
) -> ParetoFrontierResult:
    """
    Compute Pareto frontier from a list of benchmark results.

    This is the main entry point for notebooks. It accepts any result type
    and extracts x/y values using provided functions.

    Example:
        ```python
        from reckon.metrics.pareto import compute_pareto_frontier

        result = compute_pareto_frontier(
            results=benchmark_results,
            x_fn=lambda r: r.probe_overhead_ratio,
            y_fn=lambda r: r.quality_metrics["mean_accuracy"],
            label_fn=lambda r: f"{r.policy_name}@{r.config.get('budget', '?')}",
        )

        for p in result.frontier_points:
            print(f"{p.label}: overhead={p.x:.2%}, quality={p.y:.3f}")
        ```

    Args:
        results: List of benchmark results
        x_fn: Function to extract x value (cost, lower is better)
        y_fn: Function to extract y value (quality, higher is better)
        label_fn: Optional function to create labels
        config_fn: Optional function to extract config dict

    Returns:
        ParetoFrontierResult with frontier points
    """
    points: List[ParetoPoint] = []

    for i, r in enumerate(results):
        x = x_fn(r)
        y = y_fn(r)
        label = label_fn(r) if label_fn else f"point_{i}"
        config = config_fn(r) if config_fn else {}

        points.append(
            ParetoPoint(
                x=x,
                y=y,
                label=label,
                config=config,
                metadata={"index": i},
            )
        )

    return compute_pareto_frontier_2d(points)


# =============================================================================
# Convenience functions for common metrics
# =============================================================================


def require_metric_value(metrics: dict, name: str) -> float:
    """Read one named finite measurement without substituting another quantity."""
    value = metrics.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Metric {name!r} must supply a finite number")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"Metric {name!r} must supply a finite number") from error
    if not math.isfinite(number):
        raise ValueError(f"Metric {name!r} must supply a finite number")
    return number


def make_quality_vs_overhead_points(
    results: List[dict],
    quality_metric: str,
    overhead_metric: str = "probe_overhead_ratio",
) -> List[ParetoPoint]:
    """
    Create Pareto points from result dictionaries.

    Both selected keys must contain finite numbers in every result. A missing
    measurement raises ValueError; an observed zero remains zero. The caller
    chooses a higher-is-better outcome whose producer and units it understands.

    Args:
        results: List of result dictionaries
        quality_metric: Key for quality value (y-axis, higher is better)
        overhead_metric: Key for overhead value (x-axis, lower is better)

    Returns:
        List of ParetoPoint objects
    """
    points = []

    for i, r in enumerate(results):
        x = require_metric_value(r, overhead_metric)
        y = require_metric_value(r, quality_metric)

        # Build label
        policy = r.get("policy_name", r.get("policy", f"config_{i}"))
        budget = r.get("budget", r.get("config", {}).get("budget", ""))
        label = f"{policy}" + (f"@{budget}" if budget else "")

        points.append(
            ParetoPoint(
                x=x,
                y=y,
                label=label,
                config=r.get("config", {}),
                metadata=r,
                x_metric=overhead_metric,
                y_metric=quality_metric,
            )
        )

    return points


# =============================================================================
# Frontier Stability and Operating Point Selection
# =============================================================================


def compute_frontier_stability(
    frontiers: List[ParetoFrontierResult],
) -> FrontierStability:
    """
    Compute stability of Pareto frontiers across multiple trial runs.

    Uses Jaccard index to measure set overlap between frontiers and
    churn rate to measure point changes. Useful for assessing whether
    the frontier is stable under different random seeds.

    A Jaccard index >= 0.7 is considered stable for most applications.

    Args:
        frontiers: List of ParetoFrontierResult from different trial runs
                   (at least 2 required for meaningful comparison)

    Returns:
        FrontierStability with Jaccard index, churn rate, and reference frontier

    Raises:
        ValueError: If fewer than 2 frontiers provided

    Example:
        ```python
        frontiers = [compute_pareto_frontier_2d(points) for points in trial_points]
        stability = compute_frontier_stability(frontiers)
        if stability.jaccard_index >= 0.7:
            print("Frontier is stable across trials")
        ```
    """
    if len(frontiers) < 2:
        raise ValueError("At least 2 frontiers required for stability computation")

    # Use first frontier as reference
    ref_labels = {p.label for p in frontiers[0].frontier_points}

    # Compute pairwise Jaccard indices
    jaccard_scores: List[float] = []
    for frontier in frontiers[1:]:
        other_labels = {p.label for p in frontier.frontier_points}
        intersection = len(ref_labels & other_labels)
        union = len(ref_labels | other_labels)
        jaccard = intersection / union if union > 0 else 1.0
        jaccard_scores.append(jaccard)

    # Average Jaccard index
    avg_jaccard = sum(jaccard_scores) / len(jaccard_scores)

    # Compute churn rate: fraction of labels that differ from reference
    all_labels: set[str] = set()
    for frontier in frontiers:
        all_labels.update(p.label for p in frontier.frontier_points)

    # Labels that appear in reference but not in all frontiers
    inconsistent_labels = set()
    for frontier in frontiers[1:]:
        other_labels = {p.label for p in frontier.frontier_points}
        inconsistent_labels.update(ref_labels - other_labels)
        inconsistent_labels.update(other_labels - ref_labels)

    churn_rate = len(inconsistent_labels) / len(all_labels) if all_labels else 0.0

    return FrontierStability(
        jaccard_index=avg_jaccard,
        churn_rate=churn_rate,
        reference_frontier=sorted(ref_labels),
    )


def _normalized_coordinates(points: List[ParetoPoint]) -> List[Tuple[float, float]]:
    """Scale each axis to its observed range, keeping constant axes at zero."""
    x_min, x_max = min(p.x for p in points), max(p.x for p in points)
    y_min, y_max = min(p.y for p in points), max(p.y for p in points)
    x_range = x_max - x_min if x_max > x_min else 1.0
    y_range = y_max - y_min if y_max > y_min else 1.0
    return [((p.x - x_min) / x_range, (p.y - y_min) / y_range) for p in points]


def _knee_point(points: List[ParetoPoint]) -> ParetoPoint:
    """Choose the greatest interior distance from the normalized endpoint line.

    Preserve the first tied point in x order. Fewer than three points, coincident
    endpoints or a maximum distance below 0.05 fall back to highest quality.
    """
    ordered = sorted(points, key=lambda p: p.x)
    if len(ordered) <= 2:
        return max(ordered, key=lambda p: p.y)
    coordinates = _normalized_coordinates(ordered)
    start, end = coordinates[0], coordinates[-1]
    line_a = end[1] - start[1]
    line_b = start[0] - end[0]
    line_c = end[0] * start[1] - start[0] * end[1]
    line_length = (line_a**2 + line_b**2) ** 0.5
    if line_length == 0:
        return max(ordered, key=lambda p: p.y)
    max_distance = -1.0
    knee_point = ordered[0]
    for point, coordinate in zip(ordered[1:-1], coordinates[1:-1]):
        distance = abs(line_a * coordinate[0] + line_b * coordinate[1] + line_c) / line_length
        if distance > max_distance:
            max_distance, knee_point = distance, point
    return max(ordered, key=lambda p: p.y) if max_distance < 0.05 else knee_point


def select_operating_point(
    frontier: ParetoFrontierResult,
    method: Literal["knee", "budget_cap", "utility_weighted"] = "knee",
    budget_cap: Optional[float] = None,
    utility_weights: Optional[Tuple[float, float]] = None,
) -> ParetoPoint:
    """
    Select an operating point from the Pareto frontier.

    Supports three selection methods:
    - "knee": Select the greatest distance from the normalized endpoint line
    - "budget_cap": Select the highest-y point with x <= budget_cap
    - "utility_weighted": Select point maximizing weighted utility (w1*y - w2*x)

    The "knee" method uses the distance from the normalized endpoint line as
    a geometric tradeoff heuristic. It falls back to max-y if no clear knee
    exists; it does not establish which policy the owner should choose.

    Args:
        frontier: ParetoFrontierResult containing frontier_points
        method: Selection method ("knee", "budget_cap", or "utility_weighted")
        budget_cap: For "budget_cap" method, maximum x value allowed
        utility_weights: For "utility_weighted" method, tuple of (y_weight, x_cost)

    Returns:
        Selected ParetoPoint from the frontier

    Raises:
        ValueError: If frontier is empty or required parameters are missing

    Example:
        ```python
        result = compute_pareto_frontier_2d(points)

        # Select point with x <= 0.2 (20% overhead cap)
        point = select_operating_point(result, "budget_cap", budget_cap=0.2)

        # Select knee point (best tradeoff)
        knee = select_operating_point(result, "knee")

        # Select utility-weighted (prioritize y with 0.7 weight)
        weighted = select_operating_point(
            result, "utility_weighted", utility_weights=(0.7, 0.3)
        )
        ```
    """
    if not frontier.frontier_points:
        raise ValueError("Frontier is empty, cannot select operating point")

    points = frontier.frontier_points

    if method == "budget_cap":
        if budget_cap is None:
            raise ValueError("budget_cap required for 'budget_cap' method")

        # Filter to points within budget
        eligible = [p for p in points if p.x <= budget_cap]
        if not eligible:
            # No points within budget, return the one with minimum x
            return min(points, key=lambda p: p.x)

        # Return highest y among eligible
        return max(eligible, key=lambda p: p.y)

    if method == "utility_weighted":
        if utility_weights is None:
            utility_weights = (1.0, 1.0)  # Default equal weights

        y_weight, x_cost = utility_weights

        # Maximize: y_weight * y - x_cost * x
        def utility(p: ParetoPoint) -> float:
            return y_weight * p.y - x_cost * p.x

        return max(points, key=utility)

    if method == "knee":
        return _knee_point(points)

    raise ValueError(f"Unknown method: {method}. Use 'knee', 'budget_cap', or 'utility_weighted'")
