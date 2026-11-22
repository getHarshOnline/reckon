"""
Artifact management for Reckon notebook runs.

Handles run directory creation, saving configs/metrics/figures/logs,
and generating summary reports. All artifacts are organized by date,
notebook name, and configuration hash for reproducibility.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from .config import NotebookConfig, hash_config

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["RunManager", "get_runs_dir"]


def get_runs_dir() -> Path:
    """
    Get the runs directory path (notebooks/runs/).

    Returns:
        Path to the runs directory.
    """
    return Path(__file__).parent.parent / "runs"


class RunManager:
    """
    Manages artifacts for a single notebook run.

    Creates a structured directory hierarchy for reproducible experiments:

        runs/<date>/<notebook_name>/<config_hash>/
            config.json      # Full configuration
            metrics.csv      # Tabular results
            figures/         # PNG plots
            logs/            # JSONL event logs (debugger-compatible)
            summary.md       # Auto-generated report

    This structure ensures that identical configurations produce identical
    artifact paths, enabling result caching and comparison across runs.

    Example:
        config = NotebookConfig(notebook_name="my_notebook", ...)
        run = RunManager(config)

        run.save_config()
        run.save_metrics(results_df)
        run.save_figure(fig, "pareto_frontier")
        run.save_logs(events)
        run.write_summary({"success_rate": 0.85})
        run.print_artifacts()
    """

    def __init__(
        self, config: NotebookConfig, base_dir: Optional[Path] = None, *, require_new: bool = False
    ) -> None:
        """
        Initialize run manager and create directory structure.

        Args:
            config: Notebook configuration.
            base_dir: Override base runs directory (default: notebooks/runs/).
            require_new: Refuse an existing run directory before writing anything.
        """
        self.config = config
        self.config_hash = hash_config(config)

        # Build path: runs/<date>/<notebook>/<hash>/
        base = base_dir or get_runs_dir()
        date_str = datetime.now().strftime("%Y-%m-%d")
        self.run_dir = base / date_str / config.notebook_name / self.config_hash

        # Subdirectories
        self.figures_dir = self.run_dir / "figures"
        self.logs_dir = self.run_dir / "logs"

        # Create directories
        self.run_dir.mkdir(parents=True, exist_ok=not require_new)
        self.figures_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)

        # Track saved artifacts for summary
        self._saved_figures: list[str] = []
        self._saved_logs: list[str] = []
        self._saved_files: list[str] = []

    def save_config(self) -> Path:
        """
        Save configuration to config.json.

        Returns:
            Path to the saved configuration file.
        """
        path = self.run_dir / "config.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.config.to_json())
        self._saved_files.append("config.json")
        return path

    def save_metrics(
        self,
        data: Union[pd.DataFrame, dict, list[dict]],
        filename: str = "metrics.csv",
    ) -> Path:
        """
        Save metrics to CSV format.

        Accepts pandas DataFrames, single dictionaries, or lists of dictionaries.
        Dictionary rows use the standard CSV writer; only DataFrames need pandas.

        Args:
            data: Metrics data (DataFrame, dict, or list of dicts).
            filename: Output filename (default: metrics.csv).

        Returns:
            Path to the saved metrics file.

        Raises:
            TypeError: If data type is not supported.
        """
        path = self.run_dir / filename

        if isinstance(data, dict):
            data = [data]
        if isinstance(data, list):
            import csv

            if not data or not all(isinstance(row, dict) for row in data):
                raise TypeError("Metrics must contain at least one dictionary row")
            keys = list(dict.fromkeys(key for row in data for key in row))
            with open(path, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=keys)
                writer.writeheader()
                writer.writerows(data)
        else:
            import pandas as pd_module

            if not isinstance(data, pd_module.DataFrame):
                raise TypeError(f"Unsupported data type: {type(data)}")
            data.to_csv(path, index=False)

        self._saved_files.append(filename)
        return path

    def save_figure(
        self,
        fig: Any,
        name: str,
        dpi: int = 150,
        fmt: str = "png",
    ) -> Path:
        """
        Save a matplotlib figure.

        Args:
            fig: Matplotlib figure object.
            name: Figure name (without extension).
            dpi: Image resolution (default: 150).
            fmt: Image format (default: "png").

        Returns:
            Path to the saved figure file.

        Raises:
            ValueError: If dpi is not positive.
        """
        if dpi <= 0:
            raise ValueError(f"dpi must be positive, got {dpi}")

        filename = f"{name}.{fmt}"
        path = self.figures_dir / filename
        fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
        self._saved_figures.append(filename)
        return path

    def save_logs(
        self,
        events: list[dict],
        filename: str = "events.jsonl",
    ) -> Path:
        """
        Save event logs as JSONL (debugger-compatible format).

        Each event is written as a single JSON line, compatible with
        the viz-ui debugger's log loading functionality.

        Args:
            events: List of event dictionaries.
            filename: Output filename (default: events.jsonl).

        Returns:
            Path to the saved log file.
        """
        path = self.logs_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, default=str) + "\n")
        self._saved_logs.append(filename)
        return path

    def save_jsonl(self, data: list[dict], filename: str) -> Path:
        """
        Save arbitrary data as JSONL.

        Args:
            data: List of dictionaries to save.
            filename: Output filename.

        Returns:
            Path to the saved file.
        """
        path = self.run_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, default=str) + "\n")
        self._saved_files.append(filename)
        return path

    def write_summary(
        self,
        key_metrics: dict[str, Any],
        notes: Optional[str] = None,
    ) -> Path:
        """
        Write auto-generated summary.md report.

        Creates a markdown summary including configuration, key metrics,
        and links to saved artifacts.

        Args:
            key_metrics: Dictionary of key results to highlight.
            notes: Optional additional notes to include.

        Returns:
            Path to the summary file.
        """
        path = self.run_dir / "summary.md"

        lines = [
            f"# {self.config.notebook_name} Run Summary",
            "",
            f"**Mode:** {self.config.run_mode}",
            f"**Git:** {self.config.git_hash}",
            f"**Time:** {self.config.timestamp}",
            f"**Config Hash:** {self.config_hash}",
            "",
            "## Configuration",
            "",
            f"- Seed: {self.config.seed} (x{self.config.seed_count})",
            f"- Budget: {self.config.budget_slots} slots",
            f"- Task: {self.config.task_name} ({self.config.num_episodes} episodes)",
            f"- Policy: {self.config.policy_name}",
            "",
            "## Key Metrics",
            "",
        ]

        for key, value in key_metrics.items():
            if isinstance(value, float):
                lines.append(f"- **{key}:** {value:.4f}")
            else:
                lines.append(f"- **{key}:** {value}")

        if self._saved_figures:
            lines.extend(["", "## Figures", ""])
            for fig in self._saved_figures:
                lines.append(f"- [figures/{fig}](figures/{fig})")

        if self._saved_logs:
            lines.extend(["", "## Logs", ""])
            for log in self._saved_logs:
                lines.append(f"- [logs/{log}](logs/{log})")

        if notes:
            lines.extend(["", "## Notes", "", notes])

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self._saved_files.append("summary.md")
        return path

    def get_run_path(self) -> Path:
        """Get the run directory path."""
        return self.run_dir

    def print_artifacts(self) -> None:
        """
        Print saved artifacts with paths relative to the repository root.

        Lists all files that were saved during this run, confirming
        their existence on disk.
        """
        print(f"\n{'=' * 50}")
        print(f"ARTIFACTS SAVED")
        print(f"{'=' * 50}")
        repository_root = Path(__file__).resolve().parents[2]
        display_dir = Path(os.path.relpath(self.run_dir, repository_root))
        print(f"Directory (from repository root): {display_dir}")
        print()

        all_artifacts = []

        # Config and other root files
        for filename in self._saved_files:
            filepath = self.run_dir / filename
            exists = filepath.exists()
            status = "OK" if exists else "MISSING"
            size = filepath.stat().st_size if exists else 0
            all_artifacts.append((filename, status, size))

        # Figures
        for fig in self._saved_figures:
            filepath = self.figures_dir / fig
            exists = filepath.exists()
            status = "OK" if exists else "MISSING"
            size = filepath.stat().st_size if exists else 0
            all_artifacts.append((f"figures/{fig}", status, size))

        # Logs
        for log in self._saved_logs:
            filepath = self.logs_dir / log
            exists = filepath.exists()
            status = "OK" if exists else "MISSING"
            size = filepath.stat().st_size if exists else 0
            all_artifacts.append((f"logs/{log}", status, size))

        # Print table
        for name, status, size in all_artifacts:
            size_str = f"{size:,} bytes" if size > 0 else ""
            print(f"  [{status}] {name:<30} {size_str}")

        print(f"{'=' * 50}")
        print(f"Total: {len(all_artifacts)} files")

        # Print debugger instructions if logs exist
        if self._saved_logs:
            print()
            print("To view in debugger:")
            print(f"  1. cd viz-ui && pnpm dev")
            print(f"  2. Load (from repository root): {display_dir / 'logs' / self._saved_logs[0]}")
