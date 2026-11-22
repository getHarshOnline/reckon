"""
CMM Registry for Visualization Server

Provides a way to register a CausalMemoryManager instance with the viz server
so that event routes can access real event data from the Rust EventLogger.

Usage:
    from reckon.viz.registry import register_cmm, get_cmm

    # In your application code
    cmm = CausalMemoryManager(budget)
    register_cmm(cmm)

    # The viz routes will now use the registered CMM's EventLogger
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from reckon.memory.manager import CausalMemoryManager


class CMMRegistry:
    """Registry for the active CausalMemoryManager instance.

    Uses a class to avoid module-level mutable state and global statements.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._cmm: Optional["CausalMemoryManager"] = None

    def register(self, cmm: "CausalMemoryManager") -> None:
        """Register a CausalMemoryManager instance.

        Args:
            cmm: The CMM instance to use for event data.
        """
        self._cmm = cmm

    def unregister(self) -> None:
        """Unregister the current CMM instance."""
        self._cmm = None

    def get(self) -> Optional["CausalMemoryManager"]:
        """Get the registered CMM instance.

        Returns:
            The registered CMM, or None if no CMM is registered.
        """
        return self._cmm

    def has_cmm(self) -> bool:
        """Check if a CMM is registered.

        Returns:
            True if a CMM is registered with the viz server.
        """
        return self._cmm is not None


# Singleton registry instance
REGISTRY = CMMRegistry()


# Convenience functions for cleaner API
def register_cmm(cmm: "CausalMemoryManager") -> None:
    """Register a CausalMemoryManager instance with the viz server.

    Args:
        cmm: The CMM instance to use for event data.
    """
    REGISTRY.register(cmm)


def unregister_cmm() -> None:
    """Unregister the current CMM instance."""
    REGISTRY.unregister()


def get_cmm() -> Optional["CausalMemoryManager"]:
    """Get the registered CMM instance, if any.

    Returns:
        The registered CMM, or None if no CMM is registered.
    """
    return REGISTRY.get()


def has_cmm() -> bool:
    """Check if a CMM is registered.

    Returns:
        True if a CMM is registered with the viz server.
    """
    return REGISTRY.has_cmm()
