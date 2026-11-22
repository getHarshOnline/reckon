"""Run the declared memory-path controls without changing their workloads."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
from statistics import mean, stdev
import subprocess
import sys

from reckon import _rust
from reckon.experiments import Experiment, compare_experiments
from reckon.measured_retention import RetentionProbeConfig

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "notebooks"))
from _utils.artifacts import RunManager
from _utils.config import NotebookConfig

CONFIG = ROOT / "notebooks/experiments/workload_controls.json"
PROTOCOL = ROOT / "docs/experiments/workload-controls.md"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def identity(config_path, protocol_path):
    paths = subprocess.check_output(
        ["git", "ls-files", "src/reckon", "kernel", "protos", "pyproject.toml"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    paths += [
        "kernel/Cargo.lock",
        str(config_path.relative_to(ROOT)),
        str(protocol_path.relative_to(ROOT)),
        str(Path(__file__).relative_to(ROOT)),
        "notebooks/_utils/config.py",
        "notebooks/_utils/artifacts.py",
    ]
    if subprocess.check_output(["git", "diff", "HEAD", "--", *paths], cwd=ROOT):
        raise RuntimeError("Commit the experiment and runtime inputs before executing")
    for path in [config_path, protocol_path, Path(__file__)]:
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT))],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    return {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": {p: digest(ROOT / p) for p in sorted(set(paths))},
        "extension_sha256": digest(Path(_rust.__file__)),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": {
            p: importlib.metadata.version(p) for p in ["numpy", "scipy", "PyYAML", "reckon"]
        },
    }


def seed_report(plan, seed, index, smoke):
    rows = []
    for task_index, (task, environment) in enumerate(plan["tasks"].items()):
        probe = deepcopy(plan["retention_probe"])
        probe["sampling"]["seed"] = (2_000_000_000 if smoke else plan["probe_seed_base"]) + (
            len(plan["seeds"]) * task_index + index
        ) * plan["probe_seed_stride"]
        config = Experiment(
            task=task,
            environment=environment,
            episodes=plan["episodes"],
            seed=seed,
            retention_probe=RetentionProbeConfig.from_dict(probe),
        )
        rows.extend(
            compare_experiments([config], plan["policies"], plan["budgets"], [seed])["rows"]
        )
    return {"seed": seed, "rows": rows}


def summarize(reports):
    """Describe every arm and intervention; unexpected outcomes never discard a run."""
    output = []
    for number, first in enumerate(reports[0]["rows"]):
        rows = [report["rows"][number] for report in reports]
        runs = [row["runs"][0] for row in rows]
        assert len(runs) == len(reports)
        values = [row["mean"] for row in rows]
        full, utility = [], []
        for report, value in zip(reports, values):
            peers = [r for r in report["rows"] if r["task"] == first["task"]]
            full.append(value - next(r["mean"] for r in peers if r["policy"] == "full"))
            if first["budget_slots"] is not None:
                utility.append(
                    value
                    - next(
                        r["mean"]
                        for r in peers
                        if r["policy"] == "utility" and r["budget_slots"] == first["budget_slots"]
                    )
                )
        batches = [batch for run in runs for batch in run["retention_probes"]]
        evidence = [item for batch in batches for item in batch["evidence"]]
        pairs = [pair for item in evidence for pair in item["trials"]]
        assert sum(run["usage"]["probe_episodes"] for run in runs) == 2 * len(pairs)
        for run in runs:
            usage = run["usage"]
            assert usage["total_episodes"] == usage["task_episodes"] + usage["probe_episodes"]
            assert usage["elapsed_s"] >= usage["probe_elapsed_s"] >= 0
        output.append(
            {
                "task": first["task"],
                "policy": first["policy"],
                "slots": first["budget_slots"],
                "metric": first["metric"],
                "mean": mean(values),
                "stdev": stdev(values) if len(values) > 1 else None,
                "values": values,
                "minus_full": full,
                "minus_utility": utility,
                "writes": sum(run["usage"]["writes"] for run in runs),
                "policy_prunes": sum(run["usage"]["policy_prunes"] for run in runs),
                "task_prunes": sum(
                    ep.get("task_prunes", 0)
                    for run in runs
                    for ep in run["result"]["raw_data"]["episodes"]
                ),
                "mean_peak_slots": mean(run["usage"]["peak_slots"] for run in runs),
                "mean_peak_bytes": mean(run["usage"]["peak_bytes"] for run in runs),
                "task_episodes": sum(run["usage"]["task_episodes"] for run in runs),
                "probe_episodes": 2 * len(pairs),
                "elapsed_s": sum(run["usage"]["elapsed_s"] for run in runs),
                "probe_elapsed_s": sum(run["usage"]["probe_elapsed_s"] for run in runs),
                "probe_batches": len(batches),
                "probe_record_estimates": len(evidence),
                "nonzero_record_deltas": sum(item["delta"] != 0 for item in evidence),
                "initial_record_reads": sum(
                    sum(pair[arm]["initial_record_reads"].values())
                    for pair in pairs
                    for arm in ["baseline", "intervention"]
                ),
                "unequal_probe_pairs": sum(
                    pair["baseline"]["outcome"] != pair["intervention"]["outcome"] for pair in pairs
                ),
            }
        )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--smoke", type=Path)
    args = parser.parse_args()
    config_path = args.config.resolve()
    plan = json.loads(config_path.read_text())
    protocol_path = ROOT / plan.get("protocol", str(PROTOCOL.relative_to(ROOT)))
    if args.plan:
        print(json.dumps(plan, indent=2))
        return
    inputs = identity(config_path, protocol_path)
    smoke_seed = plan.get("smoke_seed", 29_999)
    config = NotebookConfig(
        notebook_name=plan.get("notebook_name", "workload_controls"),
        seed=smoke_seed if args.smoke else plan["seeds"][0],
        seed_count=1 if args.smoke else len(plan["seeds"]),
        num_episodes=plan["episodes"],
        task_name="_".join(plan["tasks"]),
        policy_name="matrix",
        budget_slots=1,
        eval_n_trials=4,
        git_hash=inputs["source_commit"],
        custom={"declaration": plan, "identity": inputs, "smoke_only": bool(args.smoke)},
    )
    if args.smoke:
        output = args.smoke.resolve()
        output.mkdir(parents=True, exist_ok=False)
        seeds = [smoke_seed]
        write_json(output / "config.json", config.to_dict())
    else:
        manager = RunManager(config)
        output = manager.run_dir
        if (output / "config.json").exists():
            raise RuntimeError("Existing run retained; reconcile it before continuing")
        manager.save_config()
        seeds = plan["seeds"]
    print(output, flush=True)
    shutil.copy2(config_path, output / "declaration.json")
    shutil.copy2(protocol_path, output / "protocol.md")
    shutil.copy2(__file__, output / "runner.py")
    shutil.copy2(ROOT / "kernel/Cargo.lock", output / "kernel.Cargo.lock")
    write_json(output / "env_meta.json", inputs)
    reports, hashes = [], {}
    for index, seed in enumerate(seeds):
        report = seed_report(plan, seed, index, bool(args.smoke))
        path = output / f"seed-{seed}.json.gz"
        with gzip.open(path, "xb") as stream:
            stream.write(json.dumps(report, allow_nan=False).encode())
        hashes[path.name] = digest(path)
        reports.append(report)
        print(f"Completed seed {seed}: {len(report['rows'])} rows", flush=True)
    rows = summarize(reports)
    write_json(output / "analysis.json", {"seeds": seeds, "rows": rows})
    write_json(
        output / "complete.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "seeds": seeds,
            "seed_sha256": hashes,
            "identity": inputs,
            "smoke_only": bool(args.smoke),
        },
    )
    print("Completed declared diagnostic and accounting checks.", flush=True)


if __name__ == "__main__":
    main()
