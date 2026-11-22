"""
Reckon Tasks Module

Benchmark tasks for evaluating memory management:
- Task A: Key-Door Delayed Credit Gridworld
- Task B: Hidden-Mode Contextual Bandit
- Task C: Continual Classification with Replay Budget
- Task D: Tutor Loop Simulation

Each task:
1. Requires selective memory (unlimited memory unnecessary, zero memory fails)
2. Exposes clear success metrics
3. Integrates with the CausalMemoryManager
"""

from reckon.tasks.base import BaseTask, TaskResult
from reckon.tasks.task_a_keydoor import KeyDoorTask
from reckon.tasks.task_b_bandit import BanditTask
from reckon.tasks.task_c_continual import ContinualTask
from reckon.tasks.task_d_tutor import TutorTask

__all__ = [
    "BaseTask",
    "TaskResult",
    "KeyDoorTask",
    "BanditTask",
    "ContinualTask",
    "TutorTask",
]
