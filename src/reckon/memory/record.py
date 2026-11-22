"""Python behavior and object adapters for Rust-owned laboratory records."""

import hashlib
import json
import operator
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, ClassVar, cast

from reckon import _rust

_PAYLOAD_TYPES = _rust.payload_types()


def _empty_native(cls):
    """Allocate before restoring state so pickle can reconnect cyclic objects."""
    if issubclass(cls, _rust.MemoryRecord):
        return _rust.MemoryRecord.__new__(
            cls, "", 0, None, None, None, [], None, None, None, "", {}
        )
    return cls._native_type.__new__(cls)


class PayloadType(Enum):
    """Types of payloads that can be stored in a record."""

    OBSERVATION = _PAYLOAD_TYPES["OBSERVATION"]
    ACTION = _PAYLOAD_TYPES["ACTION"]
    REWARD = _PAYLOAD_TYPES["REWARD"]
    CUE = _PAYLOAD_TYPES["CUE"]
    TRACE = _PAYLOAD_TYPES["TRACE"]
    REPRESENTATION = _PAYLOAD_TYPES["REPRESENTATION"]
    CUSTOM = _PAYLOAD_TYPES["CUSTOM"]


class _NativeValue:
    """Retain dataclass copying and equality around native field storage."""

    _native_type: Any
    _field_values: Callable[[], dict[str, Any]]
    __dataclass_fields__: ClassVar[dict[str, Any]]

    def __copy__(self):
        copied = self._native_type.__new__(type(self), **self._field_values())
        copied.__dict__.update(self.__dict__)
        return copied

    def __deepcopy__(self, memo):
        copied = self.__copy__()
        memo[id(self)] = copied
        for name, value in self._field_values().items():
            setattr(copied, name, deepcopy(value, memo))
        copied.__dict__.update(deepcopy(self.__dict__, memo))
        return copied

    def __reduce_ex__(self, _protocol):
        return _empty_native, (type(self),), (self._field_values(), self.__dict__)

    def __setstate__(self, state):
        fields, attributes = state
        for name, value in fields.items():
            setattr(self, name, value)
        self.__dict__.update(attributes)


def _adapter(cls):
    # Rust supplies the field list; dataclass helpers operate on native getters.
    cls.__annotations__ = dict.fromkeys(cls._field_names(), Any)
    return dataclass(init=False)(cls)


@_adapter
class RecordOrigin(_NativeValue, _rust.RecordOrigin):
    """Creating operation, ordered inputs and supplied content hash."""

    _native_type = _rust.RecordOrigin


@_adapter
class UtilityEstimate(_NativeValue, _rust.UtilityEstimate):
    """Mutable utility, uncertainty and access statistics stored in Rust."""

    _native_type = _rust.UtilityEstimate

    # Constants for bounded utility updates
    MAX_DELTA = 1000.0
    NORMALIZATION_THRESHOLD = 1e6

    def update_utility(self, delta: float) -> bool:
        """Update utility with clamped delta.

        Args:
            delta: The utility change to apply.

        Returns:
            True if normalization is needed (absolute value exceeds threshold).
        """
        clamped_delta = max(-self.MAX_DELTA, min(self.MAX_DELTA, delta))
        self.value += clamped_delta
        return abs(self.value) > self.NORMALIZATION_THRESHOLD


@_adapter
class CausalScore(_NativeValue, _rust.CausalScore):
    """Optional attribution measurements; absence differs from measured zero."""

    _native_type = _rust.CausalScore

    def __new__(
        cls, ablation_delta=None, counterfactual_delta=None, influence_proxy=None, last_evaluated=-1
    ):
        value = cast(
            CausalScore,
            super().__new__(
                cls, ablation_delta, counterfactual_delta, influence_proxy, last_evaluated
            ),
        )
        value.__post_init__()
        return value

    @property
    def is_proxy_only(self) -> bool:
        """Whether only a proxy was supplied; zero and negative deltas remain present."""
        return (
            self.influence_proxy is not None
            and self.ablation_delta is None
            and self.counterfactual_delta is None
        )

    def __post_init__(self):
        """Validate causal score ranges."""
        for name, val, low, high in [
            ("ablation_delta", self.ablation_delta, -1.0, 1.0),
            ("counterfactual_delta", self.counterfactual_delta, -1.0, 1.0),
            ("influence_proxy", self.influence_proxy, 0.0, 1.0),
        ]:
            if val is not None and not low <= val <= high:
                raise ValueError(f"{name} must be in [{low}, {high}], got {val}")


@_adapter
class RecordCost(_NativeValue, _rust.RecordCost):
    """Byte and slot cost, with None for an uncounted token cost."""

    _native_type = _rust.RecordCost

    def __new__(cls, bytes=1, tokens=None, slots=1):
        if bytes < 1:
            raise ValueError(f"Record cost must be at least 1 byte, got {bytes}")
        if slots < 1:
            raise ValueError(f"Record cost must be at least 1 slot, got {slots}")
        if tokens is not None and (type(tokens) is not int or tokens < 0):
            raise ValueError(f"Record tokens must be a non-negative integer, got {tokens}")
        return super().__new__(cls, bytes, tokens, slots)


@_adapter
class MemoryRecord(_NativeValue, _rust.MemoryRecord):
    """A native record retaining its caller's payload, lists and metadata objects."""

    _native_type = _rust.MemoryRecord

    def __new__(
        cls,
        id,
        timestamp,
        payload_type,
        payload,
        cost=None,
        tags=None,
        provenance=None,
        utility=None,
        causal_score=None,
        episode_id="",
        metadata=None,
        compressed=False,
        encoding="",
        created_at_step=None,
        created_at_sequence=None,
    ):
        value = cast(
            MemoryRecord,
            super().__new__(
                cls,
                id,
                timestamp,
                payload_type,
                payload,
                RecordCost() if cost is None else cost,
                [] if tags is None else tags,
                RecordOrigin() if provenance is None else provenance,
                UtilityEstimate() if utility is None else utility,
                CausalScore() if causal_score is None else causal_score,
                episode_id,
                {} if metadata is None else metadata,
                compressed,
                encoding,
                created_at_step,
                created_at_sequence,
            ),
        )
        value.__post_init__()
        return value

    def snapshot_json(self, payload_bytes: bytes, metadata_bytes: bytes) -> str:
        """Export a typed snapshot using caller-supplied encodings for opaque objects.

        Integer fields use decimal strings and unknown tokens remain null.
        The live payload and metadata objects are never replaced or serialized implicitly.
        """
        return self._snapshot_json(payload_bytes, metadata_bytes)

    def snapshot_wire(self, payload_bytes: bytes, metadata_bytes: bytes) -> bytes:
        """Export the historical laboratory wire, refusing unknown token counts."""
        return self._snapshot_wire(payload_bytes, metadata_bytes)

    def __post_init__(self):
        """Compute hash if not provided."""
        if not self.provenance.hash:
            self.provenance.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute content hash for deduplication."""
        content = json.dumps(
            {
                "payload_type": self.payload_type.value,
                "payload": str(self.payload),
                "timestamp": self.timestamp,
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def utility_per_cost(self) -> float:
        """Compute utility per unit cost (uses min floor of 1 byte)."""
        return self.utility.value / max(self.cost.bytes, 1)

    def update_utility(self, delta: float, timestamp: int) -> None:
        """Update utility estimate."""
        value = self.utility.value + delta
        timestamp = operator.index(timestamp)
        count = self.utility.use_count + 1
        if not -(2**63) <= timestamp < 2**63 or not -(2**31) <= count < 2**31:
            raise OverflowError("Record access exceeds the native integer range")
        self.utility.value = value
        self.utility.last_used = timestamp
        self.utility.use_count = count

    def to_dict(self) -> dict:
        """Convert to dictionary (for JSON serialization)."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "episode_id": self.episode_id,
            "payload": {
                "type": self.payload_type.value,
                "data": self.payload,
            },
            "cost": {
                "bytes": self.cost.bytes,
                **({"tokens": self.cost.tokens} if self.cost.tokens is not None else {}),
                "slots": self.cost.slots,
            },
            "tags": self.tags,
            "provenance": {
                "source_op": self.provenance.source_op,
                "input_ids": self.provenance.input_ids,
                "hash": self.provenance.hash,
            },
            "utility": {
                "value": self.utility.value,
                "uncertainty": self.utility.uncertainty,
                "last_used": self.utility.last_used,
                "use_count": self.utility.use_count,
            },
            "causal_score": {
                "ablation_delta": self.causal_score.ablation_delta,
                "counterfactual_delta": self.causal_score.counterfactual_delta,
                "influence_proxy": self.causal_score.influence_proxy,
                "last_evaluated": self.causal_score.last_evaluated,
            },
            "metadata": self.metadata,
        }
