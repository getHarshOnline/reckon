"""
Gymnasium environment wrapper for Reckon notebooks.

Provides a consistent interface for interacting with Gymnasium environments
and converting observations to Reckon memory records.

Requirements:
    pip install gymnasium
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional, Union

__all__ = [
    "GymEnvConfig",
    "GymEnvWrapper",
    "obs_to_record",
    "action_space_to_text",
    "GYMNASIUM_AVAILABLE",
    "get_install_command",
]

# Guarded imports
try:
    import gymnasium as gym
    from gymnasium import spaces
    GYMNASIUM_AVAILABLE = True
except ImportError:
    GYMNASIUM_AVAILABLE = False
    gym = None
    spaces = None


def get_install_command() -> str:
    """Get installation command for Gymnasium."""
    return "pip install gymnasium"


def check_available() -> bool:
    """Check if Gymnasium is available."""
    return GYMNASIUM_AVAILABLE


@dataclass
class GymEnvConfig:
    """Configuration for Gymnasium environment wrapper."""
    env_id: str = "Taxi-v3"
    max_episode_steps: Optional[int] = None
    render_mode: Optional[str] = None
    record_observations: bool = True
    record_actions: bool = True
    record_rewards: bool = True
    obs_format: str = "auto"  # "auto", "json", "text"


class GymEnvWrapper:
    """
    Wrapper around Gymnasium environments for Reckon integration.

    Provides a consistent interface for reset/step operations and
    utilities for converting observations to memory records.

    Example:
        wrapper = GymEnvWrapper(GymEnvConfig(env_id="Taxi-v3"))
        obs, info = wrapper.reset(seed=42)
        action = wrapper.sample_action()
        obs, reward, terminated, truncated, info = wrapper.step(action)
        wrapper.close()
    """

    def __init__(self, config: Optional[GymEnvConfig] = None):
        """
        Initialize wrapper.

        Args:
            config: Environment configuration

        Raises:
            ImportError: If Gymnasium is not installed
        """
        if not GYMNASIUM_AVAILABLE:
            raise ImportError(
                f"Gymnasium not available. Install with: {get_install_command()}"
            )

        self.config = config or GymEnvConfig()
        self._env: Optional[gym.Env] = None
        self._step_count: int = 0

    def make_env(self) -> gym.Env:
        """Create and return the environment."""
        kwargs = {}
        if self.config.render_mode:
            kwargs["render_mode"] = self.config.render_mode
        if self.config.max_episode_steps:
            kwargs["max_episode_steps"] = self.config.max_episode_steps

        self._env = gym.make(self.config.env_id, **kwargs)
        return self._env

    @property
    def env(self) -> gym.Env:
        """Get or create environment."""
        if self._env is None:
            self.make_env()
        return self._env

    def reset(self, seed: Optional[int] = None) -> tuple[Any, dict]:
        """
        Reset environment and return initial observation.

        Args:
            seed: Random seed for reproducibility

        Returns:
            Tuple of (observation, info dict)
        """
        self._step_count = 0
        return self.env.reset(seed=seed)

    def step(self, action: Any) -> tuple[Any, float, bool, bool, dict]:
        """
        Take a step in the environment.

        Args:
            action: Action to take

        Returns:
            Tuple of (observation, reward, terminated, truncated, info)
        """
        self._step_count += 1
        return self.env.step(action)

    def sample_action(self) -> Any:
        """Sample a random action."""
        return self.env.action_space.sample()

    def close(self) -> None:
        """Close environment."""
        if self._env is not None:
            self._env.close()
            self._env = None

    @property
    def action_space(self) -> Any:
        """Get action space."""
        return self.env.action_space

    @property
    def observation_space(self) -> Any:
        """Get observation space."""
        return self.env.observation_space

    def get_action_meanings(self) -> list[str]:
        """
        Get human-readable action meanings if available.

        Returns:
            List of action descriptions or generic names
        """
        if hasattr(self.env, "get_action_meanings"):
            return self.env.get_action_meanings()

        # Generate generic names for discrete actions
        if GYMNASIUM_AVAILABLE and isinstance(self.env.action_space, spaces.Discrete):
            return [f"action_{i}" for i in range(self.env.action_space.n)]

        return ["unknown_action"]


def obs_to_record(
    obs: Any,
    info: dict,
    step: int,
    env_id: str = "unknown",
) -> dict[str, Any]:
    """
    Convert a Gymnasium observation to a Reckon memory record payload.

    Handles common observation types:
    - Discrete (int): Simple state ID
    - Box (ndarray): Continuous observations
    - Dict: Composite observations
    - Text: String observations

    Args:
        obs: Observation from environment
        info: Info dict from environment
        step: Current step number
        env_id: Environment identifier

    Returns:
        Record payload suitable for CMM.write()
    """
    payload = {
        "step": step,
        "env_id": env_id,
    }

    # Handle different observation types
    if isinstance(obs, int):
        # Discrete observation (e.g., Taxi state)
        payload["state"] = obs
        payload["type"] = "discrete"

    elif hasattr(obs, "tolist"):
        # NumPy array
        try:
            import numpy as np
            if obs.size <= 100:  # Small enough to store fully
                payload["observation"] = obs.tolist()
            else:
                # Store summary statistics
                payload["observation_shape"] = list(obs.shape)
                payload["observation_mean"] = float(np.mean(obs))
                payload["observation_std"] = float(np.std(obs))
            payload["type"] = "continuous"
        except ImportError:
            payload["observation"] = str(obs)
            payload["type"] = "array"

    elif isinstance(obs, dict):
        # Dict observation
        payload["observation"] = _serialize_dict(obs)
        payload["type"] = "dict"

    elif isinstance(obs, str):
        # Text observation
        payload["text"] = obs
        payload["type"] = "text"

    else:
        # Fallback
        payload["observation"] = str(obs)
        payload["type"] = "unknown"

    # Include relevant info
    if info:
        payload["info"] = _serialize_dict(info)

    return payload


def _serialize_dict(d: dict) -> dict:
    """Serialize a dict to JSON-compatible format."""
    result = {}
    for k, v in d.items():
        if hasattr(v, "tolist"):
            result[k] = v.tolist()
        elif isinstance(v, (int, float, str, bool, type(None))):
            result[k] = v
        elif isinstance(v, dict):
            result[k] = _serialize_dict(v)
        elif isinstance(v, (list, tuple)):
            result[k] = [str(x) for x in v]
        else:
            result[k] = str(v)
    return result


def action_space_to_text(
    action_space: Any,
    action_meanings: Optional[list[str]] = None,
) -> str:
    """
    Convert action space to text description for LLM policy mode.

    Useful when using an LLM as a policy - provides the action space
    description in natural language.

    Args:
        action_space: Gymnasium action space
        action_meanings: Optional human-readable action names

    Returns:
        Text description of available actions

    Example:
        >>> desc = action_space_to_text(env.action_space)
        >>> print(desc)
        "Available actions (Discrete(6)):
         0: action_0
         1: action_1
         ...
        "
    """
    if not GYMNASIUM_AVAILABLE:
        return "Action space: unknown (Gymnasium not available)"

    lines = [f"Available actions ({action_space}):"]

    if isinstance(action_space, spaces.Discrete):
        n_actions = action_space.n
        if action_meanings and len(action_meanings) == n_actions:
            for i, meaning in enumerate(action_meanings):
                lines.append(f"  {i}: {meaning}")
        else:
            for i in range(n_actions):
                lines.append(f"  {i}: action_{i}")

    elif isinstance(action_space, spaces.Box):
        shape = action_space.shape
        low = action_space.low
        high = action_space.high
        lines.append(f"  Shape: {shape}")
        lines.append(f"  Range: [{low.min():.2f}, {high.max():.2f}]")
        lines.append("  (Provide continuous values as JSON array)")

    elif isinstance(action_space, spaces.MultiDiscrete):
        lines.append(f"  Dimensions: {action_space.nvec}")
        lines.append("  (Provide values as JSON array)")

    else:
        lines.append(f"  Type: {type(action_space).__name__}")

    return "\n".join(lines)


def parse_llm_action(
    response: str,
    action_space: Any,
) -> Any:
    """
    Parse LLM response to get action.

    Expects JSON with action_index for discrete spaces.

    Args:
        response: LLM response text
        action_space: Gymnasium action space

    Returns:
        Parsed action

    Raises:
        ValueError: If parsing fails or action is invalid
    """
    # Clean response
    text = response.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Parse JSON
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    if not GYMNASIUM_AVAILABLE:
        raise ValueError("Gymnasium not available")

    # Handle different action space types
    if isinstance(action_space, spaces.Discrete):
        if "action_index" not in parsed:
            raise ValueError("Missing 'action_index' in response")

        action_idx = parsed["action_index"]
        if not isinstance(action_idx, int):
            raise ValueError(f"action_index must be int, got {type(action_idx)}")

        if action_idx < 0 or action_idx >= action_space.n:
            raise ValueError(f"action_index {action_idx} out of range [0, {action_space.n})")

        return action_idx

    elif isinstance(action_space, spaces.Box):
        if "action" not in parsed:
            raise ValueError("Missing 'action' in response")

        action = parsed["action"]
        try:
            import numpy as np
            action = np.array(action, dtype=action_space.dtype)
            action = np.clip(action, action_space.low, action_space.high)
            return action
        except ImportError:
            return action

    else:
        if "action" in parsed:
            return parsed["action"]
        raise ValueError(f"Unsupported action space type: {type(action_space)}")


# =============================================================================
# Replay Trace Environment (fallback when deps missing)
# =============================================================================

class ReplayTraceEnv:
    """
    Replay a pre-recorded trace when real environment is unavailable.

    This allows notebooks to run in demo mode without actual RL dependencies.
    """

    def __init__(
        self,
        traces: list[dict[str, Any]],
        env_id: str = "replay",
    ):
        """
        Initialize with pre-recorded traces.

        Args:
            traces: List of step dicts with obs, reward, terminated, info
            env_id: Identifier for this replay environment
        """
        self.traces = traces
        self.env_id = env_id
        self._step_idx = 0
        self._episode_traces: list[dict] = []
        self._current_trace_idx = 0

    def reset(self, seed: Optional[int] = None) -> tuple[Any, dict]:
        """Reset to beginning of trace."""
        self._step_idx = 0
        if seed is not None:
            self._current_trace_idx = seed % max(len(self.traces), 1)
        self._episode_traces = self.traces[self._current_trace_idx] \
            if isinstance(self.traces[0], list) else self.traces

        if self._episode_traces:
            first = self._episode_traces[0]
            return first.get("obs", 0), first.get("info", {"replay": True})
        return 0, {"replay": True}

    def step(self, action: Any) -> tuple[Any, float, bool, bool, dict]:
        """Return next step from trace."""
        self._step_idx += 1

        if self._step_idx < len(self._episode_traces):
            step_data = self._episode_traces[self._step_idx]
            return (
                step_data.get("obs", 0),
                step_data.get("reward", 0.0),
                step_data.get("terminated", False),
                step_data.get("truncated", False),
                step_data.get("info", {"replay": True}),
            )

        # Episode ended
        return 0, 0.0, True, False, {"replay": True, "done": True}

    def sample_action(self) -> int:
        """Return action from trace or 0."""
        if self._step_idx < len(self._episode_traces):
            return self._episode_traces[self._step_idx].get("action", 0)
        return 0

    def close(self) -> None:
        """No-op for replay env."""
        pass

    @property
    def action_space(self):
        """Return a mock discrete action space."""
        if GYMNASIUM_AVAILABLE:
            return spaces.Discrete(6)
        # Fallback mock
        return type("MockDiscrete", (), {"n": 6, "sample": lambda: 0})()


# Demo traces for Taxi-v3-like environment
TAXI_DEMO_TRACES = [
    # Episode 1: Simple pickup and dropoff
    {"obs": 123, "reward": 0, "action": 4, "terminated": False, "info": {}},  # Pickup
    {"obs": 124, "reward": -1, "action": 0, "terminated": False, "info": {}},  # South
    {"obs": 125, "reward": -1, "action": 0, "terminated": False, "info": {}},  # South
    {"obs": 126, "reward": -1, "action": 1, "terminated": False, "info": {}},  # North
    {"obs": 127, "reward": 20, "action": 5, "terminated": True, "info": {}},  # Dropoff
]

# Demo traces for MiniGrid MemoryEnv-like environment
MEMORY_ENV_DEMO_TRACES = [
    {"obs": {"image": [[0, 0, 0]], "direction": 0}, "reward": 0, "action": 2, "terminated": False, "info": {"step": 0}},
    {"obs": {"image": [[1, 0, 0]], "direction": 0}, "reward": 0, "action": 2, "terminated": False, "info": {"step": 1}},
    {"obs": {"image": [[0, 1, 0]], "direction": 0}, "reward": 0, "action": 2, "terminated": False, "info": {"step": 2}},
    {"obs": {"image": [[0, 0, 1]], "direction": 0}, "reward": 1, "action": 2, "terminated": True, "info": {"step": 3}},
]


def get_demo_traces(env_type: str = "taxi") -> list[dict]:
    """Get demo traces for fallback mode."""
    if env_type == "taxi":
        return TAXI_DEMO_TRACES.copy()
    elif env_type == "memory":
        return MEMORY_ENV_DEMO_TRACES.copy()
    else:
        return TAXI_DEMO_TRACES.copy()
