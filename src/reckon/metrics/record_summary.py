"""
Usage/oracle summaries and stored attribution deltas.

Record usage needs no ground-truth labels. Cue retention and retrieval fractions
use their own supplied labels or counts. Stored ablation deltas are summarized
without performing or validating an intervention. The separate
CausalRecordEvaluator has its own method and interpretation limits; see README.md.
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from reckon.memory.manager import CausalMemoryManager


@dataclass
class RecordSummaryMetrics:
    """
    Producer-specific usage, label and attribution summaries.

    Attributes:
        used_record_fraction: Current stored records with use_count > 0 / stored records.
        necessary_cue_retention: Retained necessary IDs / positive total_cues.
        useful_retrieval_fraction: Caller-supplied useful retrievals / retrievals
            when no positive necessary-cue denominator is supplied.
        max_abs_stored_ablation_delta: Largest absolute finite stored ablation delta.
        mean_stored_ablation_delta: Signed mean of finite stored ablation deltas.
        proxy_only_record_ids: Current record IDs with a proxy and neither delta,
            sorted for reporting; None when no record inventory was supplied.
    """
    used_record_fraction: Optional[float] = None
    necessary_cue_retention: Optional[float] = None
    useful_retrieval_fraction: Optional[float] = None
    max_abs_stored_ablation_delta: Optional[float] = None
    mean_stored_ablation_delta: Optional[float] = None
    proxy_only_record_ids: Optional[list[str]] = None

    @property
    def proxy_only_record_count(self) -> Optional[int]:
        """Count the supplied proxy-only IDs; an unexamined inventory stays unavailable."""
        return None if self.proxy_only_record_ids is None else len(self.proxy_only_record_ids)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            k: v for k, v in {
                "used_record_fraction": self.used_record_fraction,
                "necessary_cue_retention": self.necessary_cue_retention,
                "useful_retrieval_fraction": self.useful_retrieval_fraction,
                "max_abs_stored_ablation_delta": self.max_abs_stored_ablation_delta,
                "mean_stored_ablation_delta": self.mean_stored_ablation_delta,
                "proxy_only_record_ids": self.proxy_only_record_ids,
                "proxy_only_record_count": self.proxy_only_record_count,
            }.items() if v is not None
        }

    @classmethod
    def from_cmm(  # pylint: disable=too-many-locals
        cls,
        cmm: "CausalMemoryManager",
        ground_truth: dict,
    ) -> "RecordSummaryMetrics":
        """
        Summarize current record usage, supplied labels and existing deltas.

        Usage is a stored-record fraction. Cue retention uses the supplied IDs
        when total_cues is positive, defaulting that denominator to the number
        of supplied IDs; otherwise the separately named useful-retrieval fraction
        uses supplied counts.
        Missing denominators or finite scores leave the affected field None.
        This helper does not run the Causal Record Contract or identify effects.

        Args:
            cmm: CausalMemoryManager instance after task execution
            ground_truth: Caller-owned labels/counts, interpreted by branch:
                - necessary_cues: list[str] - IDs labelled necessary by the caller
                - total_cues: int - Recall denominator, defaulting to len(necessary_cues)
                - useful_retrievals: int - Numerator of the fallback retrieval ratio
                - total_retrievals: int - Denominator of that fallback ratio

        Returns:
            RecordSummaryMetrics instance with computed values.
        """
        # Get all records
        records = cmm.get_all_records()
        total_stored = len(records)

        # Access-count proxy; a retrieval does not establish outcome influence.
        used_records = [r for r in records if r.utility.use_count > 0]
        used_count = len(used_records)

        # Read the caller's labels and selected denominator.
        necessary_cues = ground_truth.get("necessary_cues", [])
        total_necessary = ground_truth.get("total_cues", len(necessary_cues))

        # Fraction of current records accessed, independent of their effect.
        used_record_fraction = used_count / total_stored if total_stored > 0 else None

        # Keep the original branch, naming its two different quantities separately.
        necessary_cue_retention = None
        useful_retrieval_fraction = None
        if total_necessary > 0:
            retained_necessary = sum(
                1 for cue_id in necessary_cues
                if cmm.get_record(cue_id) is not None
            )
            necessary_cue_retention = retained_necessary / total_necessary
        else:
            # A nonpositive cue denominator selects the caller's retrieval ratio.
            useful = ground_truth.get("useful_retrievals", 0)
            total = ground_truth.get("total_retrievals", 0)
            useful_retrieval_fraction = useful / total if total > 0 else None

        # Summarize stored deltas; this does not execute an ablation.
        # Filter out None, inf, and NaN values before aggregation
        ablation_deltas = [
            r.causal_score.ablation_delta
            for r in records
            if r.causal_score.ablation_delta is not None
            and math.isfinite(r.causal_score.ablation_delta)
        ]

        if ablation_deltas:
            mean_stored_ablation_delta = sum(ablation_deltas) / len(ablation_deltas)
            max_abs_stored_ablation_delta = max(abs(d) for d in ablation_deltas)
        else:
            mean_stored_ablation_delta = None
            max_abs_stored_ablation_delta = None

        return cls(
            used_record_fraction=used_record_fraction,
            necessary_cue_retention=necessary_cue_retention,
            useful_retrieval_fraction=useful_retrieval_fraction,
            max_abs_stored_ablation_delta=max_abs_stored_ablation_delta,
            mean_stored_ablation_delta=mean_stored_ablation_delta,
            proxy_only_record_ids=sorted(r.id for r in records if r.causal_score.is_proxy_only),
        )
