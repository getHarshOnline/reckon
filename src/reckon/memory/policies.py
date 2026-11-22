"""Laboratory choices over the kernel's named retention rules."""

from abc import ABC, abstractmethod
import math
import random

from reckon._rust import select_retention  # pylint: disable=no-name-in-module
from reckon.memory.record import MemoryRecord


class RetentionPolicy(ABC):
    """Choose records to free requested bytes, record slots and tokens."""

    @abstractmethod
    def select_for_pruning(
        self,
        records: list[MemoryRecord],
        overflow_bytes: int,
        overflow_slots: int = 0,
        overflow_tokens: int = 0,
    ) -> list[str]:
        """Return record IDs in removal order without changing the records."""

    @abstractmethod
    def reason(self) -> str:
        """Return the policy's log identifier."""


class _KernelPolicy(RetentionPolicy):
    rule = "ordered"
    log_reason = ""
    evidence_weight = 0.5
    min_per_type = 1

    def select_for_pruning(
        self,
        records: list[MemoryRecord],
        overflow_bytes: int,
        overflow_slots: int = 0,
        overflow_tokens: int = 0,
    ) -> list[str]:
        inputs = []
        for record in records:
            if overflow_tokens and record.cost.tokens is None:
                raise ValueError("Token pressure requires a count for every candidate")
            utility = record.utility.value
            if self.rule == "importance_per_byte":
                utility = record.metadata.get("importance", 0.0)
                if type(utility) not in (int, float) or not math.isfinite(utility):
                    raise ValueError("Record importance must be a finite number")
            inputs.append(
                (
                    record.id,
                    record.timestamp,
                    record.utility.last_used,
                    record.cost.bytes,
                    utility,
                    record.causal_score.ablation_delta,
                    record.causal_score.counterfactual_delta,
                    record.causal_score.influence_proxy,
                    record.payload_type.value,
                    record.cost.tokens or 0,
                )
            )
        return select_retention(
            inputs,
            self.rule,
            overflow_bytes,
            overflow_slots,
            self.evidence_weight,
            self.min_per_type,
            overflow_tokens,
        )

    def reason(self) -> str:
        return self.log_reason


class FIFOPolicy(_KernelPolicy):
    """Prune oldest records first; equal timestamps keep input order."""

    rule = "fifo"
    log_reason = "fifo"


class LRUPolicy(_KernelPolicy):
    """Prune least recently used records, then older creation timestamps."""

    rule = "lru"
    log_reason = "lru"


class UtilityPolicy(_KernelPolicy):
    """Online greedy utility-per-byte heuristic, lowest ratio removed first."""

    rule = "utility_per_byte"
    log_reason = "low_utility"


class ImportancePolicy(_KernelPolicy):
    """Caller-supplied importance per byte, separate from learned utility.

    Read finite ``metadata.importance`` from each record, using zero when
    missing. Invalid weights fail before selection changes the store.
    """

    rule = "importance_per_byte"
    log_reason = "low_explicit_importance"


class EvidencePerBytePolicy(_KernelPolicy):
    """Mix utility with a beneficial measured effect, or an unmeasured proxy, per byte."""

    rule = "evidence_per_byte"
    log_reason = "low_evidence_per_byte"

    def __init__(self, evidence_weight: float = 0.5):
        self.evidence_weight = evidence_weight


class DiversityPolicy(_KernelPolicy):
    """Remove low-utility surplus by payload type before reducing protected minima."""

    rule = "diversity"
    log_reason = "diversity_maintain_coverage"

    def __init__(self, min_per_type: int = 1):
        self.min_per_type = min_per_type


class RandomPolicy(_KernelPolicy):
    """Seeded permutation independent of task randomness and record UUIDs."""

    log_reason = "random"

    def __init__(self, seed: int = 0):
        self.seed = seed
        self.pruning_round = 0

    def select_for_pruning(
        self,
        records: list[MemoryRecord],
        overflow_bytes: int,
        overflow_slots: int = 0,
        overflow_tokens: int = 0,
    ) -> list[str]:
        candidates = list(records)
        random.Random(self.seed + self.pruning_round).shuffle(candidates)
        selected = super().select_for_pruning(
            candidates, overflow_bytes, overflow_slots, overflow_tokens
        )
        self.pruning_round += 1
        return selected
