"""Executed intervention checks, rather than differences between untouched runs."""

import json
from dataclasses import dataclass

import pytest

from reckon.core.episode_context import EpisodeContext
from reckon.core.resources import MemoryBudget
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.record import PayloadType
from reckon.metrics import (
    MemoryEfficiencyMetrics,
    PerformanceMetrics,
    CausalRecordEvaluator,
    InterventionMethod,
)
from reckon.tasks.base import BaseTask, TaskResult
from reckon.tasks import KeyDoorTask, BanditTask, ContinualTask, TutorTask
from reckon.tasks.task_c_continual import ContinualConfig
from reckon.tasks.task_d_tutor import TutorConfig


@dataclass
class CueConfig:
    effect: float = 1.0
    count: int = 1


class CueTask(BaseTask):
    name = "Cue decision"
    description = "Write after reset, then decide from the retained cue"

    def __init__(self, effect=1.0, count=1):
        self.config = CueConfig(effect, count)

    def run(self, cmm, num_episodes, seed, **kwargs):
        cmm.set_episode("trial", reset_memory=True)
        with EpisodeContext("trial"):
            for _ in range(self.config.count):
                cmm.write(self.config.effect, PayloadType.CUE, tags=["target"])
            records = cmm.retrieve(query={"tags": ["target"]})
            score = sum(record.payload for record in records)
            cmm.observe(score)
        return TaskResult(
            PerformanceMetrics(mean_return=score),
            MemoryEfficiencyMetrics(),
            {},
        )


def evaluator(task_factory=CueTask, cmm_factory=None, **kwargs):
    return CausalRecordEvaluator(
        task_factory,
        cmm_factory or (lambda: CausalMemoryManager(MemoryBudget(max_slots=16))),
        lambda result: result.performance.mean_return,
        **kwargs,
    )


def target(record):
    return "target" in record.tags


@pytest.mark.parametrize(
    "effect,useful", [(1, True), (-1, False), (0, False), (0.05, True), (0.049, False)]
)
def test_signed_effect_and_aggregate_usefulness(effect, useful):
    report = evaluator(lambda: CueTask(effect)).evaluate_all(
        ["cue"], ground_truth_ids={"cue"}, record_selectors={"cue": target}
    )
    result = report.evaluated_records[0]
    assert result.delta == pytest.approx(effect)
    assert result.is_useful == useful
    assert report.contract_precision == float(useful)
    assert report.contract_recall == float(useful)
    assert result.is_significant == (abs(effect) >= 0.05)
    for trial in result.trials:
        assert trial["baseline"]["record_id"] != trial["intervention"]["record_id"]
        assert trial["baseline"]["target_sha256"] == trial["intervention"]["target_sha256"]
        assert trial["baseline"]["removed"] is False
        assert trial["intervention"]["removed"] is True
    json.dumps(report.to_dict())


def test_task_created_cue_is_removed_before_read_and_credit():
    memories = []

    def factory():
        memory = CausalMemoryManager(MemoryBudget(max_slots=16))
        memories.append(memory)
        return memory

    result = evaluator(cmm_factory=factory, n_trials=2).evaluate_record(
        "cue", record_selector=target
    )
    assert result.delta == 1
    for memory, trial in zip(memories[3::2], result.trials):
        removed = trial["intervention"]["record_id"]
        events = memory.get_event_log()
        assert any(e["op_type"] == "prune" and e["record_id"] == removed for e in events)
        assert [json.loads(e["details"]) for e in events if e["op_type"] == "read"] == [[]]
        assert not any(e["op_type"] == "update_score" for e in events)
        assert memory.get_record(removed) is None


@pytest.mark.parametrize("method", [InterventionMethod.MASK, InterventionMethod.REPLACE])
def test_unsupported_method_fails_before_running_task(method):
    evaluation = evaluator()
    with pytest.raises(NotImplementedError):
        evaluation.evaluate_record("cue", method, record_selector=target)


def test_missing_and_ambiguous_targets_fail():
    with pytest.raises(ValueError, match="never reached"):
        evaluator(n_trials=2).evaluate_record("absent")
    with pytest.raises(ValueError, match="ambiguous"):
        evaluator(lambda: CueTask(count=2), n_trials=2).evaluate_record(
            "cue", record_selector=target
        )


def test_failed_prune_is_not_reported_as_ablation():
    class RefusesRemoval(CausalMemoryManager):
        def prune(self, record_id, reason="manual"):
            return False

    with pytest.raises(RuntimeError, match="did not remove"):
        evaluator(cmm_factory=lambda: RefusesRemoval(MemoryBudget()), n_trials=2).evaluate_record(
            "cue", record_selector=target
        )


def test_configuration_is_checked_after_construction():
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        return CausalMemoryManager(MemoryBudget(max_slots=16 if calls <= 2 else 17))

    with pytest.raises(ValueError, match="configuration"):
        evaluator(cmm_factory=factory, n_trials=2).evaluate_record("cue", record_selector=target)


def test_different_selected_payloads_fail_despite_matching_configuration():
    class DriftingCue(CueTask):
        occurrence = 0

        def run(self, *args, **kwargs):
            type(self).occurrence += 1
            self.config.effect = type(self).occurrence
            return super().run(*args, **kwargs)

    with pytest.raises(ValueError, match="different record states"):
        evaluator(DriftingCue, n_trials=2).evaluate_record("cue", record_selector=target)


@pytest.mark.parametrize("ground_truth", [None, set()])
def test_missing_ground_truth_leaves_recall_unavailable(ground_truth):
    report = evaluator(n_trials=2).evaluate_all(
        ["cue"], ground_truth_ids=ground_truth, record_selectors={"cue": target}
    )
    assert report.contract_recall is None


def test_read_intervention_refills_query_and_cleans_up_after_failure():
    memory = CausalMemoryManager(MemoryBudget(max_slots=4))
    first = memory.write(1, PayloadType.CUE, initial_utility=10)
    second = memory.write(2, PayloadType.CUE)
    with memory.before_read(lambda hits: memory.prune(first)):
        assert [r.id for r in memory.retrieve(limit=1)] == [second]

    def fail(hits):
        raise RuntimeError("stop trial")

    with pytest.raises(RuntimeError, match="stop trial"):
        with memory.before_read(fail):
            memory.retrieve()
    assert [r.id for r in memory.retrieve()] == [second]
    assert memory.get_record(second).utility.use_count == 2


@pytest.mark.parametrize(
    "task_factory,metric",
    [
        (KeyDoorTask, "success_rate"),
        (BanditTask, "mean_return"),
        (
            lambda: ContinualTask(
                ContinualConfig(num_tasks=3, samples_per_task=40, replay_fraction=1)
            ),
            "mean_accuracy",
        ),
        (
            lambda: TutorTask(
                TutorConfig(
                    num_concepts=2,
                    num_sessions=2,
                    questions_per_session=10,
                    misconception_probability=1,
                )
            ),
            "mean_return",
        ),
    ],
)
def test_builtin_tasks_reach_actual_intervention(task_factory, metric):
    evaluation = CausalRecordEvaluator(
        task_factory,
        lambda: CausalMemoryManager(MemoryBudget(max_slots=16)),
        lambda result: getattr(result.performance, metric),
        n_trials=2,
        num_episodes=2,
    )
    result = evaluation.evaluate_record(
        "first eligible record", record_selector=lambda record: True
    )
    assert len(result.trials) == 2
    assert all(trial["intervention"]["removed"] for trial in result.trials)
