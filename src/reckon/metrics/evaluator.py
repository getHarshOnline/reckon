"""Paired evaluation of an actual record removal at a task's read boundary."""

from copy import deepcopy
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
import hashlib
import json
import math
from statistics import mean
from typing import Any, Callable, Optional, TYPE_CHECKING

from reckon.memory.manager import ReckonJSONEncoder
from reckon.memory.record import MemoryRecord
from reckon.metrics.tests.paired import paired_inference

if TYPE_CHECKING:
    from reckon.memory.manager import CausalMemoryManager
    from reckon.tasks.base import BaseTask


def _config(value: Any) -> Any:
    """Snapshot declared configuration without retaining a mutable factory object."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return deepcopy(vars(value))
    return deepcopy(value)


class InterventionMethod(Enum):
    """Only physical ablation is currently executable."""

    ABLATE = "ablate"
    MASK = "mask"
    REPLACE = "replace"


# These fields are the public record shape, rather than independent object responsibilities.
@dataclass
class EvaluationResult:  # pylint: disable=too-many-instance-attributes
    """Signed paired effect with evidence of the selected record in each arm."""

    record_id: str
    intervention_method: InterventionMethod
    baseline_metric: float
    intervention_metric: float
    delta: float
    n_trials: int
    p_value: float
    is_significant: bool
    is_useful: bool
    trials: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Encode the declared fields with the intervention’s string value."""
        result = asdict(self)
        result["intervention_method"] = self.intervention_method.value
        return result


@dataclass
class ContractEvaluationReport:
    """Useful fraction among evaluated targets and optional labelled recall."""

    contract_precision: float
    contract_recall: Optional[float]
    evaluated_records: list[EvaluationResult]
    delta_threshold: float
    alpha: float
    n_trials: int

    def to_dict(self) -> dict:
        """Encode the aggregate and each target’s complete signed result."""
        result = asdict(self)
        result["evaluated_records"] = [record.to_dict() for record in self.evaluated_records]
        return result


# Factories and sampling controls remain individually accessible to existing callers.
class CausalRecordEvaluator:  # pylint: disable=too-many-instance-attributes
    """Remove one selected record immediately before its first eligible read.

    Each arm gets a fresh task and manager with matching declared configuration.
    A selector identifies the same logical record despite newly generated UUIDs.
    It must select exactly one candidate at the first matching read. The paired
    arms must reach the same read ordinal with the same record content and state.
    Missing, ambiguous or mismatched targets fail instead of producing evidence.
    """

    # Factories and sampling controls remain explicit in the existing public constructor.
    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        task_factory: Callable[[], "BaseTask"],
        cmm_factory: Callable[[], "CausalMemoryManager"],
        metric_fn: Callable[[Any], float],
        n_trials: int = 10,
        delta_threshold: float = 0.05,
        alpha: float = 0.05,
        seed_base: int = 42,
        num_episodes: int = 1,
    ):
        if n_trials < 2:
            raise ValueError("n_trials must be at least two")
        if num_episodes < 1:
            raise ValueError("num_episodes must be positive")
        if not math.isfinite(delta_threshold) or delta_threshold < 0:
            raise ValueError("delta_threshold must be finite and non-negative")
        if not 0 < alpha < 1:
            raise ValueError("alpha must be between zero and one")
        self.task_factory = task_factory
        self.cmm_factory = cmm_factory
        self.metric_fn = metric_fn
        self.n_trials = n_trials
        self.delta_threshold = delta_threshold
        self.alpha = alpha
        self.seed_base = seed_base
        self.num_episodes = num_episodes
        task, memory = task_factory(), cmm_factory()
        other_task, other_memory = task_factory(), cmm_factory()
        if task is other_task or memory is other_memory:
            raise ValueError("Factories must create fresh task and manager instances")
        self._expected_config = self._configuration(task, memory)
        self._check_configuration(other_task, other_memory)

    @staticmethod
    def _configuration(task: "BaseTask", memory: "CausalMemoryManager") -> tuple:
        return (
            type(task),
            _config(getattr(task, "config", None)),
            _config(memory.budget),
            type(memory.retention_policy),
            _config(memory.retention_policy),
        )

    def _check_configuration(self, task: "BaseTask", memory: "CausalMemoryManager") -> None:
        if self._configuration(task, memory) != self._expected_config:
            raise ValueError("Factories changed the task, budget or policy configuration")

    @staticmethod
    def _target_digest(record: MemoryRecord, read_ordinal: int) -> str:
        # UUIDs and provenance input IDs vary between fresh runs. The task's
        # selector supplies logical identity; compare the selected state as well.
        state = {
            "read_ordinal": read_ordinal,
            "timestamp": record.timestamp,
            "episode_id": record.episode_id,
            "payload_type": record.payload_type.value,
            "payload": record.payload,
            "cost": record.cost,
            "tags": record.tags,
            "source_op": record.provenance.source_op,
            "utility": record.utility,
            "causal_score": record.causal_score,
            "metadata": record.metadata,
        }
        encoded = json.dumps(state, cls=ReckonJSONEncoder, sort_keys=True, allow_nan=False)
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _run_trial(
        self,
        arm: tuple["BaseTask", "CausalMemoryManager"],
        seed: int,
        selector: Callable[[MemoryRecord], bool],
        ablate: bool,
    ) -> tuple[float, dict]:
        task, memory = arm
        self._check_configuration(task, memory)
        evidence: dict = {}
        read_ordinal = 0

        def at_read(candidates: list[MemoryRecord]) -> None:
            nonlocal read_ordinal
            read_ordinal += 1
            if evidence:
                return
            matches = [record for record in candidates if selector(record)]
            if len(matches) > 1:
                raise ValueError("Record selector is ambiguous at the read boundary")
            if not matches:
                return
            record = matches[0]
            evidence.update(
                record_id=record.id,
                target_sha256=self._target_digest(record, read_ordinal),
                read_ordinal=read_ordinal,
                removed=False,
            )
            if ablate:
                removed = memory.prune(record.id, reason="ablation_evaluation")
                if not removed or memory.get_record(record.id) is not None:
                    raise RuntimeError("Ablation did not remove the selected record")
                evidence["removed"] = True

        with memory.before_read(at_read):
            result = task.run(memory, num_episodes=self.num_episodes, seed=seed)
        if not evidence:
            raise ValueError("The target record never reached a read boundary")
        score = float(self.metric_fn(result))
        if not math.isfinite(score):
            raise ValueError("Evaluation metric must be finite")
        return score, evidence

    def _evaluate_pair(self, seed: int, selector: Callable[[MemoryRecord], bool]) -> dict:
        """Run fresh matched arms and retain their actual target and read boundary."""
        task, memory = self.task_factory(), self.cmm_factory()
        other_task, other_memory = self.task_factory(), self.cmm_factory()
        if task is other_task or memory is other_memory:
            raise ValueError("Each arm needs a fresh task and manager")
        baseline, baseline_evidence = self._run_trial((task, memory), seed, selector, False)
        intervention, intervention_evidence = self._run_trial(
            (other_task, other_memory), seed, selector, True
        )
        if baseline_evidence["target_sha256"] != intervention_evidence["target_sha256"]:
            raise ValueError("Paired arms selected different record states or read boundaries")
        return {
            "seed": seed,
            "episodes_per_arm": self.num_episodes,
            "baseline_metric": baseline,
            "intervention_metric": intervention,
            "baseline": baseline_evidence,
            "intervention": intervention_evidence,
        }

    def evaluate_record(
        self,
        record_id: str,
        method: InterventionMethod = InterventionMethod.ABLATE,
        *,
        record_selector: Optional[Callable[[MemoryRecord], bool]] = None,
    ) -> EvaluationResult:
        """Evaluate one target, using exact ID unless a logical selector is supplied.

        With a selector, record_id is the caller's stable label in the report.
        Later replacement records are allowed: the estimand is removal of this
        one instance at its first eligible read, not permanent suppression of a
        fact. Task randomness must come from the supplied seed.
        """
        if method is not InterventionMethod.ABLATE:
            raise NotImplementedError("Only ABLATE executes a supported intervention")
        selector = record_selector or (lambda record: record.id == record_id)
        trials = [
            self._evaluate_pair(self.seed_base + trial, selector) for trial in range(self.n_trials)
        ]
        baseline_scores = [trial["baseline_metric"] for trial in trials]
        intervention_scores = [trial["intervention_metric"] for trial in trials]
        differences = [b - i for b, i in zip(baseline_scores, intervention_scores)]
        delta = mean(differences)
        p_value, _ = paired_inference(differences, "permutation", 10000, self.alpha, self.seed_base)
        significant = p_value < self.alpha and abs(delta) >= self.delta_threshold
        return EvaluationResult(
            record_id=record_id,
            intervention_method=method,
            baseline_metric=mean(baseline_scores),
            intervention_metric=mean(intervention_scores),
            delta=delta,
            n_trials=self.n_trials,
            p_value=p_value,
            is_significant=significant,
            is_useful=significant and delta > 0 and delta >= self.delta_threshold,
            trials=trials,
        )

    def evaluate_all(
        self,
        record_ids: list[str],
        method: InterventionMethod = InterventionMethod.ABLATE,
        ground_truth_ids: Optional[set[str]] = None,
        *,
        record_selectors: Optional[dict[str, Callable[[MemoryRecord], bool]]] = None,
    ) -> ContractEvaluationReport:
        """Evaluate distinct labels; aggregate beneficial effects only.

        Per-record p-values are unadjusted. This descriptive useful fraction
        does not claim family-wise error or false-discovery control.
        """
        if method is not InterventionMethod.ABLATE:
            raise NotImplementedError("Only ABLATE executes a supported intervention")
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("Evaluation target labels must be distinct")
        selectors = record_selectors or {}
        if set(selectors) - set(record_ids):
            raise ValueError("A record selector has no requested target label")
        results = [
            self.evaluate_record(rid, method, record_selector=selectors.get(rid))
            for rid in record_ids
        ]
        useful = {result.record_id for result in results if result.is_useful}
        recall = (
            None if not ground_truth_ids else len(useful & ground_truth_ids) / len(ground_truth_ids)
        )
        return ContractEvaluationReport(
            contract_precision=len(useful) / len(results) if results else 0.0,
            contract_recall=recall,
            evaluated_records=results,
            delta_threshold=self.delta_threshold,
            alpha=self.alpha,
            n_trials=self.n_trials,
        )
