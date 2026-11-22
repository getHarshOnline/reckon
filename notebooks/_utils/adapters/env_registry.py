"""
Environment registry for Reckon notebooks.

Provides a unified interface for accessing RL environments with
graceful fallback to replay traces when dependencies are missing.

Supported environments:
- MiniGrid MemoryEnv: Memory-critical, lightweight
- Memory Gym: Memory benchmark suite (optional)
- Gymnasium ToyText Taxi: Baseline familiarity
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Type, Union

__all__ = [
    "EnvSpec",
    "get_env",
    "list_envs",
    "check_env_available",
    "get_install_instructions",
    "print_fallback_banner",
]


@dataclass
class EnvSpec:
    """Specification for a registered environment."""
    name: str
    display_name: str
    env_id: str
    package: str
    install_cmd: str
    requires_memory: bool  # Whether memory is critical for this env
    description: str
    fallback_traces: Optional[str] = None  # Key for fallback traces


# Environment registry
ENV_REGISTRY: dict[str, EnvSpec] = {
    # MiniGrid Memory Environments
    "minigrid_memory": EnvSpec(
        name="minigrid_memory",
        display_name="MiniGrid MemoryEnv",
        env_id="MiniGrid-MemoryS7-v0",
        package="minigrid",
        install_cmd="pip install minigrid gymnasium",
        requires_memory=True,
        description=(
            "Agent must remember object seen at start of corridor to choose "
            "correct door at the end. Memory is critical for success."
        ),
        fallback_traces="memory",
    ),
    "minigrid_keycorridor": EnvSpec(
        name="minigrid_keycorridor",
        display_name="MiniGrid KeyCorridor",
        env_id="MiniGrid-KeyCorridorS3R1-v0",
        package="minigrid",
        install_cmd="pip install minigrid gymnasium",
        requires_memory=True,
        description=(
            "Agent must pick up key and use it to unlock door. "
            "Requires remembering key location."
        ),
        fallback_traces="memory",
    ),
    "minigrid_unlock": EnvSpec(
        name="minigrid_unlock",
        display_name="MiniGrid Unlock",
        env_id="MiniGrid-Unlock-v0",
        package="minigrid",
        install_cmd="pip install minigrid gymnasium",
        requires_memory=True,
        description="Simple key-door task.",
        fallback_traces="memory",
    ),

    # Memory Gym Environments
    "memory_gym_mortar": EnvSpec(
        name="memory_gym_mortar",
        display_name="Memory Gym Mortar Mayhem",
        env_id="MortarMayhem-v0",
        package="memory_gym",
        install_cmd="pip install memory-gym",
        requires_memory=True,
        description=(
            "Dodge mortars based on remembered pattern. "
            "Part of Memory Gym benchmark suite."
        ),
        fallback_traces="memory",
    ),
    "memory_gym_mystery": EnvSpec(
        name="memory_gym_mystery",
        display_name="Memory Gym Mystery Path",
        env_id="MysteryPath-v0",
        package="memory_gym",
        install_cmd="pip install memory-gym",
        requires_memory=True,
        description=(
            "Navigate maze using remembered path indicators. "
            "Part of Memory Gym benchmark suite."
        ),
        fallback_traces="memory",
    ),

    # Gymnasium ToyText
    "taxi": EnvSpec(
        name="taxi",
        display_name="Gymnasium Taxi",
        env_id="Taxi-v3",
        package="gymnasium",
        install_cmd="pip install gymnasium",
        requires_memory=False,
        description=(
            "Classic Taxi environment. Pick up and drop off passengers. "
            "Good baseline for testing without memory requirements."
        ),
        fallback_traces="taxi",
    ),
    "frozen_lake": EnvSpec(
        name="frozen_lake",
        display_name="Gymnasium FrozenLake",
        env_id="FrozenLake-v1",
        package="gymnasium",
        install_cmd="pip install gymnasium",
        requires_memory=False,
        description="Navigate frozen lake to goal. Slippery by default.",
        fallback_traces="taxi",
    ),
    "cliff_walking": EnvSpec(
        name="cliff_walking",
        display_name="Gymnasium CliffWalking",
        env_id="CliffWalking-v0",
        package="gymnasium",
        install_cmd="pip install gymnasium",
        requires_memory=False,
        description="Navigate cliff edge to goal.",
        fallback_traces="taxi",
    ),

    # TextWorld
    "textworld": EnvSpec(
        name="textworld",
        display_name="TextWorld",
        env_id="textworld",
        package="textworld",
        install_cmd="pip install textworld",
        requires_memory=True,
        description="Text-based adventure game. Requires remembering items and locations.",
        fallback_traces="taxi",  # Will use custom textworld fallback
    ),
}


def _check_package_available(package: str) -> bool:
    """Check if a Python package is available."""
    try:
        __import__(package)
        return True
    except ImportError:
        return False


def _create_gymnasium_env(env_id: str, **kwargs) -> Any:
    """Create a Gymnasium environment."""
    import gymnasium as gym
    return gym.make(env_id, **kwargs)


def _create_minigrid_env(env_id: str, **kwargs) -> Any:
    """Create a MiniGrid environment."""
    import gymnasium as gym
    import minigrid  # noqa: F401 - registers environments
    return gym.make(env_id, **kwargs)


def _create_memory_gym_env(env_id: str, **kwargs) -> Any:
    """Create a Memory Gym environment."""
    import gymnasium as gym
    import memory_gym  # noqa: F401 - registers environments
    return gym.make(env_id, **kwargs)


def print_fallback_banner(package: str, install_cmd: str) -> None:
    """
    Print a LOUD banner when using fallback replay traces.

    This makes it IMPOSSIBLE to miss that results are from pre-recorded data,
    not live environment interaction.
    """
    banner = f'''
================================================================================
    WARNING: RUNNING FALLBACK TRACE (NOT REAL ENVIRONMENT)
================================================================================

    {package} is not installed. You are running a PRE-RECORDED demo trace.
    Results are NOT from live environment interaction!

    To enable live runs:
        {install_cmd}

================================================================================
'''
    print(banner)


def _create_fallback_env(spec: EnvSpec) -> Any:
    """Create a fallback replay environment."""
    from .gym_env import ReplayTraceEnv, get_demo_traces

    traces = get_demo_traces(spec.fallback_traces or "taxi")
    return ReplayTraceEnv(traces, env_id=spec.env_id)


def check_env_available(name: str) -> bool:
    """
    Check if an environment's dependencies are available.

    Args:
        name: Environment name from registry

    Returns:
        True if environment can be created, False otherwise
    """
    if name not in ENV_REGISTRY:
        return False

    spec = ENV_REGISTRY[name]
    return _check_package_available(spec.package)


def get_env(
    name: str,
    fallback: bool = True,
    verbose: bool = True,
    **kwargs,
) -> tuple[Any, bool]:
    """
    Get an environment by name.

    If dependencies are missing and fallback=True, returns a ReplayTraceEnv.
    Otherwise raises ImportError.

    Args:
        name: Environment name from registry
        fallback: If True, use fallback env when deps missing
        verbose: If True, print install instructions when using fallback
        **kwargs: Additional kwargs passed to environment creation

    Returns:
        Tuple of (environment, is_real) where is_real indicates if this
        is the real environment or a fallback

    Raises:
        ValueError: If environment name is unknown
        ImportError: If dependencies missing and fallback=False

    Example:
        env, is_real = get_env("minigrid_memory")
        if not is_real:
            print("Using fallback traces")
        obs, info = env.reset(seed=42)
    """
    if name not in ENV_REGISTRY:
        available = ", ".join(ENV_REGISTRY.keys())
        raise ValueError(f"Unknown environment: {name}. Available: {available}")

    spec = ENV_REGISTRY[name]

    # Check if package is available
    if _check_package_available(spec.package):
        # Create real environment
        try:
            if spec.package == "minigrid":
                env = _create_minigrid_env(spec.env_id, **kwargs)
            elif spec.package == "memory_gym":
                env = _create_memory_gym_env(spec.env_id, **kwargs)
            elif spec.package == "gymnasium":
                env = _create_gymnasium_env(spec.env_id, **kwargs)
            else:
                # Generic gymnasium-style creation
                env = _create_gymnasium_env(spec.env_id, **kwargs)
            return env, True
        except Exception as e:
            if verbose:
                print(f"Failed to create {spec.display_name}: {e}")
            if not fallback:
                raise

    # Package not available or creation failed
    if not fallback:
        raise ImportError(
            f"{spec.display_name} requires: {spec.install_cmd}"
        )

    if verbose:
        # Print LOUD banner - impossible to miss
        print_fallback_banner(spec.display_name, spec.install_cmd)

    return _create_fallback_env(spec), False


def list_envs(
    filter_available: bool = False,
    filter_memory: bool = False,
) -> list[EnvSpec]:
    """
    List registered environments.

    Args:
        filter_available: If True, only return envs with available deps
        filter_memory: If True, only return memory-critical envs

    Returns:
        List of EnvSpec objects
    """
    envs = list(ENV_REGISTRY.values())

    if filter_available:
        envs = [e for e in envs if check_env_available(e.name)]

    if filter_memory:
        envs = [e for e in envs if e.requires_memory]

    return envs


def get_install_instructions(envs: Optional[list[str]] = None) -> str:
    """
    Get installation instructions for environments.

    Args:
        envs: List of env names, or None for all

    Returns:
        Formatted installation instructions
    """
    lines = ["# Environment Installation Instructions", ""]

    if envs is None:
        envs = list(ENV_REGISTRY.keys())

    # Group by package
    packages: dict[str, list[EnvSpec]] = {}
    for name in envs:
        if name in ENV_REGISTRY:
            spec = ENV_REGISTRY[name]
            if spec.package not in packages:
                packages[spec.package] = []
            packages[spec.package].append(spec)

    for package, specs in packages.items():
        lines.append(f"## {package}")
        lines.append("")
        lines.append(f"```bash")
        lines.append(specs[0].install_cmd)
        lines.append("```")
        lines.append("")
        lines.append("Environments:")
        for spec in specs:
            available = "OK" if check_env_available(spec.name) else "NOT INSTALLED"
            lines.append(f"- {spec.display_name} ({spec.env_id}): [{available}]")
            lines.append(f"  {spec.description}")
        lines.append("")

    return "\n".join(lines)


def print_env_status() -> None:
    """Print status of all registered environments."""
    print("=" * 70)
    print("Reckon Environment Registry Status")
    print("=" * 70)

    # Group by package
    current_package = None
    for spec in ENV_REGISTRY.values():
        if spec.package != current_package:
            current_package = spec.package
            print(f"\n{spec.package}:")
            print("-" * 40)

        available = check_env_available(spec.name)
        status = "OK" if available else "MISSING"
        memory = "MEMORY" if spec.requires_memory else "      "

        print(f"  [{status:7}] [{memory}] {spec.name:25} {spec.env_id}")

    print("\n" + "=" * 70)

    # Print install commands for missing packages
    missing_packages = set()
    for spec in ENV_REGISTRY.values():
        if not check_env_available(spec.name):
            missing_packages.add((spec.package, spec.install_cmd))

    if missing_packages:
        print("\nTo install missing packages:")
        for package, cmd in sorted(missing_packages):
            print(f"  {cmd}")
    else:
        print("\nAll packages available!")
