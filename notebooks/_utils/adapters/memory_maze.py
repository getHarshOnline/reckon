"""A declared controller for MiniGrid's fixed-length Memory corridor.

Navigation uses the current full-grid observation and the known corridor layout.
The start-room object is admitted once, then masked from every controller input.
At the fork, the controller reads that record to select the matching end object.
This tests retention, not learned navigation or general MiniGrid competence.
"""

import random
import time

import numpy as np

from reckon.core.episode_context import EpisodeContext
from reckon.core.resources import MemoryBudget
from reckon.memory import FIFOPolicy, PayloadType
from .minigrid_adapter import MinigridAdapter, MinigridConfig
from .episode_memory import episode_memory


def mask_start_object(observation):
    """Remove the initial cue from subsequent observations before selection."""
    masked = dict(observation)
    masked["image"] = observation["image"].copy()
    masked["image"][1, masked["image"].shape[1] // 2 - 1] = [1, 0, 0]
    return masked


def run_memory_maze(
    seed,
    budget_slots=20,
    max_steps=100,
    policy=None,
    use_memory=True,
    env_id="MiniGrid-MemoryS7-v0",
    *,
    memory=None,
):
    """Run an actual Memory environment, failing if its dependency is missing."""
    if env_id != "MiniGrid-MemoryS7-v0":
        raise ValueError("This controller is specified for MiniGrid-MemoryS7-v0")
    started = time.perf_counter()
    policy = policy or FIFOPolicy()
    cmm = episode_memory(
        MemoryBudget(max_slots=budget_slots, max_bytes=budget_slots * 500),
        policy,
        f"memory-maze-{seed}",
        memory,
    )
    adapter = MinigridAdapter(
        MinigridConfig(
            env_id=env_id,
            fully_observable=True,
            max_steps=max_steps,
        )
    )
    fallback_rng = random.Random(seed + 1_000_003)
    transcript = []
    context = EpisodeContext(episode_id=f"memory-maze-{seed}")
    cue_retrieved = False
    chosen_branch = None
    reward_sum = 0.0
    done = False
    truncated = False
    step = 0
    try:
        observation, _ = adapter.reset(seed=seed)
        cmm.set_step(0)
        cue_id = cmm.write(
            {"object_type": int(observation["image"][1, 2, 0]), "source_step": 0},
            PayloadType.CUE,
            tags=["initial_cue"],
            initial_utility=2.0,
        )
        observation = mask_start_object(observation)
        while not done and not truncated and step < max_steps:
            image = observation["image"]
            position = np.argwhere(image[:, :, 0] == 10)[0].tolist()
            records = []
            if position == [5, 3] and chosen_branch is None:
                records = (
                    cmm.retrieve(query={"tags": ["initial_cue"]}, limit=1, context=context)
                    if use_memory
                    else []
                )
                cue_retrieved = bool(records)
                if records:
                    cue = records[0].payload["object_type"]
                    chosen_branch = "north" if cue == int(image[5, 1, 0]) else "south"
                else:
                    chosen_branch = fallback_rng.choice(["north", "south"])
            desired_direction = (3 if chosen_branch == "north" else 1) if chosen_branch else 0
            direction = observation["direction"]
            action = (
                2
                if direction == desired_direction
                else (0 if (direction - desired_direction) % 4 == 1 else 1)
            )
            # Record compact observations after the decision; the initial cue is
            # absent and neither environment success_pos nor its grid is read.
            step += 1
            cmm.set_step(step)
            cmm.write(
                {"position": position, "direction": direction},
                PayloadType.OBSERVATION,
                tags=["observation"],
                initial_utility=0.1,
            )
            cmm.write({"action": action}, PayloadType.ACTION, tags=["action"], initial_utility=0.1)
            observation, reward, done, truncated, _ = adapter.step(action)
            observation = mask_start_object(observation)
            reward_sum += reward
            transcript.append(
                {
                    "step": step,
                    "position": position,
                    "action": action,
                    "retrieved_ids": [record.id for record in records],
                    "retrieved_payloads": [record.payload for record in records],
                    "chosen_branch": chosen_branch,
                    "reward": reward,
                }
            )
        cmm.observe(reward_sum, context=context)
    finally:
        adapter.close()
    return {
        "seed": seed,
        "budget": budget_slots,
        "policy": type(policy).__name__,
        "success": reward_sum > 0,
        "total_reward": reward_sum,
        "steps": step,
        "records": cmm.current_usage_slots,
        "initial_cue_retained": cue_id in {r.id for r in cmm.get_all_records()},
        "cue_retrieved_at_fork": cue_retrieved,
        "use_memory": use_memory,
        "chosen_branch": chosen_branch,
        "truncated": truncated,
        "events": cmm.get_event_log(),
        "transcript": transcript,
        "demo_mode": False,
        "environment": env_id,
        "elapsed_seconds": time.perf_counter() - started,
        "score_source": "assigned_utility; outcome_credit_after_final_decision",
    }
