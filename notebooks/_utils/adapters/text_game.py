"""Text-game actions use current observations and the records actually retrieved.

The scripted selector follows the generated game's visible ordered instructions
using only the current observation and retrieved records. It is a narrow grammar
heuristic, not a general game solver. Without a usable instruction it falls back
to untried commands. Optional model failures are counted explicitly.
"""

import json
import hashlib
import re
from pathlib import Path
import time
from typing import Callable, Optional

from reckon.core.episode_context import EpisodeContext
from reckon.core.resources import MemoryBudget
from reckon.memory import EvidencePerBytePolicy
from . import textworld_adapter
from .episode_memory import episode_memory
from .ollama_client import OLLAMA_AVAILABLE, ollama_chat


def instruction_plan(observation: str) -> list[str]:
    """Read the unblended quest instructions printed before the first room.

    Match the player's text, never game metadata, walkthroughs or policy commands.
    The default TextWorld house grammar prints one action per sentence; compound
    quests and arbitrary prose are outside this controller's supported scope.
    """
    if "-=" not in observation:
        return []
    prologue = observation.split("-=", 1)[0].strip().split("\n\n")[-1].lower()
    start = re.search(r"\b(?:first|your first objective|your task for today is to|the objective is to)\b", prologue)
    if start is None:
        return []
    return [part.strip() for part in prologue[start.start():].split(".") if part.strip()]


def instruction_matches(command: str, instruction: str) -> bool:
    """Ground a visible instruction in an admissible command's verb and objects."""
    command = command.lower()
    # Unblended house instructions put introductions and completed prerequisites
    # before commas. Only the final clause names the current action and entities.
    words = set(re.findall(r"[a-z0-9]+", instruction.rsplit(",", 1)[-1].lower()))
    verb, _, arguments = command.partition(" ")
    if verb == "go":
        return arguments in words and bool(words & {"go", "move", "head", "venture", "travel", "trip"})
    if words & {"unlock", "unlocked"}:
        intended = "unlock"
    elif words & {"lock", "locked"}:
        intended = "lock"
    elif words & {"open", "opened", "ajar"}:
        intended = "open"
    elif words & {"close", "closed", "shut"}:
        intended = "close"
    elif words & {"take", "retrieve", "recover", "pick", "lift"}:
        intended = "take"
    elif "eat" in words:
        intended = "eat"
    elif words & {"drop", "ditch", "throw", "toss"} or "floor" in words:
        intended = "drop"
    elif words & {"put", "place", "sit", "rest", "insert", "deposit"}:
        intended = "put" if "on" in words else "insert"
    else:
        return False
    if verb != intended:
        return False
    # The command supplies exact entity names, including multiword names. A key
    # can be implicit in an unlock instruction; its target still must match.
    required = arguments.split(" with ", 1)[0] if verb in {"lock", "unlock"} else arguments
    required_words = set(re.findall(r"[a-z0-9]+", required)) - {"the", "from", "on", "into", "in"}
    return bool(required_words) and required_words <= words


def select_scripted_action(admissible: list[str], records: list, observation: str = "") -> str:
    """Reconstruct instruction progress solely from the retained action history."""
    instructions = instruction_plan(observation)
    if not instructions:
        for record in sorted(records, key=lambda item: item.timestamp):
            if "description" in record.tags:
                instructions = instruction_plan(record.payload.get("description", ""))
                if instructions:
                    break
    if instructions:
        index = 0
        for record in sorted(records, key=lambda item: item.timestamp):
            if "action" in record.tags and index < len(instructions):
                if instruction_matches(record.payload.get("command", ""), instructions[index]):
                    index += 1
        if index < len(instructions):
            for command in admissible:
                if instruction_matches(command, instructions[index]):
                    return command
    tried = {record.payload.get("command") for record in records if "action" in record.tags}
    return next(
        (command for command in admissible if command not in tried),
        admissible[0] if admissible else "look",
    )


def select_action_llm(
    observation: str, admissible: list[str], records: list, model: str = "llama3.2"
) -> tuple[str, bool]:
    """Return the chosen command and whether the scripted fallback was used."""
    fallback = select_scripted_action(admissible, records, observation)
    if not OLLAMA_AVAILABLE or not admissible:
        return fallback, True
    context = json.dumps([record.payload for record in records], ensure_ascii=False)
    commands = json.dumps(admissible, ensure_ascii=False)
    prompt = (
        f"Current observation:\n{observation}\n\nRetained memory:\n{context}\n\n"
        f"Available commands (zero-based indices):\n{commands}\n\n"
        "Choose an available command using the observation and memory. "
        'Reply with only a JSON object: {"action_index": <integer>}.'
    )
    try:
        response = ollama_chat(
            model=model, messages=[{"role": "user", "content": prompt}], timeout_s=30
        )
        content = response["message"]["content"].strip()
        if content.startswith("```"):
            content = "\n".join(content.splitlines()[1:-1])
        parsed = json.loads(content)
        index = parsed.get("action_index") if isinstance(parsed, dict) else None
        if type(index) is int and 0 <= index < len(admissible):
            return admissible[index], False
    except (ValueError, KeyError, TypeError, OSError, RuntimeError):
        pass
    return fallback, True


def run_textworld_episode(
    seed: int,
    budget_slots: int = 25,
    max_steps: int = 30,
    policy=None,
    policy_backend: str = "scripted",
    verbose: bool = False,
    use_memory: bool = True,
    adapter_factory: Optional[Callable] = None,
    game_file: Optional[str] = None,
    *,
    memory=None,
) -> dict:
    """Run a live game, or clearly label the unchanged prerecorded fallback.

    adapter_factory supports controlled integration fixtures. Those fixtures must
    not be labelled live TextWorld evidence. The live adapter seeds generation;
    a replay claim still needs the generated game and dependency versions.
    """
    if policy_backend not in {"scripted", "ollama"}:
        raise ValueError("policy_backend must be scripted or ollama")
    started = time.perf_counter()
    policy = policy or EvidencePerBytePolicy(0.5)
    cmm = episode_memory(
        MemoryBudget(max_slots=budget_slots, max_bytes=None),
        policy,
        f"textworld-{seed}",
        memory,
    )
    if adapter_factory is None and not textworld_adapter.check_available():
        result = textworld_adapter.run_demo_episode(cmm, seed, quiet=not verbose)
        writes = sum(event["type"] == "inventory" for event in textworld_adapter.get_demo_trace())
        result.update(
            {
                "seed": seed,
                "seed_controls_game": False,
                "budget": budget_slots,
                "byte_budget": None,
                "final_bytes": cmm.current_usage_bytes,
                "policy": type(policy).__name__,
                "policy_backend": "prerecorded",
                "requested_backend": policy_backend,
                "fallback_count": 0,
                "records": cmm.current_usage_slots,
                "inventory_retention": (
                    sum("inventory" in r.tags for r in cmm.get_all_records()) / writes
                    if writes
                    else None
                ),
                "events": cmm.get_event_log(),
                "transcript": [],
                "use_memory": False,
                "environment": "fixed_trace",
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
        return result

    settings = textworld_adapter.TextworldConfig(
        max_steps=max_steps, seed=seed, game_file=game_file
    )
    adapter = (adapter_factory or textworld_adapter.TextworldAdapter)(settings)
    transcript = []
    inventory_ids = []
    fallback_count = 0
    score = 0.0
    done = False
    info = {}
    step = 0
    try:
        observation, info = adapter.reset()
        cmm.set_step(0)
        adapter.record_description(cmm, observation, info, step=0)
        if info.get("inventory"):
            record_id = adapter.record_inventory(cmm, info, step=0)
            if record_id:
                inventory_ids.append(record_id)
        while not done and step < max_steps:
            step += 1
            cmm.set_step(step)
            context = EpisodeContext(episode_id=f"textworld-{seed}")
            records = (
                cmm.retrieve(
                    query={"tags": ["description", "inventory", "action"]},
                    limit=budget_slots,
                    context=context,
                )
                if use_memory
                else []
            )
            admissible = info.get("admissible_commands", [])
            if policy_backend == "ollama":
                command, used_fallback = select_action_llm(observation, admissible, records)
                fallback_count += int(used_fallback)
            else:
                command = select_scripted_action(admissible, records, observation)
            previous_observation = observation
            observation, next_score, done, info = adapter.step(command)
            reward = next_score - score
            score = next_score
            cmm.observe(reward, context=context)
            adapter.record_action(cmm, command, step)
            adapter.record_description(cmm, observation, info, step)
            if info.get("inventory"):
                record_id = adapter.record_inventory(cmm, info, step)
                if record_id:
                    inventory_ids.append(record_id)
            if reward:
                adapter.record_reward(cmm, reward, step)
            transcript.append(
                {
                    "step": step,
                    "observation": previous_observation,
                    "admissible": admissible,
                    "command": command,
                    "retrieved_ids": [record.id for record in records],
                    "memory_context": [record.payload for record in records],
                    "reward_delta": reward,
                    "cumulative_score": score,
                }
            )
    finally:
        adapter.close()
    retained_ids = {record.id for record in cmm.get_all_records()}
    game_path = getattr(adapter, "game_file", None)
    game_identity = (
        {
            "file": Path(game_path).name,
            "sha256": hashlib.sha256(Path(game_path).read_bytes()).hexdigest(),
            "metadata_sha256": hashlib.sha256(
                Path(game_path).with_suffix(".json").read_bytes()
            ).hexdigest(),
        }
        if game_path
        else None
    )
    return {
        "seed": seed,
        "seed_controls_game": adapter_factory is None and game_file is None,
        "game_identity": game_identity,
        "budget": budget_slots,
        "byte_budget": None,
        "final_bytes": cmm.current_usage_bytes,
        "policy": type(policy).__name__,
        "policy_backend": policy_backend,
        "scripted_controller": "visible_ordered_instructions_v2",
        "requested_backend": policy_backend,
        "fallback_count": fallback_count,
        "use_memory": use_memory,
        "success": bool(info.get("won", False)),
        "total_reward": score,
        "done": done,
        "step_limit_reached": not done and step >= max_steps,
        "steps": step,
        "records": cmm.current_usage_slots,
        "inventory_retention": (
            sum(rid in retained_ids for rid in inventory_ids) / len(inventory_ids)
            if inventory_ids
            else None
        ),
        "events": cmm.get_event_log(),
        "transcript": transcript,
        "demo_mode": False,
        "environment": "integration_fixture" if adapter_factory else "textworld",
        "elapsed_seconds": time.perf_counter() - started,
        "score_source": "learned_utility_without_measured_retention_effects",
    }
