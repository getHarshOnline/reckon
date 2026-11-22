"""
Memory efficiency metrics for Reckon evaluations.
"""

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from reckon.memory.manager import CausalMemoryManager


@dataclass
class MemoryEfficiencyMetrics:  # pylint: disable=too-many-instance-attributes
    """
    Memory activity and efficiency summaries.

    These descriptions apply to from_cmm(). Task runners keep task-specific
    outcomes in TaskResult.diagnostics; their reads_per_write denominator
    is max(writes, 1), with each task defining which reads it counts.

    Attributes:
        total_reward_per_byte: Supplied total reward / sampled peak or current bytes.
        total_reward_per_slot: Supplied total reward / current occupied slots.
        mean_return_per_byte: Supplied mean return / sampled peak or current bytes,
            only when total_reward is absent.
        mean_return_per_slot: That mean return / current occupied slots.
        reads_per_write: Selected read count / write count; can exceed one.
        useful_reads_per_read: Supplied useful reads / selected read count.
        peak_usage_bytes: Peak recognized write sample, or current usage.
        average_usage_bytes: Mean recognized write sample, or None.
    """

    total_reward_per_byte: Optional[float] = None
    total_reward_per_slot: Optional[float] = None
    mean_return_per_byte: Optional[float] = None
    mean_return_per_slot: Optional[float] = None
    reads_per_write: Optional[float] = None
    useful_reads_per_read: Optional[float] = None
    peak_usage_bytes: Optional[int] = None
    average_usage_bytes: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {key: value for key, value in asdict(self).items() if value is not None}

    @classmethod
    def from_cmm(  # pylint: disable=too-many-locals
        cls,
        cmm: "CausalMemoryManager",
        task_result: dict,
    ) -> "MemoryEfficiencyMetrics":
        """
        Summarize current CMM state and caller-supplied task totals.

        This consumes get_event_log(), draining the native event buffer.
        Recognized event counts take priority over supplied count fallbacks.
        Write samples use the native logger's bytes_after (total stored
        bytes). Absent samples use current usage for peak and None for
        average. This is not a time-weighted whole-run memory average.
        Total reward takes priority over mean return, with distinct output keys;
        absent reward inputs produce no reward ratios rather than a measured zero.

        Args:
            cmm: CausalMemoryManager instance after task execution
            task_result: Dictionary with task-specific results, may contain:
                - total_reward: float
                - mean_return: float, separately named when total_reward is absent
                - total_writes: int
                - total_reads: int
                - useful_reads: int

        Returns:
            MemoryEfficiencyMetrics instance with computed values.
        """
        # Consume the retained native event buffer.
        events = cmm.get_event_log()

        # Read the native logger projection directly.
        write_events = [e for e in events if e.get("op_type") == "write"]
        read_events = [e for e in events if e.get("op_type") == "read"]

        total_writes = len(write_events) if write_events else task_result.get("total_writes", 0)
        total_reads = len(read_events) if read_events else task_result.get("total_reads", 0)

        # Sample total stored bytes after each write.
        bytes_used = [e["bytes_after"] for e in write_events]
        peak_bytes = max(bytes_used) if bytes_used else cmm.current_usage_bytes
        avg_bytes = sum(bytes_used) / len(bytes_used) if bytes_used else None

        # Preserve the caller's numerator scope in the output field names.
        reward_metric = next(
            (name for name in ("total_reward", "mean_return") if name in task_result), None
        )
        reward_ratios = {}
        if reward_metric is not None:
            reward = task_result[reward_metric]
            if peak_bytes and peak_bytes > 0:
                reward_ratios[f"{reward_metric}_per_byte"] = reward / peak_bytes
            if cmm.current_usage_slots > 0:
                reward_ratios[f"{reward_metric}_per_slot"] = reward / cmm.current_usage_slots

        reads_per_write = total_reads / total_writes if total_writes > 0 else None

        useful_reads = task_result.get("useful_reads", 0)
        useful_reads_per_read = useful_reads / total_reads if total_reads > 0 else None

        return cls(
            **reward_ratios,
            reads_per_write=reads_per_write,
            useful_reads_per_read=useful_reads_per_read,
            peak_usage_bytes=peak_bytes,
            average_usage_bytes=avg_bytes,
        )
