"""
Environment adapters for Reckon notebooks.

Each adapter provides a consistent interface for integrating
external environments (RL, text games, conversation, etc.) with the CMM.

Adapters use guarded imports - they return None or raise ImportError
when optional dependencies are missing.

Modules:
    minigrid_adapter: MiniGrid environment integration
    textworld_adapter: TextWorld text-based game integration
    ollama_client: Local Ollama LLM integration
    tool_env: Tool-using conversation environment (no deps)
    gym_env: Gymnasium environment wrapper
    env_registry: Unified environment registry with fallbacks
"""

from typing import Optional, Type

# Lazy imports to avoid requiring all deps
_ADAPTERS: dict[str, str] = {
    "minigrid": ".minigrid_adapter",
    "textworld": ".textworld_adapter",
    "ollama": ".ollama_client",
    "tool_env": ".tool_env",
    "gym": ".gym_env",
    "registry": ".env_registry",
}


def get_adapter(name: str) -> Optional[Type]:
    """
    Get an adapter class by name.

    Args:
        name: Adapter name ("minigrid", "textworld", "ollama", etc.)

    Returns:
        Adapter class or None if dependency not available

    Raises:
        ValueError: If adapter name is unknown
    """
    if name not in _ADAPTERS:
        raise ValueError(f"Unknown adapter: {name}. Available: {list(_ADAPTERS.keys())}")

    module_name = _ADAPTERS[name]

    try:
        import importlib
        module = importlib.import_module(module_name, package=__name__)

        # Map adapter names to their main classes
        class_names = {
            "minigrid": "MinigridAdapter",
            "textworld": "TextworldAdapter",
            "ollama": "OllamaConfig",  # Return config as main export
            "tool_env": "ToolEnv",
            "gym": "GymEnvWrapper",
            "registry": None,  # Module-level functions
        }

        class_name = class_names.get(name)
        if class_name:
            return getattr(module, class_name)
        return module

    except ImportError as e:
        print(f"Adapter '{name}' not available: {e}")
        print(f"Install required package to enable this adapter.")
        return None


def list_adapters() -> list[str]:
    """List available adapter names."""
    return list(_ADAPTERS.keys())


def check_adapter(name: str) -> bool:
    """Check if an adapter's dependencies are available."""
    return get_adapter(name) is not None


# Environment modules load on explicit import; conversation use does not load
# optional game engines or their native display libraries.

# These adapters have no external dependencies and can be imported directly
from .tool_env import (
    ToolEnv,
    ToolEnvConfig,
    Episode,
    EpisodeMetrics,
    StepResult,
    get_demo_episodes,
    run_demo_episode,
)

from .ollama_client import (
    OllamaConfig,
    ollama_healthcheck,
    ollama_list_models,
    ollama_chat,
    ollama_chat_json,
    parse_agent_response,
    OLLAMA_AVAILABLE,
    SimulatedOllamaBackend,
    AGENT_SYSTEM_PROMPT,
)

from .gym_env import (
    GymEnvConfig,
    GymEnvWrapper,
    ReplayTraceEnv,
    obs_to_record,
    action_space_to_text,
    parse_llm_action,
    GYMNASIUM_AVAILABLE,
    get_demo_traces,
)

from .env_registry import (
    EnvSpec,
    get_env,
    list_envs,
    check_env_available,
    get_install_instructions,
    print_env_status,
    print_fallback_banner,
)


__all__ = [
    # Registry functions
    "get_adapter",
    "list_adapters",
    "check_adapter",
    # Modules
    "minigrid_adapter",
    "textworld_adapter",
    # Tool Environment (no deps)
    "ToolEnv",
    "ToolEnvConfig",
    "Episode",
    "EpisodeMetrics",
    "StepResult",
    "get_demo_episodes",
    "run_demo_episode",
    # Ollama Client
    "OllamaConfig",
    "ollama_healthcheck",
    "ollama_list_models",
    "ollama_chat",
    "ollama_chat_json",
    "parse_agent_response",
    "OLLAMA_AVAILABLE",
    "SimulatedOllamaBackend",
    "AGENT_SYSTEM_PROMPT",
    # Gymnasium
    "GymEnvConfig",
    "GymEnvWrapper",
    "ReplayTraceEnv",
    "obs_to_record",
    "action_space_to_text",
    "parse_llm_action",
    "GYMNASIUM_AVAILABLE",
    "get_demo_traces",
    # Environment Registry
    "EnvSpec",
    "get_env",
    "list_envs",
    "check_env_available",
    "get_install_instructions",
    "print_env_status",
    "print_fallback_banner",
]
