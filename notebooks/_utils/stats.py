"""
Statistical testing utilities for Reckon notebooks.

Provides non-parametric statistical tests suitable for comparing
experiment results with proper uncertainty quantification:

- Paired permutation test: Compare two paired samples
- Bootstrap confidence intervals: Uncertainty around point estimates
- Effect size: Magnitude of differences (Cohen's d)

These methods are robust to non-normal distributions common in
reinforcement learning and memory system evaluation.
"""

from __future__ import annotations

import math
import random
from typing import Optional

__all__ = [
    "paired_permutation_test",
    "bootstrap_ci",
    "effect_size",
    "format_ci",
    "summarize_stats",
]


def paired_permutation_test(
    baseline: list[float],
    treatment: list[float],
    n_permutations: int = 10000,
    seed: Optional[int] = None,
) -> float:
    """
    Two-sided paired permutation test.

    Tests the null hypothesis that there is no difference between
    baseline and treatment conditions. This non-parametric test makes
    no assumptions about the underlying distribution.

    The test works by computing paired differences, then randomly
    flipping signs to generate the null distribution.

    Args:
        baseline: Baseline scores (one per trial/seed).
        treatment: Treatment scores (same length, paired with baseline).
        n_permutations: Number of permutations for null distribution.
        seed: Random seed for reproducibility.

    Returns:
        Two-sided p-value.

    Raises:
        ValueError: If baseline and treatment have different lengths.

    Example:
        baseline = [0.80, 0.75, 0.82, 0.79, 0.81]
        treatment = [0.85, 0.78, 0.88, 0.82, 0.86]
        p = paired_permutation_test(baseline, treatment)
        print(f"p = {p:.4f}")  # p < 0.05 suggests significant difference
    """
    if len(baseline) != len(treatment):
        raise ValueError(
            f"baseline and treatment must have same length, "
            f"got {len(baseline)} and {len(treatment)}"
        )

    n = len(baseline)
    if n == 0:
        return 1.0

    if seed is not None:
        random.seed(seed)

    # Compute paired differences (baseline - treatment)
    differences = [b - t for b, t in zip(baseline, treatment)]

    # Observed test statistic: mean difference
    observed_mean = sum(differences) / n

    # Generate null distribution by randomly flipping signs
    count_extreme = 0
    for _ in range(n_permutations):
        permuted = [d * random.choice([-1, 1]) for d in differences]
        permuted_mean = sum(permuted) / n
        if abs(permuted_mean) >= abs(observed_mean):
            count_extreme += 1

    # P-value with continuity correction (avoids p=0)
    p_value = (count_extreme + 1) / (n_permutations + 1)
    return p_value


def bootstrap_ci(
    values: list[float],
    confidence: float = 0.95,
    n_bootstrap: int = 10000,
    statistic: str = "mean",
    seed: Optional[int] = None,
) -> tuple[float, float]:
    """
    Bootstrap confidence interval using the percentile method.

    Estimates uncertainty around a point estimate by resampling
    with replacement and computing the statistic on each sample.

    Args:
        values: Sample values.
        confidence: Confidence level (default 0.95 for 95% CI).
        n_bootstrap: Number of bootstrap samples.
        statistic: Statistic to compute ("mean" or "median").
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (lower_bound, upper_bound) for the confidence interval.

    Raises:
        ValueError: If confidence is not in (0, 1) or statistic is unknown.

    Example:
        deltas = [0.05, 0.08, 0.03, 0.07, 0.06]
        low, high = bootstrap_ci(deltas, confidence=0.95)
        print(f"95% CI: [{low:.3f}, {high:.3f}]")
    """
    if len(values) == 0:
        return (float("nan"), float("nan"))

    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    if statistic not in ("mean", "median"):
        raise ValueError(f"statistic must be 'mean' or 'median', got '{statistic}'")

    if seed is not None:
        random.seed(seed)

    n = len(values)

    # Generate bootstrap distribution
    bootstrap_stats = []
    for _ in range(n_bootstrap):
        sample = [random.choice(values) for _ in range(n)]

        if statistic == "mean":
            stat = sum(sample) / n
        else:  # median
            sorted_sample = sorted(sample)
            mid = n // 2
            if n % 2 == 0:
                stat = (sorted_sample[mid - 1] + sorted_sample[mid]) / 2
            else:
                stat = sorted_sample[mid]

        bootstrap_stats.append(stat)

    # Percentile method for CI bounds
    bootstrap_stats.sort()
    alpha = 1 - confidence
    lower_idx = int(n_bootstrap * (alpha / 2))
    upper_idx = int(n_bootstrap * (1 - alpha / 2))

    # Clamp indices to valid range
    lower_idx = max(0, min(lower_idx, n_bootstrap - 1))
    upper_idx = max(0, min(upper_idx, n_bootstrap - 1))

    return (bootstrap_stats[lower_idx], bootstrap_stats[upper_idx])


def effect_size(
    baseline: list[float],
    treatment: list[float],
    method: str = "cohens_d",
) -> float:
    """
    Compute effect size between baseline and treatment.

    Effect size measures the magnitude of a difference independent
    of sample size, useful for practical significance assessment.

    Args:
        baseline: Baseline scores.
        treatment: Treatment scores.
        method: Effect size measure to compute.
            - "cohens_d": Standardized mean difference (default)
            - "simple": Raw mean difference

    Returns:
        Effect size value.

    Interpretation for Cohen's d:
        |d| < 0.2: Negligible effect
        0.2 <= |d| < 0.5: Small effect
        0.5 <= |d| < 0.8: Medium effect
        |d| >= 0.8: Large effect

    Raises:
        ValueError: If method is unknown.

    Example:
        baseline = [0.70, 0.72, 0.68, 0.71, 0.69]
        treatment = [0.85, 0.82, 0.88, 0.84, 0.86]
        d = effect_size(baseline, treatment)
        print(f"Cohen's d = {d:.2f}")  # Large effect if d > 0.8
    """
    if len(baseline) == 0 or len(treatment) == 0:
        return float("nan")

    mean_b = sum(baseline) / len(baseline)
    mean_t = sum(treatment) / len(treatment)

    if method == "simple":
        return mean_t - mean_b

    if method == "cohens_d":
        # Pooled standard deviation
        n_b, n_t = len(baseline), len(treatment)

        var_b = sum((x - mean_b) ** 2 for x in baseline) / max(n_b - 1, 1)
        var_t = sum((x - mean_t) ** 2 for x in treatment) / max(n_t - 1, 1)

        pooled_var = ((n_b - 1) * var_b + (n_t - 1) * var_t) / max(n_b + n_t - 2, 1)
        pooled_std = math.sqrt(pooled_var) if pooled_var > 0 else 0.0

        if pooled_std == 0:
            # No variance: effect is infinite if means differ, 0 otherwise
            return float("inf") if mean_t != mean_b else 0.0

        return (mean_t - mean_b) / pooled_std

    raise ValueError(f"Unknown method: '{method}'. Use 'cohens_d' or 'simple'.")


def format_ci(
    value: float,
    ci: tuple[float, float],
    decimals: int = 3,
) -> str:
    """
    Format a value with confidence interval for display.

    Args:
        value: Point estimate.
        ci: Tuple of (lower, upper) confidence interval bounds.
        decimals: Number of decimal places.

    Returns:
        Formatted string like "0.523 [0.412, 0.634]".

    Example:
        mean = 0.523
        ci = (0.412, 0.634)
        print(format_ci(mean, ci))  # "0.523 [0.412, 0.634]"
    """
    fmt = f".{decimals}f"
    return f"{value:{fmt}} [{ci[0]:{fmt}}, {ci[1]:{fmt}}]"


def summarize_stats(
    baseline: list[float],
    treatment: list[float],
    confidence: float = 0.95,
    n_permutations: int = 10000,
    seed: Optional[int] = None,
) -> dict[str, float | int | bool]:
    """
    Compute comprehensive statistics for baseline vs treatment comparison.

    This convenience function computes all standard statistics needed
    for reporting experimental comparisons.

    Args:
        baseline: Baseline scores.
        treatment: Treatment scores (must have same length as baseline).
        confidence: Confidence level for CI.
        n_permutations: Number of permutations for significance test.
        seed: Random seed for reproducibility.

    Returns:
        Dictionary containing:
        - n: Sample size
        - mean_baseline: Mean of baseline scores
        - mean_treatment: Mean of treatment scores
        - mean_diff: Mean difference (treatment - baseline)
        - ci_low: Lower CI bound for mean_diff
        - ci_high: Upper CI bound for mean_diff
        - p_value: Two-sided permutation test p-value
        - effect_size: Cohen's d
        - is_significant: True if p < 0.05

    Raises:
        ValueError: If baseline and treatment have different lengths.

    Example:
        stats = summarize_stats(baseline_scores, treatment_scores)
        print(f"Diff: {stats['mean_diff']:.3f}, p={stats['p_value']:.4f}")
        if stats['is_significant']:
            print("Significant improvement!")
    """
    if len(baseline) != len(treatment):
        raise ValueError(
            f"baseline and treatment must have same length, "
            f"got {len(baseline)} and {len(treatment)}"
        )

    n = len(baseline)
    mean_b = sum(baseline) / n if n > 0 else 0.0
    mean_t = sum(treatment) / n if n > 0 else 0.0

    # Paired differences (treatment - baseline)
    diffs = [t - b for b, t in zip(baseline, treatment)]
    mean_diff = sum(diffs) / n if n > 0 else 0.0

    ci_low, ci_high = bootstrap_ci(diffs, confidence=confidence, seed=seed)
    p_val = paired_permutation_test(baseline, treatment, n_permutations, seed)
    d = effect_size(baseline, treatment, method="cohens_d")

    return {
        "n": n,
        "mean_baseline": mean_b,
        "mean_treatment": mean_t,
        "mean_diff": mean_diff,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": p_val,
        "effect_size": d,
        "is_significant": p_val < 0.05,
    }
