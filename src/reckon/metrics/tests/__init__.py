"""
Statistical Tests Module for Reckon Probing.

Provides pure Python statistical tests for causal probing:
- Permutation test (no scipy required)
- t-test (requires scipy, optional)
- FDR correction methods

All core functionality works without scipy. scipy is optional
for convenience methods like t-test.
"""

from reckon.metrics.tests.statistical import (
    permutation_test,
    t_test,
    cohens_d,
    confidence_interval,
    pooled_std,
)
from reckon.metrics.tests.fdr import (
    benjamini_hochberg,
    bonferroni,
    apply_fdr_correction,
    FDRMethod,
)

# Public re-exports intentionally repeat the defining modules’ names.
# pylint: disable=duplicate-code
__all__ = [
    # Statistical tests
    "permutation_test",
    "t_test",
    "cohens_d",
    "confidence_interval",
    "pooled_std",
    # FDR correction
    "benjamini_hochberg",
    "bonferroni",
    "apply_fdr_correction",
    "FDRMethod",
]
# pylint: enable=duplicate-code
