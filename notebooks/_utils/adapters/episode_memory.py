"""Use a fresh caller-owned manager so evaluations reach the actual episode."""

from reckon.memory import CausalMemoryManager


def episode_memory(budget, policy, episode_id, memory=None):
    """Validate an injected manager without replacing its intervention hooks."""
    if memory is None:
        return CausalMemoryManager(budget, policy, episode_id)
    if memory.budget != budget or memory.retention_policy is not policy:
        raise ValueError("Injected memory must use the episode's budget and policy")
    if memory.current_usage_slots:
        raise ValueError("Notebook episodes require initially empty memory")
    memory.set_episode(episode_id, reset_memory=False)
    return memory
