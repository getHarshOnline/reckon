"""Conversation episodes whose answers consume the records retrieved this turn."""

from __future__ import annotations

import time
from reckon.core.episode_context import EpisodeContext
from reckon.core.resources import MemoryBudget
from reckon.memory import CausalMemoryManager, PayloadType
from .tool_env import ToolEnv, ToolEnvConfig
from .episode_memory import episode_memory
from .ollama_client import (
    AGENT_SYSTEM_PROMPT,
    OLLAMA_AVAILABLE,
    SimulatedOllamaBackend,
    ollama_chat,
    parse_agent_response,
)


def run_conversation_episode(
    policy,
    budget_slots: int,
    seed: int,
    backend: str = "sim",
    model: str = "llama3.2",
    verbose: bool = False,
    n_steps: int = 8,
    use_memory: bool = True,
    *,
    memory: CausalMemoryManager | None = None,
) -> dict:
    """
    Run one conversation episode with memory-augmented agent.

    Returns dict with metrics and transcript.
    """
    started = time.perf_counter()
    if backend not in {"sim", "ollama"}:
        raise ValueError("backend must be sim or ollama")
    # Create CMM
    budget = MemoryBudget(max_slots=budget_slots, max_bytes=budget_slots * 500)
    cmm = episode_memory(budget, policy, f"conv-{seed}", memory)

    # Create environment
    env = ToolEnv(ToolEnvConfig(n_steps=n_steps))
    obs, info = env.reset(seed)

    # Keep the simulated backend available for any optional Ollama failure path.
    sim_backend = SimulatedOllamaBackend(seed)
    fallback_count = 0

    transcript = []
    step = 0
    terminated = False
    parse_failures = 0

    while not terminated:
        cmm.set_step(step)

        # Write user message to memory
        user_msg = obs
        cmm.write(
            payload={"role": "user", "content": user_msg, "step": step},
            payload_type=PayloadType.OBSERVATION,
            tags=["user", "message"],
            initial_utility=0.5,
        )

        # Retrieve relevant context
        context = EpisodeContext(episode_id=f"conv-{seed}")
        context_records = (
            cmm.retrieve(
                query={"tags": ["constraint", "tool_result"]}, limit=budget_slots, context=context
            )
            if use_memory
            else []
        )
        context_str = "\n".join(
            [f"- {r.payload.get('content', str(r.payload))}" for r in context_records]
        )

        # Compose prompt
        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        ]
        if context_str:
            messages.append({"role": "system", "content": f"MEMORY CONTEXT:\n{context_str}"})
        messages.append({"role": "user", "content": user_msg})

        # Call backend
        if backend == "ollama" and OLLAMA_AVAILABLE:
            try:
                response = ollama_chat(
                    model=model,
                    messages=messages,
                    timeout_s=60,
                )
                response_text = response["message"]["content"]
            except Exception as e:
                if verbose:
                    print(f"Ollama error: {e}")
                # Fallback to sim; keep its use visible in the result.
                fallback_count += 1
                response = sim_backend.chat(messages)
                response_text = response["message"]["content"]
        else:
            fallback_count += int(backend == "ollama")
            response = sim_backend.chat(messages)
            response_text = response["message"]["content"]

        # Parse agent response
        try:
            parsed = parse_agent_response(response_text)
        except ValueError as e:
            if verbose:
                print(f"Parse error at step {step}: {e}")
            parse_failures += 1
            parsed = {
                "tool": None,
                "final": "I apologize, I had trouble responding.",
                "memory_write": [],
            }

        # Write memory records from agent
        for mem in parsed.get("memory_write", []):
            cmm.write(
                payload={"role": "memory", "content": mem["content"], "step": step},
                payload_type=PayloadType.CUE,
                tags=["constraint", mem["tag"]],
                initial_utility=1.0,
            )

        # Step environment
        obs, reward, terminated, truncated, step_info = env.step(parsed)

        cmm.observe(reward, context=context)
        terminated = terminated or truncated

        # If tool was called, write result to memory
        if step_info.get("tool_result"):
            cmm.write(
                payload={"role": "tool", "result": step_info["tool_result"], "step": step},
                payload_type=PayloadType.CUE,
                tags=["tool_result", parsed["tool"]["name"]],
                initial_utility=1.5,
            )

        # Log transcript
        transcript.append(
            {
                "step": step,
                "retrieved_ids": [r.id for r in context_records],
                "memory_context": context_str,
                "user": user_msg,
                "agent_response": parsed,
                "tool_result": step_info.get("tool_result"),
                "reward": reward,
            }
        )

        step += 1

    # Get metrics
    metrics = env.get_metrics()

    return {
        "seed": seed,
        "budget": budget_slots,
        "policy": policy.__class__.__name__,
        "backend": backend,  # Requested mode; fallback_count records failed/missing model calls.
        "fallback_count": fallback_count,
        "constraint_retention": metrics.constraint_retention_accuracy,
        "tool_correctness": metrics.tool_use_correctness,
        "contradiction_rate": metrics.contradiction_rate,
        "final_success": metrics.final_goal_success and parse_failures == 0,
        "use_memory": use_memory,
        "elapsed_seconds": time.perf_counter() - started,
        "score_source": "learned_utility_without_measured_retention_effects",
        "parse_failures": parse_failures,
        "total_steps": step,
        "final_slots": cmm.current_usage_slots,
        "transcript": transcript,
        "events": cmm.get_event_log(),
    }
