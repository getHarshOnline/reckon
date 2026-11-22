"""
Plotting utilities for Reckon notebooks.

Provides consistent matplotlib styling, publication-quality captions,
and common plot types used across experiments. Uses Matplotlib only
(no seaborn) for minimal dependencies.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Optional, Union

__all__ = [
    "setup_plotting",
    "add_caption",
    "save_figure",
    "plot_pareto_frontier",
    "plot_quality_vs_overhead",
    "plot_comparison_bars",
    "plot_delta_distribution",
    "COLORS",
    "POLICY_COLORS",
]


# =============================================================================
# Color Palettes
# =============================================================================

COLORS = {
    # Primary palette
    "primary": "#3B82F6",    # Blue
    "secondary": "#10B981",  # Green
    "accent": "#F59E0B",     # Amber
    "danger": "#EF4444",     # Red
    "warning": "#F97316",    # Orange
    "neutral": "#6B7280",    # Gray

    # Policy-specific colors (for consistency across notebooks)
    "fifo": "#3B82F6",       # Blue
    "lru": "#10B981",        # Green
    "utility": "#F59E0B",    # Amber
    "evidence_per_byte": "#8B5CF6",     # Purple

    # Edge type colors (for causal graphs)
    "measured": "#3B82F6",   # Blue (solid)
    "proxy": "#9CA3AF",      # Gray (dashed)
}

POLICY_COLORS = {
    "fifo": COLORS["fifo"],
    "lru": COLORS["lru"],
    "utility": COLORS["utility"],
    "evidence_per_byte": COLORS["evidence_per_byte"],
}


# =============================================================================
# Setup and Configuration
# =============================================================================

def setup_plotting(
    style: str = "default",
    figsize: tuple[float, float] = (8, 5),
    dpi: int = 100,
) -> None:
    """
    Configure matplotlib for consistent notebook plots.

    Sets publication-quality defaults including font sizes, grid styling,
    and color scheme. Call this once at the start of each notebook.

    Args:
        style: Matplotlib style name ("default", "dark_background", etc.).
        figsize: Default figure size as (width, height) in inches.
        dpi: Display resolution in dots per inch.

    Example:
        setup_plotting()
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 4, 9])
        plt.show()
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib as mpl
    except ImportError:
        warnings.warn("matplotlib not available, plotting disabled")
        return

    # Reset to default first
    mpl.rcdefaults()

    # Apply named style if not default
    if style != "default":
        try:
            plt.style.use(style)
        except OSError:
            warnings.warn(f"Style '{style}' not found, using default")

    # Publication-quality settings
    plt.rcParams.update({
        # Figure
        "figure.figsize": figsize,
        "figure.dpi": dpi,
        "figure.facecolor": "white",
        "figure.edgecolor": "white",

        # Axes
        "axes.facecolor": "white",
        "axes.edgecolor": "#333333",
        "axes.linewidth": 1.0,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.labelsize": 11,
        "axes.titlesize": 12,

        # Grid
        "grid.color": "#E5E5E5",
        "grid.linewidth": 0.5,
        "grid.alpha": 0.8,

        # Ticks
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "xtick.direction": "out",
        "ytick.direction": "out",

        # Legend
        "legend.fontsize": 10,
        "legend.framealpha": 0.9,
        "legend.edgecolor": "#CCCCCC",

        # Lines
        "lines.linewidth": 2.0,
        "lines.markersize": 6,

        # Font
        "font.family": "sans-serif",
        "font.size": 10,

        # Savefig defaults
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "savefig.facecolor": "white",
    })


# =============================================================================
# Captions and Annotations
# =============================================================================

def add_caption(
    ax: Any,
    text: str,
    n: Optional[int] = None,
    seeds: Optional[str] = None,
    test: Optional[str] = None,
    mode: Optional[str] = None,
    policy: Optional[str] = None,
    budget: Optional[int] = None,
    position: str = "below",
) -> None:
    """
    Add a publication-quality caption to a plot.

    Captions include the main description plus optional metadata about
    sample size, seeds, statistical tests, and experimental conditions.

    Args:
        ax: Matplotlib axes object.
        text: Main caption text describing what the plot shows.
        n: Sample size (displayed as "n=X").
        seeds: Seed range string (e.g., "42-51").
        test: Statistical test used (e.g., "permutation").
        mode: Run mode (e.g., "demo" or "paper").
        policy: Policy name (e.g., "evidence_per_byte").
        budget: Memory budget in slots.
        position: Caption position ("below" or "title").

    Example:
        add_caption(
            ax,
            "EvidencePerBytePolicy outperforms FIFO under memory pressure",
            n=100,
            seeds="42-51",
            test="permutation",
            mode="paper",
        )
    """
    # Build caption parts
    parts = [text]
    meta = []

    if n is not None:
        meta.append(f"n={n}")
    if seeds is not None:
        meta.append(f"seeds={seeds}")
    if test is not None:
        meta.append(f"test={test}")
    if mode is not None:
        meta.append(f"mode={mode}")
    if policy is not None:
        meta.append(f"policy={policy}")
    if budget is not None:
        meta.append(f"budget={budget}")

    if meta:
        parts.append(f"({', '.join(meta)})")

    caption = " ".join(parts)

    if position == "below":
        ax.annotate(
            caption,
            xy=(0.5, -0.15),
            xycoords="axes fraction",
            ha="center",
            va="top",
            fontsize=9,
            color="#666666",
            style="italic",
        )
    elif position == "title":
        ax.set_title(caption, fontsize=11)


def save_figure(
    fig: Any,
    path: Union[str, Path],
    dpi: int = 150,
    close: bool = True,
) -> Path:
    """
    Save figure with consistent settings.

    Args:
        fig: Matplotlib figure object.
        path: Output path (directory will be created if needed).
        dpi: Image resolution.
        close: Whether to close figure after saving.

    Returns:
        Path to the saved file.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise RuntimeError("matplotlib required for save_figure") from e

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")

    if close:
        plt.close(fig)

    return path


# =============================================================================
# Common Plot Types
# =============================================================================

def plot_pareto_frontier(
    ax: Any,
    budgets: list[float],
    performances: list[float],
    labels: Optional[list[str]] = None,
    highlight_pareto: bool = True,
    xlabel: str = "Memory Budget (slots)",
    ylabel: str = "Performance",
) -> None:
    """
    Plot budget vs performance with Pareto frontier highlighted.

    Points on the Pareto frontier are those that are not dominated by
    any other point (no other point has both better performance AND
    lower budget).

    Args:
        ax: Matplotlib axes object.
        budgets: X-axis values (lower is better, e.g., memory cost).
        performances: Y-axis values (higher is better, e.g., success rate).
        labels: Optional text labels for each point.
        highlight_pareto: Whether to highlight Pareto-optimal points.
        xlabel: X-axis label.
        ylabel: Y-axis label.

    Example:
        plot_pareto_frontier(
            ax,
            budgets=[10, 20, 30, 40],
            performances=[0.6, 0.75, 0.85, 0.88],
            labels=["FIFO@10", "FIFO@20", "Evidence per byte@10", "Evidence per byte@20"],
        )
    """
    # Plot all points
    ax.scatter(
        budgets, performances,
        c=COLORS["primary"], s=50, alpha=0.7, zorder=3,
    )

    # Find and highlight Pareto frontier
    if highlight_pareto:
        pareto_mask = _get_pareto_mask(budgets, performances)
        pareto_x = [b for b, m in zip(budgets, pareto_mask) if m]
        pareto_y = [p for p, m in zip(performances, pareto_mask) if m]

        # Sort by budget for connected line
        sorted_pairs = sorted(zip(pareto_x, pareto_y))
        pareto_x = [p[0] for p in sorted_pairs]
        pareto_y = [p[1] for p in sorted_pairs]

        ax.plot(
            pareto_x, pareto_y,
            c=COLORS["accent"], linewidth=2,
            label="Pareto frontier", zorder=2,
        )
        ax.scatter(
            pareto_x, pareto_y,
            c=COLORS["accent"], s=80, marker="*", zorder=4,
        )

    # Add text labels
    if labels:
        for x, y, label in zip(budgets, performances, labels):
            ax.annotate(
                label, (x, y),
                textcoords="offset points",
                xytext=(5, 5),
                fontsize=8,
            )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()


def _get_pareto_mask(
    budgets: list[float],
    performances: list[float],
) -> list[bool]:
    """
    Identify Pareto-optimal points.

    A point is Pareto-optimal if no other point dominates it
    (has lower/equal budget AND higher/equal performance with
    at least one strict inequality).

    Args:
        budgets: Budget values (lower is better).
        performances: Performance values (higher is better).

    Returns:
        Boolean mask where True indicates Pareto-optimal points.
    """
    n = len(budgets)
    mask = [True] * n

    for i in range(n):
        for j in range(n):
            if i != j:
                # Check if j dominates i
                budget_ok = budgets[j] <= budgets[i]
                perf_ok = performances[j] >= performances[i]
                strictly_better = (
                    budgets[j] < budgets[i] or
                    performances[j] > performances[i]
                )

                if budget_ok and perf_ok and strictly_better:
                    mask[i] = False
                    break

    return mask


def plot_quality_vs_overhead(
    ax: Any,
    points: list,
    highlight_pareto: bool = True,
    show_labels: bool = True,
    xlabel: str = "Probe Overhead Ratio",
    ylabel: str = "Memory Quality",
    title: str = "Quality vs Probe Overhead",
) -> None:
    """
    Plot memory quality vs probe overhead with Pareto frontier.

    This visualization shows the tradeoff between:
    - X-axis: Probe overhead (fraction of compute spent on causal evaluation)
    - Y-axis: An explicitly selected outcome with known producer and units

    Points on the Pareto frontier represent configurations where you cannot
    improve quality without increasing probe overhead.

    Args:
        ax: Matplotlib axes object.
        points: List of ParetoPoint objects with x, y, label, is_pareto.
        highlight_pareto: Whether to highlight Pareto-optimal points.
        show_labels: Whether to show point labels.
        xlabel: X-axis label.
        ylabel: Y-axis label.
        title: Plot title.

    Example:
        from _utils import generate_pareto_data
        points = generate_pareto_data(results, x_metric="probe_overhead_ratio",
                                       y_metric="success_rate")
        plot_quality_vs_overhead(ax, points, ylabel="Success rate")
    """
    # Separate Pareto and dominated points
    pareto_points = [p for p in points if getattr(p, 'is_pareto', False)]
    dominated_points = [p for p in points if not getattr(p, 'is_pareto', False)]

    # Plot dominated points (gray, smaller)
    if dominated_points:
        dom_x = [p.x for p in dominated_points]
        dom_y = [p.y for p in dominated_points]
        ax.scatter(
            dom_x, dom_y,
            c=COLORS["neutral"], s=40, alpha=0.5, zorder=2,
            label="Dominated",
        )

    # Plot Pareto-optimal points
    if pareto_points and highlight_pareto:
        par_x = [p.x for p in pareto_points]
        par_y = [p.y for p in pareto_points]

        # Sort for line drawing
        sorted_pairs = sorted(zip(par_x, par_y))
        sorted_x = [pair[0] for pair in sorted_pairs]
        sorted_y = [pair[1] for pair in sorted_pairs]

        # Draw frontier line
        ax.plot(
            sorted_x, sorted_y,
            c=COLORS["accent"], linewidth=2, linestyle="--",
            label="Pareto frontier", zorder=3,
        )

        # Draw frontier points (stars)
        ax.scatter(
            par_x, par_y,
            c=COLORS["secondary"], s=100, marker="*", zorder=4,
            label="Pareto optimal",
        )

    # Add labels
    if show_labels:
        for p in points:
            label = getattr(p, 'label', '')
            if label:
                offset = (5, 5) if getattr(p, 'is_pareto', False) else (3, 3)
                ax.annotate(
                    label, (p.x, p.y),
                    textcoords="offset points",
                    xytext=offset,
                    fontsize=8,
                    alpha=0.8,
                )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="lower right")

    # Format x-axis as percentage
    ax.set_xlim(-0.02, max(p.x for p in points) * 1.1 + 0.02)
    ax.set_ylim(0, min(1.05, max(p.y for p in points) * 1.1))


def plot_comparison_bars(
    ax: Any,
    labels: list[str],
    values: list[float],
    ci_bounds: Optional[list[tuple[float, float]]] = None,
    colors: Optional[list[str]] = None,
    horizontal: bool = False,
) -> None:
    """
    Plot comparison bar chart with optional confidence intervals.

    Args:
        ax: Matplotlib axes object.
        labels: Bar labels.
        values: Bar heights/lengths.
        ci_bounds: Optional (lower, upper) CI bounds for each bar.
        colors: Optional colors for each bar.
        horizontal: If True, use horizontal bars.

    Example:
        plot_comparison_bars(
            ax,
            labels=["FIFO", "LRU", "Evidence per byte"],
            values=[0.65, 0.72, 0.89],
            ci_bounds=[(0.60, 0.70), (0.67, 0.77), (0.85, 0.93)],
        )
    """
    try:
        import numpy as np
    except ImportError as e:
        raise RuntimeError("numpy required for plot_comparison_bars") from e

    n = len(labels)
    positions = np.arange(n)

    if colors is None:
        colors = [COLORS["primary"]] * n

    # Compute error bar values from CI bounds
    yerr = None
    if ci_bounds:
        yerr = np.array([
            [v - lo for (lo, hi), v in zip(ci_bounds, values)],
            [hi - v for (lo, hi), v in zip(ci_bounds, values)],
        ])

    if horizontal:
        ax.barh(positions, values, xerr=yerr, color=colors, alpha=0.8, capsize=3)
        ax.set_yticks(positions)
        ax.set_yticklabels(labels)
    else:
        ax.bar(positions, values, yerr=yerr, color=colors, alpha=0.8, capsize=3)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=45, ha="right")


def plot_delta_distribution(
    ax: Any,
    deltas: list[float],
    threshold: float = 0.05,
    title: str = "Effect Size Distribution",
) -> None:
    """
    Plot distribution of effect sizes with significance threshold.

    Useful for visualizing the distribution of ablation deltas
    or other effect size measures across multiple records/trials.

    Args:
        ax: Matplotlib axes object.
        deltas: Effect size values to plot.
        threshold: Significance threshold to mark.
        title: Plot title.

    Example:
        deltas = [compute_delta(record) for record in records]
        plot_delta_distribution(ax, deltas, threshold=0.05)
    """
    try:
        import numpy as np
    except ImportError as e:
        raise RuntimeError("numpy required for plot_delta_distribution") from e

    # Histogram
    ax.hist(deltas, bins=20, color=COLORS["primary"], alpha=0.7, edgecolor="white")

    # Threshold lines
    ax.axvline(
        threshold, color=COLORS["danger"], linestyle="--",
        label=f"threshold=±{threshold}",
    )
    ax.axvline(-threshold, color=COLORS["danger"], linestyle="--")

    # Mean line
    mean_delta = float(np.mean(deltas))
    ax.axvline(
        mean_delta, color=COLORS["accent"], linestyle="-",
        linewidth=2, label=f"mean={mean_delta:.3f}",
    )

    ax.set_xlabel("Delta (effect size)")
    ax.set_ylabel("Count")
    ax.set_title(title)
    ax.legend()
