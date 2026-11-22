"""Admission of read and write calls in episode-step windows."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from typing import Iterator

from reckon.core.resources import MemoryBudget


class OperationLimits:
    """Count successful calls and reserve space for calls still in progress.

    The manager holds its lock throughout admission and execution. Settings stay
    fixed until a full episode reset; changing a window cannot recover history
    already discarded under its previous size.
    """

    def __init__(self, budget: MemoryBudget):
        budget.__post_init__()
        self._settings = self._configuration(budget)
        self._calls: dict[str, deque[int]] = {"read": deque(), "write": deque()}
        self._active = 0

    @staticmethod
    def _configuration(budget: MemoryBudget) -> tuple[int | None, int | None, int]:
        return (
            budget.max_read_ops_per_window,
            budget.max_write_ops_per_window,
            budget.window_size,
        )

    @property
    def enabled(self) -> bool:
        """Whether either operation has a finite limit."""
        return any(value is not None for value in self._settings[:2])

    def check_step(self, current: int, proposed: int, *, reset: bool = False) -> None:
        """Refuse time reversal or a timeline change during a limited call."""
        if not self.enabled:
            return
        if self._active and (reset or proposed != current):
            raise RuntimeError("Cannot change the rate-limit timeline during a memory operation")
        if not reset and proposed < current:
            raise ValueError("Operation-rate limits require non-decreasing steps")

    @contextmanager
    def consume(self, operation: str, step: int, budget: MemoryBudget) -> Iterator[None]:
        """Admit one call; failed calls release their reservation."""
        if self._configuration(budget) != self._settings:
            raise ValueError("Changed operation-rate settings require a full episode reset")
        limit = self._settings[0 if operation == "read" else 1]
        calls = self._calls[operation]
        if limit is not None:
            while calls and calls[0] <= step - self._settings[2]:
                calls.popleft()
            if len(calls) >= limit:
                raise RuntimeError(f"Memory {operation} rate limit reached")
            calls.append(step)
        self._active += 1
        try:
            yield
        except BaseException:
            if limit is not None:
                calls.remove(step)
            raise
        finally:
            self._active -= 1
