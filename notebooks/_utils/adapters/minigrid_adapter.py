"""
MiniGrid environment adapter for Reckon.

Converts MiniGrid observations and events into Reckon memory records.

Requirements:
    pip install minigrid gymnasium
"""

from dataclasses import dataclass
from typing import Any, Optional, Callable
import json

# Guarded imports
try:
    import gymnasium as gym
    import minigrid
    from minigrid.wrappers import FullyObsWrapper
    MINIGRID_AVAILABLE = True
except ImportError:
    MINIGRID_AVAILABLE = False
    gym = None
    minigrid = None


def check_available() -> bool:
    """Check if MiniGrid is available."""
    return MINIGRID_AVAILABLE


def get_install_command() -> str:
    """Get installation command for MiniGrid."""
    return "pip install minigrid gymnasium"


@dataclass
class MinigridConfig:
    """Configuration for MiniGrid adapter."""
    env_id: str = "MiniGrid-KeyCorridorS3R1-v0"
    fully_observable: bool = True
    max_steps: Optional[int] = None
    record_observations: bool = True
    record_actions: bool = True
    record_rewards: bool = True
    compress_observations: bool = False


class MinigridAdapter:
    """
    Adapter for MiniGrid environments.

    Converts MiniGrid observations and actions into Reckon memory records.

    Example:
        from reckon.memory import CausalMemoryManager, PayloadType
        from reckon.core.resources import MemoryBudget

        adapter = MinigridAdapter(MinigridConfig())
        cmm = CausalMemoryManager(MemoryBudget(max_slots=100))

        obs, info = adapter.reset(seed=42)
        adapter.record_observation(cmm, obs, info, step=0)

        action = adapter.sample_action()
        obs, reward, done, truncated, info = adapter.step(action)
        adapter.record_action(cmm, action, step=1)
        adapter.record_reward(cmm, reward, step=1)
    """

    def __init__(self, config: Optional[MinigridConfig] = None):
        """
        Initialize adapter.

        Args:
            config: Adapter configuration

        Raises:
            ImportError: If MiniGrid is not installed
        """
        if not MINIGRID_AVAILABLE:
            raise ImportError(
                f"MiniGrid not available. Install with: {get_install_command()}"
            )

        self.config = config or MinigridConfig()
        self._env: Optional[gym.Env] = None
        self._step_count: int = 0

    def make_env(self) -> "gym.Env":
        """Create and return the environment."""
        env = gym.make(self.config.env_id)

        if self.config.fully_observable:
            env = FullyObsWrapper(env)

        if self.config.max_steps is not None:
            env = gym.wrappers.TimeLimit(env, max_episode_steps=self.config.max_steps)

        self._env = env
        return env

    @property
    def env(self) -> "gym.Env":
        """Get or create environment."""
        if self._env is None:
            self.make_env()
        return self._env

    def reset(self, seed: Optional[int] = None) -> tuple[Any, dict]:
        """Reset environment and return initial observation."""
        self._step_count = 0
        obs, info = self.env.reset(seed=seed)
        return obs, info

    def step(self, action: int) -> tuple[Any, float, bool, bool, dict]:
        """Take a step in the environment."""
        self._step_count += 1
        return self.env.step(action)

    def sample_action(self) -> int:
        """Sample a random action."""
        return self.env.action_space.sample()

    def close(self) -> None:
        """Close environment."""
        if self._env is not None:
            self._env.close()
            self._env = None

    # === Memory Integration ===

    def record_observation(
        self,
        cmm: "CausalMemoryManager",
        obs: Any,
        info: dict,
        step: int,
        tags: Optional[list[str]] = None,
    ) -> str:
        """
        Record an observation as a memory record.

        Args:
            cmm: CausalMemoryManager instance
            obs: Observation from environment
            info: Info dict from environment
            step: Current step number
            tags: Additional tags

        Returns:
            Record ID
        """
        from reckon.memory import PayloadType

        if not self.config.record_observations:
            return ""

        # Convert observation to serializable format
        payload = self._serialize_observation(obs, info)

        base_tags = ["observation", "minigrid"]
        if tags:
            base_tags.extend(tags)

        # Add semantic tags based on observation content
        if "key" in str(info).lower() or self._contains_key(obs):
            base_tags.append("key")
        if "door" in str(info).lower() or self._contains_door(obs):
            base_tags.append("door")
        if "goal" in str(info).lower():
            base_tags.append("goal")

        cmm.set_step(step)
        return cmm.write(
            payload=payload,
            payload_type=PayloadType.OBSERVATION,
            tags=base_tags,
            source_op="minigrid_obs",
        )

    def record_action(
        self,
        cmm: "CausalMemoryManager",
        action: int,
        step: int,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Record an action as a memory record."""
        from reckon.memory import PayloadType

        if not self.config.record_actions:
            return ""

        action_names = ["left", "right", "forward", "pickup", "drop", "toggle", "done"]
        action_name = action_names[action] if action < len(action_names) else f"action_{action}"

        payload = {
            "action": action,
            "action_name": action_name,
        }

        base_tags = ["action", "minigrid", action_name]
        if tags:
            base_tags.extend(tags)

        cmm.set_step(step)
        return cmm.write(
            payload=payload,
            payload_type=PayloadType.ACTION,
            tags=base_tags,
            source_op="minigrid_action",
        )

    def record_reward(
        self,
        cmm: "CausalMemoryManager",
        reward: float,
        step: int,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Record a reward as a memory record."""
        from reckon.memory import PayloadType

        if not self.config.record_rewards:
            return ""

        if reward == 0:
            return ""  # Don't record zero rewards

        payload = {
            "reward": reward,
            "is_positive": reward > 0,
        }

        base_tags = ["reward", "minigrid"]
        if reward > 0:
            base_tags.append("positive_reward")
        else:
            base_tags.append("negative_reward")
        if tags:
            base_tags.extend(tags)

        cmm.set_step(step)
        return cmm.write(
            payload=payload,
            payload_type=PayloadType.REWARD,
            tags=base_tags,
            source_op="minigrid_reward",
            initial_utility=abs(reward),  # Higher utility for larger rewards
        )

    def _serialize_observation(self, obs: Any, info: dict) -> dict:
        """Convert observation to JSON-serializable dict."""
        import numpy as np

        if isinstance(obs, dict):
            # Already a dict (e.g., from wrapper)
            serialized = {}
            for k, v in obs.items():
                if isinstance(v, np.ndarray):
                    if self.config.compress_observations:
                        # Just store shape and key objects
                        serialized[k] = {"shape": list(v.shape), "dtype": str(v.dtype)}
                    else:
                        serialized[k] = v.tolist()
                else:
                    serialized[k] = v
        elif hasattr(obs, "tolist"):
            # NumPy array
            if self.config.compress_observations:
                serialized = {"shape": list(obs.shape), "dtype": str(obs.dtype)}
            else:
                serialized = {"image": obs.tolist()}
        else:
            serialized = {"obs": obs}

        # Add info
        serialized["info"] = {k: str(v) for k, v in info.items()}

        return serialized

    def _contains_key(self, obs: Any) -> bool:
        """Check if observation contains a key object."""
        import numpy as np
        if isinstance(obs, dict) and "image" in obs:
            img = np.array(obs["image"])
            # MiniGrid key object type = 5
            return np.any(img[:, :, 0] == 5)
        return False

    def _contains_door(self, obs: Any) -> bool:
        """Check if observation contains a door object."""
        import numpy as np
        if isinstance(obs, dict) and "image" in obs:
            img = np.array(obs["image"])
            # MiniGrid door object type = 4
            return np.any(img[:, :, 0] == 4)
        return False


# === Fallback traces for demo mode ===

DEMO_TRACE = [
    {"step": 0, "type": "obs", "payload": {"position": [1, 1], "objects": ["key_yellow"]}, "reward": 0},
    {"step": 1, "type": "action", "payload": {"action": 2, "name": "forward"}, "reward": 0},
    {"step": 2, "type": "obs", "payload": {"position": [2, 1], "objects": []}, "reward": 0},
    {"step": 3, "type": "action", "payload": {"action": 3, "name": "pickup"}, "reward": 0},
    {"step": 4, "type": "obs", "payload": {"position": [2, 1], "carrying": "key_yellow"}, "reward": 0},
    {"step": 5, "type": "action", "payload": {"action": 2, "name": "forward"}, "reward": 0},
    {"step": 6, "type": "obs", "payload": {"position": [3, 1], "objects": ["door_yellow"]}, "reward": 0},
    {"step": 7, "type": "action", "payload": {"action": 5, "name": "toggle"}, "reward": 1.0},
    {"step": 8, "type": "reward", "payload": {"reward": 1.0}, "reward": 1.0},
]


def get_demo_trace() -> list[dict]:
    """Get a demo trace when MiniGrid is not available."""
    return DEMO_TRACE.copy()


def run_demo_episode(cmm: "CausalMemoryManager", seed: int = 42, quiet: bool = False) -> dict:
    """
    Run a demo episode using fallback trace.

    Args:
        cmm: CausalMemoryManager instance
        seed: Seed (not used for demo, but kept for API compatibility)
        quiet: If False, prints fallback warning banner

    Returns:
        Episode result dict
    """
    from reckon.memory import PayloadType

    if not quiet:
        print('''
================================================================================
    WARNING: RUNNING FALLBACK TRACE (NOT REAL ENVIRONMENT)
================================================================================

    MiniGrid is not installed. Running PRE-RECORDED demo trace.

    To enable live runs:
        pip install minigrid gymnasium

================================================================================
''')

    trace = get_demo_trace()
    total_reward = 0

    for event in trace:
        step = event["step"]
        cmm.set_step(step)

        if event["type"] == "obs":
            cmm.write(
                payload=event["payload"],
                payload_type=PayloadType.OBSERVATION,
                tags=["observation", "demo"],
                source_op="demo_obs",
            )
        elif event["type"] == "action":
            cmm.write(
                payload=event["payload"],
                payload_type=PayloadType.ACTION,
                tags=["action", "demo", event["payload"]["name"]],
                source_op="demo_action",
            )
        elif event["type"] == "reward":
            reward = event["payload"]["reward"]
            total_reward += reward
            cmm.write(
                payload=event["payload"],
                payload_type=PayloadType.REWARD,
                tags=["reward", "demo"],
                source_op="demo_reward",
                initial_utility=abs(reward),
            )

    return {
        "success": total_reward > 0,
        "total_reward": total_reward,
        "steps": len(trace),
        "demo_mode": True,
    }
