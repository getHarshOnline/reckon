"""
Resource vectors and memory budgets.

Defines the multi-dimensional resource constraints under which agents operate.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ResourceVector:
    """
    A multi-dimensional resource constraint vector.

    Attributes:
        memory_slots: Maximum number of memory slots
        memory_bytes: Maximum memory in bytes
        memory_tokens: Maximum memory in tokens
        bandwidth: Maximum bandwidth (ops/step)
        compute: Maximum compute per step
        noise_floor: Irreducible noise level
    """

    memory_slots: Optional[int] = None
    memory_bytes: Optional[int] = None
    memory_tokens: Optional[int] = None
    bandwidth: Optional[float] = None
    compute: Optional[float] = None
    noise_floor: float = 0.0

    def __post_init__(self):
        """Validate resource vector constraints."""
        if self.noise_floor < 0:
            raise ValueError(f"noise_floor must be >= 0, got {self.noise_floor}")
        if self.memory_slots is not None and self.memory_slots < 0:
            raise ValueError(f"memory_slots must be >= 0, got {self.memory_slots}")
        if self.memory_bytes is not None and self.memory_bytes < 0:
            raise ValueError(f"memory_bytes must be >= 0, got {self.memory_bytes}")
        if self.memory_tokens is not None and self.memory_tokens < 0:
            raise ValueError(f"memory_tokens must be >= 0, got {self.memory_tokens}")
        if self.bandwidth is not None and self.bandwidth < 0:
            raise ValueError(f"bandwidth must be >= 0, got {self.bandwidth}")
        if self.compute is not None and self.compute < 0:
            raise ValueError(f"compute must be >= 0, got {self.compute}")

    def is_satisfied(self, usage: "ResourceVector") -> bool:
        """Compare supplied slot, byte and token usage with the supplied limits.

        A dimension is skipped when either value is None. Bandwidth, compute
        and noise are not checked; this is not the full formal protocol order.
        """
        if (
            self.memory_slots is not None
            and usage.memory_slots is not None
            and usage.memory_slots > self.memory_slots
        ):
            return False
        if (
            self.memory_bytes is not None
            and usage.memory_bytes is not None
            and usage.memory_bytes > self.memory_bytes
        ):
            return False
        if (
            self.memory_tokens is not None
            and usage.memory_tokens is not None  # noqa: SIM103
            and usage.memory_tokens > self.memory_tokens
        ):
            return False
        return True


@dataclass
class MemoryBudget:
    """
    Memory-specific budget configuration for the Causal Memory Manager.

    Attributes:
        max_slots: Maximum number of records to store
        max_bytes: Maximum total bytes
        max_tokens: Maximum total tokens
        max_write_ops_per_window: Write rate limit
        max_read_ops_per_window: Read rate limit
        window_size: Window size for rate limiting (in steps)
    """

    max_slots: int = 100
    max_bytes: Optional[int] = None
    max_tokens: Optional[int] = None
    max_write_ops_per_window: Optional[int] = None
    max_read_ops_per_window: Optional[int] = None
    window_size: int = 100

    def __post_init__(self):
        """Validate memory budget constraints."""
        if self.max_slots < 1:
            raise ValueError(f"max_slots must be >= 1, got {self.max_slots}")
        if self.max_bytes is not None and self.max_bytes < 1:
            raise ValueError(f"max_bytes must be >= 1, got {self.max_bytes}")
        for name in (
            "max_tokens",
            "max_write_ops_per_window",
            "max_read_ops_per_window",
            "window_size",
        ):
            value = getattr(self, name)
            if value is None and name != "window_size":
                continue
            # A Boolean is not an operation count, despite being an int subclass.
            if type(value) is not int or value < 1:  # pylint: disable=unidiomatic-typecheck
                raise ValueError(f"{name} must be a positive integer, got {value}")

    def to_resource_vector(self) -> ResourceVector:
        """Copy slot, byte and token limits, without constructing a formal protocol budget."""
        return ResourceVector(
            memory_slots=self.max_slots,
            memory_bytes=self.max_bytes,
            memory_tokens=self.max_tokens,
        )
