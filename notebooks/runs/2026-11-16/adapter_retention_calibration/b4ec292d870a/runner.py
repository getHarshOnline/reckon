"""Execute the fixed notebook-adapter calibration and retain complete replay evidence."""

import argparse
from datetime import datetime, timezone
import gzip
import importlib.metadata
import json
from pathlib import Path
import shutil
from statistics import mean, stdev
import subprocess
import sys
from time import perf_counter

from reckon.experiments import POLICIES
from reckon.memory import CausalMemoryManager, RandomPolicy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "notebooks"))
from _utils.adapters.live_retention import (
    ReplayEpisode,
    game_identity,
    run_replay_retention_episode,
)
from _utils.adapters.record_probe import AdapterProbeConfig
from _utils.artifacts import RunManager
from _utils.config import NotebookConfig
from workload_controls import digest, identity, write_json

CONFIG = Path(__file__).with_suffix(".json")


class ComparisonMemory(CausalMemoryManager):
    """Discard no-memory admissions or freeze the explicit-importance input."""

    def __init__(self, budget, policy, name):
        super().__init__(budget, policy)
        self.name = name

    def write(self, *args, **kwargs):
        if self.name == "importance":
            kwargs["metadata"] = {
                **kwargs.get("metadata", {}),
                "importance": kwargs.get("initial_utility", 0.0),
            }
        record_id = super().write(*args, **kwargs)
        if self.name == "none":
            self.prune(record_id, reason="no_memory_baseline")
        return record_id


def input_identity(plan):
    """Include the shared runtime plus every notebook adapter and this runner."""
    result = identity(CONFIG, ROOT / plan["protocol"])
    paths = subprocess.check_output(
        ["git", "ls-files", "notebooks/_utils"], cwd=ROOT, text=True
    ).splitlines()
    paths.append(str(Path(__file__).relative_to(ROOT)))
    subprocess.run(
        ["git", "ls-files", "--error-unmatch", *paths],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if subprocess.check_output(["git", "diff", "HEAD", "--", *paths], cwd=ROOT):
        raise RuntimeError("Commit the notebook implementation before calibration")
    result["source_sha256"].update({path: digest(ROOT / path) for path in paths})
    result["dependencies"].update(
        {
            name: importlib.metadata.version(name)
            for name in ["gymnasium", "minigrid", "textworld", "jericho"]
        }
    )
    return result


def usage(result):
    """Count actual main-store events, including immediate baseline discards."""
    slots = peak_slots = peak_bytes = writes = prunes = discards = 0
    for event in result["events"]:
        if event["op_type"] == "write":
            writes += 1
            slots += 1
        elif event["op_type"] == "prune":
            prunes += 1
            slots -= 1
            details = json.loads(event["details"]) if event.get("details") else {}
            discards += int(details.get("reason") == "no_memory_baseline")
        peak_slots = max(peak_slots, slots)
        peak_bytes = max(peak_bytes, event["bytes_after"])
    return {
        "writes": writes,
        "prunes": prunes,
        "discards": discards,
        "peak_slots": peak_slots,
        "peak_bytes": peak_bytes,
        "final_slots": slots,
    }


def run_arm(
    adapter, steps, seed, name, slots, game_file, causal_weight, expected_game_identity=None
):
    if adapter == "textworld" and expected_game_identity is None:
        raise ValueError("TextWorld comparison requires the identity pinned at generation")
    capacity = 6 * steps + 16 if name in {"none", "full"} else slots
    config = AdapterProbeConfig(adapter, budget_slots=capacity, max_steps=steps)
    started = perf_counter()
    if name == "measured":
        evidence = run_replay_retention_episode(
            config,
            seed,
            game_file=game_file,
            causal_weight=causal_weight,
            expected_game_identity=expected_game_identity,
        )
        result, outcome = evidence["result"], evidence["outcome"]
    else:
        policy = RandomPolicy(seed) if name == "random" else POLICIES[name]()
        memory = ComparisonMemory(config.memory_budget(), policy, name)
        result, outcome = ReplayEpisode(config, seed, game_file, expected_game_identity).run(
            policy, memory
        )
        evidence = {"result": result, "probe_episodes": 0, "probe_elapsed_s": 0}
    elapsed = perf_counter() - started
    counts = usage(result)
    if name == "full" and counts["prunes"]:
        raise RuntimeError("Full-memory allowance did not cover all admissions")
    if name == "none" and (counts["final_slots"] or counts["writes"] != counts["prunes"]):
        raise RuntimeError("No-memory arm retained an admission")
    return {
        "adapter": adapter,
        "policy": name,
        "slots": slots,
        "actual_budget": vars(config.memory_budget()),
        "seed": seed,
        "outcome": outcome,
        "success": result.get("success", result.get("final_success")),
        "usage": counts,
        "inclusive_elapsed_s": elapsed,
        "probe_elapsed_s": evidence["probe_elapsed_s"],
        "probe_episodes": evidence["probe_episodes"],
        "evidence": evidence,
    }


def seed_report(plan, seed, output):
    started = perf_counter()
    rows = []
    games = []
    preparation_elapsed_s = 0.0
    for adapter, steps in plan["adapters"].items():
        game_file = None
        expected_game_identity = None
        if adapter == "textworld":
            from _utils.adapters.textworld_adapter import TextworldAdapter, TextworldConfig

            preparation_started = perf_counter()
            game_dir = output / "games" / str(seed)
            game_dir.mkdir(parents=True, exist_ok=False)
            generator = TextworldAdapter(TextworldConfig(seed=seed, game_dir=str(game_dir)))
            try:
                generator.make_env()
                game_file = generator.game_file
            finally:
                generator.close()
            expected_game_identity = game_identity(game_file)
            games.append(
                {
                    "path": str(Path(game_file).resolve().relative_to(output.resolve())),
                    "identity": expected_game_identity,
                }
            )
            preparation_elapsed_s += perf_counter() - preparation_started
        for name in plan["policies"]:
            for slots in ([None] if name in {"none", "full"} else plan["budgets"]):
                rows.append(
                    run_arm(
                        adapter,
                        steps,
                        seed,
                        name,
                        slots,
                        game_file,
                        plan["causal_weight"],
                        expected_game_identity,
                    )
                )
    return {
        "seed": seed,
        "rows": rows,
        "games": games,
        "game_preparation_elapsed_s": preparation_elapsed_s,
        "seed_elapsed_s": perf_counter() - started,
    }


def compact(report):
    """Keep full arms on disk; aggregate only observed outcomes and measured costs."""
    rows = []
    for row in report["rows"]:
        evidence = row["evidence"]
        batches = evidence.get("batches", [])
        pairs = [entry for batch in batches for entry in batch["evidence"]]
        if row["probe_episodes"] != 2 * len(pairs):
            raise RuntimeError("Replay episode count disagrees with retained pairs")
        if not row["inclusive_elapsed_s"] >= row["probe_elapsed_s"] >= 0:
            raise RuntimeError("Replay time is outside the inclusive episode time")
        rows.append(
            {
                **{key: value for key, value in row.items() if key != "evidence"},
                "probe_batches": len(batches),
                "record_estimates": len(pairs),
                "nonzero_deltas": sum(pair["delta"] != 0 for pair in pairs),
            }
        )
    return {
        "seed": report["seed"],
        "rows": rows,
        "games": report.get("games", []),
        "game_preparation_elapsed_s": report.get("game_preparation_elapsed_s", 0),
        "seed_elapsed_s": report.get("seed_elapsed_s"),
    }


def verify_games(output, reports):
    """Refuse completion if retained games differ from their generated identities."""
    hashes = {}
    for report in reports:
        for game in report["games"]:
            path = output / game["path"]
            if game_identity(path) != game["identity"]:
                raise RuntimeError(
                    "Retained TextWorld game differs from the pinned comparison identity"
                )
            hashes[game["path"]] = game["identity"]["sha256"]
            hashes[str(Path(game["path"]).with_suffix(".json"))] = game["identity"][
                "metadata_sha256"
            ]
    return hashes


def summarize(reports):
    rows = []
    for index, first in enumerate(reports[0]["rows"]):
        arms = [report["rows"][index] for report in reports]
        values = [arm["outcome"] for arm in arms]
        paired = {"none": [], "utility": []}
        for report, value in zip(reports, values):
            for reference in paired:
                if reference == "utility" and first["slots"] is None:
                    continue
                match = next(
                    row
                    for row in report["rows"]
                    if (
                        row["adapter"] == first["adapter"]
                        and row["policy"] == reference
                        and row["slots"] == (None if reference == "none" else first["slots"])
                    )
                )
                paired[reference].append(value - match["outcome"])
        rows.append(
            {
                "adapter": first["adapter"],
                "policy": first["policy"],
                "slots": first["slots"],
                "values": values,
                "mean": mean(values),
                "sd": stdev(values) if len(values) > 1 else None,
                "paired": {
                    name: {
                        "values": vector,
                        "mean": mean(vector),
                        "sd": stdev(vector) if len(vector) > 1 else None,
                    }
                    for name, vector in paired.items()
                    if vector
                },
                "successes": sum(bool(arm["success"]) for arm in arms),
                "main_episodes": len(arms),
                **{
                    name: sum(arm[name] for arm in arms)
                    for name in (
                        "probe_episodes",
                        "probe_elapsed_s",
                        "inclusive_elapsed_s",
                        "probe_batches",
                        "record_estimates",
                        "nonzero_deltas",
                    )
                },
                "usage": [arm["usage"] for arm in arms],
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--smoke", type=Path)
    args = parser.parse_args()
    plan = json.loads(CONFIG.read_text())
    if args.plan:
        print(json.dumps(plan, indent=2))
        return
    inputs = input_identity(plan)
    seeds = [plan["smoke_seed"]] if args.smoke else plan["seeds"]
    config = NotebookConfig(
        notebook_name=plan["notebook_name"],
        run_mode="demo",
        seed=seeds[0],
        seed_count=len(seeds),
        num_episodes=1,
        policy_name="matrix",
        eval_n_trials=1,
        git_hash=inputs["source_commit"],
        custom={
            "declaration": plan,
            "identity": inputs,
            "purpose": "calibration",
            "smoke_only": bool(args.smoke),
        },
    )
    if args.smoke:
        output = args.smoke.resolve()
        output.mkdir(parents=True, exist_ok=False)
    else:
        output = RunManager(config).run_dir
    write_json(output / "config.json", config.to_dict())
    write_json(output / "env_meta.json", inputs)
    shutil.copy2(CONFIG, output / "declaration.json")
    shutil.copy2(ROOT / plan["protocol"], output / "protocol.md")
    shutil.copy2(__file__, output / "runner.py")
    shutil.copy2(ROOT / "kernel/Cargo.lock", output / "kernel.Cargo.lock")
    print(output, flush=True)
    reports, hashes = [], {}
    for seed in seeds:
        report = seed_report(plan, seed, output)
        path = output / f"seed-{seed}.json.gz"
        with gzip.open(path, "xb") as stream:
            stream.write(json.dumps(report, allow_nan=False).encode())
        hashes[path.name] = digest(path)
        reports.append(compact(report))
        print(f"Completed seed {seed}: {len(report['rows'])} main episodes", flush=True)
    if input_identity(plan) != inputs:
        raise RuntimeError("Inputs changed during calibration; preserve the incomplete run")
    game_hashes = verify_games(output, reports)
    write_json(
        output / "analysis.json",
        {
            "seeds": seeds,
            "rows": summarize(reports),
            "seed_costs": [
                {key: value for key, value in report.items() if key != "rows"} for report in reports
            ],
        },
    )
    write_json(
        output / "complete.json",
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "identity": inputs,
            "seeds": seeds,
            "seed_sha256": hashes,
            "game_sha256": game_hashes,
            "smoke_only": bool(args.smoke),
        },
    )


if __name__ == "__main__":
    main()
