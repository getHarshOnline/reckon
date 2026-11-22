"""Run the saved key-door demonstration once, from the repository root.

To repeat it, copy this script and config.json to a fresh directory first.
The native task, memory manager and event exporter supply the result.
"""

from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

from reckon import CausalMemoryManager, MemoryBudget
from reckon import _rust
from reckon.memory.policies import FIFOPolicy
from reckon.tasks.task_a_keydoor import KeyDoorTask


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


root = Path.cwd()
output = Path(__file__).resolve().parent
config = json.loads((output / "config.json").read_text())
assert config["task_name"] == "keydoor"
assert config["policy_name"] == "FIFOPolicy"
(output / "logs").mkdir()

tracked = subprocess.check_output(
    ["git", "ls-files", "src/reckon", "kernel", "protos", "pyproject.toml"],
    text=True,
).splitlines()
sources = {name: digest(root / name) for name in tracked if (root / name).is_file()}
extension_hash = digest(Path(_rust.__file__))
environment = {
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "source_sha256": sources,
    "tracked_diff": subprocess.check_output(["git", "diff", "HEAD", "--stat"], text=True),
    "extension_sha256": extension_hash,
    "runner_sha256": digest(Path(__file__)),
    "python": sys.version.split()[0],
    "platform": platform.platform(),
    "dependencies": {item.metadata["Name"]: item.version for item in metadata.distributions()},
}
save(output / "env_meta.json", environment)
with (output / "kernel.Cargo.lock").open("xb") as handle:
    handle.write((root / "kernel/Cargo.lock").read_bytes())

budget = MemoryBudget(max_slots=config["budget_slots"], max_bytes=config["budget_bytes"])
memory = CausalMemoryManager(budget, retention_policy=FIFOPolicy())
started_at = datetime.now(timezone.utc)
started = perf_counter()
result = KeyDoorTask().run(
    memory,
    num_episodes=config["num_episodes"],
    seed=config["seed"],
    reset_memory=config["reset_memory"],
    learn_utility=config["learn_utility"],
).to_dict()
wall_time_ms = (perf_counter() - started) * 1000
save(output / "result.json", result)
with (output / "logs/events.jsonl").open("x") as handle:
    handle.write(memory.get_event_log_jsonl())
save(output / "final_records.json", [record.to_dict() for record in memory.get_all_records()])
save(output / "summary.json", {
    "config_id": digest(output / "config.json"),
    "notebook_name": "keydoor-export-demonstration",
    "task_name": config["task_name"],
    "started_at_ms": int(started_at.timestamp() * 1000),
    "policy_name": config["policy_name"],
    "num_episodes": config["num_episodes"],
    "budget_slots": config["budget_slots"],
    "config": config,
    "metrics": {
        "success_rate": result["performance"]["success_rate"],
        "total_writes": result["raw_data"]["total_writes"],
        "total_reads": result["raw_data"]["total_reads"],
    },
    "wall_time_ms": wall_time_ms,
})
assert all(digest(root / name) == value for name, value in sources.items())
assert digest(Path(_rust.__file__)) == extension_hash
print(json.dumps(result, indent=2))
