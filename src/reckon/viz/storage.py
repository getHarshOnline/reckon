"""
RunIndex (SQLite) + RunStore (filesystem) for viz server.

Storage layer for the Reckon visualization server. Provides:
- RunIndex: SQLite-based index for run metadata (fast queries)
- RunStore: Filesystem storage for run artifacts (events.jsonl)

This architecture decouples the viz server from live CMM instances,
allowing it to consume RunExport bundles from any source.
"""

import json
import os
import re
import sqlite3
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from reckon.viz.projection import parse_events_jsonl, project_event

# Default paths
DEFAULT_DB_NAME = "runs.db"
DEFAULT_STORE_DIR = "run_artifacts"


# These fields are the public record shape, rather than independent object responsibilities.
@dataclass
class RunMeta:  # pylint: disable=too-many-instance-attributes
    """Metadata for a stored run."""

    run_id: str
    config_id: str
    notebook_name: str
    task_name: str
    created_at: int  # milliseconds since epoch
    events_path: str  # Relative path to events.jsonl within RunStore
    policy_name: str = ""
    num_episodes: int = 0
    budget_slots: int = 0
    success_rate: Optional[float] = None
    summary_json: str = ""  # Full RunSummary as JSON for UI consumption

    @classmethod
    def from_summary(cls, run_id, summary, notebook_name="", *, omit_empty=False):
        """Project the same supplied summary fields for file and directory imports."""
        return cls(
            run_id=run_id,
            config_id=summary.get("config_id", ""),
            notebook_name=summary.get("notebook_name", notebook_name),
            task_name=summary.get("task_name", ""),
            created_at=summary.get("started_at_ms", 0),
            events_path=f"{run_id}/events.jsonl",
            policy_name=summary.get("policy_name", ""),
            num_episodes=summary.get("num_episodes", 0),
            budget_slots=summary.get("budget_slots", 0),
            success_rate=summary.get("metrics", {}).get("success_rate"),
            summary_json="" if omit_empty and not summary else json.dumps(summary),
        )


class RunIndex:
    """SQLite index for run metadata.

    Thread-safe via connection-per-thread pattern.

    Usage:
        index = RunIndex(Path("./data/runs.db"))
        index.add_run(run_meta)
        runs = index.list_runs(limit=10)
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize the run index.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._local = threading.local()

        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize schema
        self._init_schema()

    @property
    def db_path(self) -> Path:
        """The selected SQLite database path."""
        return self._db_path

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                config_id TEXT NOT NULL,
                notebook_name TEXT NOT NULL,
                task_name TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                events_path TEXT NOT NULL,
                policy_name TEXT DEFAULT '',
                num_episodes INTEGER DEFAULT 0,
                budget_slots INTEGER DEFAULT 0,
                success_rate REAL DEFAULT NULL,
                summary_json TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_runs_created_at
            ON runs(created_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_runs_config_id
            ON runs(config_id)
        """)
        self._migrate_success_rate(conn)
        conn.commit()

    @staticmethod
    def _migrate_success_rate(conn: sqlite3.Connection) -> None:
        """Recover explicit legacy zeroes; an ambiguous default is unavailable.

        The old index used zero for missing measurements. Only the retained
        summary can establish a measured zero. Versioning prevents later
        explicitly supplied zeroes from being reinterpreted on reopening.
        """
        if conn.execute("PRAGMA user_version").fetchone()[0] >= 1:
            return
        rows = conn.execute(
            "SELECT run_id, summary_json FROM runs WHERE success_rate = 0"
        ).fetchall()
        for row in rows:
            try:
                summary = json.loads(row["summary_json"])
                value = summary.get("metrics", {}).get("success_rate")
            except (json.JSONDecodeError, AttributeError, TypeError):
                value = None
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value != 0:
                conn.execute(
                    "UPDATE runs SET success_rate = NULL WHERE run_id = ?", (row["run_id"],)
                )
        conn.execute("PRAGMA user_version = 1")

    def add_run(self, meta: RunMeta) -> None:
        """Add or update a run in the index.

        Args:
            meta: Run metadata to store.
        """
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, config_id, notebook_name, task_name, created_at,
                events_path, policy_name, num_episodes, budget_slots,
                success_rate, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meta.run_id,
                meta.config_id,
                meta.notebook_name,
                meta.task_name,
                meta.created_at,
                meta.events_path,
                meta.policy_name,
                meta.num_episodes,
                meta.budget_slots,
                meta.success_rate,
                meta.summary_json,
            ),
        )
        conn.commit()

    def get_run(self, run_id: str) -> Optional[RunMeta]:
        """Get a run by ID.

        Args:
            run_id: The run ID to look up.

        Returns:
            RunMeta if found, None otherwise.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_meta(row)

    def list_runs(
        self,
        limit: int = 100,
        offset: int = 0,
        config_id: Optional[str] = None,
        task_name: Optional[str] = None,
    ) -> list[RunMeta]:
        """List runs with optional filtering.

        Args:
            limit: Maximum number of runs to return.
            offset: Number of runs to skip.
            config_id: Filter by config_id.
            task_name: Filter by task_name.

        Returns:
            List of RunMeta objects, ordered by created_at descending.
        """
        conn = self._get_conn()

        query = "SELECT * FROM runs WHERE 1=1"
        params: list = []

        if config_id:
            query += " AND config_id = ?"
            params.append(config_id)
        if task_name:
            query += " AND task_name = ?"
            params.append(task_name)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        return [self._row_to_meta(row) for row in cursor.fetchall()]

    def delete_run(self, run_id: str) -> bool:
        """Delete a run from the index.

        Args:
            run_id: The run ID to delete.

        Returns:
            True if a run was deleted, False otherwise.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM runs WHERE run_id = ?",
            (run_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    def count_runs(self) -> int:
        """Count total number of runs.

        Returns:
            Total number of runs in the index.
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM runs")
        row = cursor.fetchone()
        return row[0] if row else 0

    @staticmethod
    def _row_to_meta(row: sqlite3.Row) -> RunMeta:
        """Convert a database row to RunMeta."""
        return RunMeta(
            run_id=row["run_id"],
            config_id=row["config_id"],
            notebook_name=row["notebook_name"],
            task_name=row["task_name"],
            created_at=row["created_at"],
            events_path=row["events_path"],
            policy_name=row["policy_name"],
            num_episodes=row["num_episodes"],
            budget_slots=row["budget_slots"],
            success_rate=row["success_rate"],
            summary_json=row["summary_json"],
        )


class RunStore:
    """Filesystem storage for run artifacts.

    Organizes artifacts by run_id with the following structure:
        base_path/
            {run_id}/
                events.jsonl
                summary.json

    Usage:
        store = RunStore(Path("./data/run_artifacts"))
        path = store.store_events("run_001", events_bytes)
        events = store.get_events("run_001")
    """

    def __init__(self, base_path: Path) -> None:
        """Initialize the run store.

        Args:
            base_path: Base directory for artifact storage.
        """
        self._base_path = base_path
        base_path.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> Path:
        """Get the directory for a run's artifacts."""
        if not isinstance(run_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id
        ):
            raise ValueError(
                "run_id must be 1–128 letters, digits, dots, underscores or hyphens, "
                "starting with a letter or digit"
            )
        path = self._base_path / run_id
        if path.is_symlink():
            raise ValueError("run directory must not be a symlink")
        if path.resolve().parent != self._base_path.resolve():
            raise ValueError("run directory must remain inside the configured store")
        return path

    def _artifact_path(self, run_id: str, filename: str) -> Path:
        run_dir = self._run_dir(run_id)
        path = run_dir / filename
        if path.resolve().parent != run_dir.resolve():
            raise ValueError("artifact must remain inside its run directory")
        return path

    def create_run(self, run_id: str, events_jsonl: bytes, summary_json: str = "") -> None:
        """Reserve a new run directory and write artifacts without replacing any data.

        An interrupted import leaves its directory reserved, even without an index entry.
        Existing directories, files and symlinks must be handled explicitly by their owner.
        """
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(exist_ok=False)
        with self._artifact_path(run_id, "events.jsonl").open("xb") as output:
            output.write(events_jsonl)
        if summary_json:
            with self._artifact_path(run_id, "summary.json").open("x") as output:
                output.write(summary_json)

    def store_events(self, run_id: str, events_jsonl: bytes) -> Path:
        """Store events JSONL for a run.

        Args:
            run_id: The run ID.
            events_jsonl: Events as JSONL bytes.

        Returns:
            Path to the stored events file.
        """
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        events_path = self._artifact_path(run_id, "events.jsonl")
        events_path.write_bytes(events_jsonl)
        return events_path

    def append_events(self, run_id: str, events_jsonl: bytes) -> None:
        """Append events to an existing run.

        Args:
            run_id: The run ID.
            events_jsonl: Events as JSONL bytes to append.

        Raises:
            FileNotFoundError: If the run doesn't exist.
        """
        events_path = self._artifact_path(run_id, "events.jsonl")

        # Create if doesn't exist
        if not events_path.exists():
            events_path.parent.mkdir(parents=True, exist_ok=True)
            events_path.write_bytes(events_jsonl)
        else:
            # Append with newline if needed
            with events_path.open("ab") as f:
                existing = events_path.read_bytes()
                if existing and not existing.endswith(b"\n"):
                    f.write(b"\n")
                f.write(events_jsonl)

    def get_events(self, run_id: str) -> bytes:
        """Get events JSONL for a run.

        Args:
            run_id: The run ID.

        Returns:
            Events as JSONL bytes.

        Raises:
            FileNotFoundError: If the run doesn't exist.
        """
        events_path = self._artifact_path(run_id, "events.jsonl")
        return events_path.read_bytes()

    def get_events_path(self, run_id: str) -> Path:
        """Get the path to events file for a run.

        Args:
            run_id: The run ID.

        Returns:
            Path to the events.jsonl file.
        """
        return self._artifact_path(run_id, "events.jsonl")

    def store_summary(self, run_id: str, summary_json: str) -> Path:
        """Store run summary as JSON.

        Args:
            run_id: The run ID.
            summary_json: RunSummary as JSON string.

        Returns:
            Path to the stored summary file.
        """
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        summary_path = self._artifact_path(run_id, "summary.json")
        summary_path.write_text(summary_json)
        return summary_path

    def get_summary(self, run_id: str) -> Optional[str]:
        """Get run summary JSON.

        Args:
            run_id: The run ID.

        Returns:
            Summary JSON string, or None if not found.
        """
        summary_path = self._artifact_path(run_id, "summary.json")
        if not summary_path.exists():
            return None
        return summary_path.read_text()

    def run_exists(self, run_id: str) -> bool:
        """Check if a run exists in the store.

        Args:
            run_id: The run ID.

        Returns:
            True if the run directory exists.
        """
        return self._run_dir(run_id).exists()

    def delete_run(self, run_id: str) -> bool:
        """Delete a run and all its artifacts.

        Args:
            run_id: The run ID.

        Returns:
            True if a run was deleted, False otherwise.
        """
        run_dir = self._run_dir(run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir)
            return True
        return False

    def list_run_ids(self) -> list[str]:
        """List all run IDs in the store.

        Returns:
            List of run IDs (directory names).
        """
        if not self._base_path.exists():
            return []
        return [
            d.name
            for d in self._base_path.iterdir()
            if d.is_dir() and (d / "events.jsonl").exists()
        ]


def parse_run_export(export_json: dict) -> tuple[RunMeta, bytes]:
    """Parse a RunExport JSON into RunMeta and events bytes.

    Args:
        export_json: The RunExport as a dictionary.

    Returns:
        Tuple of (RunMeta, events_jsonl_bytes).
    """
    run_id = export_json.get("run_id", "")
    summary = export_json.get("summary", {})

    # Extract events - handle both string and bytes representations
    events_data = export_json.get("events_jsonl_bytes", "")
    if isinstance(events_data, str):
        events_bytes = events_data.encode("utf-8")
    else:
        events_bytes = bytes(events_data)

    meta = RunMeta.from_summary(run_id, summary)

    return meta, events_bytes


def check_event_duplicates(new_events: list[dict], existing_events_bytes: bytes) -> list[dict]:
    """Keep distinct identities at tied steps; refuse changed content under one ID."""
    known = {event["eventId"]: event for event in parse_events_jsonl(existing_events_bytes)}
    unique = []
    for source in new_events:
        event = project_event(source)
        previous = known.get(event["eventId"])
        if previous is not None:
            if previous != event:
                raise ValueError(f"conflicting content for event {event['eventId']}")
        else:
            unique.append(source)
            known[event["eventId"]] = event
    return unique


def find_events_file(path: Path) -> Optional[Path]:
    """Find events.jsonl file in a directory.

    Searches for:
    1. {path}/events.jsonl
    2. {path}/logs/events.jsonl

    Args:
        path: Directory to search in.

    Returns:
        Path to events.jsonl if found, None otherwise.
    """
    events_path = path / "events.jsonl"
    if events_path.exists():
        return events_path

    events_path = path / "logs" / "events.jsonl"
    if events_path.exists():
        return events_path

    return None


def get_default_data_dir() -> Path:
    """Get the default data directory for viz storage.

    Uses RECKON_VIZ_DATA_DIR env var if set, otherwise uses
    $XDG_DATA_HOME/reckon/viz (default ~/.local/share/reckon/viz).

    Returns:
        Path to the data directory.
    """
    env_dir = os.environ.get("RECKON_VIZ_DATA_DIR")
    if env_dir:
        return Path(env_dir)

    # User-owned run data must not be written into the installed source tree.
    return (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "reckon" / "viz"
    )


def create_storage(
    data_dir: Optional[Path] = None,
) -> tuple[RunIndex, RunStore]:
    """Create RunIndex and RunStore with default paths.

    Args:
        data_dir: Base data directory. Uses default if not specified.

    Returns:
        Tuple of (RunIndex, RunStore).
    """
    if data_dir is None:
        data_dir = get_default_data_dir()

    index = RunIndex(data_dir / DEFAULT_DB_NAME)
    store = RunStore(data_dir / DEFAULT_STORE_DIR)

    return index, store
