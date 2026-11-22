"""
Configuration management for Reckon notebooks.

Provides dataclass-based configuration with deterministic hashing
for reproducible artifact directories and experiment tracking.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

__all__ = [
    "NotebookConfig",
    "hash_config",
    "print_config",
    "print_repro_stamp",
    "get_git_hash",
    "get_python_version",
    "get_dependency_versions",
]


def get_git_hash() -> str:
    """
    Get current git commit hash.

    Returns:
        Short git hash (7 chars) or 'unknown' if not in a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # Git not available or not in a repo
        pass
    return "unknown"


def get_python_version() -> str:
    """Get Python version string."""
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_dependency_versions() -> dict[str, str]:
    """
    Get versions of key dependencies.

    Returns:
        Dictionary mapping package name to version string.
    """
    versions = {}

    # Core dependencies
    packages = ["numpy", "matplotlib", "reckon"]

    for pkg in packages:
        try:
            module = __import__(pkg)
            version = getattr(module, "__version__", "unknown")
            versions[pkg] = version
        except ImportError:
            versions[pkg] = "not installed"

    return versions


@dataclass
class NotebookConfig:
    """
    Configuration for a notebook run.

    All notebooks should use this dataclass to ensure consistent
    configuration, reproducible artifact hashing, and proper metadata tracking.

    Attributes:
        notebook_name: Identifier for this notebook (used in artifact paths).
        run_mode: Either "demo" (quick validation) or "paper" (full statistics).
        seed: Base random seed for reproducibility.
        seed_count: Number of seed iterations for paper mode.
        budget_slots: Memory budget in number of slots.
        budget_bytes: Optional memory budget in bytes.
        budget_tokens: Optional memory budget in tokens.
        task_name: Task identifier (e.g., "keydoor", "conversation").
        num_episodes: Number of episodes to run.
        policy_name: Retention policy identifier.
        evidence_weight: Weight parameter for EvidencePerBytePolicy.
        eval_n_trials: Number of trials for causal evaluation.
        eval_delta_threshold: Minimum effect size for causal significance.
        eval_alpha: Significance level for statistical tests.
        git_hash: Auto-populated git commit hash.
        timestamp: Auto-populated ISO timestamp.
        custom: Dictionary for task-specific parameters.
    """

    # Identity
    notebook_name: str
    run_mode: str = "demo"

    # Reproducibility
    seed: int = 42
    seed_count: int = 1

    # Memory budget
    budget_slots: int = 100
    budget_bytes: Optional[int] = None
    budget_tokens: Optional[int] = None

    # Task parameters
    task_name: str = "keydoor"
    num_episodes: int = 10

    # Policy
    policy_name: str = "fifo"
    evidence_weight: float = 0.5

    # Evaluator
    eval_n_trials: int = 10
    eval_delta_threshold: float = 0.05
    eval_alpha: float = 0.05

    # Metadata (excluded from hash)
    git_hash: str = field(default_factory=get_git_hash)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Custom parameters (included in hash)
    custom: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        valid_modes = {"demo", "paper"}
        if self.run_mode not in valid_modes:
            raise ValueError(f"run_mode must be one of {valid_modes}, got '{self.run_mode}'")

        if self.seed < 0:
            raise ValueError(f"seed must be non-negative, got {self.seed}")

        if self.budget_slots <= 0:
            raise ValueError(f"budget_slots must be positive, got {self.budget_slots}")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert configuration to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotebookConfig:
        """
        Create configuration from dictionary.

        Unknown keys are ignored to allow forward compatibility.
        """
        if "causal_weight" in data or data.get("policy_name") == "causal":
            raise ValueError("Read earlier retention configuration with its original source revision")
        # Filter to known fields only
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


def hash_config(config: NotebookConfig) -> str:
    """
    Generate a stable hash from configuration.

    The hash excludes volatile fields (timestamp, git_hash) to ensure
    that the same experimental configuration produces the same hash
    across multiple runs.

    Args:
        config: Notebook configuration to hash.

    Returns:
        12-character hexadecimal hash string.
    """
    # Fields that affect experiment outcome (exclude metadata)
    hashable = {
        "notebook_name": config.notebook_name,
        "run_mode": config.run_mode,
        "seed": config.seed,
        "seed_count": config.seed_count,
        "budget_slots": config.budget_slots,
        "budget_bytes": config.budget_bytes,
        "budget_tokens": config.budget_tokens,
        "task_name": config.task_name,
        "num_episodes": config.num_episodes,
        "policy_name": config.policy_name,
        "evidence_weight": config.evidence_weight,
        "eval_n_trials": config.eval_n_trials,
        "eval_delta_threshold": config.eval_delta_threshold,
        "eval_alpha": config.eval_alpha,
        "custom": config.custom,
    }

    # Stable JSON serialization with sorted keys
    json_str = json.dumps(hashable, sort_keys=True, default=str)

    return hashlib.sha256(json_str.encode()).hexdigest()[:12]


def print_config(config: NotebookConfig) -> None:
    """
    Pretty-print configuration to stdout.

    Displays all key configuration parameters in a formatted block
    suitable for notebook output cells.
    """
    print("=" * 60)
    print(f"NOTEBOOK: {config.notebook_name}")
    print(f"MODE: {config.run_mode.upper()}")
    print(f"GIT: {config.git_hash}")
    print(f"TIME: {config.timestamp}")
    print("-" * 60)
    print(f"Seed: {config.seed} (x{config.seed_count})")

    budget_parts = [f"{config.budget_slots} slots"]
    if config.budget_bytes:
        budget_parts.append(f"{config.budget_bytes} bytes")
    if config.budget_tokens:
        budget_parts.append(f"{config.budget_tokens} tokens")
    print(f"Budget: {', '.join(budget_parts)}")

    print(f"Task: {config.task_name} ({config.num_episodes} episodes)")

    policy_str = config.policy_name
    if config.policy_name == "evidence_per_byte":
        policy_str += f" (weight={config.evidence_weight})"
    print(f"Policy: {policy_str}")

    if config.custom:
        print(f"Custom: {config.custom}")
    print(f"Config hash: {hash_config(config)}")
    print("=" * 60)


def print_repro_stamp(config: NotebookConfig) -> None:
    """
    Print reproducibility stamp for publication quality.

    This stamp should appear in every notebook to enable exact
    reproduction of results. It includes git hash, Python version,
    and key dependency versions.

    Args:
        config: Notebook configuration (for git hash and mode).
    """
    deps = get_dependency_versions()
    dep_str = ", ".join(f"{k}={v}" for k, v in deps.items())

    print("-" * 60)
    print("REPRODUCIBILITY STAMP")
    print(f"  Git commit: {config.git_hash}")
    print(f"  Python: {get_python_version()}")
    print(f"  Dependencies: {dep_str}")
    print(f"  Run mode: {config.run_mode}")
    print(f"  Timestamp: {config.timestamp}")
    print("-" * 60)
