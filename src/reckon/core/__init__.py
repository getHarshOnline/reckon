"""
Reckon Core Module

Mathematical foundations and base abstractions:
- Resource vectors and budgets
- Coarse-graining channels
- Record channels
- Operational causality primitives
- Transitivity diagnostics for empirical influence relations
- Episode context for credit assignment
- Credit assignment policies
"""

from reckon.core.causality import (
    DirectInfluenceRecords,
    CausalRelation,
    DistinguishabilityMeasure,
    TransitivityReport,
    TransitivityViolation,
)
from reckon.core.channels import CoarseGraining, RecordChannel
from reckon.core.resources import MemoryBudget, ResourceVector
from reckon.core.episode_context import (
    EpisodeContext,
    get_current_context,
    set_current_context,
    clear_current_context,
)
from reckon.core.credit import (
    CreditPolicy,
    CreditAssignment,
    compute_credit,
    update_utility,
)

__all__ = [
    "ResourceVector",
    "MemoryBudget",
    "CoarseGraining",
    "RecordChannel",
    "DirectInfluenceRecords",
    "CausalRelation",
    "DistinguishabilityMeasure",
    "TransitivityReport",
    "TransitivityViolation",
    # Episode context
    "EpisodeContext",
    "get_current_context",
    "set_current_context",
    "clear_current_context",
    # Credit assignment
    "CreditPolicy",
    "CreditAssignment",
    "compute_credit",
    "update_utility",
]
