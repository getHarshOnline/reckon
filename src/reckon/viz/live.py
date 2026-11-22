"""Persist and stream a registered memory manager's actual kernel operations."""

import asyncio
import time
from queue import Empty

from reckon.viz.registry import get_cmm
from reckon.viz.storage import RunMeta


def _take_batch(queue, limit=1000):
    batches = {}
    for _ in range(limit):
        try:
            source, event = queue.get_nowait()
        except Empty:
            break
        batches.setdefault(source, []).append(event)
    return batches


async def _persist(app, manager, batches):
    for source, events in batches.items():
        run_id = f"live-{source}"
        index = app.state.run_index
        store = app.state.run_store
        if index.get_run(run_id) is None:
            index.add_run(
                RunMeta(
                    run_id=run_id,
                    config_id="",
                    notebook_name="live",
                    task_name="memory manager",
                    created_at=int(time.time() * 1000),
                    events_path=f"{run_id}/events.jsonl",
                    policy_name=type(manager.retention_policy).__name__,
                )
            )
        await app.state.event_fanout.append_events(store, run_id, events)


async def follow_registered_manager(app) -> None:
    """Follow in-process registration and flush the detached queue on shutdown."""
    stop = app.state.live_stop
    while not stop.is_set():
        manager = get_cmm()
        if manager is None:
            await asyncio.sleep(0.05)
            continue
        try:
            with manager.subscribe_events() as queue:
                app.state.live_error = None
                while not stop.is_set() and get_cmm() is manager:
                    await _persist(app, manager, _take_batch(queue))
                    await asyncio.sleep(0.01)
            # Detachment holds the manager lock: no later operation can join this queue.
            while not queue.empty():
                await _persist(app, manager, _take_batch(queue))
        except (RuntimeError, ValueError, OSError) as exc:
            app.state.live_error = str(exc)
            while not stop.is_set() and get_cmm() is manager:
                await asyncio.sleep(0.05)
