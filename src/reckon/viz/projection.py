"""Project native kernel operations into the debugger's event format.

The kernel supplies logical steps, operation details and partial usage, not wall
times or record snapshots. Keep its complete source event beside the projection.
Malformed input is refused before an import can be reported as successful.
"""

from copy import deepcopy
import json
import math

_OPERATIONS = {
    "write": 1,
    "read": 2,
    "prune": 3,
    "update_score": 4,
    "compress": 5,
    "budget_check": 6,
}
_KERNEL_FIELDS = {
    "event_id",
    "op_type",
    "timestamp",
    "episode_id",
    "sequence",
    "record_id",
    "duration_us",
    "slots_after",
    "bytes_after",
    "details",
}
_DEBUGGER_FIELDS = {
    "eventId",
    "eventType",
    "wallTimeMs",
    "episodeId",
    "step",
    "sequence",
    "initialBudget",
    "finalUsage",
    "totalWrites",
    "totalPrunes",
    "memoryEvents",
    "exceededDimension",
    "snapshot",
    "metadata",
    "timeBasis",
    "kernelEvent",
}


def _identity(value) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or value == "":
        raise ValueError("event identity must be a nonempty string or integer")
    return str(value)


def _is_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _integer(value, field: str, *, nonnegative: bool = False) -> int:
    if not _is_integer(value) or (nonnegative and value < 0):
        raise ValueError(f"{field} must be {'a nonnegative' if nonnegative else 'an'} integer")
    # Steps and sequence are JS numbers; IDs are strings and have no such limit.
    if abs(value) > 2**53 - 1:
        raise ValueError(f"{field} exceeds the viewer's exact integer range")
    return value


def _project_legacy_export(event: dict) -> dict:
    """Read the repository's older named-event export, with supplied snapshots."""
    names = {
        "event_id": "eventId",
        "episode_id": "episodeId",
        "wall_time_ms": "wallTimeMs",
        "timestamp": "step",
        "sequence": "sequence",
        "snapshot": "snapshot",
    }
    allowed = set(names) | {"event_type", "record_id", "prune_reason"}
    if event.keys() - allowed:
        raise ValueError(f"unsupported export fields: {', '.join(sorted(event.keys() - allowed))}")
    name = event["event_type"]
    event_types = {
        "UNSPECIFIED": 0,
        "EPISODE_START": 1,
        "EPISODE_END": 2,
        "STEP": 3,
        "POLICY_CHANGE": 4,
        "BUDGET_EXCEEDED": 5,
        "CAUSAL_UPDATE": 6,
        "CHECKPOINT": 7,
    }
    operation = name.lower() if isinstance(name, str) else ""
    if name not in event_types and operation not in _OPERATIONS:
        raise ValueError(f"unsupported export event_type: {name}")
    result = {
        target: deepcopy(event[source]) for source, target in names.items() if source in event
    }
    result["eventType"] = event_types.get(name, 3)
    result["snapshot"] = result.get("snapshot", [])
    result["memoryEvents"] = []
    if operation in _OPERATIONS:
        memory = {
            "eventId": event["event_id"],
            "opType": _OPERATIONS[operation],
            "timestamp": event["timestamp"],
            "episodeId": event["episode_id"],
            "resultIds": [],
            "pruneReason": event.get("prune_reason", ""),
            "scoreType": "",
        }
        if "record_id" in event:
            memory["recordId"] = event["record_id"]
        result["memoryEvents"].append(memory)
    return project_event(result)


def _normalize_nested_ids(result: dict) -> None:
    """Validate operation and snapshot identities in a copied viewer event."""
    for memory in result["memoryEvents"]:
        if not isinstance(memory, dict) or "eventId" not in memory:
            raise ValueError("each memory operation needs an eventId")
        memory["eventId"] = _identity(memory["eventId"])
        if not _is_integer(memory.get("opType")) or memory["opType"] not in range(7):
            raise ValueError("unsupported memory operation type")
        if memory.get("recordId") is not None:
            memory["recordId"] = _identity(memory["recordId"])
        if "resultIds" in memory:
            if not isinstance(memory["resultIds"], list):
                raise ValueError("resultIds must be an array")
            memory["resultIds"] = [_identity(value) for value in memory["resultIds"]]
    for record in result["snapshot"]:
        if not isinstance(record, dict) or "id" not in record:
            raise ValueError("each snapshot record needs an id")
        record["id"] = _identity(record["id"])


def _project_viewer(event: dict) -> dict:
    """Validate a supplied viewer event without changing its observations."""
    unknown = event.keys() - _DEBUGGER_FIELDS
    if unknown:
        raise ValueError(f"unsupported debugger fields: {', '.join(sorted(unknown))}")
    required = {
        "eventId",
        "eventType",
        "wallTimeMs",
        "episodeId",
        "step",
        "memoryEvents",
        "snapshot",
    }
    if required - event.keys():
        raise ValueError(f"missing debugger fields: {', '.join(sorted(required - event.keys()))}")
    result = deepcopy(event)
    result["eventId"] = _identity(event["eventId"])
    if not _is_integer(event["eventType"]) or event["eventType"] not in range(8):
        raise ValueError("unsupported debugger eventType")
    if not isinstance(event["episodeId"], str):
        raise ValueError("episodeId must be a string")
    _integer(event["step"], "step")
    if not isinstance(event["wallTimeMs"], (int, float)) or not math.isfinite(event["wallTimeMs"]):
        raise ValueError("wallTimeMs must be finite")
    if "sequence" in event:
        _integer(event["sequence"], "sequence", nonnegative=True)
    if not isinstance(event["memoryEvents"], list) or not isinstance(event["snapshot"], list):
        raise ValueError("memoryEvents and snapshot must be arrays")
    if event.get("timeBasis", "wall") not in {"wall", "step"}:
        raise ValueError("timeBasis must be wall or step")
    _normalize_nested_ids(result)
    return result


def _add_operation_details(memory: dict, operation: str, details) -> None:
    """Translate only the details supplied by this operation's logger."""
    if details is not None:
        if not isinstance(details, str):
            raise ValueError("kernel details must be a JSON string or null")
        try:
            details = json.loads(details)
        except (ValueError, TypeError) as exc:
            raise ValueError("kernel details must contain valid JSON") from exc
    if operation == "read" and details is not None:
        if not isinstance(details, list):
            raise ValueError("read details must contain the retrieved IDs")
        memory["resultIds"] = [_identity(item) for item in details]
    if operation == "prune" and isinstance(details, dict):
        memory["pruneReason"] = details.get("reason", "")
    if operation == "update_score" and isinstance(details, dict):
        memory["scoreType"] = details.get("score_type", "")
        for source, target in [("old", "oldScore"), ("new", "newScore")]:
            if source in details:
                value = details[source]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ValueError(f"score {source} must be finite")
                memory[target] = value


def _project_kernel(event: dict) -> dict:
    """Preserve a native operation and expose its recorded memory details."""
    unknown = event.keys() - _KERNEL_FIELDS
    if unknown:
        raise ValueError(f"unsupported kernel fields: {', '.join(sorted(unknown))}")
    required = {"event_id", "op_type", "timestamp", "episode_id"}
    if required - event.keys():
        raise ValueError(f"missing kernel fields: {', '.join(sorted(required - event.keys()))}")
    operation = event["op_type"]
    if operation not in _OPERATIONS:
        raise ValueError(f"unsupported kernel operation: {operation}")
    event_id = _identity(event["event_id"])
    step = _integer(event["timestamp"], "timestamp")
    episode = event["episode_id"]
    if not isinstance(episode, str):
        raise ValueError("episode_id must be a string")
    memory = {
        "eventId": event_id,
        "opType": _OPERATIONS[operation],
        "timestamp": step,
        "episodeId": episode,
        "resultIds": [],
        "pruneReason": "",
        "scoreType": "",
        "durationUs": _integer(event.get("duration_us", 0), "duration_us", nonnegative=True),
    }
    record_id = event.get("record_id")
    if record_id is not None:
        memory["recordId"] = _identity(record_id)
    _add_operation_details(memory, operation, event.get("details"))
    # Python's logger records bytes for writes, but does not supply full usage.
    # Preserve all logged counters in kernelEvent rather than claiming a snapshot.
    result = {
        "eventId": event_id,
        "eventType": 3,
        "wallTimeMs": 0,
        "timeBasis": "step",
        "episodeId": episode,
        "step": step,
        "memoryEvents": [memory],
        "exceededDimension": "",
        "snapshot": [],
        "kernelEvent": deepcopy(event),
    }
    # Large integer fields must survive JSON's JavaScript number conversion.
    for field, value in result["kernelEvent"].items():
        if _is_integer(value) and abs(value) > 2**53 - 1:
            result["kernelEvent"][field] = str(value)
    if "sequence" in event:
        result["sequence"] = _integer(event["sequence"], "sequence", nonnegative=True)
    return result


def project_event(event: dict) -> dict:
    """Return one independent viewer event; never invent record snapshots."""
    if not isinstance(event, dict):
        raise ValueError("each event must be an object")
    if "op_type" in event:
        return _project_kernel(event)
    if "event_type" in event:
        return _project_legacy_export(event)
    return _project_viewer(event)


def parse_events_jsonl(data: bytes) -> list[dict]:
    """Read every nonempty line, reporting its number on invalid input."""
    events = []
    identities = {}
    for number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = project_event(json.loads(line))
            previous = identities.get(event["eventId"])
            if previous is not None and previous != event:
                raise ValueError(f"conflicting content for event {event['eventId']}")
            if previous is None:
                events.append(event)
                identities[event["eventId"]] = event
        except (ValueError, TypeError) as exc:
            raise ValueError(f"event line {number}: {exc}") from exc
    return events
