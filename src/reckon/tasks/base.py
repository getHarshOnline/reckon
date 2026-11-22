"""
Base class for Reckon benchmark tasks.

All benchmark tasks inherit from BaseTask and implement the run() method.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reckon.memory.manager import CausalMemoryManager

# pylint: disable=wrong-import-position
from reckon.metrics import MemoryEfficiencyMetrics, PerformanceMetrics

# pylint: enable=wrong-import-position


@dataclass
class TaskResult:
    """
    Result of running a benchmark task.

    Attributes:
        performance: Performance metrics (success rate, return, etc.)
        memory: Memory activity and efficiency metrics
        diagnostics: Named task-specific summaries, not intervention results
        raw_data: Episode-level data for detailed analysis
    """

    performance: PerformanceMetrics
    memory: MemoryEfficiencyMetrics
    diagnostics: dict[str, float]
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "performance": self.performance.to_dict(),
            "memory": self.memory.to_dict(),
            "diagnostics": dict(self.diagnostics),
            "raw_data": self.raw_data,
        }


class BaseTask(ABC):
    """
    Abstract base class for Reckon benchmark tasks.

    Tasks must:
    1. Require selective memory (unlimited memory unnecessary, zero memory fails)
    2. Expose clear success metrics
    3. Integrate with the CausalMemoryManager

    Subclasses implement run() which executes the task for a given number
    of episodes and returns aggregated metrics.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable task name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief task description."""

    @abstractmethod
    # Keep the common task interface, including its keyword-only memory controls.
    def run(  # pylint: disable=too-many-arguments
        self,
        cmm: "CausalMemoryManager",
        num_episodes: int,
        seed: int,
        *,
        reset_memory: bool = False,
        learn_utility: bool = True,
    ) -> TaskResult:
        """
        Run the task and return metrics.

        Args:
            cmm: CausalMemoryManager instance for memory operations
            num_episodes: Number of episodes to run
            seed: Random seed for reproducibility
            reset_memory: Clear memory each episode instead of carrying it
            learn_utility: Update retrieved records from the episode outcome

        Returns:
            TaskResult containing performance, memory, and task diagnostics
        """
