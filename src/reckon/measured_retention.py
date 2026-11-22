"""Measure retained records on independent task episodes before a pruning decision."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields, replace
import hashlib
import json
import math
from queue import Empty
from time import perf_counter
from typing import Callable

from reckon.memory.manager import CausalMemoryManager, ReckonJSONEncoder
from reckon.memory.policies import EvidencePerBytePolicy, RetentionPolicy
from reckon.memory.record import MemoryRecord
from reckon.metrics.probe import ProbeConfig, Prober, StatTestType
from reckon.metrics.tests.fdr import FDRMethod
from reckon.tasks.base import BaseTask


@dataclass
class RetentionProbeConfig:
    """Declared future-task experiment; it does not resume the live environment.

    Each trial starts a fresh task from a copy of current memory, carrying that
    memory across the specified episodes under the reference policy. Sampling
    seeds advance by the maximum pair count at each pruning decision. Inference
    corrections cover one decision's candidates, not the whole adaptive run.
    """

    episodes_per_arm: int = 1
    reference_policy: str = "fifo"
    sampling: ProbeConfig = field(default_factory=lambda: ProbeConfig(seed=1_000_000))

    def validate(self) -> None:
        """Refuse an invalid declaration before the main experiment starts."""
        # Counts and flags must not accept one another through bool's int subclass.
        # pylint: disable=unidiomatic-typecheck
        if type(self.episodes_per_arm) is not int or self.episodes_per_arm < 1:
            raise ValueError("Probe episodes_per_arm must be a positive integer")
        sampling = self.sampling
        for name in ("n_trials", "min_trials", "max_trials", "n_permutations", "seed"):
            value = getattr(sampling, name)
            if type(value) is not int or value < (0 if name == "seed" else 1):
                raise ValueError(f"Probe {name} must be an integer in its declared range")
        if sampling.n_trials < 2 or sampling.min_trials < 2:
            raise ValueError("Probe sampling requires at least two paired trials")
        if sampling.max_trials < sampling.min_trials:
            raise ValueError("Probe max_trials must cover min_trials")
        for name in ("adaptive_sampling", "early_stopping"):
            if type(getattr(sampling, name)) is not bool:
                raise ValueError(f"Probe {name} must be Boolean")
        if not math.isfinite(sampling.alpha) or not 0 < sampling.alpha < 1:
            raise ValueError("Probe alpha must lie between zero and one")
        if not math.isfinite(sampling.delta_threshold) or sampling.delta_threshold < 0:
            raise ValueError("Probe delta_threshold must be finite and non-negative")
        if not isinstance(sampling.test_type, StatTestType) or not isinstance(
            sampling.fdr_method, FDRMethod
        ):
            raise ValueError("Probe test and correction must name implemented methods")

    def to_dict(self) -> dict:
        """Keep the actual statistical choices with every experiment."""
        return {
            "episodes_per_arm": self.episodes_per_arm,
            "reference_policy": self.reference_policy,
            "sampling": self.sampling.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> RetentionProbeConfig:
        """Decode only supported fields; reject unused configuration."""
        if not isinstance(data, dict) or set(data) - {item.name for item in fields(cls)}:
            raise ValueError("Unsupported retention_probe configuration")
        raw = data.get("sampling", {})
        if not isinstance(raw, dict) or set(raw) - {item.name for item in fields(ProbeConfig)}:
            raise ValueError("Unsupported retention_probe sampling configuration")
        sampling = dict(raw)
        if "test_type" in sampling:
            sampling["test_type"] = StatTestType(sampling["test_type"])
        if "fdr_method" in sampling:
            sampling["fdr_method"] = FDRMethod(sampling["fdr_method"])
        sampling.setdefault("seed", 1_000_000)
        result = cls(
            episodes_per_arm=data.get("episodes_per_arm", 1),
            reference_policy=data.get("reference_policy", "fifo"),
            sampling=ProbeConfig(**sampling),
        )
        result.validate()
        return result


class MeasuredRetentionPolicy(EvidencePerBytePolicy):  # pylint: disable=too-many-instance-attributes
    """Use paired warm-memory contrasts in the existing per-byte ranking.

    A batch measures each current record's removal before fresh task episodes.
    It does not evaluate the live task's hidden continuation or transfer a score
    from a different record. All trials use independent copies and a non-probing
    reference policy. The live store changes only when its manager accepts the
    selected removals. Signed estimates and uncertainty remain in the report;
    the ranking uses the point estimate without a significance pass mark.
    """

    log_reason = "measured_ablation_per_byte"

    # The separate factories declare the task, initial memory and reference policy.
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(
        self,
        config: RetentionProbeConfig,
        snapshot_factory: Callable[[], CausalMemoryManager],
        task_factory: Callable[[], BaseTask],
        reference_factory: Callable[[], RetentionPolicy],
        metric: str,
        main_seed: int,
        learn_utility: bool,
        evidence_weight: float = 0.5,
    ):
        super().__init__(evidence_weight)
        config.validate()
        self.config = deepcopy(config)
        self.snapshot_factory = snapshot_factory
        self.task_factory = task_factory
        self.reference_factory = reference_factory
        self.metric = metric
        self.main_seed = main_seed
        self.learn_utility = learn_utility
        self.batches: list[dict] = []

    @property
    def elapsed_s(self) -> float:
        """All measured-selection work, including copies, statistics and ranking."""
        return sum(batch["elapsed_s"] for batch in self.batches)

    @property
    def episodes(self) -> int:
        """Actual task episodes in both arms of all completed probes."""
        return sum(batch["probe_episodes"] for batch in self.batches)

    # Keep each experiment and its resource accounting in one timed operation.
    # pylint: disable=too-many-locals
    def _trial(self, snapshot: CausalMemoryManager, removed: str | None, seed: int) -> dict:
        started = perf_counter()
        memory = snapshot.fork_for_trial(self.reference_factory())
        initial = {record.id for record in memory.get_all_records()}
        initial_bytes = memory.current_usage_bytes
        reads: Counter = Counter()

        def observe_read(candidates: list[MemoryRecord]) -> None:
            reads.update(record.id for record in candidates if record.id in initial)

        with memory.subscribe_events() as events, memory.before_read(observe_read):
            if removed is not None:
                if not memory.prune(removed, reason="retention_probe_ablation"):
                    raise RuntimeError("Retention probe failed to remove its target")
                if memory.get_record(removed) is not None:
                    raise RuntimeError("Retention probe target survived removal")
            result = self.task_factory().run(
                memory,
                self.config.episodes_per_arm,
                seed,
                reset_memory=False,
                learn_utility=self.learn_utility,
            )
        outcome = getattr(result.performance, self.metric)
        if outcome is None or not math.isfinite(outcome):
            raise ValueError("Retention probe requires a finite task outcome")
        counts: Counter = Counter()
        peak_bytes = initial_bytes
        sources = set()
        while True:
            try:
                source, event = events.get_nowait()
            except Empty:
                break
            sources.add(source)
            counts[event["op_type"]] += 1
            if event["op_type"] == "write":
                peak_bytes = max(peak_bytes, event["bytes_after"])
        return {
            "seed": seed,
            "outcome": float(outcome),
            "removed_record_id": removed,
            "episodes": self.config.episodes_per_arm,
            "elapsed_s": perf_counter() - started,
            "initial_record_reads": dict(reads),
            "memory_events": {
                "coverage": "complete_trial_subscription",
                "source_ids": sorted(sources),
                "counts": dict(counts),
                "initial_bytes": initial_bytes,
                "peak_bytes": peak_bytes,
            },
        }

    def select_for_pruning(
        self,
        records: list[MemoryRecord],
        overflow_bytes: int,
        overflow_slots: int = 0,
        overflow_tokens: int = 0,
    ) -> list[str]:
        started = perf_counter()
        sampling = self.config.sampling
        assert sampling.seed is not None
        stride = max(sampling.n_trials, sampling.max_trials)
        sampling = replace(sampling, seed=sampling.seed + len(self.batches) * stride)
        assert sampling.seed is not None
        if sampling.seed <= self.main_seed < sampling.seed + stride:
            raise ValueError("Probe seed range overlaps the main task seed")
        snapshot = self.snapshot_factory()
        states = [record.to_dict() for record in snapshot.get_all_records()]
        if [state["id"] for state in states] != [record.id for record in records]:
            raise ValueError("Probe snapshot differs from the retention candidates")
        inputs = {
            "records": states,
            "budget": asdict(snapshot.budget),
            "native_costs": {
                record.id: {"bytes": record.cost.bytes, "tokens": record.cost.tokens}
                for record in records
            },
        }
        encoded = json.dumps(inputs, cls=ReckonJSONEncoder, sort_keys=True, allow_nan=False)
        pairs: list[dict] = []
        pending: dict | None = None

        def run(removed: list[str], seed: int) -> float:
            nonlocal pending
            if not removed:
                if pending is not None:
                    raise RuntimeError("Probe requested two unmatched baseline arms")
                pending = self._trial(snapshot, None, seed)
                return pending["outcome"]
            if len(removed) != 1 or pending is None or pending["seed"] != seed:
                raise RuntimeError("Probe intervention lacks its matching baseline")
            intervention = self._trial(snapshot, removed[0], seed)
            pairs.append(
                {"record_id": removed[0], "baseline": pending, "intervention": intervention}
            )
            pending = None
            return intervention["outcome"]

        result = Prober(run).probe([record.id for record in records], sampling)
        if pending is not None or 2 * len(pairs) != result.probe_episodes:
            raise RuntimeError("Probe evidence and executed arm counts disagree")
        by_id = {evidence.record_id: evidence for evidence in result.evidence}
        ranked = deepcopy(records)
        for record in ranked:
            record.causal_score.ablation_delta = by_id[record.id].delta
        selected = super().select_for_pruning(
            ranked, overflow_bytes, overflow_slots, overflow_tokens
        )
        evidence_rows = []
        for evidence in result.evidence:
            trials = [pair for pair in pairs if pair["record_id"] == evidence.record_id]
            encoded_evidence = evidence.to_dict()
            if not math.isfinite(evidence.effect_size_d):
                encoded_evidence["effect_size_d"] = None
                encoded_evidence["effect_size_d_unavailable"] = "non_finite"
            evidence_rows.append(
                {
                    **encoded_evidence,
                    "probe_episodes": 2 * len(trials) * self.config.episodes_per_arm,
                    "trial_elapsed_s": sum(
                        trial[arm]["elapsed_s"]
                        for trial in trials
                        for arm in ("baseline", "intervention")
                    ),
                    "trials": trials,
                }
            )
        self.batches.append(
            {
                "snapshot_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
                **json.loads(encoded),
                "protocol": "remove_one_retained_record_before_fresh_task_episodes",
                "reset_memory": False,
                "learn_utility": self.learn_utility,
                "correction_scope": "candidates_at_this_pruning_decision",
                "sampling": result.config.to_dict(),
                "reference_policy": self.config.reference_policy,
                "episodes_per_arm": self.config.episodes_per_arm,
                "metric": self.metric,
                "probe_calls": result.probe_episodes,
                "probe_episodes": result.probe_episodes * self.config.episodes_per_arm,
                "probe_wall_time_s": result.probe_wall_time_s,
                "evidence": evidence_rows,
                "selected": selected,
                "elapsed_s": perf_counter() - started,
            }
        )
        return selected
