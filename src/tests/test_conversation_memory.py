"""Exercise actual retained-context use by the notebook conversation runner."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "notebooks"))
from _utils.adapters import conversation
from _utils.adapters.ollama_client import SimulatedOllamaBackend
from _utils.adapters.tool_env import ToolEnv
from reckon.memory import FIFOPolicy


@pytest.mark.parametrize("seed", [42, 43, 44, 45, 46])
def test_final_answer_requires_retained_context(seed):
    supplied = conversation.run_conversation_episode(FIFOPolicy(), 100, seed)
    withheld = conversation.run_conversation_episode(FIFOPolicy(), 100, seed, use_memory=False)
    assert supplied["constraint_retention"] == 1
    assert withheld["constraint_retention"] == 0
    assert supplied["transcript"][-1]["retrieved_ids"]
    assert all(not turn["retrieved_ids"] for turn in withheld["transcript"])
    assert any(e["op_type"] == "update_score" for e in supplied["events"])
    assert not any(e["op_type"] == "update_score" for e in withheld["events"])
    assert not any(e["op_type"] == "prune" for e in supplied["events"])


def test_pruning_changes_final_answer_without_hidden_backend_memory():
    small = conversation.run_conversation_episode(FIFOPolicy(), 1, 42)
    assert small["constraint_retention"] == 0
    assert not small["transcript"][-1]["retrieved_ids"]
    assert any(e["op_type"] == "prune" for e in small["events"])


def test_earlier_acknowledgements_and_writes_do_not_count_as_final_recall():
    env = ToolEnv()
    _, info = env.reset(42)
    values = " ".join(info["constraints"].values())
    for index in range(len(env.get_episode().messages)):
        final = "Done." if index == len(env.get_episode().messages) - 1 else values
        env.step(
            {"tool": None, "final": final, "memory_write": [{"tag": "all", "content": values}]}
        )
    assert env.get_metrics().constraint_retention_accuracy == 0


def test_simulator_reads_current_prompt_and_does_not_cache_constraints():
    backend = SimulatedOllamaBackend()
    backend.chat(
        [{"role": "user", "content": "Important: when you respond, use casual (tone requirement)."}]
    )
    prompt = {"role": "user", "content": "Please provide a final answer."}
    absent = json.loads(backend.chat([prompt])["message"]["content"])
    present = json.loads(
        backend.chat([{"role": "system", "content": "MEMORY CONTEXT:\n- tone: casual"}, prompt])[
            "message"
        ]["content"]
    )
    assert "casual" not in absent["final"]
    assert "casual" in present["final"]


def test_optional_model_receives_retained_context_and_fallback_is_counted(monkeypatch):
    calls = []
    backend = SimulatedOllamaBackend()

    def model(**kwargs):
        calls.append(kwargs["messages"])
        if len(calls) == 1:
            raise RuntimeError("model unavailable")
        return backend.chat(kwargs["messages"])

    monkeypatch.setattr(conversation, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(conversation, "ollama_chat", model)
    result = conversation.run_conversation_episode(FIFOPolicy(), 100, 42, backend="ollama")
    assert result["fallback_count"] == 1
    assert result["constraint_retention"] == 1
    assert any(m["content"].startswith("MEMORY CONTEXT:") for m in calls[-1])


def test_parse_failure_prevents_composite_success(monkeypatch):
    monkeypatch.setattr(conversation, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(
        conversation, "ollama_chat", lambda **kwargs: {"message": {"content": "invalid json"}}
    )
    result = conversation.run_conversation_episode(FIFOPolicy(), 100, 42, backend="ollama")
    assert result["parse_failures"] == result["total_steps"]
    assert result["final_success"] is False
