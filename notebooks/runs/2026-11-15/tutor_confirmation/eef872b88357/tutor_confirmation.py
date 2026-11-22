"""Run the fixed Tutor protocol, retaining resumable per-seed raw evidence."""

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import shutil
from statistics import mean, stdev
import subprocess

from scipy.stats import nct, t, ttest_1samp

from reckon import _rust
from reckon.experiments import compare_experiments, load_experiment

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "notebooks/experiments/tutor_confirmation.json"
PROTOCOL = ROOT / "docs/experiments/tutor-confirmation.md"
POLICIES = [
    "none",
    "full",
    "fifo",
    "lru",
    "random",
    "importance",
    "utility",
    "diversity",
    "measured",
]
SEEDS = list(range(20_000, 20_256))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    """Replace only this runner's completed index or temporary result."""
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def planning():
    results = []
    for label, sigma, family in [("outer", 0.25, 2), ("probe", 0.20, 4)]:
        critical = t.ppf(1 - 0.05 / family / 2, 255)
        nc = 0.05 * math.sqrt(256) / sigma
        results.append(
            {
                "scope": label,
                "n": 256,
                "paired_sd": sigma,
                "family_size": family,
                "effect": 0.05,
                "power": float(nct.sf(critical, 255, nc) + nct.cdf(-critical, 255, nc)),
            }
        )
    return results


def identity():
    tracked = subprocess.check_output(
        ["git", "ls-files", "src", "kernel", "protos", "pyproject.toml"], cwd=ROOT, text=True
    ).splitlines()
    paths = sorted(
        set(
            tracked
            + [
                "kernel/Cargo.lock",
                str(CONFIG.relative_to(ROOT)),
                str(PROTOCOL.relative_to(ROOT)),
                str(Path(__file__).resolve().relative_to(ROOT)),
            ]
        )
    )
    if subprocess.check_output(["git", "diff", "HEAD", "--", *paths], cwd=ROOT):
        raise RuntimeError("Commit the reviewed source, configuration and protocol before running")
    for path in [CONFIG, PROTOCOL, Path(__file__).resolve()]:
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT))],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    return {
        "source_sha256": {path: digest(ROOT / path) for path in paths},
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ["numpy", "scipy", "PyYAML", "reckon"]
        },
        "extension_sha256": digest(Path(_rust.__file__)),
        "seeds": SEEDS,
        "policies": POLICIES,
        "budgets": [2, 4],
        "planning": planning(),
    }


def one_seed(seed, index):
    experiment = load_experiment(str(CONFIG))
    probe = experiment.retention_probe
    assert probe is not None
    experiment = replace(
        experiment,
        retention_probe=replace(
            probe, sampling=replace(probe.sampling, seed=10_000_000 + index * 1_000_000)
        ),
    )
    report = compare_experiments([experiment], POLICIES, [2, 4], [seed])
    if len(report["rows"]) != 16:
        raise RuntimeError("Incomplete policy matrix")
    for row in report["rows"]:
        (run,) = row["runs"]
        assert run["configuration"]["seed"] == seed
        assert run["usage"]["task_episodes"] == 5
        assert math.isclose(row["mean"], run["result"]["performance"]["mean_return"])
        count = sum(batch["probe_episodes"] for batch in run["retention_probes"])
        assert count == run["usage"]["probe_episodes"]
        for batch in run["retention_probes"]:
            assert len(batch["records"]) <= row["budget_slots"]
            for evidence in batch["evidence"]:
                assert evidence["n_trials"] == len(evidence["trials"]) == 256
                assert evidence["probe_episodes"] == 512
                for trial in evidence["trials"]:
                    assert trial["baseline"]["seed"] == trial["intervention"]["seed"]
    return report


def store_seed(directory, seed, report):
    path = directory / f"seed-{seed}.json.gz"
    if path.exists():
        raise RuntimeError(f"Existing unindexed result needs reconciliation: {path}")
    temporary = path.with_suffix(path.suffix + ".pending")
    raw = json.dumps(report, separators=(",", ":"), allow_nan=False).encode()
    temporary.write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
    temporary.replace(path)
    return {"path": path.name, "sha256": digest(path)}


def summarize(directory, saved):
    groups = {}
    for seed in SEEDS:
        entry = saved[str(seed)]
        path = directory / entry["path"]
        if digest(path) != entry["sha256"]:
            raise RuntimeError(f"Changed result: {path}")
        report = json.loads(gzip.decompress(path.read_bytes()))
        assert report["seeds"] == [seed]
        for row in report["rows"]:
            key = (row["policy"], row["budget_slots"])
            groups.setdefault(key, []).append((seed, row["runs"][0]))
    assert len(groups) == 16, "Incomplete saved policy matrix"
    rows = []
    values = {}
    for (policy, slots), runs in groups.items():
        assert [seed for seed, _ in runs] == SEEDS
        scores = [run["result"]["performance"]["mean_return"] for _, run in runs]
        values[(policy, slots)] = scores
        spread = stdev(scores)
        margin = float(t.ppf(0.975, 255)) * spread / 16
        row = {
            "policy": policy,
            "slots": slots,
            "n": 256,
            "mean": mean(scores),
            "stdev": spread,
            "ci95_lower": mean(scores) - margin,
            "ci95_upper": mean(scores) + margin,
        }
        for key in [
            "task_episodes",
            "probe_episodes",
            "elapsed_s",
            "task_elapsed_s",
            "probe_elapsed_s",
            "writes",
            "policy_prunes",
        ]:
            row[key] = sum(run["usage"][key] for _, run in runs)
        for key in ["peak_bytes", "peak_slots"]:
            row["mean_" + key] = mean(run["usage"][key] for _, run in runs)
        rows.append(row)
    contrasts = []
    for slots in [2, 4]:
        diffs = [a - b for a, b in zip(values[("measured", slots)], values[("utility", slots)])]
        delta, spread = mean(diffs), stdev(diffs)
        margin = float(t.ppf(1 - 0.025 / 2, 255)) * spread / 16
        p = float(getattr(ttest_1samp(diffs, 0), "pvalue")) if spread else float(delta == 0)
        contrasts.append(
            {
                "slots": slots,
                "difference": "measured_minus_utility",
                "mean": delta,
                "stdev": spread,
                "ci97_5_lower": delta - margin,
                "ci97_5_upper": delta + margin,
                "p_value": p,
                "p_value_bonferroni": min(1, 2 * p),
                "paired_differences": diffs,
            }
        )
    write_json(
        directory / "analysis.json",
        {"complete": True, "rows": rows, "primary_contrasts": contrasts},
    )
    with (directory / "metrics.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows, contrasts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--smoke", type=Path)
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    load_experiment(str(CONFIG)).validate()
    if args.plan:
        print(
            json.dumps(
                {
                    "seeds": [SEEDS[0], SEEDS[-1]],
                    "policies": POLICIES,
                    "budgets": [2, 4],
                    "planning": planning(),
                },
                indent=2,
            )
        )
        return
    if args.smoke:
        args.smoke.mkdir(parents=True, exist_ok=True)
        print(store_seed(args.smoke, 105, one_seed(105, 999)), flush=True)
        return
    inputs = identity()
    run_id = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:12]
    directory = ROOT / "notebooks/runs/2026-11-15/tutor_confirmation" / run_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "manifest.json"
    if manifest.exists():
        state = json.loads(manifest.read_text())
        assert state["identity"] == inputs
    else:
        state = {
            "identity": inputs,
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "complete": False,
            "results": {},
        }
        for source in [CONFIG, PROTOCOL, Path(__file__).resolve(), ROOT / "kernel/Cargo.lock"]:
            shutil.copy2(source, directory / source.name)
        write_json(manifest, state)
    print(directory, flush=True)
    for index, seed in enumerate(SEEDS):
        if str(seed) in state["results"]:
            entry = state["results"][str(seed)]
            assert digest(directory / entry["path"]) == entry["sha256"]
            continue
        report = one_seed(seed, index)
        state["results"][str(seed)] = store_seed(directory, seed, report)
        write_json(manifest, state)
        print(f"Completed {index+1}/{len(SEEDS)} seeds", flush=True)
    summarize(directory, state["results"])
    state["complete"] = True
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(manifest, state)
    print("Complete; analysis.json and metrics.csv retain the fixed analysis.", flush=True)


if __name__ == "__main__":
    main()
