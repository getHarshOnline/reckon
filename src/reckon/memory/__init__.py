"""
Reckon's memory module: the records a run keeps under a resource budget, the
manager that keeps them and the policies that decide what to drop.

It holds:
- MemoryRecord: Core record abstraction
- CausalMemoryManager: Main memory management component
- Retention policies: FIFO, LRU, random, explicit importance, utility and measured-effect-aware
- Retrieval: explicit record IDs or tag, payload-type and utility filters
"""

# pylint: disable=duplicate-code

from reckon.memory.manager import CausalMemoryManager
from reckon.memory.policies import (
    EvidencePerBytePolicy,
    FIFOPolicy,
    LRUPolicy,
    RetentionPolicy,
    UtilityPolicy,
    RandomPolicy,
    ImportancePolicy,
    DiversityPolicy,
)
from reckon.memory.record import MemoryRecord, PayloadType

__all__ = [
    "MemoryRecord",
    "PayloadType",
    "CausalMemoryManager",
    "RetentionPolicy",
    "FIFOPolicy",
    "LRUPolicy",
    "UtilityPolicy",
    "EvidencePerBytePolicy",
    "RandomPolicy",
    "ImportancePolicy",
    "DiversityPolicy",
]
