"""
Task A: Key-Door Delayed Credit Gridworld

A simple gridworld where an agent must reach a goal, but a door blocks the path.
The agent sees a colored key early in the episode that determines which door opens.
Red and blue identify a door; green leaves the door random. The controller
uses a retrieved cue, or guesses left when the cue is absent or green.

Memory challenge: Store the key observation, retrieve it at decision time.
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
class GridState:
    """State of the gridworld."""

    agent_pos: tuple[int, int]
    key_color: str
    key_seen: bool = False
    door_reached: bool = False
    done: bool = False
    reward: float = 0.0


class KeyDoorGridworld:
    """
    5x5 Gridworld with key-door mechanic.

    Layout:
        S . . . .     S = Start
        . . K . .     K = Key location
        . . . . .     D1, D2 = Doors
        # D1 # D2 #   G = Goal, # = Wall
        . . G . .

    Agent starts at S, sees key color at K, must choose correct door.
    The door row is a wall except at the two doors. Red opens the left door,
    blue the right; green opens a seeded random door that the cue cannot predict.
    """

    GRID_SIZE = 5
    START_POS = (0, 0)
    KEY_POS = (1, 2)
    DOOR1_POS = (3, 1)  # Left door
    DOOR2_POS = (3, 3)  # Right door
    GOAL_POS = (4, 2)
    KEY_COLORS = ["red", "blue", "green"]

    # Actions: 0=up, 1=down, 2=left, 3=right, 4=store_cue
    ACTIONS = ["up", "down", "left", "right", "store_cue"]

    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.reset()

    def reset(self) -> GridState:
        """Reset to initial state with random key color."""
        self.key_color = str(self.rng.choice(self.KEY_COLORS))
        # Map key color to correct door: red->left, blue->right, green->random
        if self.key_color == "red":
            self.correct_door = self.DOOR1_POS
        elif self.key_color == "blue":
            self.correct_door = self.DOOR2_POS
        else:
            # For green, randomly choose door (use tuple selection)
            door_choice = int(self.rng.integers(0, 2))
            self.correct_door = [self.DOOR1_POS, self.DOOR2_POS][door_choice]

        self.state = GridState(
            agent_pos=self.START_POS,
            key_color=self.key_color,
        )
        self.steps = 0
        return self.state

    def step(self, action: int) -> GridState:
        """Execute action and return new state."""
        self.steps += 1
        row, col = self.state.agent_pos

        # Movement actions
        if action == 0:  # up
            row = max(0, row - 1)
        elif action == 1:  # down
            row = min(self.GRID_SIZE - 1, row + 1)
        elif action == 2:  # left
            col = max(0, col - 1)
        elif action == 3:  # right
            col = min(self.GRID_SIZE - 1, col + 1)
        # action == 4 is store_cue, handled by agent

        new_pos = (row, col)

        # Crossing the wall requires the open door; the gaps are impassable.
        if row == self.DOOR1_POS[0]:
            if new_pos != self.correct_door:
                new_pos = self.state.agent_pos
            else:
                self.state.door_reached = True

        self.state.agent_pos = new_pos

        # Check if at key position
        if new_pos == self.KEY_POS and not self.state.key_seen:
            self.state.key_seen = True

        # Check for goal
        if new_pos == self.GOAL_POS:
            self.state.done = True
            self.state.reward = 1.0

        # Timeout
        if self.steps >= 20:
            self.state.done = True

        return self.state

    def get_observation(self) -> dict:
        """Get current observation."""
        obs = {
            "position": self.state.agent_pos,
            "step": self.steps,
        }
        # Can only see key color when at key position
        if self.state.agent_pos == self.KEY_POS:
            obs["key_color"] = self.key_color
        return obs


class KeyDoorTask(BaseTask):
    """
    Key-Door Gridworld benchmark task.

    Tests agent's ability to:
    1. Store critical observations (key color)
    2. Retrieve them at decision time (at door)
    3. Make correct decisions based on memory

    Metrics:
    - success_rate: Fraction of episodes reaching goal
    - successful_stored_key_episode_fraction: Stored-key episodes with retrieval and success
    """

    @property
    def name(self) -> str:
        return "Key-Door Gridworld"

    @property
    def description(self) -> str:
        return "Navigate to goal using remembered key color to choose correct door"

    # Keep the common task interface, including its keyword-only memory controls.
    def run(  # pylint: disable=too-many-locals,too-many-arguments
        self,
        cmm: CausalMemoryManager,
        num_episodes: int,
        seed: int,
        *,
        reset_memory: bool = False,
        learn_utility: bool = True,
    ) -> TaskResult:
        """Run the Key-Door task."""
        if num_episodes < 1:
            raise ValueError("num_episodes must be positive")
        rng = np.random.default_rng(seed)
        env = KeyDoorGridworld(rng)

        episodes_data = []
        total_writes = 0
        total_reads = 0
        useful_writes = 0
        successful_episodes = 0

        for ep in range(num_episodes):
            with EpisodeContext(episode_id=f"keydoor_ep{ep}"):
                # Reset the environment; carry memory unless reset_memory is requested.
                state = env.reset()
                cmm.set_episode(f"keydoor_ep{ep}", reset_memory=reset_memory)
                cmm.set_step(0)

                episode_info = {
                    "key_color": env.key_color,
                    "correct_door": env.correct_door,
                    "success": False,
                    "writes": 0,
                    "reads": 0,
                    "key_stored": False,
                    "key_retrieved": False,
                }

                key_record_id: Optional[str] = None
                step = 0

                while not state.done:
                    cmm.set_step(step)
                    obs = env.get_observation()

                    # Simple agent policy:
                    # 1. Move towards key first
                    # 2. Store key when seen
                    # 3. Move towards doors
                    # 4. At door, retrieve memory and choose
                    # 5. Move to goal

                    action = self._select_action(obs, state, env, cmm, key_record_id, episode_info)

                    # Handle store_cue action
                    if action == 4 and obs.get("key_color"):
                        record_id = cmm.write(
                            payload={"key_color": obs["key_color"]},
                            payload_type=PayloadType.CUE,
                            tags=["key", "color"],
                            source_op="store_cue",
                        )
                        key_record_id = record_id
                        episode_info["writes"] += 1
                        episode_info["key_stored"] = True
                        total_writes += 1

                    state = env.step(action)
                    step += 1

                # Record success
                if state.reward > 0:
                    successful_episodes += 1
                    episode_info["success"] = True
                    if episode_info["key_stored"] and episode_info["key_retrieved"]:
                        useful_writes += 1

                episodes_data.append(episode_info)
                total_reads += episode_info["reads"]

                if learn_utility:
                    cmm.observe(outcome=float(state.reward))

        # Compute metrics
        success_rate = successful_episodes / num_episodes

        # Stored-key episodes with both retrieval and success; no record removal is tested.
        stored_count = sum(1 for e in episodes_data if e["key_stored"])
        useful_count = sum(
            1 for e in episodes_data if e["key_stored"] and e["key_retrieved"] and e["success"]
        )
        successful_stored_key_episode_fraction = (
            useful_count / stored_count if stored_count > 0 else 0.0
        )

        # Memory efficiency
        successful_key_episodes_per_write = (
            useful_writes / total_writes if total_writes > 0 else 0.0
        )

        performance = PerformanceMetrics(
            success_rate=success_rate,
            mean_return=success_rate,  # Binary reward
        )

        memory = MemoryEfficiencyMetrics()
        diagnostics = {
            "successful_key_episodes_per_write": successful_key_episodes_per_write,
            "key_retrievals_per_query": (
                sum(e["key_retrieved"] for e in episodes_data) / max(total_reads, 1)
            ),
            "successful_stored_key_episode_fraction": successful_stored_key_episode_fraction,
        }

        return TaskResult(
            performance=performance,
            memory=memory,
            diagnostics=diagnostics,
            raw_data={
                "reset_memory": reset_memory,
                "learn_utility": learn_utility,
                "episodes": episodes_data,
                "total_writes": total_writes,
                "total_reads": total_reads,
            },
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    # pylint: disable=too-many-return-statements,too-many-branches
    def _select_action(
        self,
        obs: dict,
        state: GridState,
        env: KeyDoorGridworld,
        cmm: CausalMemoryManager,
        key_record_id: Optional[str],
        episode_info: dict,
    ) -> int:
        """Simple policy for agent action selection."""
        pos = state.agent_pos

        # If at key and haven't stored, store it
        # Note: key_color appears in obs when at KEY_POS, key_seen becomes True after step
        if pos == env.KEY_POS and obs.get("key_color") and not episode_info["key_stored"]:
            return 4  # store_cue

        # Try the current episode's cue once, counting an empty read as an attempt.
        if pos[0] >= 2 and key_record_id and episode_info["reads"] == 0:
            records = cmm.retrieve(record_ids=[key_record_id])
            episode_info["reads"] += 1
            if records:
                episode_info["key_retrieved"] = True
                episode_info["retrieved_color"] = records[0].payload.get("key_color")

        if not state.key_seen:
            return self._move_towards(pos, env.KEY_POS)
        if not state.door_reached:
            # No cue or an ambiguous green cue means a fixed left-door guess.
            target = (
                env.DOOR2_POS if episode_info.get("retrieved_color") == "blue" else env.DOOR1_POS
            )
            approach = (target[0] - 1, target[1])
            return self._move_towards(pos, target if pos == approach else approach)
        return self._move_towards(pos, env.GOAL_POS)

    def _move_towards(self, current: tuple[int, int], target: tuple[int, int]) -> int:
        """Return action to move from current towards target."""
        row, col = current
        target_row, target_col = target

        # Prioritize vertical movement
        if row < target_row:
            return 1  # down
        if row > target_row:
            return 0  # up
        if col < target_col:
            return 3  # right
        if col > target_col:
            return 2  # left
        return 1  # default
