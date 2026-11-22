"""Record the memory calls needed to verify a deterministic episode prefix."""

from dataclasses import asdict
from enum import Enum
import hashlib
import json

from reckon.core.episode_context import EpisodeContext
from reckon.memory import CausalMemoryManager
from reckon.memory.manager import ReckonJSONEncoder


def digest(value):
    """Hash a JSON value without allowing unavailable numeric evidence."""
    encoded = json.dumps(value, cls=ReckonJSONEncoder, sort_keys=True, allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


class ReplayMemory(CausalMemoryManager):
    """Use ordinary native memory while recording calls with stable write ordinals.

    Record UUIDs and context creation times are incidental to these controllers.
    Their payloads, order, budgets, reads, credit inputs and stored state are not.
    Only the explicit-context notebook controllers use this recorder; it does
    not claim to capture an arbitrary agent's hidden state or external services.
    """

    def __init__(self, budget, policy):
        super().__init__(budget, policy)
        self.ordinals = {}
        self.journal = []

    def canonical(self, value):
        """Replace record identities with their unique admission order."""
        if isinstance(value, EpisodeContext):
            return self.canonical(
                {
                    "episode_id": value.episode_id,
                    "step": value.step,
                    "retrieved_record_ids": value.retrieved_record_ids,
                }
            )
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, str):
            return self.ordinals.get(value, value)
        if isinstance(value, dict):
            return {key: self.canonical(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [self.canonical(item) for item in value]
        return value

    def record_call(self, operation, args, kwargs):
        # Materialize before the operation can clear or extend a context.
        row = self.canonical({"operation": operation, "args": args, "kwargs": kwargs})
        self.journal.append(json.loads(json.dumps(row, cls=ReckonJSONEncoder)))

    def set_step(self, step):
        self.record_call("set_step", (step,), {})
        return super().set_step(step)

    def set_episode(self, episode_id, *, reset_memory=True):
        self.record_call("set_episode", (episode_id,), {"reset_memory": reset_memory})
        return super().set_episode(episode_id, reset_memory=reset_memory)

    def write(self, *args, **kwargs):
        self.record_call("write", args, kwargs)
        record_id = super().write(*args, **kwargs)
        self.ordinals[record_id] = len(self.ordinals)
        return record_id

    def retrieve(self, *args, **kwargs):
        self.record_call("retrieve", args, kwargs)
        records = super().retrieve(*args, **kwargs)
        self.journal.append({"retrieved": self.canonical([record.to_dict() for record in records])})
        return records

    def observe(self, *args, **kwargs):
        context = kwargs.get("context")
        if context is not None and context.is_expired():
            raise RuntimeError("Episode context expired during replay experiment")
        self.record_call("observe", args, kwargs)
        return super().observe(*args, **kwargs)

    def boundary(self, records, overflow):
        """Include the pending write, all prior calls and the actual candidates."""
        return {
            "journal_sha256": digest(self.journal),
            "journal_length": len(self.journal),
            "write_ordinal": len(self.ordinals),
            "budget": asdict(self.budget),
            "records": self.canonical([record.to_dict() for record in records]),
            "overflow": list(overflow),
        }
