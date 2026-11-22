"""Built-in tasks learn from the records they actually retrieve."""

import json
from copy import deepcopy

import pytest
import numpy as np

from reckon.core.episode_context import get_current_context
from reckon.core.resources import MemoryBudget
from reckon.experiments import Experiment, run_experiment
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.record import PayloadType
from reckon.tasks import BanditTask, ContinualTask, KeyDoorTask, TutorTask
from reckon.tasks.task_a_keydoor import KeyDoorGridworld
from reckon.tasks.task_b_bandit import BanditConfig, HiddenModeBandit
from reckon.tasks.task_c_continual import ContinualConfig, ContinualClassificationTask
from reckon.tasks.task_d_tutor import TutorConfig, TutorEnvironment


@pytest.mark.parametrize("seed", [7, 42])
def test_bandit_policy_keeps_modes_indicators_and_reward_noise_paired(monkeypatch, seed):
    traces = []
    original_step = HiddenModeBandit.step

    def trace_pull(bandit, arm):
        reward, indicator = original_step(bandit, arm)
        # A small noise scale keeps these fixtures away from clipping, so the
        # exogenous reward shock can be recovered separately from arm quality.
        assert 0 < reward < 1
        traces[-1].append(
            (
                bandit.step_count,
                int(bandit.current_mode),
                indicator,
                round(reward - bandit.mean_rewards[bandit.current_mode, arm], 12),
            )
        )
        return reward, indicator

    monkeypatch.setattr(HiddenModeBandit, "step", trace_pull)
    returns = []
    for policy in ("none", "full"):
        traces.append([])
        report = run_experiment(
            Experiment(
                task="bandit",
                policy=policy,
                episodes=3,
                seed=seed,
                environment={"reward_std": 0.001},
            )
        )
        returns.append(report["result"]["performance"]["mean_return"])
    assert len(traces[0]) == len(traces[1]) == 600
    assert traces[0] == traces[1]
    assert returns[0] != returns[1]


def test_tutor_pairs_starting_students_and_question_response_draws(monkeypatch):
    traces = []
    original_init = TutorEnvironment.__init__
    original_question = TutorEnvironment.ask_question
    original_hint = TutorEnvironment.give_hint

    def init_student(env, config, rng):
        original_init(env, config, rng)
        traces[-1].append({"initial": dict(env.student.misconceptions), "question": 0, "draws": {}})

    def ask_question(env, concept):
        traces[-1][-1]["question"] += 1
        return original_question(env, concept)

    def give_hint(env, concept, hint, was_effective=False):
        episode = traces[-1][-1]
        # Observe the next response draw without consuming the live stream.
        episode["draws"][episode["question"]] = deepcopy(env.rng).random()
        return original_hint(env, concept, hint, was_effective)

    monkeypatch.setattr(TutorEnvironment, "__init__", init_student)
    monkeypatch.setattr(TutorEnvironment, "ask_question", ask_question)
    monkeypatch.setattr(TutorEnvironment, "give_hint", give_hint)
    for policy in ("none", "full"):
        traces.append([])
        run_experiment(
            Experiment(
                task="tutor",
                policy=policy,
                episodes=5,
                seed=42,
                environment={
                    "num_concepts": 6,
                    "num_sessions": 1,
                    "questions_per_session": 6,
                    "misconception_probability": 0.5,
                    "hint_success_probability": 0.3,
                    "hint_effectiveness_boost": 0.2,
                },
            )
        )
    assert len(traces[0]) == len(traces[1]) == 5
    shared_responses = 0
    for baseline, remembered in zip(*traces):
        assert baseline["initial"] == remembered["initial"]
        for question in baseline["draws"].keys() & remembered["draws"].keys():
            assert baseline["draws"][question] == remembered["draws"][question]
            shared_responses += 1
    assert shared_responses >= 10


@pytest.mark.parametrize("seed", [7, 42])
def test_continual_pairs_data_and_replay_opportunities_across_memory_policies(monkeypatch, seed):
    datasets, queries = [], []
    original_init = ContinualClassificationTask.__init__
    original_retrieve = CausalMemoryManager.retrieve

    def create_dataset(env, config, rng):
        original_init(env, config, rng)
        datasets[-1].append(
            [
                [[(x.tolist(), int(y)) for x, y in task] for task in split]
                for split in (env.train_data, env.test_data)
            ]
        )

    def query(memory, *args, **kwargs):
        # Query timing includes misses, so differing retention cannot hide a draw.
        queries[-1].append((memory.episode_id, memory._current_step))
        return original_retrieve(memory, *args, **kwargs)

    monkeypatch.setattr(ContinualClassificationTask, "__init__", create_dataset)
    monkeypatch.setattr(CausalMemoryManager, "retrieve", query)
    outcomes = []
    for policy in ("none", "full", "utility"):
        datasets.append([])
        queries.append([])
        outcomes.append(
            run_experiment(
                Experiment(
                    task="continual",
                    policy=policy,
                    budget_slots=2,
                    episodes=3,
                    seed=seed,
                    environment={"num_tasks": 3, "samples_per_task": 40},
                )
            )
        )
    assert len(datasets[0]) == 3
    assert datasets[0] == datasets[1] == datasets[2]
    assert queries[0] and queries[0] == queries[1] == queries[2]
    assert outcomes[0]["usage"]["final_slots"] == 0
    assert outcomes[1]["usage"]["final_slots"] > 2


@pytest.mark.parametrize("reset_memory", [False, True])
def test_continual_can_read_carried_memory_before_a_new_write(monkeypatch, reset_memory):
    def fixed_dataset(env, config, rng):
        # The ordinary update learns this sample correctly, so no new record
        # is written. A retained example must still be eligible for replay.
        env.train_data = [[(np.array([0.0, 1.0]), 1)]]
        env.test_data = [[(np.array([0.0, 1.0]), 1)]]

    monkeypatch.setattr(ContinualClassificationTask, "__init__", fixed_dataset)
    memory = CausalMemoryManager(MemoryBudget(max_slots=2))
    marker = memory.write(
        {"x": [0.0, 1.0], "y": 1, "task": 0}, PayloadType.REPRESENTATION, tags=["replay_sample"]
    )
    reads = []
    with memory.before_read(lambda records: reads.extend(r.id for r in records)):
        result = ContinualTask(ContinualConfig(num_tasks=1, replay_fraction=1)).run(
            memory, 1, 42, reset_memory=reset_memory
        )
    assert result.raw_data["episodes"][0]["total_writes"] == 0
    assert reads == ([] if reset_memory else [marker])


@pytest.mark.parametrize("column", [0, 2, 4])
@pytest.mark.parametrize("row,action", [(2, 1), (4, 0)])
def test_keydoor_wall_has_no_route_around_the_doors(column, row, action):
    env = KeyDoorGridworld(np.random.default_rng(42))
    env.state.agent_pos = (row, column)
    env.step(action)
    assert env.state.agent_pos == (row, column)
    assert not env.state.door_reached


@pytest.mark.parametrize("correct_door", [(3, 1), (3, 3)])
def test_keydoor_only_the_open_door_allows_crossing(correct_door):
    env = KeyDoorGridworld(np.random.default_rng(42))
    env.correct_door = correct_door
    for column in [1, 3]:
        env.state.agent_pos = (2, column)
        env.state.door_reached = False
        env.step(1)
        opened = (3, column) == correct_door
        assert env.state.agent_pos == ((3, column) if opened else (2, column))
        assert env.state.door_reached == opened


@pytest.fixture(params=["keydoor", "bandit", "continual", "tutor"])
def task(request):
    return {
        "keydoor": KeyDoorTask(),
        "bandit": BanditTask(),
        "continual": ContinualTask(
            ContinualConfig(num_tasks=3, samples_per_task=40, replay_fraction=1)
        ),
        "tutor": TutorTask(
            TutorConfig(
                num_concepts=2,
                num_sessions=2,
                questions_per_session=10,
                misconception_probability=1,
            )
        ),
    }[request.param]


def test_each_task_connects_retrieval_to_observation(task):
    memory = CausalMemoryManager(MemoryBudget(max_slots=16))
    result = task.run(memory, num_episodes=3, seed=42)
    events = memory.get_event_log()
    updates = [e for e in events if e["op_type"] == "update_score"]
    assert updates
    assert {json.loads(e["details"])["signal_source"] for e in updates} == {"observe:simple"}
    assert len({e["episode_id"] for e in events}) == 3
    assert result.raw_data["reset_memory"] is False
    assert result.raw_data["learn_utility"] is True
    assert get_current_context() is None


@pytest.mark.parametrize("reset_memory", [False, True])
def test_each_task_declares_carry_and_can_disable_learning(task, reset_memory):
    memory = CausalMemoryManager(MemoryBudget(max_slots=1000))
    marker = memory.write("prior episode", PayloadType.CUE)
    result = task.run(memory, 2, 42, reset_memory=reset_memory, learn_utility=False)
    assert (memory.get_record(marker) is None) == reset_memory
    assert not any(e["op_type"] == "update_score" for e in memory.get_event_log())
    assert result.raw_data["reset_memory"] == reset_memory
    assert result.raw_data["learn_utility"] is False


def test_bandit_reports_its_own_prunes_separately():
    memory = CausalMemoryManager(MemoryBudget(max_slots=1000))
    result = BanditTask().run(memory, 1, 42)
    events = memory.get_event_log()
    task_prunes = [e for e in events if e["op_type"] == "prune"]
    assert len(task_prunes) == result.raw_data["episodes"][0]["task_prunes"]
    assert task_prunes
    assert {json.loads(e["details"])["reason"] for e in task_prunes} <= {
        "mode_switch",
        "newer_indicator",
    }


def test_bandit_uses_new_mode_indicator_on_the_next_decision(monkeypatch):
    memory = CausalMemoryManager(MemoryBudget(max_slots=16))
    config = BanditConfig(mode_switch_interval=2, indicator_probability=1)
    decisions = []
    original_step = HiddenModeBandit.step

    def trace_decision(bandit, arm):
        context = get_current_context()
        assert context is not None
        records = [memory.get_record(rid) for rid in context.retrieved_record_ids]
        decisions.append((bandit.step_count + 1, arm, records))
        return original_step(bandit, arm)

    monkeypatch.setattr(HiddenModeBandit, "step", trace_decision)
    result = BanditTask(config).run(memory, 1, 42)
    events = memory.get_event_log()

    for pull, arm, records in decisions[2::2]:
        # Pulls 3, 5, ... must use the indicator emitted during the preceding switch.
        assert len(records) == 1
        record = records[0]
        assert record.payload["step"] == pull - 1
        assert arm == record.payload["mode_hint"] % config.num_arms

    credits = [event["record_id"] for event in events if event["op_type"] == "update_score"]
    assert credits == [records[0].id for _, _, records in decisions[1:]]

    assert result.raw_data["episodes"][0]["mode_switches"] == 100
    assert result.raw_data["mean_detection_lag"] == 1
