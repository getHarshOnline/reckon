"""
False Discovery Rate (FDR) Control Methods.

Pure Python implementations for multiple testing correction.
No external dependencies required.

Methods:
    - Bonferroni: Conservative, controls family-wise error rate
    - Benjamini-Hochberg: Less conservative, controls FDR

When to use:
    - Bonferroni: When you need strict control, few tests, or tests are correlated
    - Benjamini-Hochberg: Default choice for many independent tests
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List

__all__ = [
    "FDRMethod",
    "FDRResult",
    "benjamini_hochberg",
    "bonferroni",
    "apply_fdr_correction",
]


class FDRMethod(Enum):
    """FDR correction method."""

    NONE = "none"
    BONFERRONI = "bonferroni"
    BENJAMINI_HOCHBERG = "bh"


@dataclass
class FDRResult:
    """Result of FDR correction."""

    p_values: List[float]  # Original p-values
    q_values: List[float]  # Adjusted p-values (q-values for BH)
    rejected: List[bool]  # Which hypotheses are rejected
    method: FDRMethod
    alpha: float
    n_rejected: int

    @property
    def significant_indices(self) -> List[int]:
        """Indices of significant tests (rejected hypotheses)."""
        return [i for i, r in enumerate(self.rejected) if r]


def bonferroni(
    p_values: List[float],
    alpha: float = 0.05,
) -> FDRResult:
    """
    Bonferroni correction for multiple testing.

    Adjusts p-values by multiplying by the number of tests.
    Controls family-wise error rate (FWER) at level alpha.

    Very conservative - use when:
    - Tests are correlated
    - You need strict error control
    - Number of tests is small

    Args:
        p_values: List of p-values from individual tests
        alpha: Significance level (default 0.05)

    Returns:
        FDRResult with adjusted p-values and rejection decisions

    Example:
        >>> p_values = [0.01, 0.03, 0.04, 0.5]
        >>> result = bonferroni(p_values, alpha=0.05)
        >>> print(result.q_values)  # [0.04, 0.12, 0.16, 2.0]
    """
    if not p_values:
        return FDRResult(
            p_values=[],
            q_values=[],
            rejected=[],
            method=FDRMethod.BONFERRONI,
            alpha=alpha,
            n_rejected=0,
        )

    n = len(p_values)

    # Bonferroni: multiply each p-value by n, cap at 1.0
    q_values = [min(1.0, p * n) for p in p_values]

    # Reject if adjusted p-value <= alpha
    rejected = [q <= alpha for q in q_values]

    return FDRResult(
        p_values=list(p_values),
        q_values=q_values,
        rejected=rejected,
        method=FDRMethod.BONFERRONI,
        alpha=alpha,
        n_rejected=sum(rejected),
    )


def benjamini_hochberg(
    p_values: List[float],
    alpha: float = 0.05,
) -> FDRResult:
    """
    Benjamini-Hochberg procedure for FDR control.

    Controls the expected proportion of false positives among
    rejected hypotheses (False Discovery Rate) at level alpha.

    Less conservative than Bonferroni - use when:
    - Tests are independent or positively dependent
    - You're okay with controlling FDR rather than FWER
    - Number of tests is large

    Algorithm:
    1. Sort p-values in ascending order
    2. For each p-value p_i with rank i, compute threshold = i/n * alpha
    3. Find largest i where p_i <= threshold
    4. Reject all hypotheses with rank <= i

    Args:
        p_values: List of p-values from individual tests
        alpha: Target FDR level (default 0.05)

    Returns:
        FDRResult with q-values and rejection decisions

    Example:
        >>> p_values = [0.01, 0.03, 0.04, 0.5]
        >>> result = benjamini_hochberg(p_values, alpha=0.05)
        >>> print(result.rejected)  # [True, True, True, False]
    """
    if not p_values:
        return FDRResult(
            p_values=[],
            q_values=[],
            rejected=[],
            method=FDRMethod.BENJAMINI_HOCHBERG,
            alpha=alpha,
            n_rejected=0,
        )

    n = len(p_values)

    # Create list of (p_value, original_index)
    indexed_p = [(p, i) for i, p in enumerate(p_values)]

    # Sort by p-value ascending
    indexed_p.sort(key=lambda x: x[0])

    # Compute q-values using BH procedure
    # q_i = min(p_j * n / j for j >= i), working backwards
    q_values = [0.0] * n
    rejected = [False] * n

    # Work backwards from largest to smallest p-value
    # q_i = min(q_{i+1}, p_i * n / rank_i)
    min_q = 1.0
    for rank in range(n, 0, -1):
        p_val, orig_idx = indexed_p[rank - 1]

        # BH adjusted p-value
        adjusted = p_val * n / rank

        # Ensure monotonicity (q-values can only decrease going up)
        min_q = min(min_q, adjusted)

        # Cap at 1.0
        q_values[orig_idx] = min(1.0, min_q)

    # Determine rejections
    # Find the largest rank k where p_(k) <= k/n * alpha
    max_rejected_rank = 0
    for rank in range(1, n + 1):
        p_val, _ = indexed_p[rank - 1]
        threshold = rank / n * alpha
        if p_val <= threshold:
            max_rejected_rank = rank

    # Reject all hypotheses with rank <= max_rejected_rank
    for rank in range(1, max_rejected_rank + 1):
        _, orig_idx = indexed_p[rank - 1]
        rejected[orig_idx] = True

    return FDRResult(
        p_values=list(p_values),
        q_values=q_values,
        rejected=rejected,
        method=FDRMethod.BENJAMINI_HOCHBERG,
        alpha=alpha,
        n_rejected=sum(rejected),
    )


def apply_fdr_correction(
    p_values: List[float],
    method: FDRMethod = FDRMethod.BENJAMINI_HOCHBERG,
    alpha: float = 0.05,
) -> FDRResult:
    """
    Apply FDR correction using the specified method.

    Convenience function that dispatches to the appropriate method.

    Args:
        p_values: List of p-values from individual tests
        method: FDR correction method
        alpha: Significance level (default 0.05)

    Returns:
        FDRResult with adjusted p-values and rejection decisions

    Example:
        >>> p_values = [0.01, 0.03, 0.04, 0.5]
        >>> result = apply_fdr_correction(p_values, FDRMethod.BENJAMINI_HOCHBERG)
        >>> significant = result.significant_indices
    """
    if method == FDRMethod.NONE:
        # No correction - just compare raw p-values to alpha
        rejected = [p <= alpha for p in p_values]
        return FDRResult(
            p_values=list(p_values),
            q_values=list(p_values),  # q-values same as p-values
            rejected=rejected,
            method=FDRMethod.NONE,
            alpha=alpha,
            n_rejected=sum(rejected),
        )

    if method == FDRMethod.BONFERRONI:
        return bonferroni(p_values, alpha)

    if method == FDRMethod.BENJAMINI_HOCHBERG:
        return benjamini_hochberg(p_values, alpha)

    raise ValueError(f"Unknown FDR method: {method}")
