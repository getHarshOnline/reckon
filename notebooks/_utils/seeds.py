"""
Seed management for reproducible experiments.

Provides utilities for setting random seeds across all common
random number generators, enabling deterministic experiment runs.
"""

from __future__ import annotations

import random
from typing import Any, Optional

__all__ = ["set_all_seeds", "get_seed_range", "SeedContext"]


def set_all_seeds(seed: int, verbose: bool = False) -> None:
    """
    Set random seeds for all available RNG sources.

    This function ensures reproducibility by setting consistent seeds
    across Python's random module, NumPy, PyTorch, and TensorFlow.
    Missing packages are silently skipped.

    Args:
        seed: The seed value to use (must be non-negative).
        verbose: If True, print confirmation for each RNG set.

    Example:
        set_all_seeds(42)  # Deterministic execution
        result = run_experiment()  # Same results every time
    """
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")

    # Python random (always available)
    random.seed(seed)
    if verbose:
        print(f"Python random seed set to {seed}")

    # NumPy (optional)
    try:
        import numpy as np
        np.random.seed(seed)
        if verbose:
            print(f"NumPy seed set to {seed}")
    except ImportError:
        if verbose:
            print("NumPy not available, skipping")

    # PyTorch (optional)
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        if verbose:
            print(f"PyTorch seed set to {seed}")
    except ImportError:
        if verbose:
            print("PyTorch not available, skipping")

    # TensorFlow (optional)
    try:
        import tensorflow as tf
        tf.random.set_seed(seed)
        if verbose:
            print(f"TensorFlow seed set to {seed}")
    except ImportError:
        if verbose:
            print("TensorFlow not available, skipping")


def get_seed_range(base_seed: int, count: int) -> list[int]:
    """
    Generate a deterministic range of seeds.

    Creates a contiguous sequence of seeds starting from base_seed,
    useful for running multiple independent trials.

    Args:
        base_seed: Starting seed value.
        count: Number of seeds to generate.

    Returns:
        List of seeds [base_seed, base_seed+1, ..., base_seed+count-1].

    Example:
        seeds = get_seed_range(42, 5)
        # Returns [42, 43, 44, 45, 46]
        for seed in seeds:
            set_all_seeds(seed)
            run_trial()
    """
    if count < 0:
        raise ValueError(f"count must be non-negative, got {count}")
    return list(range(base_seed, base_seed + count))


class SeedContext:
    """
    Context manager for temporary seed setting.

    Useful when you need to run a specific block of code with a
    deterministic seed while preserving the outer RNG state.

    Example:
        # Outer code uses its own random state
        x = random.random()

        with SeedContext(123):
            # This block always produces the same result
            y = random.random()  # Always 0.052363...

        # Outer random state is restored
        z = random.random()  # Continues from where x left off
    """

    def __init__(self, seed: int) -> None:
        """
        Initialize context with target seed.

        Args:
            seed: The seed to use within this context.
        """
        self.seed = seed
        self._random_state: Optional[tuple[Any, ...]] = None
        self._numpy_state: Optional[dict[str, Any]] = None

    def __enter__(self) -> SeedContext:
        """Enter context: save current state and set new seed."""
        # Save Python random state
        self._random_state = random.getstate()

        # Save NumPy state if available
        try:
            import numpy as np
            self._numpy_state = np.random.get_state()
        except ImportError:
            self._numpy_state = None

        # Set new seed
        set_all_seeds(self.seed)
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """Exit context: restore previous state."""
        # Restore Python random state
        if self._random_state is not None:
            random.setstate(self._random_state)

        # Restore NumPy state if it was saved
        if self._numpy_state is not None:
            try:
                import numpy as np
                np.random.set_state(self._numpy_state)
            except ImportError:
                pass
