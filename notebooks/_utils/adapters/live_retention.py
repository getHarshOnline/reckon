"""Measure a live notebook prune by replaying its verified episode prefix.

The supported controllers are deterministic for a fixed episode seed. Each
candidate therefore gets one pair, not repeated pseudo-independent samples.
Both arms reconstruct the actual earlier pruning decisions; after the target
write they follow FIFO. The intervention removes its candidate first, then
FIFO frees any remaining capacity. The baseline follows FIFO at that write.
This is a conditional removal effect under a bounded continuation policy,
not a guaranteed-retention baseline or an estimate across future environments.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import math
from pathlib import Path
from time import perf_counter

from reckon.memory import EvidencePerBytePolicy, FIFOPolicy
from .record_probe import AdapterProbeConfig, AdapterProbeTask
from .replay_memory import ReplayMemory, digest


def game_identity(game_file):
    """Identify the executable and metadata without depending on their directory."""
    game = Path(game_file)
    return {
        "file": game.name,
        "sha256": hashlib.sha256(game.read_bytes()).hexdigest(),
        "metadata_sha256": hashlib.sha256(game.with_suffix(".json").read_bytes()).hexdigest(),
    }


class ReplayPolicy(FIFOPolicy):
    """Replay earlier decisions exactly, intervene once, then use ordinary FIFO."""

    def __init__(self, decisions, boundary, removed_ordinal):
        self.decisions = decisions
        self.expected_boundary = boundary
        self.removed_ordinal = removed_ordinal
        self.memory: ReplayMemory | None = None
        self.decision_index = 0
        self.reached = False
        self.removal_ids = []

    def select_for_pruning(self, records, overflow_bytes, overflow_slots=0, overflow_tokens=0):
        assert self.memory is not None
        overflow = (overflow_bytes, overflow_slots, overflow_tokens)
        index = self.decision_index
        self.decision_index += 1
        if index <= len(self.decisions):
            expected = (
                self.decisions[index]["boundary"]
                if index < len(self.decisions)
                else self.expected_boundary
            )
            if self.memory.boundary(records, overflow) != expected:
                raise RuntimeError("Replay prefix or pruning state differs from the live episode")
        if index < len(self.decisions):
            by_ordinal = {self.memory.ordinals[record.id]: record.id for record in records}
            return [by_ordinal[ordinal] for ordinal in self.decisions[index]["selected_ordinals"]]
        if index == len(self.decisions):
            self.reached = True
            if self.removed_ordinal is not None:
                target = next(
                    record
                    for record in records
                    if self.memory.ordinals[record.id] == self.removed_ordinal
                )
                remaining = [record for record in records if record.id != target.id]
                selected = [target.id] + super().select_for_pruning(
                    remaining,
                    max(0, overflow_bytes - target.cost.bytes),
                    max(0, overflow_slots - 1),
                    max(0, overflow_tokens - (target.cost.tokens or 0)),
                )
                self.removal_ids = selected
                return selected
        selected = super().select_for_pruning(records, *overflow)
        if index == len(self.decisions):
            self.removal_ids = selected
        return selected


class ReplayRetentionPolicy(EvidencePerBytePolicy):
    """Default to retention scores; optionally prefer a measured improving removal.

    The opt-in rule handles one-slot pressure only. It does not infer a joint
    removal from separate interventions or change their FIFO continuation.
    """

    log_reason = "replayed_continuation_per_byte"

    def __init__(self, episode, evidence_weight=0.5, selection_rule="retention-score"):
        if not math.isfinite(evidence_weight) or not 0 <= evidence_weight <= 1:
            raise ValueError("Evidence weight must be finite and between zero and one")
        if selection_rule not in {"retention-score", "improving-removal"}:
            raise ValueError("Unknown replay removal selection rule")
        super().__init__(evidence_weight)
        self.episode = episode
        self.selection_rule = selection_rule
        if selection_rule == "improving-removal":
            self.log_reason = "improving_removal_then_retention_per_byte"
        self.memory: ReplayMemory | None = None
        self.batches = []

    def select_for_pruning(self, records, overflow_bytes, overflow_slots=0, overflow_tokens=0):
        if self.selection_rule == "improving-removal" and (
            overflow_bytes != 0 or overflow_slots != 1 or overflow_tokens != 0
        ):
            raise ValueError(
                "Improving-removal selection requires exactly one slot and no byte/token pressure"
            )
        assert self.memory is not None
        started = perf_counter()
        boundary = self.memory.boundary(records, (overflow_bytes, overflow_slots, overflow_tokens))
        evidence = []
        ranked = deepcopy(records)
        for record in ranked:
            ordinal = self.memory.ordinals[record.id]
            arms = []
            for removed in (None, ordinal):
                replay = ReplayPolicy(self.batches, boundary, removed)
                arm_started = perf_counter()
                trial_memory = ReplayMemory(self.episode.config.memory_budget(), replay)
                replay.memory = trial_memory
                result, outcome = self.episode.run(replay, trial_memory)
                if not replay.reached:
                    raise RuntimeError("Replay never reached the live pruning decision")
                if not math.isfinite(outcome):
                    raise ValueError("Continuation outcome must be finite")
                arms.append(
                    {
                        "outcome": outcome,
                        "elapsed_s": perf_counter() - arm_started,
                        "removed_ordinal": removed,
                        "selected_ordinals": trial_memory.canonical(replay.removal_ids),
                        "boundary_sha256": digest(boundary),
                        "record_ids": {
                            str(order): rid for rid, order in trial_memory.ordinals.items()
                        },
                        "journal": trial_memory.journal,
                        "result": result,
                    }
                )
            delta = arms[0]["outcome"] - arms[1]["outcome"]
            record.causal_score.ablation_delta = delta
            evidence.append({"record_ordinal": ordinal, "delta": delta, "arms": arms})
        selected = None
        if self.selection_rule == "improving-removal":
            baselines = {entry["arms"][0]["outcome"] for entry in evidence}
            if len(baselines) != 1:
                raise RuntimeError("Repeated FIFO baseline outcomes differ at the same boundary")
            best = min(
                evidence,
                key=lambda entry: (-entry["arms"][1]["outcome"], entry["record_ordinal"]),
            )
            if best["arms"][1]["outcome"] > best["arms"][0]["outcome"]:
                selected = [
                    record.id for record in ranked
                    if self.memory.ordinals[record.id] == best["record_ordinal"]
                ]
        if selected is None:
            selected = super().select_for_pruning(
                ranked, overflow_bytes, overflow_slots, overflow_tokens
            )
        # Trials must never advance or mutate the main store while it is paused.
        if (
            self.memory.boundary(records, (overflow_bytes, overflow_slots, overflow_tokens))
            != boundary
        ):
            raise RuntimeError("Probes changed the live pruning state")
        self.batches.append(
            {
                "boundary": boundary,
                "boundary_sha256": digest(boundary),
                "selected_ordinals": self.memory.canonical(selected),
                "evidence": evidence,
                "probe_episodes": 2 * len(evidence),
                "elapsed_s": perf_counter() - started,
            }
        )
        return selected


class ReplayEpisode:
    """Bind the existing scripted controller and its real environment inputs.

    TextWorld requires an existing generated game. Its executable and metadata
    are hashed before and after every arm, so all replays use identical bytes.
    A model call or prerecorded fallback cannot enter this experiment.
    """

    def __init__(
        self, config: AdapterProbeConfig, seed: int, game_file=None, expected_game_identity=None
    ):
        if type(seed) is not int or seed < 0:
            raise ValueError("Episode seed must be a non-negative integer")
        self.config = config
        self.seed = seed
        self.game_file = game_file
        self.game_identity = None
        if config.adapter == "textworld":
            from .textworld_adapter import check_available

            if not check_available() or game_file is None:
                raise ValueError("Live replay requires TextWorld and an explicit generated game")
            self.game_identity = self.current_game_identity()
            if expected_game_identity is not None and self.game_identity != expected_game_identity:
                raise RuntimeError(
                    "TextWorld game bytes differ from the pinned comparison identity"
                )
        elif game_file is not None:
            raise ValueError("Only TextWorld accepts a game file")

    def current_game_identity(self):
        assert self.game_file is not None
        return game_identity(self.game_file)

    def run(self, policy, memory):
        if self.config.adapter == "textworld":
            from .text_game import run_textworld_episode

            if self.current_game_identity() != self.game_identity:
                raise RuntimeError("TextWorld game bytes changed before replay")
            result = run_textworld_episode(
                self.seed,
                self.config.budget_slots,
                self.config.max_steps,
                policy,
                game_file=self.game_file,
                memory=memory,
            )
            if result["game_identity"] != self.game_identity:
                raise RuntimeError("TextWorld game bytes changed during replay")
            outcome = float(result["total_reward"])
        else:
            result, outcome = AdapterProbeTask(self.config, [])._run_episode(memory, self.seed)
        if result.get("demo_mode") or result.get("fallback_count", 0):
            raise RuntimeError("Fallback episodes cannot supply replay evidence")
        return result, outcome


def run_replay_retention_episode(
    config, seed, *, game_file=None, evidence_weight=0.5, expected_game_identity=None,
    selection_rule="retention-score",
):
    """Run the measured policy on a live episode, returning every replay arm.

    Probe costs include reconstruction of the prefix and the continuation. Main
    elapsed time already includes all nested replay work; do not add it twice.
    No per-candidate p-value or confidence interval is assigned to an exact pair.
    Comparisons across independently generated outer episodes need their own
    predeclared sample size, contrasts and correction family.
    selection_rule defaults to the original retention-score ranking. The
    improving-removal development rule requires one-slot pressure only.
    """
    episode = ReplayEpisode(config, seed, game_file, expected_game_identity)
    policy = ReplayRetentionPolicy(episode, evidence_weight, selection_rule)
    memory = ReplayMemory(config.memory_budget(), policy)
    policy.memory = memory
    result, outcome = episode.run(policy, memory)
    result["score_source"] = "measured_conditional_removal_effect_under_fifo_continuation"
    result["selection_rule"] = selection_rule
    return {
        "protocol": "replay_actual_prefix_then_remove_one_before_pending_write_under_fifo",
        "seed": seed,
        "config": vars(config),
        "game_identity": episode.game_identity,
        "reference_policy": "fifo",
        "selection_rule": selection_rule,
        "evidence_weight": evidence_weight,
        "sampling": "one_deterministic_pair_per_candidate; no_within_episode_inference",
        "probe_episodes": sum(batch["probe_episodes"] for batch in policy.batches),
        "probe_elapsed_s": sum(batch["elapsed_s"] for batch in policy.batches),
        "inclusive_elapsed_s": result["elapsed_seconds"],
        "outcome": outcome,
        "result": result,
        "record_ids": {str(order): rid for rid, order in memory.ordinals.items()},
        "journal": memory.journal,
        "batches": policy.batches,
    }
