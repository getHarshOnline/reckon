"""
Basic example of using the Causal Memory Manager.

This example demonstrates:
1. Creating a memory manager with a budget
2. Writing records with different types and tags
3. Reading records with queries
4. Observing automatic pruning under budget constraints
5. Accessing the event log for debugging
"""

import json

from reckon.core.resources import MemoryBudget
from reckon.memory import (
    CausalMemoryManager,
    PayloadType,
    FIFOPolicy,
    UtilityPolicy,
)


def main():
    # Create a memory budget
    budget = MemoryBudget(
        max_slots=5,  # Only 5 records at a time
        max_bytes=1000,
    )

    # Create memory manager with FIFO policy
    cmm = CausalMemoryManager(
        budget=budget,
        retention_policy=FIFOPolicy(),
        episode_id="demo-episode-1",
    )

    print("=== Reckon Causal Memory Manager Demo ===\n")

    # Simulate an agent storing observations
    observations = [
        ("key_red", ["cue", "important"]),
        ("door_blue", ["observation"]),
        ("wall", ["observation"]),
        ("key_used", ["action", "important"]),
        ("reward_found", ["reward"]),
        ("new_room", ["observation"]),
        ("key_green", ["cue", "important"]),
    ]

    print("Storing observations (budget: 5 slots):")
    for i, (obs, tags) in enumerate(observations):
        cmm.set_step(i)
        rid = cmm.write(
            payload=obs,
            payload_type=PayloadType.OBSERVATION,
            tags=tags,
            initial_utility=1.0 if "important" in tags else 0.5,
        )
        print(f"  Step {i}: Stored '{obs}' -> ID: {rid}")
        print(f"           Current usage: {cmm.current_usage_slots} slots")

    print(f"\nFinal memory state: {cmm.current_usage_slots} records")

    # Query for important cues
    print("\nQuerying for 'important' tagged records:")
    important = cmm.read(query={"tags": ["important"]})
    for record in important:
        print(f"  - {record.payload} (utility: {record.utility.value})")

    # Show pruning events
    print("\nEvent log (pruning events):")
    for event in cmm.get_event_log():
        if event["op_type"] == "prune":
            details = json.loads(event["details"]) if event["details"] else {}
            print(f"  Step {event['timestamp']}: Pruned record {event['record_id']}")
            print(f"    Reason: {details.get('reason')}")

    # Try with utility-based policy
    print("\n\n=== Now with Utility-Based Policy ===\n")

    cmm2 = CausalMemoryManager(
        budget=budget,
        retention_policy=UtilityPolicy(),
        episode_id="demo-episode-2",
    )

    for i, (obs, tags) in enumerate(observations):
        cmm2.set_step(i)
        cmm2.write(
            payload=obs,
            payload_type=PayloadType.OBSERVATION,
            tags=tags,
            initial_utility=2.0 if "important" in tags else 0.1,
        )

    print("Remaining records with utility policy:")
    for record in cmm2.get_all_records():
        print(f"  - {record.payload} (utility: {record.utility.value})")


if __name__ == "__main__":
    main()
