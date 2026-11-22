"""
Task B: Hidden-Mode Contextual Bandit

A multi-armed bandit where the optimal arm depends on a hidden "mode".
The mode switches periodically, and the agent occasionally sees a mode indicator.
The agent must remember mode indicators to identify the optimal arm.

Memory challenge: Remember mode indicators, forget stale ones after mode switches.
"""

# pylint: disable=duplicate-code

# Standard library
from dataclasses import dataclass
from typing import Optional

# Third party
import numpy as np

from reckon.core.episode_context import EpisodeContext
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.record import PayloadType
from reckon.metrics import MemoryEfficiencyMetrics, PerformanceMetrics

# Local
from reckon.tasks.base import BaseTask, TaskResult


@dataclass
class BanditConfig:
    """Configuration for the bandit task."""

    num_arms: int = 4
    num_modes: int = 3
    mode_switch_interval: int = 50
    indicator_probability: float = 0.1
    reward_std: float = 0.1


class HiddenModeBandit:
    """
    Contextual bandit with hidden modes.

    - K arms, M modes
    - Each mode has a different optimal arm
    - Mode switches every N steps
    - Mode indicators appear with probability p
    """

    def __init__(self, config: BanditConfig, rng: np.random.Generator):
        self.config = config
        self.rng = rng

        # Initialize attributes (set properly in reset())
        self.step_count = 0
        self.current_mode = 0
        self.mode_history: list[int] = []
        self.last_mode_switch = 0

        # Generate mean rewards for each (mode, arm) pair
        # Ensure each mode has a distinct optimal arm
        self.mean_rewards = np.zeros((config.num_modes, config.num_arms))
        for mode in range(config.num_modes):
            # Base rewards around 0.5
            self.mean_rewards[mode] = rng.uniform(0.3, 0.6, config.num_arms)
            # Make one arm optimal (reward ~0.9)
            optimal_arm = mode % config.num_arms
            self.mean_rewards[mode, optimal_arm] = rng.uniform(0.85, 0.95)

        self.reset()

    def reset(self) -> None:
        """Reset the bandit to initial state."""
        self.step_count = 0
        self.current_mode = int(self.rng.integers(0, self.config.num_modes))
        self.mode_history.clear()
        self.mode_history.append(self.current_mode)
        self.last_mode_switch = 0

    def get_optimal_arm(self) -> int:
        """Return the optimal arm for the current mode."""
        return int(np.argmax(self.mean_rewards[self.current_mode]))

    def get_optimal_reward(self) -> float:
        """Return the expected reward of the optimal arm."""
        return float(np.max(self.mean_rewards[self.current_mode]))

    def step(self, arm: int) -> tuple[float, Optional[dict]]:
        """
        Pull an arm and get reward.

        Returns:
            (reward, mode_indicator or None)
        """
        self.step_count += 1

        # Check for mode switch
        if (self.step_count - self.last_mode_switch) >= self.config.mode_switch_interval:
            old_mode = self.current_mode
            # Switch to a different mode
            new_modes = [m for m in range(self.config.num_modes) if m != old_mode]
            self.current_mode = self.rng.choice(new_modes)
            self.mode_history.append(self.current_mode)
            self.last_mode_switch = self.step_count

        # Get reward
        mean = self.mean_rewards[self.current_mode, arm]
        reward = self.rng.normal(mean, self.config.reward_std)
        reward = np.clip(reward, 0.0, 1.0)

        # Maybe show mode indicator
        indicator = None
        if self.rng.random() < self.config.indicator_probability:
            indicator = {
                "mode_hint": int(self.current_mode),
                "step": int(self.step_count),
            }

        return float(reward), indicator


class BanditTask(BaseTask):
    """
    Hidden-Mode Contextual Bandit benchmark task.

    Tests agent's ability to:
    1. Store mode indicators when they appear
    2. Use stored indicators to select optimal arm
    3. Forget outdated indicators after mode switches

    Metrics:
    - mean_regret: Average regret vs optimal arm
    - detection_lag: Steps after mode switch to identify new mode
    """

    def __init__(self, config: Optional[BanditConfig] = None):
        self.config = config or BanditConfig()

    @property
    def name(self) -> str:
        return "Hidden-Mode Bandit"

    @property
    def description(self) -> str:
        return "Multi-armed bandit with hidden modes; remember mode indicators"

    # pylint: disable=too-many-locals,too-many-statements
    # Keep the common task interface, including its keyword-only memory controls.
    def run(  # pylint: disable=too-many-arguments
        self,
        cmm: CausalMemoryManager,
        num_episodes: int,
        seed: int,
        *,
        reset_memory: bool = False,
        learn_utility: bool = True,
    ) -> TaskResult:
        """Run the bandit task."""
        if num_episodes < 1:
            raise ValueError("num_episodes must be positive")
        environment_seed, action_seed = np.random.SeedSequence(seed).spawn(2)
        bandit = HiddenModeBandit(self.config, np.random.default_rng(environment_seed))
        # Exploration frequency depends on retained memory. Its draws must not
        # change the paired environment's modes, indicators or reward noise.
        rng = np.random.default_rng(action_seed)

        steps_per_episode = 200
        episodes_data = []
        total_regret = 0.0
        total_rewards = 0.0
        total_optimal_rewards = 0.0
        total_writes = 0
        total_reads = 0
        useful_reads = 0
        detection_lags = []

        for ep in range(num_episodes):
            with EpisodeContext(episode_id=f"bandit_ep{ep}") as context:
                bandit.reset()
                cmm.set_episode(f"bandit_ep{ep}", reset_memory=reset_memory)
                cmm.set_step(0)

                episode_regret = 0.0
                episode_rewards = 0.0
                mode_indicator_id: Optional[str] = None
                believed_mode: Optional[int] = None
                last_mode_switch_step = 0
                mode_detected_step: Optional[int] = None

                episode_info = {
                    "regret": 0.0,
                    "rewards": 0.0,
                    "mode_switches": 0,
                    "indicators_seen": 0,
                    "correct_selections": 0,
                    "total_pulls": 0,
                    "task_prunes": 0,
                }

                for step in range(steps_per_episode):
                    cmm.set_step(step)

                    context.clear_retrieved_records()
                    # Re-read the retained indicator at the decision, so pruning matters.
                    records = (
                        cmm.retrieve(record_ids=[mode_indicator_id]) if mode_indicator_id else []
                    )
                    believed_mode = records[0].payload.get("mode_hint") if records else None
                    if records:
                        total_reads += 1
                        if mode_detected_step is None:
                            mode_detected_step = step
                            detection_lags.append(step - last_mode_switch_step)
                            useful_reads += 1

                    # Select arm based on believed mode or random exploration
                    arm = (
                        believed_mode % self.config.num_arms
                        if believed_mode is not None
                        else int(rng.integers(0, self.config.num_arms))
                    )

                    # Pull arm
                    reward, indicator = bandit.step(arm)
                    if learn_utility:
                        cmm.observe(outcome=reward)

                    # The environment switches during the pull. Credit the record used
                    # for that decision before retiring it, then keep any new indicator.
                    if bandit.last_mode_switch == bandit.step_count:
                        last_mode_switch_step = step
                        episode_info["mode_switches"] += 1
                        mode_detected_step = None
                        if mode_indicator_id:
                            episode_info["task_prunes"] += int(
                                cmm.prune(mode_indicator_id, reason="mode_switch")
                            )
                            mode_indicator_id = None

                    optimal_reward = bandit.get_optimal_reward()
                    optimal_arm = bandit.get_optimal_arm()

                    regret = optimal_reward - reward
                    episode_regret += regret
                    episode_rewards += reward
                    episode_info["total_pulls"] += 1

                    if arm == optimal_arm:
                        episode_info["correct_selections"] += 1

                    # Store indicator if seen
                    if indicator is not None:
                        record_id = cmm.write(
                            payload=indicator,
                            payload_type=PayloadType.CUE,
                            tags=["mode_indicator"],
                            source_op="observe_indicator",
                        )
                        total_writes += 1
                        episode_info["indicators_seen"] += 1

                        # Prune old indicator
                        if mode_indicator_id:
                            episode_info["task_prunes"] += int(
                                cmm.prune(mode_indicator_id, reason="newer_indicator")
                            )

                        mode_indicator_id = record_id

                episode_info["regret"] = episode_regret
                episode_info["rewards"] = episode_rewards
                episodes_data.append(episode_info)

                total_regret += episode_regret
                total_rewards += episode_rewards
                total_optimal_rewards += steps_per_episode * 0.9  # Approximate

        # Compute metrics
        total_steps = num_episodes * steps_per_episode
        mean_regret = total_regret / total_steps

        # Detection lag: average steps to detect mode after switch
        mean_detection_lag = (
            np.mean(detection_lags) if detection_lags else float(self.config.mode_switch_interval)
        )

        # Memory efficiency
        first_mode_detections_per_successful_read = (
            useful_reads / total_reads if total_reads > 0 else 0.0
        )

        performance = PerformanceMetrics(
            mean_regret=mean_regret,
            mean_return=total_rewards / num_episodes,
        )

        memory = MemoryEfficiencyMetrics(reads_per_write=total_reads / max(total_writes, 1))
        diagnostics = {
            "first_mode_detections_per_successful_read": first_mode_detections_per_successful_read,
            "first_mode_detections_per_write": (
                useful_reads / total_writes if total_writes > 0 else 0.0
            ),
        }

        return TaskResult(
            performance=performance,
            memory=memory,
            diagnostics=diagnostics,
            raw_data={
                "reset_memory": reset_memory,
                "learn_utility": learn_utility,
                "episodes": episodes_data,
                "mean_detection_lag": mean_detection_lag,
                "total_writes": total_writes,
                "total_reads": total_reads,
            },
        )
