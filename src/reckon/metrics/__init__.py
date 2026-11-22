"""
Reckon Metrics Module

Evaluation metrics for memory management:
- Performance: success rate, return, regret, accuracy
- Memory activity and efficiency: reads per write and reward per stored byte
- Current-record usage and label summaries, separate from intervention evaluation
- Spectral entropy: graph Laplacian spectral complexity
- Probe costs: compute accounting for causal evaluation
- Pareto frontier: quality vs overhead tradeoff analysis
- Probe: statistical causal probing with FDR control
- Debuggability: failure mode detection
"""

from reckon.metrics.record_summary import RecordSummaryMetrics
from reckon.metrics.evaluator import (
    CausalRecordEvaluator,
    EvaluationResult,
    ContractEvaluationReport,
    InterventionMethod,
)
from reckon.metrics.memory import MemoryEfficiencyMetrics
from reckon.metrics.performance import PerformanceMetrics
from reckon.metrics.probe_costs import (
    ProbeCostEvent,
    ProbeCostSummary,
    ProbeCostTracker,
    EfficiencyMetrics,
)
from reckon.metrics.spectral import compute_spectral_entropy, spectral_entropy_from_edges
from reckon.metrics.pareto import (
    ParetoPoint as ParetoPt,
    ParetoPointWithUncertainty,
    ParetoFrontierResult,
    FrontierStability,
    compute_pareto_frontier,
    compute_pareto_frontier_2d,
    compute_frontier_stability,
    select_operating_point,
    is_dominated,
    make_quality_vs_overhead_points,
)
from reckon.metrics.probe import (
    Prober,
    ProbeConfig,
    ProbeResult,
    Evidence,
    StatTestType,
    InterventionMethod as ProbeInterventionMethod,
)
from reckon.metrics.tests import (
    permutation_test,
    t_test,
    cohens_d,
    benjamini_hochberg,
    bonferroni,
    FDRMethod,
)

# Public re-exports intentionally repeat the defining modules’ names.
# pylint: disable=duplicate-code
__all__ = [
    "PerformanceMetrics",
    "MemoryEfficiencyMetrics",
    "RecordSummaryMetrics",
    "CausalRecordEvaluator",
    "EvaluationResult",
    "ContractEvaluationReport",
    "InterventionMethod",
    "ProbeCostEvent",
    "ProbeCostSummary",
    "ProbeCostTracker",
    "EfficiencyMetrics",
    "compute_spectral_entropy",
    "spectral_entropy_from_edges",
    # Pareto
    "ParetoPt",
    "ParetoPointWithUncertainty",
    "ParetoFrontierResult",
    "FrontierStability",
    "compute_pareto_frontier",
    "compute_pareto_frontier_2d",
    "compute_frontier_stability",
    "select_operating_point",
    "is_dominated",
    "make_quality_vs_overhead_points",
    # Probe
    "Prober",
    "ProbeConfig",
    "ProbeResult",
    "Evidence",
    "StatTestType",
    "ProbeInterventionMethod",
    # Statistical tests
    "permutation_test",
    "t_test",
    "cohens_d",
    "benjamini_hochberg",
    "bonferroni",
    "FDRMethod",
]
# pylint: enable=duplicate-code
