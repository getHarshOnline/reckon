"""
Notebook utilities for Reckon experiments.

This package provides consistent configuration, artifact management,
statistical testing, and plotting across all publication-grade notebooks.

Modules:
    config: Configuration management with hashing for reproducibility
    seeds: Seed management for deterministic experiments
    artifacts: Run directory and artifact export
    stats: Statistical testing (permutation, bootstrap, effect size)
    plots: Publication-quality matplotlib utilities
    probe_integration: Probe cost tracking for causal evaluation

Example:
    from _utils import (
        NotebookConfig, print_config, print_repro_stamp, set_all_seeds,
        RunManager, paired_permutation_test, bootstrap_ci,
        setup_plotting, add_caption, COLORS,
        ProbeIntegration, BenchmarkResult, generate_pareto_data,
    )
"""

from .config import (
    NotebookConfig,
    hash_config,
    print_config,
    print_repro_stamp,
    get_git_hash,
)
from .seeds import set_all_seeds, get_seed_range, SeedContext
from .artifacts import RunManager, get_runs_dir
from .stats import (
    paired_permutation_test,
    bootstrap_ci,
    effect_size,
    format_ci,
    summarize_stats,
)
from .plots import (
    setup_plotting,
    add_caption,
    save_figure,
    plot_pareto_frontier,
    plot_quality_vs_overhead,
    plot_comparison_bars,
    plot_delta_distribution,
    COLORS,
    POLICY_COLORS,
)
from .probe_integration import (
    ProbeIntegration,
    BenchmarkResult,
    ParetoPoint,
    compute_efficiency_metrics,
    generate_pareto_data,
    compute_pareto_frontier,
)

__all__ = [
    # Config
    "NotebookConfig",
    "hash_config",
    "print_config",
    "print_repro_stamp",
    "get_git_hash",
    # Seeds
    "set_all_seeds",
    "get_seed_range",
    "SeedContext",
    # Artifacts
    "RunManager",
    "get_runs_dir",
    # Stats
    "paired_permutation_test",
    "bootstrap_ci",
    "effect_size",
    "format_ci",
    "summarize_stats",
    # Plots
    "setup_plotting",
    "add_caption",
    "save_figure",
    "plot_pareto_frontier",
    "plot_quality_vs_overhead",
    "plot_comparison_bars",
    "plot_delta_distribution",
    "COLORS",
    "POLICY_COLORS",
    # Probe Integration
    "ProbeIntegration",
    "BenchmarkResult",
    "ParetoPoint",
    "compute_efficiency_metrics",
    "generate_pareto_data",
    "compute_pareto_frontier",
]
