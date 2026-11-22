"""
Resource-indexed direct influence between event pairs.

The empirical relation records thresholded pairwise observations under
declared resource constraints. Detectable influence from A to B and
from B to C does not establish detectable influence from A to C.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Generic, Optional, TypeVar
import json

from reckon.core.resources import ResourceVector

# Epsilon for floating-point comparison to avoid precision issues
EPSILON = 1e-9

Event = TypeVar("Event")


class DistinguishabilityMeasure(Enum):
    """Measures for detecting causal influence."""

    TOTAL_VARIATION = "tv"
    KL_DIVERGENCE = "kl"
    HELLINGER = "hellinger"


@dataclass
class CausalRelation:
    """
    Caller-supplied distinguishability for an event pair under resources R.

    The stored threshold classifies the supplied value; this object neither
    runs an intervention nor validates causal identification assumptions.

    Attributes:
        source: The upstream event A
        target: The downstream event B
        resources: Resource constraints under which relation holds
        distinguishability: Measured distinguishability D(P(y|do(A=1)), P(y|do(A=0)))
        measure: The divergence measure used
        threshold: The threshold η for detectability
    """

    source: str
    target: str
    resources: ResourceVector
    distinguishability: float
    measure: DistinguishabilityMeasure = DistinguishabilityMeasure.TOTAL_VARIATION
    threshold: float = 0.1

    @property
    def is_causal(self) -> bool:
        """Compare the supplied value with threshold minus EPSILON (1e-9).

        Uses epsilon-based comparison to avoid floating-point precision issues.
        """
        return self.distinguishability >= self.threshold - EPSILON


class DirectInfluenceRecords(Generic[Event]):
    """
    Observed direct-influence pairs under a fixed resource vector.

    Callers supply distinguishability values and thresholds. This collection
    checks those recorded numbers; it does not run interventions or establish
    that a protocol isolates an event's causal effect.
    """

    def __init__(self, resources: ResourceVector):
        """
        Initialize with resource constraints.

        Args:
            resources: The resource vector R indexing the relation
        """
        self.resources = resources
        self._relations: dict[tuple[str, str], CausalRelation] = {}

    def add_relation(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        source: str,
        target: str,
        distinguishability: float,
        measure: DistinguishabilityMeasure = DistinguishabilityMeasure.TOTAL_VARIATION,
        threshold: float = 0.1,
    ) -> None:
        """Add or update a causal relation."""
        relation = CausalRelation(
            source=source,
            target=target,
            resources=self.resources,
            distinguishability=distinguishability,
            measure=measure,
            threshold=threshold,
        )
        self._relations[(source, target)] = relation

    def causes(self, source: str, target: str) -> bool:
        """Return the stored pair's threshold decision, or False when the pair is absent."""
        key = (source, target)
        if key in self._relations:
            return self._relations[key].is_causal
        return False

    def get_relation(self, source: str, target: str) -> Optional[CausalRelation]:
        """Get the full relation object if it exists."""
        return self._relations.get((source, target))

    def upstream_of(self, target: str) -> list[str]:
        """Get all events that cause target."""
        return [
            source for (source, t), rel in self._relations.items() if t == target and rel.is_causal
        ]

    def downstream_of(self, source: str) -> list[str]:
        """Get all events caused by source."""
        return [
            target for (s, target), rel in self._relations.items() if s == source and rel.is_causal
        ]

    def all_events(self) -> set[str]:
        """Get all unique event identifiers in the relation."""
        events: set[str] = set()
        for source, target in self._relations:
            events.add(source)
            events.add(target)
        return events

    def check_transitivity(
        self,
        alpha: float = 0.05,
        multiple_testing_correction: str = "none",
    ) -> "TransitivityReport":
        """
        Report triples whose recorded direct influences do not compose.

        WARNING: The empirical estimator hat{preceq}_{R,n,alpha,M} is a noisy
        graph. Pairwise significance does NOT compose: A->B and B->C at p<alpha
        does NOT imply A->C is detectable at p<alpha.

        This method reports violations as diagnostics, NOT failures.
        The system does NOT assume closure.

        Args:
            alpha: Report metadata for the upstream significance level.
            multiple_testing_correction: Report metadata for the upstream
                correction method. This scan uses recorded pair thresholds.

        Returns:
            TransitivityReport with violations and diagnostics
        """
        violations: list[TransitivityViolation] = []
        total_triples_tested = 0

        # Get all events and check all (A, B, C) triples where A->B and B->C
        events = sorted(self.all_events())

        for a in events:
            for b in events:
                if a == b:
                    continue
                # Check if A->B is detected
                rel_ab = self.get_relation(a, b)
                if rel_ab is None or not rel_ab.is_causal:
                    continue

                for c in events:
                    if c in (a, b):
                        continue
                    # Check if B->C is detected
                    rel_bc = self.get_relation(b, c)
                    if rel_bc is None or not rel_bc.is_causal:
                        continue

                    # We have A->B and B->C detected
                    total_triples_tested += 1

                    # Check if A->C is detected
                    rel_ac = self.get_relation(a, c)
                    a_c_detected = rel_ac is not None and rel_ac.is_causal

                    if not a_c_detected:
                        # Transitivity violation!
                        violations.append(
                            TransitivityViolation(
                                triple=(a, b, c),
                                a_b_detected=True,
                                b_c_detected=True,
                                a_c_detected=False,
                                a_b_distinguishability=rel_ab.distinguishability,
                                b_c_distinguishability=rel_bc.distinguishability,
                                a_c_distinguishability=(
                                    rel_ac.distinguishability if rel_ac else None
                                ),
                                a_c_threshold=(rel_ac.threshold if rel_ac else rel_ab.threshold),
                            )
                        )

        violation_rate = len(violations) / total_triples_tested if total_triples_tested > 0 else 0.0

        return TransitivityReport(
            violations=violations,
            violation_rate=violation_rate,
            total_triples_tested=total_triples_tested,
            alpha=alpha,
            multiple_testing_correction=multiple_testing_correction,
        )


@dataclass
class TransitivityViolation:  # pylint: disable=too-many-instance-attributes
    """
    Two detected edges whose endpoint pair is missing or below threshold.

    A missing endpoint pair has no distinguishability value. The reported
    threshold then comes from the first edge of the path.

    This is a diagnostic, not a failure. The empirical estimator can violate
    transitivity due to:
    - Stochasticity / finite sample size
    - Type I errors (false edges)
    - Type II errors (missing edges)
    - Selection bias (not all triples tested)
    - Multiple testing inflation
    """

    triple: tuple[str, str, str]  # (A, B, C)
    a_b_detected: bool
    b_c_detected: bool
    a_c_detected: bool
    a_b_distinguishability: float
    b_c_distinguishability: float
    a_c_distinguishability: Optional[float]
    a_c_threshold: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "triple": list(self.triple),
            "a_b_detected": self.a_b_detected,
            "b_c_detected": self.b_c_detected,
            "a_c_detected": self.a_c_detected,
            "a_b_distinguishability": self.a_b_distinguishability,
            "b_c_distinguishability": self.b_c_distinguishability,
            "a_c_distinguishability": self.a_c_distinguishability,
            "a_c_threshold": self.a_c_threshold,
        }


@dataclass
class TransitivityReport:
    """
    Report of triples whose observed direct influences do not compose.

    The diagnostic records the observed graph. Noise and finite samples
    can affect that graph, and direct influence need not compose in principle.
    """

    violations: list[TransitivityViolation]
    violation_rate: float
    total_triples_tested: int
    alpha: float
    multiple_testing_correction: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "violations": [v.to_dict() for v in self.violations],
            "violation_rate": self.violation_rate,
            "total_triples_tested": self.total_triples_tested,
            "alpha": self.alpha,
            "multiple_testing_correction": self.multiple_testing_correction,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_canonical_json(self) -> str:
        """Encode finite report values under reckon.transitivity-report/v1.

        The profile sorts triples by Unicode code point, breaks repeated-triple
        ties by their complete encoded values, and retains every entry. Object
        keys are sorted; strings use ASCII escapes; separators have no spaces.
        Hash the UTF-8 encoding without adding a newline. This does not mutate
        the report or normalize event identifiers or numeric representations.
        """
        data = self.to_dict()
        data["schema_version"] = "reckon.transitivity-report/v1"
        data["violations"].sort(
            key=lambda violation: (tuple(violation["triple"]), _canonical_json(violation))
        )
        return _canonical_json(data)


def _canonical_json(value: dict) -> str:
    """Use the profile's exact Python JSON encoding and refuse NaN/infinities."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
