"""Reckon, a laboratory for causal records under resource budgets.

A library for building and debugging resource-constrained agent memory systems.

Example:
    >>> from reckon import CausalMemoryManager, MemoryBudget, PayloadType
    >>> budget = MemoryBudget(max_slots=10000, max_bytes=100_000_000)
    >>> cmm = CausalMemoryManager(budget)
    >>> record_id = cmm.write(payload={"obs": [1, 2, 3]}, payload_type=PayloadType.OBSERVATION)

Core Components:
- core: Mathematical foundations and base abstractions
- memory: Causal Memory Manager implementation
- tasks: Benchmark tasks for evaluation
- metrics: Evaluation metrics and analysis
- viz: Debugger and visualization tools
"""

__author__ = "Harsh Joshi"
__license__ = "Apache-2.0"

# Rust extension (required)
# pylint: disable=no-name-in-module
from reckon._rust import EventLogger, Record, RecordStore
from reckon._rust import RetentionPolicy as RustRetentionPolicy

# The explicit alias declares this native value as a public re-export to type checkers.
from reckon._rust import __version__ as __version__  # pylint: disable=useless-import-alias

# pylint: enable=no-name-in-module
# Python API
from reckon.core import DirectInfluenceRecords, MemoryBudget, ResourceVector
from reckon.memory import (
    CausalMemoryManager,
    EvidencePerBytePolicy,
    DiversityPolicy,
    FIFOPolicy,
    LRUPolicy,
    MemoryRecord,
    PayloadType,
    RetentionPolicy,
    UtilityPolicy,
)

__all__ = [
    # Rust types (high-performance)
    "RecordStore",
    "Record",
    "EventLogger",
    "RustRetentionPolicy",
    # Core abstractions
    "ResourceVector",
    "MemoryBudget",
    "DirectInfluenceRecords",
    # Memory API
    "MemoryRecord",
    "PayloadType",
    "CausalMemoryManager",
    "RetentionPolicy",
    "FIFOPolicy",
    "LRUPolicy",
    "UtilityPolicy",
    "EvidencePerBytePolicy",
    "DiversityPolicy",
]
