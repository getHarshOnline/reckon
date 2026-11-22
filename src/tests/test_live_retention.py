"""Live pruning replays must preserve the controller prefix and charge all work."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "notebooks"))
from _utils.adapters.live_retention import (
    ReplayEpisode,
    ReplayPolicy,
    ReplayRetentionPolicy,
    run_replay_retention_episode,
)
from _utils.adapters.record_probe import AdapterProbeConfig
from _utils.adapters.replay_memory import ReplayMemory, digest
from _utils.adapters.text_game import run_textworld_episode
from _utils.adapters.textworld_adapter import TextworldAdapter
from reckon.core.episode_context import EpisodeContext
from reckon.core.resources import MemoryBudget
from reckon.memory import FIFOPolicy, PayloadType


class CueEpisode:
    """A deterministic controller where earlier useful prunes differ from FIFO."""

    config = SimpleNamespace(memory_budget=lambda: MemoryBudget(max_slots=2))

    def run(self, policy, memory):
        memory.set_episode("cue", reset_memory=False)
        context = EpisodeContext(episode_id="cue")
        memory.write("key", PayloadType.CUE, tags=["key"], initial_utility=2)
        memory.retrieve(query={"tags": ["key"]}, context=context)
        memory.write("filler", PayloadType.OBSERVATION)
        memory.set_step(1)
        memory.write("pending", PayloadType.OBSERVATION)
        memory.observe(0.5, context=context)
        memory.set_step(2)
        memory.write("next", PayloadType.OBSERVATION)
        outcome = float(bool(memory.retrieve(query={"tags": ["key"]})))
        return {"events": memory.get_event_log()}, outcome


@pytest.mark.parametrize(
    "actions,inventory,removed,expected_delta,next_step",
    [
        (["go east", "take apple from stand", "eat apple"], True, 3, 0, 1),
        (["take apple from stand", "eat apple"], True, 3, -1, 1),
        (["go east", "take apple from stand", "eat apple"], False, 2, -1, 2),
    ],
)
@pytest.mark.parametrize("selection_rule", ["retention-score", "improving-removal"])
def test_description_competition_separates_next_read_from_fifo_final_score(
    actions, inventory, removed, expected_delta, next_step, selection_rule, monkeypatch
):
    """Synthetic controls for the 64000/64003/64004 mechanisms, not game replays."""
    class ProgressAdapter(TextworldAdapter):
        def __init__(self, config):
            self.config = config
            self.progress = 0

        def info(self):
            return {
                "admissible_commands": ["drop pebble", "examine lamp", *actions[self.progress:self.progress + 1]],
                "inventory": "You are carrying: a pebble." if inventory else "",
                "won": self.progress == len(actions),
            }

        def reset(self):
            return "First, " + ". Then, ".join(actions) + ".\n\n-= Room =-", self.info()

        def step(self, command):
            if command == actions[self.progress]:
                self.progress += 1
            won = self.progress == len(actions)
            return "You acted.\n\n", float(won), won, self.info()

        def close(self):
            pass

    class ProgressEpisode:
        config = SimpleNamespace(memory_budget=lambda: MemoryBudget(max_slots=4))
        game_identity = None

        def run(self, policy, memory):
            result = run_textworld_episode(
                0, 4, max_steps=len(actions), policy=policy,
                adapter_factory=ProgressAdapter, memory=memory,
            )
            return result, result["total_reward"]

    episode = ProgressEpisode()
    monkeypatch.setattr("_utils.adapters.live_retention.ReplayEpisode", lambda *args: episode)
    report = run_replay_retention_episode(
        AdapterProbeConfig("textworld", budget_slots=4, max_steps=len(actions)),
        0, selection_rule=selection_rule,
    )
    assert report["selection_rule"] == report["result"]["selection_rule"] == selection_rule
    first = report["batches"][0]
    assert first["boundary"]["write_ordinal"] == 4
    improved = selection_rule == "improving-removal" and expected_delta < 0
    # The two-action fixture has equal improving outcomes for inventory 1 and
    # description 3. The opt-in rule chooses the earlier admission, not utility.
    assert first["selected_ordinals"] == ([1 if inventory else 2] if improved else [0])
    assert report["outcome"] == float(improved)
    evidence = next(item for item in first["evidence"] if item["record_ordinal"] == removed)
    baseline, intervention = evidence["arms"]
    assert evidence["delta"] == expected_delta
    assert baseline["outcome"] == 0
    assert intervention["selected_ordinals"] == [removed]
    baseline_turn = baseline["result"]["transcript"][next_step]
    turns = intervention["result"]["transcript"]
    assert baseline_turn["command"] == "drop pebble"
    assert not any("First," in item.get("description", "") for item in baseline_turn["memory_context"])
    assert turns[next_step]["command"] == actions[next_step]
    assert any("First," in item.get("description", "") for item in turns[next_step]["memory_context"])
    assert {item["command"] for item in turns[next_step]["memory_context"] if "command" in item} >= set(actions[:next_step])
    if expected_delta == 0:
        assert turns[2]["command"] == "drop pebble"
        assert not any("First," in item.get("description", "") for item in turns[2]["memory_context"])
    else:
        assert intervention["outcome"] == 1
        assert len(turns) == len(actions)
    assert intervention["result"]["environment"] == "integration_fixture"


@pytest.mark.parametrize("overflow", [(1, 1, 0), (0, 2, 0), (0, 1, 1)])
def test_improving_removal_refuses_joint_pressure_before_probes(overflow):
    policy = ReplayRetentionPolicy(None, selection_rule="improving-removal")
    with pytest.raises(ValueError, match="exactly one slot"):
        policy.select_for_pruning([], *overflow)
    assert policy.batches == []


def test_improving_removal_refuses_inconsistent_baselines_without_pruning_main_memory():
    class DriftingEpisode(CueEpisode):
        baseline_calls = 0

        def run(self, policy, memory):
            result, outcome = super().run(policy, memory)
            if isinstance(policy, ReplayPolicy) and policy.removed_ordinal is None:
                self.baseline_calls += 1
                outcome = float(self.baseline_calls)
            return result, outcome

    episode = DriftingEpisode()
    policy = ReplayRetentionPolicy(episode, selection_rule="improving-removal")
    memory = ReplayMemory(episode.config.memory_budget(), policy)
    policy.memory = memory
    with pytest.raises(RuntimeError, match="baseline outcomes differ"):
        episode.run(policy, memory)
    assert policy.batches == []
    assert memory.current_usage_slots == 2
    assert not any(event["op_type"] == "prune" for event in memory.get_event_log())


def test_replay_keeps_non_fifo_prefix_context_and_actual_main_memory():
    episode = CueEpisode()
    policy = ReplayRetentionPolicy(episode)
    memory = ReplayMemory(episode.config.memory_budget(), policy)
    policy.memory = memory
    _, outcome = episode.run(policy, memory)
    assert outcome == 1
    assert len(policy.batches) == 2
    assert policy.batches[0]["selected_ordinals"] == [1]  # FIFO would remove cue 0.
    assert policy.batches[1]["boundary"]["records"][0]["id"] == 0
    assert policy.batches[1]["boundary"]["records"][0]["utility"]["value"] != 2
    assert len(memory.ordinals) == 4  # Probe admissions never enter the main store.
    for batch in policy.batches:
        assert batch["probe_episodes"] == 4
        for evidence in batch["evidence"]:
            baseline, intervention = evidence["arms"]
            assert evidence["delta"] == baseline["outcome"] - intervention["outcome"]
            assert evidence["record_ordinal"] in intervention["selected_ordinals"]
            target = intervention["record_ids"][str(evidence["record_ordinal"])]
            assert any(
                event["op_type"] == "prune" and event["record_id"] == target
                for event in intervention["result"]["events"]
            )
            count = batch["boundary"]["journal_length"]
            for arm in evidence["arms"]:
                assert digest(arm["journal"][:count]) == batch["boundary"]["journal_sha256"]
                assert any(event["op_type"] == "prune" for event in arm["result"]["events"])
    # At the second decision, all probe arms must have replayed removal of 1,
    # even though their continuation reference would otherwise remove 0 first.
    for evidence in policy.batches[1]["evidence"]:
        for arm in evidence["arms"]:
            earlier_read = next(row for row in arm["journal"] if "retrieved" in row)
            assert earlier_read["retrieved"][0]["id"] == 0


def test_replay_refuses_changed_prefix_even_with_the_same_number_of_records():
    captured = []

    class CapturePolicy(FIFOPolicy):
        def select_for_pruning(self, records, overflow_bytes, overflow_slots=0, overflow_tokens=0):
            captured.append(
                reference.boundary(records, (overflow_bytes, overflow_slots, overflow_tokens))
            )
            return super().select_for_pruning(
                records, overflow_bytes, overflow_slots, overflow_tokens
            )

    reference = ReplayMemory(MemoryBudget(max_slots=1), CapturePolicy())
    reference.write("original", PayloadType.CUE)
    reference.write("pending", PayloadType.OBSERVATION)
    replay = ReplayPolicy([], captured[0], None)
    changed = ReplayMemory(MemoryBudget(max_slots=1), replay)
    replay.memory = changed
    changed.write("different", PayloadType.CUE)
    with pytest.raises(RuntimeError, match="prefix or pruning state"):
        changed.write("pending", PayloadType.OBSERVATION)

    replay = ReplayPolicy([], captured[0], None)
    matched = ReplayMemory(MemoryBudget(max_slots=1), replay)
    replay.memory = matched
    matched.write("original", PayloadType.CUE)
    matched.write("pending", PayloadType.OBSERVATION)
    assert replay.reached


def test_intervention_satisfies_remaining_byte_pressure_without_extra_removal():
    class InspectPolicy(FIFOPolicy):
        def select_for_pruning(self, records, overflow_bytes, overflow_slots=0, overflow_tokens=0):
            boundary = memory.boundary(records, (overflow_bytes, overflow_slots, overflow_tokens))
            replay = ReplayPolicy([], boundary, 0)
            replay.memory = memory
            return replay.select_for_pruning(
                records, overflow_bytes, overflow_slots, overflow_tokens
            )

    memory = ReplayMemory(MemoryBudget(max_slots=4, max_bytes=10), InspectPolicy())
    memory.write("a", PayloadType.CUE, cost_bytes=2)
    memory.write("b", PayloadType.CUE, cost_bytes=3)
    survivor = memory.write("c", PayloadType.CUE, cost_bytes=4)
    memory.write("pending", PayloadType.CUE, cost_bytes=5)
    assert memory.current_usage_bytes == 9
    assert memory.get_record(survivor) is not None
    assert memory.current_usage_slots == 2


@pytest.mark.parametrize("adapter,steps", [("conversation", 4), ("minigrid", 20)])
def test_existing_controllers_replay_without_nested_probes(adapter, steps):
    if adapter == "minigrid":
        pytest.importorskip("minigrid")
    result = run_replay_retention_episode(
        AdapterProbeConfig(adapter, budget_slots=2, max_steps=steps), 60001
    )
    count = sum(len(batch["evidence"]) * 2 for batch in result["batches"])
    assert result["probe_episodes"] == count > 0
    assert result["inclusive_elapsed_s"] >= result["probe_elapsed_s"] > 0
    assert result["probe_elapsed_s"] >= sum(
        arm["elapsed_s"]
        for batch in result["batches"]
        for evidence in batch["evidence"]
        for arm in evidence["arms"]
    )
    for batch in result["batches"]:
        for evidence in batch["evidence"]:
            for arm in evidence["arms"]:
                assert arm["result"]["policy"] == "ReplayPolicy"
                assert not arm["result"].get("demo_mode")
                assert not arm["result"].get("fallback_count")
    assert result["result"]["score_source"].startswith("measured_conditional")


def test_expired_context_is_not_silently_treated_as_no_credit():
    memory = ReplayMemory(MemoryBudget(max_slots=2), FIFOPolicy())
    context = EpisodeContext(created_at_ms=0)
    with pytest.raises(RuntimeError, match="context expired"):
        memory.observe(1, context=context)


def test_textworld_requires_live_dependency_and_pinned_game(monkeypatch, tmp_path):
    from _utils.adapters import textworld_adapter

    monkeypatch.setattr(textworld_adapter, "check_available", lambda: False)
    with pytest.raises(ValueError, match="explicit generated game"):
        ReplayEpisode(AdapterProbeConfig("textworld"), 60001, tmp_path / "game.z8")
    monkeypatch.setattr(textworld_adapter, "check_available", lambda: True)
    with pytest.raises(ValueError, match="explicit generated game"):
        ReplayEpisode(AdapterProbeConfig("textworld"), 60001)
    game = tmp_path / "game.z8"
    game.write_bytes(b"fixture, not a live game")
    game.with_suffix(".json").write_text("{}")
    episode = ReplayEpisode(AdapterProbeConfig("textworld"), 60001, game)
    game.write_bytes(b"changed fixture")
    with pytest.raises(RuntimeError, match="bytes changed before replay"):
        episode.run(FIFOPolicy(), None)


def test_real_textworld_replays_share_game_bytes_and_preserve_the_prefix(tmp_path):
    pytest.importorskip("textworld")
    from _utils.adapters.textworld_adapter import TextworldAdapter, TextworldConfig

    adapter = TextworldAdapter(TextworldConfig(seed=60001, game_dir=str(tmp_path)))
    try:
        adapter.make_env()
        game_file = adapter.game_file
    finally:
        adapter.close()
    result = run_replay_retention_episode(
        AdapterProbeConfig("textworld", budget_slots=2, max_steps=3),
        60001,
        game_file=game_file,
    )
    assert result["probe_episodes"] > 0
    assert result["result"]["environment"] == "textworld"
    for batch in result["batches"]:
        for evidence in batch["evidence"]:
            for arm in evidence["arms"]:
                assert arm["result"]["game_identity"] == result["game_identity"]
                count = batch["boundary"]["journal_length"]
                assert digest(arm["journal"][:count]) == batch["boundary"]["journal_sha256"]
                assert arm["result"]["environment"] == "textworld"
