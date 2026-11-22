"""Tests and intervals for differences between seed-matched runs."""

import math
import random
from itertools import product
from statistics import NormalDist, mean, stdev


def _permutation_probability(differences, samples, rng):
    """Enumerate or sample paired sign flips, keeping the original tie tolerance."""
    n = len(differences)
    delta = mean(differences)
    exact = 2**n <= samples
    signs = (
        product((-1, 1), repeat=n) if exact else (rng.choices((-1, 1), k=n) for _ in range(samples))
    )
    extreme = count = 0
    for trial in signs:
        value = sum(d * sign for d, sign in zip(differences, trial)) / n
        extreme += abs(value) >= abs(delta) * (1 - 1e-14)
        count += 1
    return extreme / count if exact else (extreme + 1) / (count + 1)


def _bootstrap_inference(differences, samples, alpha, rng):
    """Resample whole differences and center the null at their observed mean."""
    delta = mean(differences)
    draws = sorted(mean(rng.choices(differences, k=len(differences))) for _ in range(samples))
    extreme = sum(abs(value - delta) >= abs(delta) * (1 - 1e-14) for value in draws)
    return (extreme + 1) / (samples + 1), (
        draws[min(samples - 1, int(samples * alpha / 2))],
        draws[min(samples - 1, int(samples * (1 - alpha / 2)))],
    )


def paired_inference(differences, method, samples, alpha, seed):
    """Return a two-sided p-value and mean-difference interval.

    Permutation swaps labels within each pair (sign flips); its validity
    requires exchangeability under the null. Bootstrap resamples whole
    differences, centering them at zero for its null distribution. Normal
    and bootstrap intervals are approximations, not causal identification.
    """
    if len(differences) < 2 or not all(math.isfinite(d) for d in differences):
        raise ValueError("Paired inference needs at least two finite differences")
    rng = random.Random(seed)
    delta = mean(differences)
    n = len(differences)
    se = stdev(differences) / math.sqrt(n)
    margin = NormalDist().inv_cdf(1 - alpha / 2) * se
    interval = (delta - margin, delta + margin)

    if method == "permutation":
        p_value = _permutation_probability(differences, samples, rng)
    elif method == "t_test":
        # Other tests remain usable without loading SciPy.
        # pylint: disable-next=import-outside-toplevel
        from scipy.stats import ttest_1samp, t

        p_value = float(getattr(ttest_1samp(differences, 0), "pvalue")) if se else float(delta == 0)
        margin = float(t.ppf(1 - alpha / 2, n - 1)) * se
        interval = (delta - margin, delta + margin)
    elif method == "bootstrap":
        p_value, interval = _bootstrap_inference(differences, samples, alpha, rng)
    else:
        raise ValueError(f"Unknown paired test: {method}")
    return p_value, interval
