"""
Prober: Statistical Causal Probing for Memory Records.

Implements causal probing to measure the influence of memory records
on agent performance. Uses ablation (removal) interventions and
statistical tests to determine significance.

Key Features:
    - Multiple test types: permutation (default), t-test, bootstrap
    - FDR control: Bonferroni, Benjamini-Hochberg
    - Adaptive sampling with early stopping
    - Evidence type with full statistics including Cohen's d

Usage:
    from reckon.metrics.probe import Prober, ProbeConfig, StatTestType

    prober = Prober(run_fn=run_episode)
    result = prober.probe(record_ids=["r1", "r2", "r3"])

    for evidence in result.evidence:
        if evidence.is_significant_adjusted:
            print(f"Record {evidence.record_id}: d={evidence.effect_size_d:.2f}")
"""

from __future__ import annotations

import math
import random
from time import perf_counter
from statistics import mean, stdev
from dataclasses import dataclass, replace
from enum import Enum
from typing import List, Optional, Callable

from reckon.metrics.tests.statistical import cohens_d
from reckon.metrics.tests.paired import paired_inference
from reckon.metrics.tests.fdr import (
    FDRMethod,
    apply_fdr_correction,
)

__all__ = [
    "StatTestType",
    "InterventionMethod",
    "ProbeConfig",
    "Evidence",
    "ProbeResult",
    "Prober",
]


class StatTestType(Enum):
    """Statistical test type for probing."""

    T_TEST = "t_test"
    PERMUTATION = "permutation"
    BOOTSTRAP = "bootstrap"


class InterventionMethod(Enum):
    """Intervention method for probing."""

    ABLATE = "ablate"  # Remove the record
    REPLACE = "replace"  # Replace with random record
    SHUFFLE = "shuffle"  # Shuffle record contents


# These fields are the public record shape, rather than independent object responsibilities.
@dataclass
class ProbeConfig:  # pylint: disable=too-many-instance-attributes
    """
    Configuration for causal probing.

    Attributes:
        test_type: Statistical test to use (default: permutation)
        n_trials: Fixed pair count; also a scheduled look in adaptive mode
        n_permutations: Resampling count for permutation or bootstrap
        alpha: Significance level (default: 0.05)
        delta_threshold: Raw outcome difference considered negligible for stopping
        fdr_method: Multiple testing correction method
        adaptive_sampling: Enable adaptive sample size
        early_stopping: Stop early when effect is clear
        min_trials: Minimum trials before early stopping
        max_trials: Maximum trials for adaptive sampling
        seed: First pair seed; generated and returned in config when absent
    """

    test_type: StatTestType = StatTestType.PERMUTATION
    n_trials: int = 10
    n_permutations: int = 10000
    alpha: float = 0.05
    delta_threshold: float = 0.05
    fdr_method: FDRMethod = FDRMethod.BENJAMINI_HOCHBERG
    adaptive_sampling: bool = True
    early_stopping: bool = True
    min_trials: int = 5
    max_trials: int = 100
    seed: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "test_type": self.test_type.value,
            "n_trials": self.n_trials,
            "n_permutations": self.n_permutations,
            "alpha": self.alpha,
            "delta_threshold": self.delta_threshold,
            "fdr_method": self.fdr_method.value,
            "adaptive_sampling": self.adaptive_sampling,
            "early_stopping": self.early_stopping,
            "min_trials": self.min_trials,
            "max_trials": self.max_trials,
            "seed": self.seed,
        }


# These fields are the public record shape, rather than independent object responsibilities.
@dataclass
class Evidence:  # pylint: disable=too-many-instance-attributes
    """
    Statistical evidence from probing a single record.

    Contains full statistics from the ablation experiment:
    baseline (with record) vs intervention (without record).

    Attributes:
        record_id: ID of the probed record
        test_type: Statistical test used
        baseline_mean: Mean outcome with record present
        baseline_std: Std dev of baseline outcomes
        intervention_mean: Mean outcome without record
        intervention_std: Std dev of intervention outcomes
        delta: Difference (baseline - intervention)
        effect_size_d: Cohen's d effect size
        p_value: P-value adjusted for adaptive looks, before across-record correction
        p_value_adjusted: FDR-adjusted p-value (q-value)
        ci_lower: Lower bound of confidence interval
        ci_upper: Upper bound of confidence interval
        n_trials: Number of trials used
        power: Statistical power (if computed)
        is_significant: Whether the look-adjusted p-value < alpha
        is_significant_adjusted: Whether adjusted p-value < alpha
    """

    record_id: str
    test_type: StatTestType
    baseline_mean: float
    baseline_std: float
    intervention_mean: float
    intervention_std: float
    delta: float
    effect_size_d: float
    p_value: float
    p_value_adjusted: float
    ci_lower: float
    ci_upper: float
    n_trials: int
    power: Optional[float] = None
    is_significant: bool = False
    is_significant_adjusted: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "test_type": self.test_type.value,
            "baseline_mean": self.baseline_mean,
            "baseline_std": self.baseline_std,
            "intervention_mean": self.intervention_mean,
            "intervention_std": self.intervention_std,
            "delta": self.delta,
            "effect_size_d": self.effect_size_d,
            "p_value": self.p_value,
            "p_value_adjusted": self.p_value_adjusted,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "n_trials": self.n_trials,
            "power": self.power,
            "is_significant": self.is_significant,
            "is_significant_adjusted": self.is_significant_adjusted,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        """Create from dictionary."""
        return cls(
            record_id=data["record_id"],
            test_type=StatTestType(data["test_type"]),
            baseline_mean=data["baseline_mean"],
            baseline_std=data["baseline_std"],
            intervention_mean=data["intervention_mean"],
            intervention_std=data["intervention_std"],
            delta=data["delta"],
            effect_size_d=data["effect_size_d"],
            p_value=data["p_value"],
            p_value_adjusted=data["p_value_adjusted"],
            ci_lower=data["ci_lower"],
            ci_upper=data["ci_upper"],
            n_trials=data["n_trials"],
            power=data.get("power"),
            is_significant=data.get("is_significant", False),
            is_significant_adjusted=data.get("is_significant_adjusted", False),
        )


@dataclass
class ProbeResult:
    """
    Result of probing multiple records.

    Attributes:
        evidence: List of Evidence for each probed record
        config: ProbeConfig used
        probe_episodes: Total episodes spent on probing
        probe_wall_time_s: Total wall time in seconds
        records_probed: Number of records probed
    """

    evidence: List[Evidence]
    config: ProbeConfig
    probe_episodes: int = 0
    probe_wall_time_s: float = 0.0
    records_probed: int = 0

    @property
    def significant_records(self) -> List[str]:
        """Record IDs with significant effects (adjusted)."""
        return [e.record_id for e in self.evidence if e.is_significant_adjusted]

    @property
    def n_significant(self) -> int:
        """Number of significant records."""
        return len(self.significant_records)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "evidence": [e.to_dict() for e in self.evidence],
            "config": self.config.to_dict(),
            "probe_episodes": self.probe_episodes,
            "probe_wall_time_s": self.probe_wall_time_s,
            "records_probed": self.records_probed,
        }


def _scheduled_looks(config: ProbeConfig) -> tuple[int, set[int]]:
    """Choose all inspection sizes before observing any outcomes."""
    adaptive = config.adaptive_sampling and config.early_stopping
    limit = config.max_trials if adaptive else config.n_trials
    looks = {limit}
    if adaptive:
        size = config.min_trials
        while size < limit:
            looks.add(size)
            size *= 2
        looks.add(min(limit, max(config.min_trials, config.n_trials)))
    return limit, looks


class Prober:
    """Compare a caller's runs with and without each record, paired by seed.

    The runner receives ``(ablated_ids, seed)`` and returns a finite outcome
    where higher is better. It owns task setup and must actually remove the
    requested records before their use. Both arms start from the same state
    and seed. No precomputed, unmatched baseline is accepted.
    """

    def __init__(self, run_fn: Optional[Callable[[List[str], int], float]] = None):
        self.run_fn = run_fn

    def probe(
        self,
        record_ids: List[str],
        config: Optional[ProbeConfig] = None,
        intervention: InterventionMethod = InterventionMethod.ABLATE,
    ) -> ProbeResult:
        """Run paired trials, recording both arms' episode cost and elapsed time.

        Adaptive runs inspect predetermined sample counts and adjust p-values
        for those looks before the configured across-record correction.
        Replacement and shuffling are refused before calling the runner.
        """
        config = config or ProbeConfig()
        if self.run_fn is None:
            raise ValueError("run_fn must be set to run probes")
        if intervention != InterventionMethod.ABLATE:
            raise NotImplementedError(f"Intervention {intervention.value} is not implemented")
        if not (0 < config.alpha < 1) or config.n_permutations < 1:
            raise ValueError("alpha must be between zero and one; resamples must be positive")
        if config.n_trials < 2 or config.min_trials < 2 or config.max_trials < config.min_trials:
            raise ValueError("Trial counts must allow at least two paired observations")
        if not math.isfinite(config.delta_threshold) or config.delta_threshold < 0:
            raise ValueError("delta_threshold must be finite and nonnegative")
        if config.seed is None:
            config = replace(config, seed=random.SystemRandom().randrange(2**32))

        started = perf_counter()
        evidence_list = [self._probe_single(record_id, config) for record_id in record_ids]
        if evidence_list:
            correction = apply_fdr_correction(
                [e.p_value for e in evidence_list], method=config.fdr_method, alpha=config.alpha
            )
            for evidence, adjusted, rejected in zip(
                evidence_list, correction.q_values, correction.rejected
            ):
                evidence.p_value_adjusted = adjusted
                evidence.is_significant_adjusted = rejected
        return ProbeResult(
            evidence=evidence_list,
            config=config,
            probe_episodes=2 * sum(e.n_trials for e in evidence_list),
            probe_wall_time_s=perf_counter() - started,
            records_probed=len(record_ids),
        )

    def _probe_single(self, record_id: str, config: ProbeConfig) -> Evidence:
        assert self.run_fn is not None
        assert config.seed is not None
        limit, looks = _scheduled_looks(config)
        baseline, outcomes = [], []
        inference = None
        for trial in range(limit):
            seed = config.seed + trial
            pair = (float(self.run_fn([], seed)), float(self.run_fn([record_id], seed)))
            if not all(math.isfinite(value) for value in pair):
                raise ValueError("Probe runner returned a non-finite outcome")
            baseline.append(pair[0])
            outcomes.append(pair[1])
            if trial + 1 not in looks:
                continue
            differences = [b - i for b, i in zip(baseline, outcomes)]
            p_value, interval = paired_inference(
                differences,
                config.test_type.value,
                config.n_permutations,
                config.alpha / len(looks),
                config.seed,
            )
            # Bonferroni across the predetermined looks, then across records.
            p_value = min(1.0, p_value * len(looks))
            inference = (differences, p_value, interval)
            negligible = (
                -config.delta_threshold <= interval[0] and interval[1] <= config.delta_threshold
            )
            if p_value < config.alpha or negligible:
                break

        if inference is None:
            raise RuntimeError("Probe completed without a scheduled inference")
        differences, p_value, interval = inference
        return Evidence(
            record_id=record_id,
            test_type=config.test_type,
            baseline_mean=mean(baseline),
            baseline_std=stdev(baseline),
            intervention_mean=mean(outcomes),
            intervention_std=stdev(outcomes),
            delta=mean(differences),
            effect_size_d=cohens_d(baseline, outcomes),
            p_value=p_value,
            p_value_adjusted=p_value,
            ci_lower=interval[0],
            ci_upper=interval[1],
            n_trials=len(outcomes),
            is_significant=p_value < config.alpha,
        )

    def set_run_fn(self, run_fn: Callable[[List[str], int], float]) -> None:
        """Set the runner for both seed-matched arms."""
        self.run_fn = run_fn
