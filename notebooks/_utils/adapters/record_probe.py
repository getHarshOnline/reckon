"""Matched episode ablations for notebook controllers, with both arms charged.

The experiment removes one logical record at its first eligible read. Each
seed starts a fresh episode; this does not score a live store for retention.
Model backends and prerecorded game fallbacks cannot supply paired evidence.
"""

from dataclasses import dataclass
from copy import deepcopy
from queue import Empty
from time import perf_counter

from reckon.core.resources import MemoryBudget
from reckon.measured_retention import MeasuredRetentionPolicy
from reckon.memory import CausalMemoryManager, FIFOPolicy
from reckon.metrics import MemoryEfficiencyMetrics, PerformanceMetrics
from reckon.metrics.evaluator import CausalRecordEvaluator
from reckon.metrics.tests.paired import paired_inference
from reckon.tasks.base import BaseTask, TaskResult


@dataclass(frozen=True)
class AdapterProbeConfig:
    """Declare one controller, its memory allowance and its episode length."""

    adapter: str
    budget_slots: int = 100
    max_steps: int = 8

    def __post_init__(self):
        if self.adapter not in {"conversation", "minigrid", "textworld"}:
            raise ValueError("Unknown notebook probe adapter")
        if any(
            type(value) is not int or value < 1 for value in (self.budget_slots, self.max_steps)
        ):
            raise ValueError("Budget and episode length must be positive integers")

    def memory_budget(self):
        """Match the selected adapter's byte and slot allowances."""
        return MemoryBudget(
            max_slots=self.budget_slots,
            max_bytes=None if self.adapter == "textworld" else self.budget_slots * 500,
        )


class AdapterProbeTask(BaseTask):
    """Present a notebook controller through the native evaluation interface."""

    def __init__(self, config, executions):
        self.config = config
        self.executions = executions

    @property
    def name(self):
        return self.config.adapter

    @property
    def description(self):
        return "Remove one retained record at the first matching read"

    def run(self, cmm, num_episodes, seed, *, reset_memory=False, learn_utility=True):
        if num_episodes != 1 or reset_memory or not learn_utility:
            raise ValueError("Adapter probes run one fresh episode with outcome learning")
        started = perf_counter()
        with cmm.subscribe_events() as events:
            result, metric = self._run_episode(cmm, seed)
        if result.get("demo_mode") or result.get("fallback_count", 0):
            raise RuntimeError("Fallback episodes cannot supply paired adapter evidence")
        usage = dict(writes=0, prunes=0, peak_slots=0, peak_bytes=0)
        slots = 0
        while True:
            try:
                _, event = events.get_nowait()
            except Empty:
                break
            if event["op_type"] == "write":
                usage["writes"] += 1
                slots += 1
            elif event["op_type"] == "prune":
                usage["prunes"] += 1
                slots -= 1
            usage["peak_slots"] = max(usage["peak_slots"], slots)
            usage["peak_bytes"] = max(usage["peak_bytes"], event["bytes_after"])
        self.executions.append(
            {
                "seed": seed,
                "elapsed_s": perf_counter() - started,
                "metric": metric,
                "usage": usage,
                "result": result,
            }
        )
        return TaskResult(
            performance=PerformanceMetrics(mean_return=metric),
            memory=MemoryEfficiencyMetrics(),
            diagnostics={},
            raw_data=result,
        )

    def _run_episode(self, cmm, seed):
        settings = dict(
            seed=seed,
            policy=cmm.retention_policy,
            budget_slots=self.config.budget_slots,
            memory=cmm,
        )
        if self.config.adapter == "conversation":
            from .conversation import run_conversation_episode

            result = run_conversation_episode(**settings, n_steps=self.config.max_steps)
            metric = float(result["constraint_retention"])
        elif self.config.adapter == "minigrid":
            from .memory_maze import run_memory_maze

            result = run_memory_maze(**settings, max_steps=self.config.max_steps)
            metric = float(result["success"])
        else:
            from .text_game import run_textworld_episode
            from .textworld_adapter import check_available

            if not check_available():
                raise RuntimeError("TextWorld probes require the actual game dependency")
            result = run_textworld_episode(**settings, max_steps=self.config.max_steps)
            metric = float(result["total_reward"])
        return result, metric


def evaluate_adapter_record(
    config,
    record_label,
    record_selector,
    *,
    policy_factory=FIFOPolicy,
    n_trials=10,
    seed_base=42,
    delta_threshold=0.05,
    alpha=0.05,
):
    """Evaluate a unique logical target and retain outcomes, reads and costs.

    Factories must create fresh, non-probing policies. MeasuredRetentionPolicy
    is refused, including subclasses. Custom policies must not run additional
    episodes: this runner cannot count episodes hidden inside caller code.
    Missing or ambiguous targets fail;
    eviction before a read is not counted as a zero effect. Inference is paired
    across episode seeds, with no correction for testing multiple record labels.
    """
    executions = []
    policies = []
    started = perf_counter()

    def memory_factory():
        policy = policy_factory()
        if isinstance(policy, MeasuredRetentionPolicy):
            raise ValueError("Adapter probes require a non-probing reference policy")
        if any(policy is previous for previous in policies):
            raise ValueError("Each arm needs a fresh policy")
        policies.append(policy)
        return CausalMemoryManager(config.memory_budget(), policy)

    evaluator = CausalRecordEvaluator(
        lambda: AdapterProbeTask(config, executions),
        memory_factory,
        lambda result: result.performance.mean_return,
        n_trials=n_trials,
        seed_base=seed_base,
        delta_threshold=delta_threshold,
        alpha=alpha,
    )
    policy_config = dict(name=type(policies[0]).__name__, parameters=deepcopy(vars(policies[0])))
    evaluation = evaluator.evaluate_record(record_label, record_selector=record_selector)
    for baseline, intervention in zip(executions[::2], executions[1::2]):
        if baseline["result"].get("game_identity") != intervention["result"].get("game_identity"):
            raise ValueError("Paired TextWorld arms loaded different game bytes")
    differences = [
        trial["baseline_metric"] - trial["intervention_metric"] for trial in evaluation.trials
    ]
    _, interval = paired_inference(differences, "permutation", 10000, alpha, seed_base)
    if len(executions) != 2 * n_trials:
        raise RuntimeError("Probe episode accounting disagrees with executed arms")
    return {
        "protocol": "one_record_removed_at_first_eligible_read_in_fresh_paired_episodes",
        "config": vars(config),
        "reference_policy": policy_config,
        "episode_accounting": "adapter arms only; reference policies must not run nested episodes",
        "evaluation": evaluation.to_dict(),
        "confidence_interval": list(interval),
        "interval_method": "normal approximation of paired episode differences",
        "test_method": "paired sign permutation; up to 10000 draws",
        "alpha": alpha,
        "multiple_record_correction": "none",
        "probe_episodes": len(executions),
        "probe_elapsed_s": perf_counter() - started,
        "arms": executions,
    }
