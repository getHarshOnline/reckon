"""
Probe cost tracking integration for Reckon notebooks.

Provides utilities for wrapping benchmark evaluations with ProbeCostTracker,
computing efficiency metrics, and generating Pareto-frontier-ready data.

The key accounting rule: Total compute = task episodes + probe episodes.
No special pleading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Any
import time

from reckon.metrics.pareto import require_metric_value

__all__ = [
    "ProbeIntegration",
    "BenchmarkResult",
    "compute_efficiency_metrics",
    "generate_pareto_data",
    "ParetoPoint",
]


@dataclass
class ParetoPoint:
    """
    Point on a Pareto frontier.

    Attributes:
        x: X-axis value (e.g., probe_overhead_ratio, probe_episodes)
        y: Y-axis value for the explicitly selected outcome
        label: Human-readable label for the point
        metadata: Additional data for the point (policy config, etc.)
        is_pareto: Whether this point is on the Pareto frontier
    """
    x: float
    y: float
    label: str = ""
    metadata: dict = field(default_factory=dict)
    is_pareto: bool = False
    x_metric: str = ""
    y_metric: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "x": self.x,
            "y": self.y,
            "label": self.label,
            "metadata": self.metadata,
            "is_pareto": self.is_pareto,
            "x_metric": self.x_metric,
            "y_metric": self.y_metric,
        }


@dataclass
class BenchmarkResult:
    """
    Result from a benchmark run with probe cost tracking.

    Implements the accounting rule:
    > Total compute = task episodes for acting + episodes for probing.
    > No special pleading.

    Attributes:
        policy_name: Name of the policy evaluated
        config: Configuration dict (budget, evidence_weight, etc.)
        base_episodes: Episodes used for task execution
        base_wall_time_ms: Wall time for task execution
        probe_episodes: Episodes used for probing
        probe_wall_time_ms: Wall time for probing
        probe_calls: Number of probe operations
        records_evaluated: Number of records evaluated via probing
        total_reward: Total reward achieved
        success_rate: Supplied success rate over episodes, or None when absent
        quality_metrics: Other named outcomes with producer-defined units
    """
    policy_name: str
    config: dict = field(default_factory=dict)
    base_episodes: int = 0
    base_wall_time_ms: float = 0.0
    probe_episodes: int = 0
    probe_wall_time_ms: float = 0.0
    probe_calls: int = 0
    records_evaluated: int = 0
    total_reward: float = 0.0
    success_rate: Optional[float] = None
    quality_metrics: dict = field(default_factory=dict)

    @property
    def total_episodes(self) -> int:
        """Total episodes (base + probe). No special pleading."""
        return self.base_episodes + self.probe_episodes

    @property
    def total_wall_time_ms(self) -> float:
        """Total wall time (base + probe)."""
        return self.base_wall_time_ms + self.probe_wall_time_ms

    @property
    def probe_overhead_ratio(self) -> float:
        """
        Overhead ratio: probe_episodes / total_episodes.

        Returns 0 if total episodes is 0.
        """
        if self.total_episodes == 0:
            return 0.0
        return self.probe_episodes / self.total_episodes

    @property
    def reward_per_total_episode(self) -> float:
        """Reward per total episode (including probes)."""
        if self.total_episodes == 0:
            return 0.0
        return self.total_reward / self.total_episodes

    @property
    def utility_gain_per_probe_episode(self) -> float:
        """
        Utility gain per probe episode.

        Requires 'utility_gain' in quality_metrics.
        """
        utility_gain = self.quality_metrics.get("utility_gain", 0.0)
        if self.probe_episodes == 0:
            return 0.0
        return utility_gain / self.probe_episodes

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "policy_name": self.policy_name,
            "config": self.config,
            "base_episodes": self.base_episodes,
            "base_wall_time_ms": self.base_wall_time_ms,
            "probe_episodes": self.probe_episodes,
            "probe_wall_time_ms": self.probe_wall_time_ms,
            "probe_calls": self.probe_calls,
            "records_evaluated": self.records_evaluated,
            "total_reward": self.total_reward,
            "success_rate": self.success_rate,
            "quality_metrics": self.quality_metrics,
            # Computed
            "total_episodes": self.total_episodes,
            "total_wall_time_ms": self.total_wall_time_ms,
            "probe_overhead_ratio": self.probe_overhead_ratio,
            "reward_per_total_episode": self.reward_per_total_episode,
            "utility_gain_per_probe_episode": self.utility_gain_per_probe_episode,
        }


class ProbeIntegration:
    """
    Integration helper for tracking probe costs during evaluation.

    Wraps ProbeCostTracker with notebook-specific conveniences.

    Usage:
        integration = ProbeIntegration()

        # Track base task execution
        with integration.track_base(episodes=10):
            results = run_task_episodes(10)

        # Track probing
        for record_id in records:
            with integration.track_probe(record_id=record_id, n_trials=5):
                delta = evaluate_ablation(record_id, n_trials=5)

        # Get results
        result = integration.get_result(
            policy_name="evidence_per_byte",
            config={"budget": 10, "evidence_weight": 0.5},
            total_reward=sum_rewards,
            success_rate=successes / episodes,
        )
    """

    def __init__(self):
        """Initialize the integration helper."""
        self._base_episodes: int = 0
        self._base_wall_time_ms: float = 0.0
        self._probe_episodes: int = 0
        self._probe_wall_time_ms: float = 0.0
        self._probe_calls: int = 0
        self._record_ids: set[str] = set()
        self._current_start: Optional[float] = None
        self._in_base: bool = False
        self._in_probe: bool = False

    def track_base(self, episodes: int) -> "BaseContextManager":
        """
        Context manager for tracking base task execution.

        Args:
            episodes: Number of episodes being run.

        Returns:
            Context manager that tracks wall time.
        """
        return BaseContextManager(self, episodes)

    def track_probe(
        self,
        record_id: Optional[str] = None,
        n_trials: int = 1,
    ) -> "ProbeContextManager":
        """
        Context manager for tracking a probe operation.

        Args:
            record_id: ID of record being probed.
            n_trials: Number of trials (episodes) for this probe.

        Returns:
            Context manager that tracks wall time and episodes.
        """
        return ProbeContextManager(self, record_id, n_trials)

    def add_base_episodes(self, episodes: int, wall_time_ms: float) -> None:
        """Add base episodes and wall time."""
        self._base_episodes += episodes
        self._base_wall_time_ms += wall_time_ms

    def add_probe(
        self,
        record_id: Optional[str],
        n_trials: int,
        wall_time_ms: float,
    ) -> None:
        """Add a probe operation."""
        self._probe_episodes += n_trials
        self._probe_wall_time_ms += wall_time_ms
        self._probe_calls += 1
        if record_id:
            self._record_ids.add(record_id)

    def get_result(
        self,
        policy_name: str,
        config: Optional[dict] = None,
        total_reward: float = 0.0,
        success_rate: Optional[float] = None,
        quality_metrics: Optional[dict] = None,
    ) -> BenchmarkResult:
        """
        Get the benchmark result with all tracked costs.

        Args:
            policy_name: Name of the policy.
            config: Configuration dict.
            total_reward: Total reward achieved.
            success_rate: Supplied success rate over episodes, absent by default.
            quality_metrics: Dict of quality metrics.

        Returns:
            BenchmarkResult with computed metrics.
        """
        return BenchmarkResult(
            policy_name=policy_name,
            config=config or {},
            base_episodes=self._base_episodes,
            base_wall_time_ms=self._base_wall_time_ms,
            probe_episodes=self._probe_episodes,
            probe_wall_time_ms=self._probe_wall_time_ms,
            probe_calls=self._probe_calls,
            records_evaluated=len(self._record_ids),
            total_reward=total_reward,
            success_rate=success_rate,
            quality_metrics=quality_metrics or {},
        )

    def reset(self) -> None:
        """Reset all tracked values."""
        self._base_episodes = 0
        self._base_wall_time_ms = 0.0
        self._probe_episodes = 0
        self._probe_wall_time_ms = 0.0
        self._probe_calls = 0
        self._record_ids.clear()


class BaseContextManager:
    """Context manager for tracking base task execution."""

    def __init__(self, integration: ProbeIntegration, episodes: int):
        self._integration = integration
        self._episodes = episodes
        self._start_time: float = 0.0

    def __enter__(self) -> "BaseContextManager":
        self._start_time = time.perf_counter() * 1000  # ms
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        end_time = time.perf_counter() * 1000
        wall_time_ms = end_time - self._start_time
        self._integration.add_base_episodes(self._episodes, wall_time_ms)


class ProbeContextManager:
    """Context manager for tracking probe operations."""

    def __init__(
        self,
        integration: ProbeIntegration,
        record_id: Optional[str],
        n_trials: int,
    ):
        self._integration = integration
        self._record_id = record_id
        self._n_trials = n_trials
        self._start_time: float = 0.0

    def __enter__(self) -> "ProbeContextManager":
        self._start_time = time.perf_counter() * 1000  # ms
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        end_time = time.perf_counter() * 1000
        wall_time_ms = end_time - self._start_time
        self._integration.add_probe(self._record_id, self._n_trials, wall_time_ms)


def _quality_value(result: BenchmarkResult, name: str) -> float:
    """Select the declared success rate or one explicitly named extra outcome."""
    metrics = {"success_rate": result.success_rate} if name == "success_rate" else result.quality_metrics
    return require_metric_value(metrics, name)


def compute_efficiency_metrics(result: BenchmarkResult, quality_metric: str) -> dict:
    """
    Compute efficiency metrics from a benchmark result.

    Returns a dict with:
        - reward_per_total_episode: Reward normalized by total compute
        - probe_overhead_ratio: Fraction of compute spent on probes
        - utility_gain_per_probe_episode: Utility improvement per probe episode
        - effective_quality: Quality metric adjusted for probe cost

    Args:
        result: BenchmarkResult with tracked costs.
        quality_metric: Explicit higher-is-better outcome. "success_rate" reads
            that supplied field; other names read quality_metrics. Missing,
            nonnumeric and nonfinite measurements raise ValueError.

    Returns:
        Dict of efficiency metrics.
    """
    quality = _quality_value(result, quality_metric)

    # Effective quality: penalize high probe overhead
    # If we spend 50% on probes, effective quality is quality * 0.5
    efficiency_factor = 1.0 - result.probe_overhead_ratio
    effective_quality = quality * efficiency_factor

    return {
        "reward_per_total_episode": result.reward_per_total_episode,
        "probe_overhead_ratio": result.probe_overhead_ratio,
        "utility_gain_per_probe_episode": result.utility_gain_per_probe_episode,
        "effective_quality": effective_quality,
        "quality_metric": quality_metric,
        "total_episodes": result.total_episodes,
        "base_episodes": result.base_episodes,
        "probe_episodes": result.probe_episodes,
    }


def generate_pareto_data(
    results: list[BenchmarkResult],
    *,
    y_metric: str,
    x_metric: str = "probe_overhead_ratio",
) -> list[ParetoPoint]:
    """
    Generate Pareto frontier data from benchmark results.

    Args:
        results: List of BenchmarkResult objects.
        x_metric: Metric for X-axis (lower is better).
            Options: "probe_overhead_ratio", "probe_episodes", "total_episodes"
        y_metric: Explicit higher-is-better outcome. "success_rate" reads
            that supplied field; other names read quality_metrics. Missing,
            nonnumeric and nonfinite measurements raise ValueError.

    Returns:
        List of ParetoPoint objects with is_pareto set.
    """
    points: list[ParetoPoint] = []
    if x_metric not in {"probe_overhead_ratio", "probe_episodes", "total_episodes"}:
        raise ValueError(f"Unknown cost metric: {x_metric!r}")

    for result in results:
        x = require_metric_value({x_metric: getattr(result, x_metric)}, x_metric)
        y = _quality_value(result, y_metric)

        # Create label
        config_str = ", ".join(f"{k}={v}" for k, v in result.config.items())
        label = f"{result.policy_name}({config_str})" if config_str else result.policy_name

        points.append(ParetoPoint(
            x=x,
            y=y,
            label=label,
            metadata=result.to_dict(),
            is_pareto=False,
            x_metric=x_metric,
            y_metric=y_metric,
        ))

    # Identify Pareto-optimal points
    # A point is Pareto-optimal if no other point dominates it
    # (lower x AND higher y)
    for i, p in enumerate(points):
        is_pareto = True
        for j, q in enumerate(points):
            if i != j:
                # q dominates p if q.x <= p.x AND q.y >= p.y AND (q.x < p.x OR q.y > p.y)
                if q.x <= p.x and q.y >= p.y and (q.x < p.x or q.y > p.y):
                    is_pareto = False
                    break
        p.is_pareto = is_pareto

    return points


def compute_pareto_frontier(points: list[ParetoPoint]) -> list[ParetoPoint]:
    """
    Extract the Pareto frontier from a list of points.

    Args:
        points: List of ParetoPoint objects (with is_pareto already set).

    Returns:
        Sorted list of Pareto-optimal points.
    """
    frontier = [p for p in points if p.is_pareto]
    # Sort by x for line plotting
    frontier.sort(key=lambda p: p.x)
    return frontier
