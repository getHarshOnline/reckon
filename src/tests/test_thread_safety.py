"""
Tests for thread safety in CausalMemoryManager.
"""

import pytest
import threading
import time

from reckon.memory.manager import CausalMemoryManager
from reckon.core.resources import MemoryBudget
from reckon.memory.record import PayloadType


class TestThreadSafety:
    """Tests for concurrent access to CausalMemoryManager."""

    def test_concurrent_writes(self):
        """Multiple threads writing simultaneously should not cause errors."""
        budget = MemoryBudget(max_slots=1000, max_bytes=100000)
        cmm = CausalMemoryManager(budget)

        errors = []

        def write_records(n):
            try:
                for i in range(n):
                    cmm.write(
                        payload={"value": i},
                        payload_type=PayloadType.OBSERVATION,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_records, args=(50,)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred during concurrent writes: {errors}"
        # Should have ~500 records (some may be pruned if budget exceeded)
        assert cmm.current_usage_slots > 0

    def test_concurrent_read_write(self):
        """Readers and writers operating simultaneously should not cause errors."""
        budget = MemoryBudget(max_slots=100)
        cmm = CausalMemoryManager(budget)

        # Pre-populate
        for i in range(50):
            cmm.write(payload={"i": i}, payload_type=PayloadType.OBSERVATION)

        errors = []

        def reader():
            try:
                for _ in range(100):
                    cmm.get_all_records()
            except Exception as e:
                errors.append(("reader", e))

        def writer():
            try:
                for i in range(50):
                    cmm.write(payload={"new": i}, payload_type=PayloadType.OBSERVATION)
            except Exception as e:
                errors.append(("writer", e))

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred during concurrent read/write: {errors}"

    def test_concurrent_score_updates(self):
        """Multiple threads updating scores simultaneously should not cause errors."""
        budget = MemoryBudget(max_slots=100)
        cmm = CausalMemoryManager(budget)

        # Create records
        record_ids = []
        for i in range(20):
            rid = cmm.write(payload={"i": i}, payload_type=PayloadType.OBSERVATION)
            record_ids.append(rid)

        errors = []

        def updater(record_id, thread_id):
            try:
                for i in range(50):
                    cmm.update_score(
                        record_id=record_id,
                        score_type="utility",
                        value=float(i + thread_id),
                        signal_source=f"thread-{thread_id}",
                    )
            except Exception as e:
                errors.append((f"updater-{thread_id}", e))

        threads = [
            threading.Thread(target=updater, args=(record_ids[i % len(record_ids)], i))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred during concurrent score updates: {errors}"

    def test_concurrent_prune_operations(self):
        """Pruning while writing should not cause errors."""
        budget = MemoryBudget(max_slots=50)
        cmm = CausalMemoryManager(budget)

        errors = []
        stop_flag = threading.Event()

        def writer():
            try:
                for i in range(100):
                    if stop_flag.is_set():
                        break
                    cmm.write(
                        payload={"val": i},
                        payload_type=PayloadType.OBSERVATION,
                    )
            except Exception as e:
                errors.append(("writer", e))

        def pruner():
            try:
                for _ in range(50):
                    if stop_flag.is_set():
                        break
                    records = cmm.get_all_records()
                    if records:
                        cmm.prune(records[0].id, reason="test")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(("pruner", e))

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=pruner),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred during concurrent prune: {errors}"

    def test_event_log_thread_safety(self):
        """Event log access during writes should not cause errors."""
        budget = MemoryBudget(max_slots=100)
        cmm = CausalMemoryManager(budget)

        errors = []
        stop_flag = threading.Event()

        def writer():
            try:
                for i in range(200):
                    if stop_flag.is_set():
                        break
                    cmm.write(
                        payload={"i": i},
                        payload_type=PayloadType.OBSERVATION,
                    )
            except Exception as e:
                errors.append(("writer", e))
            finally:
                stop_flag.set()

        def log_reader():
            try:
                while not stop_flag.is_set():
                    cmm.get_event_log()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(("log_reader", e))

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=log_reader),
            threading.Thread(target=log_reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred during event log access: {errors}"

    def test_set_episode_during_writes(self):
        """Changing episode during writes should be handled safely."""
        budget = MemoryBudget(max_slots=100)
        cmm = CausalMemoryManager(budget)

        errors = []

        def writer():
            try:
                for i in range(100):
                    cmm.write(
                        payload={"i": i},
                        payload_type=PayloadType.OBSERVATION,
                    )
            except Exception as e:
                errors.append(("writer", e))

        def episode_changer():
            try:
                for i in range(10):
                    cmm.set_episode(f"episode-{i}")
                    time.sleep(0.005)
            except Exception as e:
                errors.append(("episode_changer", e))

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=episode_changer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred during episode change: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
