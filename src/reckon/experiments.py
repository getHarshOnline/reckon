"""Declared task runs and comparisons across policies, budgets and seeds."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
import math
from statistics import mean, stdev
from time import perf_counter
from typing import Any

import yaml

from reckon.core.resources import MemoryBudget
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.policies import (
    EvidencePerBytePolicy,
    FIFOPolicy,
    LRUPolicy,
    UtilityPolicy,
    RandomPolicy,
    ImportancePolicy,
    DiversityPolicy,
)
from reckon.measured_retention import MeasuredRetentionPolicy, RetentionProbeConfig
from reckon.tasks import BaseTask, BanditTask, ContinualTask, KeyDoorTask, TutorTask
from reckon.tasks.task_b_bandit import BanditConfig
from reckon.tasks.task_c_continual import ContinualConfig
from reckon.tasks.task_d_tutor import TutorConfig

TASKS: dict[str, type[BaseTask]] = {
    "keydoor": KeyDoorTask,
    "bandit": BanditTask,
    "continual": ContinualTask,
    "tutor": TutorTask,
}
POLICIES = {
    "none": FIFOPolicy,
    "full": FIFOPolicy,
    "fifo": FIFOPolicy,
    "lru": LRUPolicy,
    "utility": UtilityPolicy,
    "evidence_per_byte": EvidencePerBytePolicy,
    "random": RandomPolicy,
    "importance": ImportancePolicy,
    "diversity": DiversityPolicy,
}
POLICY_NAMES = (*POLICIES, "measured")
METRICS = {
    "keydoor": "success_rate",
    "bandit": "mean_return",
    "continual": "mean_accuracy",
    "tutor": "mean_return",
}


# SafeLoader supplies the inherited YAML constructors and resolvers.
class _ConfigLoader(yaml.SafeLoader):  # pylint: disable=too-many-ancestors
    """Keep repeated keys from silently changing an experiment."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ValueError("Configuration keys must be strings")
            if key in result:
                raise ValueError(f"Repeated configuration key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _mapping(value: Any, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a mapping with string keys")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"Unsupported {label} fields: {', '.join(sorted(unknown))}")
    return value


# These fields are the public record shape, rather than independent object responsibilities.
@dataclass
class Experiment:  # pylint: disable=too-many-instance-attributes
    """Task, resource and sampling choices for one reproducible run."""

    task: str = "keydoor"
    environment: dict = field(default_factory=dict)
    budget_slots: int = 10
    budget_bytes: int | None = None
    policy: str = "fifo"
    evidence_weight: float = 0.5
    episodes: int = 10
    seed: int = 42
    reset_memory: bool = False
    learn_utility: bool = True
    retention_probe: RetentionProbeConfig | None = None

    def make_task(self) -> BaseTask:
        """Validate the environment fields and construct the selected task."""
        if self.task == "keydoor":
            _mapping(self.environment, set(), "keydoor environment")
            return KeyDoorTask()
        config_types = {"bandit": BanditConfig, "continual": ContinualConfig, "tutor": TutorConfig}
        if self.task not in config_types:
            raise ValueError(f"Unknown task: {self.task}")
        config_type = config_types[self.task]
        _mapping(self.environment, {item.name for item in fields(config_type)}, "environment")
        defaults = asdict(config_type())
        for key, value in self.environment.items():
            expected = type(defaults[key])
            # isinstance would admit booleans and integer subclasses here.
            # pylint: disable-next=unidiomatic-typecheck
            if expected is int and (type(value) is not int or value < 1):
                raise ValueError(f"environment.{key} must be a positive integer")
            if expected is float and (
                type(value) not in (int, float) or not math.isfinite(value) or value < 0
            ):
                raise ValueError(f"environment.{key} must be a non-negative number")
            if ("probability" in key or "fraction" in key) and not 0 <= value <= 1:
                raise ValueError(f"environment.{key} must be between zero and one")
        if self.task == "bandit":
            config = BanditConfig(**self.environment)
            if config.num_modes < 2:
                raise ValueError("bandit needs at least two modes")
            return BanditTask(config)
        if self.task == "continual":
            config = ContinualConfig(**self.environment)
            if config.feature_dim != 2:
                raise ValueError("continual uses a fixed two-dimensional sample generator")
            return ContinualTask(config)
        return TutorTask(TutorConfig(**self.environment))

    def validate(self) -> None:
        """Refuse unsupported policies, invalid budgets and incomplete probe setup."""
        if self.policy not in POLICY_NAMES:
            raise ValueError(f"Unknown retention policy: {self.policy}")
        for name in ("budget_slots", "episodes"):
            # Exact built-ins keep boolean and subclass coercions out of declared configuration.
            # pylint: disable-next=unidiomatic-typecheck
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        # Exact built-ins keep boolean and subclass coercions out of declared configuration.
        # pylint: disable-next=unidiomatic-typecheck
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if self.budget_bytes is not None and (
            # Exact built-ins keep boolean and subclass coercions out of declared configuration.
            # pylint: disable-next=unidiomatic-typecheck
            type(self.budget_bytes) is not int
            or self.budget_bytes < 1
        ):
            raise ValueError("budget_bytes must be a positive integer")
        if type(self.evidence_weight) not in (int, float) or not 0 <= self.evidence_weight <= 1:
            raise ValueError("evidence_weight must be between zero and one")
        # Exact built-ins keep boolean and subclass coercions out of declared configuration.
        # pylint: disable-next=unidiomatic-typecheck
        if type(self.reset_memory) is not bool or type(self.learn_utility) is not bool:
            raise ValueError("reset_memory and learn_utility must be booleans")
        if self.policy == "measured" and self.retention_probe is None:
            raise ValueError(
                "Measured retention requires an explicit retention_probe configuration"
            )
        if self.retention_probe is not None:
            self.retention_probe.validate()
            if self.retention_probe.reference_policy not in set(POLICIES) - {"none", "full"}:
                raise ValueError("Probe reference_policy must be a non-probing retention policy")
        self.make_task()


def load_experiment(path: str) -> Experiment:
    """Load the same supported settings from YAML or JSON; refuse unused fields."""
    try:
        loaded = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_ConfigLoader)
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid experiment configuration: {error}") from error
    data = _mapping(
        loaded,
        {
            "task",
            "description",
            "environment",
            "budget",
            "retention_policy",
            "evidence_weight",
            "experiment",
            "retention_probe",
        },
        "configuration",
    )
    budget = _mapping(data.get("budget", {}), {"max_slots", "max_bytes"}, "budget")
    run = _mapping(
        data.get("experiment", {}),
        {"seed", "num_episodes", "reset_memory", "learn_utility"},
        "experiment",
    )
    result = Experiment(
        task=data.get("task", "keydoor"),
        environment=data.get("environment", {}),
        budget_slots=budget.get("max_slots", 10),
        budget_bytes=budget.get("max_bytes"),
        policy=data.get("retention_policy", "fifo"),
        evidence_weight=data.get("evidence_weight", 0.5),
        episodes=run.get("num_episodes", 10),
        seed=run.get("seed", 42),
        reset_memory=run.get("reset_memory", False),
        learn_utility=run.get("learn_utility", True),
        retention_probe=(
            RetentionProbeConfig.from_dict(data["retention_probe"])
            if "retention_probe" in data
            else None
        ),
    )
    result.validate()
    return result


class _MeasuredMemory(CausalMemoryManager):
    """Track storage after every successful write, across optional episode resets."""

    def __init__(self, budget, policy, *, discard_writes=False):
        super().__init__(budget, policy)
        self.peak_bytes = 0
        self.peak_slots = 0
        self.writes = 0
        self.policy_prunes = 0
        self.discard_writes = discard_writes
        self.baseline_discards = 0

    def write(self, *args, **kwargs):
        before = self.current_usage_slots
        record_id = super().write(*args, **kwargs)
        self.writes += 1
        self.policy_prunes += before + 1 - self.current_usage_slots
        self.peak_bytes = max(self.peak_bytes, self.current_usage_bytes)
        self.peak_slots = max(self.peak_slots, self.current_usage_slots)
        if self.discard_writes:
            self.prune(record_id, reason="no_memory_baseline")
            self.baseline_discards += 1
        return record_id


def _full_capacity(config: Experiment) -> int:
    """Bound all possible writes in these built-in runners, without huge reservation."""
    if config.task == "keydoor":
        per_episode = 1
    elif config.task == "bandit":
        per_episode = 200
    elif config.task == "continual":
        task = ContinualConfig(**config.environment)
        per_episode = task.num_tasks * task.samples_per_task
    else:
        task = TutorConfig(**config.environment)
        per_episode = task.num_sessions * task.questions_per_session
    return config.episodes * per_episode


def _policy(name: str, seed: int, evidence_weight: float):
    if name == "evidence_per_byte":
        return EvidencePerBytePolicy(evidence_weight)
    if name == "random":
        return RandomPolicy(seed)
    return POLICIES[name]()


def run_experiment(config: Experiment) -> dict:
    """Run exactly the declared settings and return outcomes with measured costs."""
    config.validate()
    policy = _policy(
        "fifo" if config.policy == "measured" else config.policy,
        config.seed,
        config.evidence_weight,
    )
    budget = MemoryBudget(max_slots=config.budget_slots, max_bytes=config.budget_bytes)
    if config.policy == "none":
        budget = MemoryBudget(max_slots=1)
    elif config.policy == "full":
        budget = MemoryBudget(max_slots=_full_capacity(config))
    memory = _MeasuredMemory(
        budget,
        policy,
        discard_writes=config.policy == "none",
    )
    measured = None
    if config.policy == "measured":
        assert config.retention_probe is not None
        reference_name = config.retention_probe.reference_policy

        def reference_factory():
            return _policy(reference_name, config.seed, config.evidence_weight)

        measured = MeasuredRetentionPolicy(
            config.retention_probe,
            lambda: memory.fork_for_trial(reference_factory()),
            config.make_task,
            reference_factory,
            METRICS[config.task],
            config.seed,
            config.learn_utility,
            config.evidence_weight,
        )
        memory.retention_policy = measured
    task = config.make_task()
    start = perf_counter()
    result = task.run(
        memory,
        config.episodes,
        config.seed,
        reset_memory=config.reset_memory,
        learn_utility=config.learn_utility,
    )
    elapsed = perf_counter() - start
    if config.policy == "full" and memory.policy_prunes:
        raise RuntimeError("Full-memory capacity did not cover this task's writes")
    configuration = asdict(config)
    configuration["retention_probe"] = (
        config.retention_probe.to_dict() if config.retention_probe else None
    )
    probe_elapsed = measured.elapsed_s if measured else 0.0
    probe_episodes = measured.episodes if measured else 0
    return {
        "configuration": configuration,
        "effective_budget": asdict(budget),
        "result": result.to_dict(),
        "usage": {
            "peak_bytes": memory.peak_bytes,
            "peak_slots": memory.peak_slots,
            "final_bytes": memory.current_usage_bytes,
            "final_slots": memory.current_usage_slots,
            "writes": memory.writes,
            "policy_prunes": memory.policy_prunes,
            "baseline_discards": memory.baseline_discards,
            "elapsed_s": elapsed,
            "task_elapsed_s": elapsed - probe_elapsed,
            "task_episodes": config.episodes,
            "probe_episodes": probe_episodes,
            "total_episodes": config.episodes + probe_episodes,
            "probe_elapsed_s": probe_elapsed,
        },
        "score_source": "learned_utility" if config.learn_utility else "fixed_initial_utility",
        "retention_score_source": (
            "measured_warm_memory_ablation_per_byte"
            if measured
            else (
                "explicit_importance_per_byte"
                if config.policy == "importance"
                else (
                    "utility_without_measured_effects"
                    if config.policy in ("utility", "evidence_per_byte", "diversity")
                    else "no_score"
                )
            )
        ),
        "measured_retention_effects": bool(measured and measured.batches),
        "retention_probes": measured.batches if measured else [],
    }


def compare_experiments(
    configs: list[Experiment], policies: list[str], budgets: list[int], seeds: list[int]
) -> dict:
    """Run a full matrix; preserve each seed rather than reporting only a mean."""
    if not configs or not policies or not budgets or not seeds:
        raise ValueError("Comparison needs tasks, policies, budgets and seeds")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Comparison seeds must be distinct")
    rows = []
    for config in configs:
        for policy in policies:
            for slots in (budgets[:1] if policy in ("none", "full") else budgets):
                runs = [
                    run_experiment(replace(config, policy=policy, budget_slots=slots, seed=seed))
                    for seed in seeds
                ]
                metric = METRICS[config.task]
                values = [run["result"]["performance"][metric] for run in runs]
                rows.append(
                    {
                        "task": config.task,
                        "policy": policy,
                        "budget_slots": None if policy in ("none", "full") else slots,
                        "budget_bytes": None if policy in ("none", "full") else config.budget_bytes,
                        "learn_utility": config.learn_utility,
                        "reset_memory": config.reset_memory,
                        "metric": metric,
                        "mean": mean(values),
                        "stdev": stdev(values) if len(values) > 1 else None,
                        "min": min(values),
                        "max": max(values),
                        "mean_peak_bytes": mean(run["usage"]["peak_bytes"] for run in runs),
                        "mean_peak_slots": mean(run["usage"]["peak_slots"] for run in runs),
                        "elapsed_s": sum(run["usage"]["elapsed_s"] for run in runs),
                        "task_episodes": sum(run["usage"]["task_episodes"] for run in runs),
                        "probe_episodes": sum(run["usage"]["probe_episodes"] for run in runs),
                        "probe_elapsed_s": sum(run["usage"]["probe_elapsed_s"] for run in runs),
                        "total_episodes": sum(run["usage"]["total_episodes"] for run in runs),
                        "runs": runs,
                    }
                )
    return {"rows": rows, "seeds": seeds, "spread": "sample standard deviation across seeds"}
