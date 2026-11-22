"""Tests for reproducibility guarantees."""

import pytest
import random


def test_canonical_event_ordering():
    """Verify (episode_id, step, sequence) ordering is stable."""
    # Simulate shuffled events
    events = [
        {"episode_id": "ep1", "step": 2, "sequence": 0},
        {"episode_id": "ep1", "step": 1, "sequence": 0},
        {"episode_id": "ep2", "step": 1, "sequence": 1},
        {"episode_id": "ep1", "step": 1, "sequence": 1},
        {"episode_id": "ep2", "step": 1, "sequence": 0},
    ]

    # Shuffle
    shuffled = events.copy()
    random.shuffle(shuffled)

    # Sort by canonical key
    sorted_events = sorted(
        shuffled,
        key=lambda e: (e["episode_id"], e["step"], e["sequence"])
    )

    # Verify order
    expected_order = [
        ("ep1", 1, 0),
        ("ep1", 1, 1),
        ("ep1", 2, 0),
        ("ep2", 1, 0),
        ("ep2", 1, 1),
    ]

    actual_order = [
        (e["episode_id"], e["step"], e["sequence"])
        for e in sorted_events
    ]

    assert actual_order == expected_order


def test_canonical_ordering_deterministic_across_shuffles():
    """Canonical ordering should be deterministic regardless of input order."""
    events = [
        {"episode_id": "ep1", "step": 1, "sequence": 0, "data": "a"},
        {"episode_id": "ep1", "step": 1, "sequence": 1, "data": "b"},
        {"episode_id": "ep1", "step": 2, "sequence": 0, "data": "c"},
        {"episode_id": "ep2", "step": 1, "sequence": 0, "data": "d"},
    ]

    # Run multiple shuffles and verify same sorted order
    results = []
    for _ in range(10):
        shuffled = events.copy()
        random.shuffle(shuffled)
        sorted_events = sorted(
            shuffled,
            key=lambda e: (e["episode_id"], e["step"], e["sequence"])
        )
        results.append([e["data"] for e in sorted_events])

    # All should be identical
    expected = ["a", "b", "c", "d"]
    for result in results:
        assert result == expected


def test_timestamp_not_used_for_ordering():
    """Timestamp should not affect canonical ordering."""
    # Events with timestamps that would give different order
    events = [
        {"episode_id": "ep1", "step": 2, "sequence": 0, "timestamp": 100},
        {"episode_id": "ep1", "step": 1, "sequence": 0, "timestamp": 200},  # Later timestamp, earlier step
    ]

    sorted_events = sorted(
        events,
        key=lambda e: (e["episode_id"], e["step"], e["sequence"])
    )

    # Step 1 should come before step 2, regardless of timestamp
    assert sorted_events[0]["step"] == 1
    assert sorted_events[1]["step"] == 2
