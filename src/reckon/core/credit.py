"""
Credit Assignment Policies for observe().

Calls the Rust kernel to distribute outcome credit
to retrieved records. The credit is used to update utility estimates
which inform retention decisions.

Credit Policies:
    - NONE: No credit assignment (standalone logging mode)
    - SIMPLE: Equal credit to all retrieved records
    - SHAPED: Credit weighted by the softplus of current utility
    - ABLATION: Credit based on positive measured ablation deltas

Credit Normalization:
    - Active weights sum to one within floating-point rounding
    - Measured non-positive effects can produce an all-zero vector
    - The utility update enforces its own bounds

Utility Update Rule:
    u <- (1 - eta) * u + eta * credit * outcome
    u = clamp(u, u_min, u_max)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional

from reckon._rust import (
    DEFAULT_ETA,
    DEFAULT_U_MIN,
    DEFAULT_U_MAX,
    DEFAULT_SHAPED_SCALE,
    compute_credit as _compute_credit,
    update_utility as _update_utility,
)

__all__ = [
    "CreditPolicy",
    "CreditAssignment",
    "compute_credit",
    "update_utility",
    "DEFAULT_ETA",
    "DEFAULT_U_MIN",
    "DEFAULT_U_MAX",
    "DEFAULT_SHAPED_SCALE",
]


class CreditPolicy(Enum):
    """
    Credit assignment policy for observe().

    Determines how outcome credit is distributed among retrieved records.
    """

    NONE = "none"  # No credit assignment (degenerate/logging mode)
    SIMPLE = "simple"  # Equal credit to all retrieved records
    SHAPED = "shaped"  # Credit weighted by the softplus of current utility
    ABLATION = "ablation"  # Credit based on positive measured ablation deltas


@dataclass
class CreditAssignment:
    """
    Credit assigned to a single record.

    Attributes:
        record_id: ID of the record receiving credit
        credit: Credit amount (0-1, normalized per-observe call)
        policy: Policy used to compute this credit
    """

    record_id: str
    credit: float
    policy: CreditPolicy

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "record_id": self.record_id,
            "credit": self.credit,
            "policy": self.policy.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CreditAssignment":
        """Create from dictionary."""
        return cls(
            record_id=data["record_id"],
            credit=data["credit"],
            policy=CreditPolicy(data["policy"]),
        )


# The public call exposes each input to the selected kernel credit rule.
def compute_credit(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    record_ids: List[str],
    outcome: float,
    policy: CreditPolicy,
    utilities: Optional[Dict[str, float]] = None,
    ablation_deltas: Optional[Dict[str, float]] = None,
    *,
    shaped_scale: float = DEFAULT_SHAPED_SCALE,
) -> List[CreditAssignment]:
    """
    Compute credit assignments for retrieved records.

    SHAPED normalizes softplus(utility / shaped_scale) across retrieved records.
    Missing utilities default to 0.5 in the laboratory. A finite negative
    outcome changes the utility update, without changing the credit weights.
    ABLATION normalizes positive measured ablation deltas. If every delta is
    absent it falls back to equal credit; measured non-positive deltas earn
    no credit, even when no positive delta remains.

    Args:
        record_ids: IDs of records that were retrieved
        outcome: Outcome value (e.g., reward, success indicator)
        policy: Credit assignment policy
        utilities: Current utility values for SHAPED policy
        ablation_deltas: Signed measured ablation deltas for ABLATION policy
        shaped_scale: Finite, positive scale for SHAPED policy

    Returns:
        Normalized assignments, or zero weights for non-positive measured effects

    Example:
        >>> credits = compute_credit(
        ...     record_ids=["r1", "r2", "r3"],
        ...     outcome=1.0,
        ...     policy=CreditPolicy.SIMPLE,
        ... )
        >>> sum(c.credit for c in credits)
        1.0
    """
    utilities = utilities or {}
    ablation_deltas = ablation_deltas or {}
    weights = _compute_credit(
        [(utilities.get(rid, 0.5), ablation_deltas.get(rid)) for rid in record_ids],
        outcome,
        policy.value,
        shaped_scale,
    )
    return [
        CreditAssignment(record_id=rid, credit=credit, policy=policy)
        for rid, credit in zip(record_ids, weights)
    ]


# The public call preserves the moving-average parameters and positional usage.
def update_utility(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    current_utility: float,
    credit: float,
    outcome: float,
    eta: float = DEFAULT_ETA,
    u_min: float = DEFAULT_U_MIN,
    u_max: float = DEFAULT_U_MAX,
) -> float:
    """
    Update utility using exponential moving average.

    Formula: u <- (1 - eta) * u + eta * credit * outcome
    Then clamp to [u_min, u_max].

    Args:
        current_utility: Current utility value
        credit: Credit assigned to this record
        outcome: Outcome value (e.g., reward)
        eta: Learning rate (default 0.1)
        u_min: Minimum utility bound (default 0.0)
        u_max: Maximum utility bound (default 1.0)

    Returns:
        Updated utility value, clamped to [u_min, u_max]

    Example:
        >>> update_utility(0.5, credit=0.33, outcome=1.0)
        0.483
    """
    return _update_utility(current_utility, credit, outcome, eta, u_min, u_max)
