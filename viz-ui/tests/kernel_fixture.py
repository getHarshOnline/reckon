"""Loopback-only browser fixture producing a real memory-manager run."""

from reckon.core.episode_context import EpisodeContext
from reckon.core.resources import MemoryBudget
from reckon.memory import CausalMemoryManager, PayloadType
from reckon.viz.registry import register_cmm
from reckon.viz.server import create_app

manager = CausalMemoryManager(MemoryBudget(max_slots=10), episode_id="browser")
register_cmm(manager)
app = create_app()


@app.post("/fixture/produce")
async def produce():
    for step in range(6):
        manager.set_step(step)
        record_id = manager.write({"cue": step}, PayloadType.CUE)
        with EpisodeContext(episode_id="browser") as context:
            manager.retrieve(context=context)
            manager.observe(1, context=context)
        manager.prune(record_id, reason="completed fixture step")
    return {"events": manager.get_event_log()}


@app.post("/fixture/read")
async def read_once():
    manager.retrieve()
    return {"events": manager.get_event_log()}
