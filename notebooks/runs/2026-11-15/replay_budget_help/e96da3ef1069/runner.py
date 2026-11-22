import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

from reckon import CausalMemoryManager, MemoryBudget
from reckon.memory.policies import FIFOPolicy
from reckon.tasks.task_c_continual import ContinualConfig, ContinualTask

output = Path("replay-budget-comparison")
output.mkdir()
task_config = ContinualConfig(
    num_tasks=3,
    samples_per_task=60,
    test_samples_per_task=60,
    feature_dim=2,
    replay_fraction=0.2,
    learning_rate=0.1,
)
rows = []

for seed in (41, 42, 43):
    accuracy_by_slots = {}
    for slots in (2, 16):
        run = output / f"replay-s{slots}-seed{seed}"
        (run / "logs").mkdir(parents=True)
        budget = MemoryBudget(max_slots=slots, max_bytes=50_000)
        memory = CausalMemoryManager(budget, retention_policy=FIFOPolicy())
        config = {
            "task_name": "continual",
            "task": asdict(task_config),
            "budget": asdict(budget),
            "policy_name": type(memory.retention_policy).__name__,
            "seed": seed,
            "num_episodes": 1,
            "reset_memory": False,
            "learn_utility": True,
        }
        config_text = json.dumps(config, sort_keys=True, indent=2)
        (run / "config.json").write_text(config_text + "\n")
        started_at = datetime.now(timezone.utc)
        started = perf_counter()
        result = ContinualTask(task_config).run(
            memory, num_episodes=1, seed=seed,
            reset_memory=False, learn_utility=True,
        )
        wall_time_ms = (perf_counter() - started) * 1000
        result_data = result.to_dict()
        (run / "result.json").write_text(json.dumps(result_data, indent=2) + "\n")
        (run / "logs" / "events.jsonl").write_text(memory.get_event_log_jsonl())
        episode = result_data["raw_data"]["episodes"][0]
        metrics = {
            "mean_accuracy": result_data["performance"]["mean_accuracy"],
            "forgetting": result_data["performance"]["forgetting"],
            "total_writes": episode["total_writes"],
            "total_reads": episode["total_reads"],
        }
        summary = {
            "config_id": hashlib.sha256(config_text.encode()).hexdigest(),
            "notebook_name": "replay-budget-comparison",
            "task_name": "continual",
            "started_at_ms": int(started_at.timestamp() * 1000),
            "policy_name": config["policy_name"],
            "num_episodes": 1,
            "budget_slots": slots,
            "config": config,
            "metrics": metrics,
            "wall_time_ms": wall_time_ms,
        }
        (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        rows.append({"seed": seed, "slots": slots, **metrics})
        accuracy_by_slots[slots] = metrics["mean_accuracy"]
        print(run)
    difference = accuracy_by_slots[16] - accuracy_by_slots[2]
    print(f"Seed {seed}: 16 minus 2 slots = {100 * difference:+.2f} percentage points")

with (output / "comparison.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
