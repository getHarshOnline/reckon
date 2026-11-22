"""Live MiniGrid checks for the declared memory-corridor controller."""

import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("minigrid")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "notebooks"))
from _utils.adapters.memory_maze import mask_start_object, run_memory_maze
from reckon.memory import EvidencePerBytePolicy, FIFOPolicy


@pytest.mark.parametrize("seed", range(42, 52))
def test_actual_fork_uses_retained_initial_object(seed):
    result = run_memory_maze(seed, budget_slots=100, policy=FIFOPolicy())
    assert result["success"]
    assert result["cue_retrieved_at_fork"]
    reads = [turn for turn in result["transcript"] if turn["retrieved_ids"]]
    assert len(reads) == 1
    assert reads[0]["position"] == [5, 3]
    assert reads[0]["retrieved_payloads"][0]["source_step"] == 0
    assert not any(event["op_type"] == "prune" for event in result["events"])


def test_withholding_read_and_pruning_have_the_same_seeded_fallback():
    outcomes = []
    for seed in range(42, 62):
        withheld = run_memory_maze(seed, 100, use_memory=False)
        pruned = run_memory_maze(seed, 1)
        assert withheld["initial_cue_retained"]
        assert not pruned["initial_cue_retained"]
        assert not withheld["cue_retrieved_at_fork"]
        assert not pruned["cue_retrieved_at_fork"]
        assert withheld["chosen_branch"] == pruned["chosen_branch"]
        assert withheld["success"] == pruned["success"]
        outcomes.append(withheld["success"])
    assert any(outcomes) and not all(outcomes)


def test_assigned_priority_can_keep_the_cue_under_real_pressure():
    for seed in range(42, 52):
        result = run_memory_maze(seed, 3, policy=EvidencePerBytePolicy(0.5))
        assert result["success"] and result["cue_retrieved_at_fork"]
        assert any(event["op_type"] == "prune" for event in result["events"])


def test_later_observation_mask_does_not_mutate_the_environment_observation():
    original = {"image": np.zeros((7, 7, 3), dtype=np.uint8), "direction": 0}
    original["image"][1, 2] = [6, 1, 0]
    masked = mask_start_object(original)
    assert masked["image"][1, 2].tolist() == [1, 0, 0]
    assert original["image"][1, 2].tolist() == [6, 1, 0]


def test_controller_refuses_unmodelled_layout():
    with pytest.raises(ValueError, match="specified for"):
        run_memory_maze(42, env_id="MiniGrid-MemoryS13Random-v0")
