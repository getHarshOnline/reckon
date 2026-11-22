"""
Probe Cost Tracking and Aggregation.

Tracks compute spent on causal evaluation (probing/ablation).
Implements the accounting rule: Total compute = task episodes + probe episodes.

See docs/11-Evaluation-Metrics.md for documentation.
"""

from dataclasses import dataclass
from typing import Optional
import time


@dataclass
class ProbeCostEvent:
    """
    Cost of a single probe operation.

    Attributes:
        record_id: Record being probed (if single-record intervention)
        probe_type: Type of probe ("ablation", "counterfactual", "mask")
        probe_episodes: Number of episodes run for this probe
        probe_calls: Number of task.run invocations
        probe_wall_time_ms: Wall time spent on probe (milliseconds)
        probe_env_steps: Environment steps consumed (if applicable)
        seed: Seed used for reproducibility
    """
    record_id: Optional[str] = None
    probe_type: str = "ablation"
    probe_episodes: int = 0
    probe_calls: int = 0
    probe_wall_time_ms: float = 0.0
    probe_env_steps: Optional[int] = None
    seed: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "record_id": self.record_id,
            "probe_type": self.probe_type,
            "probe_episodes": self.probe_episodes,
            "probe_calls": self.probe_calls,
            "probe_wall_time_ms": self.probe_wall_time_ms,
            "probe_env_steps": self.probe_env_steps,
            "seed": self.seed,
        }


@dataclass
class ProbeCostSummary:
    """
    Aggregated probe cost metrics for a complete evaluation run.

    Implements the accounting rule:
    > Total compute = task episodes for acting + episodes for probing.
    > No special pleading.

    Attributes:
        probe_episodes_total: Total episodes used for probing
        probe_wall_time_total_ms: Total wall time for all probes (ms)
        probe_calls_total: Total task.run calls for probing
        probe_env_steps_total: Total environment steps for probing
        probe_records_evaluated: Total records evaluated
        base_episodes: Base task episodes (non-probe)
        base_wall_time_ms: Base task wall time (ms)
    """
    probe_episodes_total: int = 0
    probe_wall_time_total_ms: float = 0.0
    probe_calls_total: int = 0
    probe_env_steps_total: int = 0
    probe_records_evaluated: int = 0
    base_episodes: int = 0
    base_wall_time_ms: float = 0.0

    @property
    def probe_episodes_per_record(self) -> float:
        """Average episodes per record evaluated."""
        if self.probe_records_evaluated == 0:
            return 0.0
        return self.probe_episodes_total / self.probe_records_evaluated

    @property
    def probe_wall_time_per_record_ms(self) -> float:
        """Average wall time per record evaluated (ms)."""
        if self.probe_records_evaluated == 0:
            return 0.0
        return self.probe_wall_time_total_ms / self.probe_records_evaluated

    @property
    def probe_overhead_ratio(self) -> float:
        """
        Overhead ratio: probe_time / (base_time + probe_time).

        Returns 0 if total time is 0.
        """
        total = self.base_wall_time_ms + self.probe_wall_time_total_ms
        if total == 0:
            return 0.0
        return self.probe_wall_time_total_ms / total

    @property
    def total_episodes(self) -> int:
        """Total episodes (base + probe). No special pleading."""
        return self.base_episodes + self.probe_episodes_total

    @property
    def total_wall_time_ms(self) -> float:
        """Total wall time (base + probe)."""
        return self.base_wall_time_ms + self.probe_wall_time_total_ms

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "probe_episodes_total": self.probe_episodes_total,
            "probe_wall_time_total_ms": self.probe_wall_time_total_ms,
            "probe_calls_total": self.probe_calls_total,
            "probe_env_steps_total": self.probe_env_steps_total,
            "probe_records_evaluated": self.probe_records_evaluated,
            "probe_episodes_per_record": self.probe_episodes_per_record,
            "probe_wall_time_per_record_ms": self.probe_wall_time_per_record_ms,
            "probe_overhead_ratio": self.probe_overhead_ratio,
            "base_episodes": self.base_episodes,
            "base_wall_time_ms": self.base_wall_time_ms,
            "total_episodes": self.total_episodes,
            "total_wall_time_ms": self.total_wall_time_ms,
        }


class ProbeCostTracker:
    """
    Tracks probe costs during causal evaluation.

    Usage:
        tracker = ProbeCostTracker()
        tracker.set_base_costs(episodes=100, wall_time_ms=5000)

        with tracker.track_probe(record_id="r1", probe_type="ablation"):
            # Run probe
            task.run(...)

        summary = tracker.summarize()
    """

    def __init__(self):
        """Initialize the tracker."""
        self._events: list[ProbeCostEvent] = []
        self._base_episodes: int = 0
        self._base_wall_time_ms: float = 0.0
        self._current_event: Optional[ProbeCostEvent] = None
        self._start_time: Optional[float] = None

    def set_base_costs(self, episodes: int, wall_time_ms: float) -> None:
        """Set base (non-probe) costs for overhead calculation."""
        self._base_episodes = episodes
        self._base_wall_time_ms = wall_time_ms

    def start_probe(
        self,
        record_id: Optional[str] = None,
        probe_type: str = "ablation",
        seed: Optional[int] = None,
    ) -> None:
        """Start tracking a probe operation."""
        self._current_event = ProbeCostEvent(
            record_id=record_id,
            probe_type=probe_type,
            seed=seed,
        )
        self._start_time = time.perf_counter() * 1000  # ms

    def record_call(self, episodes: int = 1, env_steps: Optional[int] = None) -> None:
        """Record a task.run call within the current probe."""
        if self._current_event is None:
            return
        self._current_event.probe_calls += 1
        self._current_event.probe_episodes += episodes
        if env_steps is not None:
            if self._current_event.probe_env_steps is None:
                self._current_event.probe_env_steps = 0
            self._current_event.probe_env_steps += env_steps

    def end_probe(self) -> Optional[ProbeCostEvent]:
        """End tracking the current probe and return the event."""
        if self._current_event is None:
            return None

        if self._start_time is not None:
            end_time = time.perf_counter() * 1000  # ms
            self._current_event.probe_wall_time_ms = end_time - self._start_time

        event = self._current_event
        self._events.append(event)
        self._current_event = None
        self._start_time = None
        return event

    def track_probe(
        self,
        record_id: Optional[str] = None,
        probe_type: str = "ablation",
        seed: Optional[int] = None,
    ) -> "ProbeContextManager":
        """Context manager for tracking a probe operation."""
        return ProbeContextManager(self, record_id, probe_type, seed)

    def summarize(self) -> ProbeCostSummary:
        """Compute aggregate probe cost summary."""
        summary = ProbeCostSummary(
            base_episodes=self._base_episodes,
            base_wall_time_ms=self._base_wall_time_ms,
        )

        record_ids: set[str] = set()
        for event in self._events:
            summary.probe_episodes_total += event.probe_episodes
            summary.probe_wall_time_total_ms += event.probe_wall_time_ms
            summary.probe_calls_total += event.probe_calls
            if event.probe_env_steps is not None:
                summary.probe_env_steps_total += event.probe_env_steps
            if event.record_id is not None:
                record_ids.add(event.record_id)

        summary.probe_records_evaluated = len(record_ids)
        return summary

    @property
    def events(self) -> list[ProbeCostEvent]:
        """Get all recorded probe events."""
        return list(self._events)


class ProbeContextManager:
    """Context manager for probe tracking."""

    def __init__(
        self,
        tracker: ProbeCostTracker,
        record_id: Optional[str],
        probe_type: str,
        seed: Optional[int],
    ):
        self._tracker = tracker
        self._record_id = record_id
        self._probe_type = probe_type
        self._seed = seed

    def __enter__(self) -> ProbeCostTracker:
        self._tracker.start_probe(
            record_id=self._record_id,
            probe_type=self._probe_type,
            seed=self._seed,
        )
        return self._tracker

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._tracker.end_probe()


@dataclass
class EfficiencyMetrics:
    """
    Efficiency metrics that account for probe costs.

    These metrics answer: "Was probing worth it?"
    """
    # Reward per total episode (including probes)
    reward_per_total_episode: float = 0.0
    # Reward per total wall time
    reward_per_total_wall_time: float = 0.0
    # Utility gain per probe episode
    utility_gain_per_probe_episode: float = 0.0
    # Total reward achieved
    total_reward: float = 0.0
    # Probe cost summary
    probe_costs: Optional[ProbeCostSummary] = None

    @classmethod
    def compute(
        cls,
        total_reward: float,
        probe_costs: ProbeCostSummary,
        utility_gain: float = 0.0,
    ) -> "EfficiencyMetrics":
        """
        Compute efficiency metrics from reward and probe costs.

        Args:
            total_reward: Total reward achieved in evaluation
            probe_costs: Aggregated probe cost summary
            utility_gain: Utility improvement from probing (optional)

        Returns:
            EfficiencyMetrics instance
        """
        total_episodes = probe_costs.total_episodes
        total_wall_time = probe_costs.total_wall_time_ms

        reward_per_episode = (
            total_reward / total_episodes if total_episodes > 0 else 0.0
        )
        reward_per_wall_time = (
            total_reward / total_wall_time if total_wall_time > 0 else 0.0
        )
        utility_per_probe_episode = (
            utility_gain / probe_costs.probe_episodes_total
            if probe_costs.probe_episodes_total > 0
            else 0.0
        )

        return cls(
            reward_per_total_episode=reward_per_episode,
            reward_per_total_wall_time=reward_per_wall_time,
            utility_gain_per_probe_episode=utility_per_probe_episode,
            total_reward=total_reward,
            probe_costs=probe_costs,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "reward_per_total_episode": self.reward_per_total_episode,
            "reward_per_total_wall_time": self.reward_per_total_wall_time,
            "utility_gain_per_probe_episode": self.utility_gain_per_probe_episode,
            "total_reward": self.total_reward,
            "probe_costs": self.probe_costs.to_dict() if self.probe_costs else None,
        }
