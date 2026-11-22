"""Run declared laboratory experiments and comparisons."""

import argparse
from dataclasses import replace
import json
import sys
from typing import Optional

from reckon import __version__
from reckon.experiments import (
    Experiment,
    TASKS,
    POLICY_NAMES,
    compare_experiments,
    load_experiment,
    run_experiment,
)


def _run_flags(parser):
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed for the task's random choices; the same seed repeats a result (default 42)",
    )
    parser.add_argument(
        "--budget-bytes",
        type=int,
        help="Byte allowance for stored records; omit it to limit slots only",
    )
    parser.add_argument("--episodes", type=int, help="Task episodes in each run (default 10)")
    parser.add_argument(
        "--evidence-weight",
        type=float,
        help=(
            "Share from 0 to 1 that the evidence_per_byte policy takes from a record's measured "
            "effect, falling back to a proxy when none was measured, against learned utility "
            "(default 0.5)"
        ),
    )
    parser.add_argument(
        "--reset-memory",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Clear memory between episodes instead of carrying it forward (default: carry)",
    )
    parser.add_argument(
        "--learn-utility",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Update each record's utility from the episode outcome; --no-learn-utility keeps "
            "its starting utility (default: learn)"
        ),
    )
    parser.add_argument(
        "--output",
        choices=["json", "text"],
        default="text",
        help="Print the full result as JSON or a short text summary (default text)",
    )


def _overrides(config, args):
    changes = {
        name: getattr(args, name)
        for name in (
            "seed",
            "budget_bytes",
            "episodes",
            "evidence_weight",
            "reset_memory",
            "learn_utility",
        )
        if getattr(args, name) is not None
    }
    return replace(config, **changes)


def _print_run(run, output):
    if output == "json":
        print(json.dumps(run, indent=2, allow_nan=False))
        return
    config = run["configuration"]
    print(f"{config['task']} / {config['policy']} / seed {config['seed']}")
    for name, value in run["result"]["performance"].items():
        print(f"  {name}: {value}")
    usage = run["usage"]
    print(f"  peak memory: {usage['peak_bytes']} bytes, {usage['peak_slots']} slots")
    print(f"  elapsed: {usage['elapsed_s']:.6f}s")
    print(f"  scores: {run['score_source']}; retention: {run['retention_score_source']}")
    print(
        f"  probe episodes: {usage['probe_episodes']}; probe time: {usage['probe_elapsed_s']:.6f}s"
    )


def _print_comparison(report, output):
    if output == "json":
        print(json.dumps(report, indent=2, allow_nan=False))
        return
    print(
        "task policy slots learn reset metric mean stddev peak_bytes peak_slots "
        "seconds probe_episodes probe_seconds total_episodes"
    )
    for row in report["rows"]:
        spread = "unavailable" if row["stdev"] is None else f"{row['stdev']:.6f}"
        slots = row["policy"] if row["budget_slots"] is None else row["budget_slots"]
        print(
            f"{row['task']} {row['policy']} {slots} {row['learn_utility']} "
            f"{row['reset_memory']} {row['metric']} "
            f"{row['mean']:.6f} {spread} {row['mean_peak_bytes']:.1f} "
            f"{row['mean_peak_slots']:.1f} {row['elapsed_s']:.6f} "
            f"{row['probe_episodes']} {row['probe_elapsed_s']:.6f} {row['total_episodes']}"
        )
    print("Peak columns are means across seeds; spread is sample standard deviation.")
    print(
        "Seconds include probe time; probe episodes count both arms separately from task episodes."
    )


def _make_parser():
    """Declare the shared task and comparison command options."""
    parser = argparse.ArgumentParser(
        prog="reckon", description="Memory experiments under resource budgets"
    )
    parser.add_argument("--version", action="version", version=f"reckon {__version__}")
    commands = parser.add_subparsers(dest="command")
    run = commands.add_parser("run", help="Run one declared experiment")
    run.add_argument(
        "--task", choices=list(TASKS), help="Built-in task to run; reckon list names them"
    )
    run.add_argument("--config", help="YAML or JSON experiment")
    run.add_argument(
        "--policy",
        choices=list(POLICY_NAMES),
        help="Retention policy that chooses what to discard when memory is full (default fifo)",
    )
    run.add_argument(
        "--budget-slots", type=int, help="Slot allowance for stored records (default 10)"
    )
    _run_flags(run)
    compare = commands.add_parser("compare", help="Compare tasks, policies, budgets and seeds")
    compare.add_argument(
        "--tasks", nargs="+", choices=list(TASKS), help="Tasks to compare (default: all of them)"
    )
    compare.add_argument(
        "--config", action="append", help="Task configuration; repeat for several tasks"
    )
    compare.add_argument(
        "--policies",
        nargs="+",
        choices=list(POLICY_NAMES),
        default=["none", "full", "fifo", "lru", "random", "importance", "utility"],
        help=(
            "Retention policies to compare "
            "(default: none, full, fifo, lru, random, importance, utility)"
        ),
    )
    compare.add_argument(
        "--budget-slots",
        nargs="+",
        type=int,
        default=[2, 10],
        help="Slot allowances to compare (default 2 and 10)",
    )
    compare.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        help=(
            "Distinct seeds to repeat each comparison over "
            "(default 42, 43 and 44, or --seed alone)"
        ),
    )
    _run_flags(compare)
    commands.add_parser("list", help="List available tasks")
    commands.add_parser("viz", help="Serve, import or inspect visualization runs")
    return parser


def _run_command(args):
    """Apply command overrides to one declared experiment."""
    if not args.task and not args.config:
        raise ValueError("run needs --task or --config")
    config = load_experiment(args.config) if args.config else Experiment()
    changes = {
        name: getattr(args, name)
        for name in ("task", "policy", "budget_slots")
        if getattr(args, name) is not None
    }
    config = _overrides(replace(config, **changes), args)
    _print_run(run_experiment(config), args.output)


def _compare_command(args):
    """Apply the same overrides to every selected task in a comparison."""
    if args.tasks and args.config:
        raise ValueError("Use --tasks or --config for task selection")
    configs = (
        [load_experiment(path) for path in args.config]
        if args.config
        else [Experiment(task=name) for name in (args.tasks or list(TASKS))]
    )
    configs = [_overrides(config, args) for config in configs]
    seeds = args.seeds or ([args.seed] if args.seed is not None else [42, 43, 44])
    report = compare_experiments(configs, args.policies, args.budget_slots, seeds)
    _print_comparison(report, args.output)


def main(arguments: Optional[list[str]] = None):
    """Run tasks, compare a matrix or use the existing visualization commands."""
    argv = sys.argv[1:] if arguments is None else arguments
    if argv and argv[0] == "viz":
        # The core CLI does not require or initialize the optional debugger.
        # pylint: disable-next=import-outside-toplevel
        from reckon.viz.cli import main as viz_main

        return viz_main(argv[1:])
    parser = _make_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "list":
        for name, task_type in TASKS.items():
            print(f"{name}: {task_type().description}")
        return 0
    handler = {"run": _run_command, "compare": _compare_command}.get(args.command)
    if handler is None:
        return 1
    try:
        handler(args)
    except (ValueError, TypeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
