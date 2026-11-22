"""
Reckon Viz CLI

Command-line interface for the visualization server.

Commands:
    reckon viz serve [--port PORT] [--load-fixtures]
    reckon viz import <path>

Usage Examples:
    # Start server with fixtures
    reckon viz serve --load-fixtures

    # Import a run directory
    reckon viz import ./runs/my_run/

    # Import a RunExport JSON file
    reckon viz import ./exports/run_001.json
"""

import argparse
import asyncio
from datetime import datetime
import signal
import json
import sys
from pathlib import Path
from typing import Optional

from reckon.viz.storage import RunMeta, create_storage, find_events_file, parse_run_export
from reckon.viz.projection import parse_events_jsonl
from reckon.viz.server import main as server_main


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the visualization server."""
    # Build args for server
    server_args = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--log-level",
        args.log_level,
    ]

    if args.reload:
        server_args.append("--reload")
    if args.load_fixtures:
        server_args.append("--load-fixtures")
    if args.data_dir:
        server_args.extend(["--data-dir", args.data_dir])

    return server_main(server_args)


def _read_import_source(path: Path, run_id):
    """Read one file or directory, preserving the CLI’s fallback and error messages."""
    # Determine if it's a file or directory
    if path.is_file():
        # Assume it's a RunExport JSON
        try:
            export_data = json.loads(path.read_text(encoding="utf-8"))
            meta, events_bytes = parse_run_export(export_data)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON: {e}")
            return None
        except (KeyError, TypeError) as e:
            print(f"Error: Invalid RunExport format: {e}")
            return None
    elif path.is_dir():
        # Look for events.jsonl
        events_path = find_events_file(path)
        if events_path is None:
            print(f"Error: No events.jsonl found in {path}")
            return None

        events_bytes = events_path.read_bytes()

        # Look for summary/config
        summary: dict = {}
        for candidate in ["summary.json", "config.json"]:
            candidate_path = path / candidate
            if candidate_path.exists():
                try:
                    summary = json.loads(candidate_path.read_text(encoding="utf-8"))
                    break
                except json.JSONDecodeError:
                    pass

        # Create RunMeta
        run_id = run_id or path.name
        meta = RunMeta.from_summary(run_id, summary, path.name, omit_empty=True)
    else:
        print(f"Error: Path must be a file or directory: {path}")
        return None

    return meta, events_bytes


def cmd_import(args: argparse.Namespace) -> int:
    """Import a run from a local path."""
    path = Path(args.path)
    if not path.exists():
        print(f"Error: Path not found: {path}")
        return 1

    # Initialize storage
    data_dir = Path(args.data_dir) if args.data_dir else None
    run_index, run_store = create_storage(data_dir)

    source = _read_import_source(path, args.run_id)
    if source is None:
        return 1
    meta, events_bytes = source

    try:
        events = parse_events_jsonl(events_bytes)
        run_store.get_events_path(meta.run_id)
    except (ValueError, TypeError) as exc:
        print(f"Error: Cannot display run: {exc}")
        return 1

    # Check if run already exists
    existing = run_index.get_run(meta.run_id)
    if existing and not args.force:
        print(f"Error: Run {meta.run_id} already exists. Use --force to overwrite.")
        return 1

    # Store
    run_store.store_events(meta.run_id, events_bytes)
    if meta.summary_json:
        run_store.store_summary(meta.run_id, meta.summary_json)
    run_index.add_run(meta)

    # Count events
    event_count = len(events)

    print(f"Imported run: {meta.run_id}")
    print(f"  Events: {event_count}")
    print(f"  Task: {meta.task_name or 'unknown'}")
    print(f"  Policy: {meta.policy_name or 'unknown'}")

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all imported runs."""
    data_dir = Path(args.data_dir) if args.data_dir else None
    run_index, _run_store = create_storage(data_dir)

    runs = run_index.list_runs(limit=args.limit)

    if not runs:
        print("No runs found.")
        return 0

    print(f"{'Run ID':<20} {'Task':<15} {'Policy':<12} {'Episodes':<10} {'Created'}")
    print("-" * 80)

    for run in runs:
        # Format timestamp
        created = datetime.fromtimestamp(run.created_at / 1000).strftime("%Y-%m-%d %H:%M")
        print(
            f"{run.run_id:<20} {run.task_name or '-':<15} "
            f"{run.policy_name or '-':<12} {run.num_episodes:<10} {created}"
        )

    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete a run."""
    data_dir = Path(args.data_dir) if args.data_dir else None
    run_index, run_store = create_storage(data_dir)

    run_id = args.run_id

    # Check if exists
    meta = run_index.get_run(run_id)
    if meta is None:
        print(f"Error: Run {run_id} not found.")
        return 1

    # Confirm
    if not args.yes:
        response = input(f"Delete run {run_id}? [y/N] ")
        if response.lower() != "y":
            print("Cancelled.")
            return 0

    # Delete
    run_index.delete_run(run_id)
    run_store.delete_run(run_id)

    print(f"Deleted run: {run_id}")
    return 0


def _print_event(event: dict) -> None:
    """Print a single event in a readable format."""
    event_type = event.get("event_type", event.get("op_type", "unknown"))
    episode_id = event.get("episode_id", "?")
    timestamp = event.get("timestamp", 0)
    record_id = event.get("record_id", "")

    # Format: [timestamp] episode:type record_id
    line = f"[{timestamp:>10}] {episode_id}:{event_type}"
    if record_id:
        line += f" {record_id}"

    # Add extra info for specific event types
    if event_type == "write" and "key" in event:
        line += f" key={event['key']}"
    elif event_type == "read" and "key" in event:
        line += f" key={event['key']}"

    print(line)


async def _print_tail_message(websocket, message, show_history):
    """Display streamed records and answer the server’s keepalive."""
    data = json.loads(message)
    msg_type = data.get("type")

    if msg_type == "snapshot":
        events = data.get("events", [])
        print(f"[snapshot] {len(events)} existing events")
        if show_history:
            for event in events:
                _print_event(event)

    elif msg_type == "events":
        events = data.get("events", [])
        for event in events:
            _print_event(event)

    elif msg_type == "ping":
        # Respond to keep-alive
        await websocket.send(json.dumps({"type": "pong"}))

    elif msg_type == "error":
        print(f"[error] {data.get('message', 'Unknown error')}")


async def _tail_events(run_id: str, server_url: str, show_history: bool) -> None:
    """Async implementation of event tailing."""
    try:
        # The other CLI commands do not require this optional transport.
        # pylint: disable-next=import-outside-toplevel
        import websockets
    except ImportError:
        print("Error: websockets package required. Install with: pip install websockets")
        return

    # Build WebSocket URL
    ws_url = f"{server_url}/v1/stream?run_id={run_id}"

    # Handle graceful shutdown
    shutdown = asyncio.Event()

    def handle_signal() -> None:
        print("\nDisconnecting...")
        shutdown.set()

    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    print(f"Connecting to {ws_url}...")

    try:
        async with websockets.connect(ws_url) as websocket:
            print(f"Connected. Tailing events for run: {run_id}")
            print("-" * 60)

            while not shutdown.is_set():
                try:
                    # Wait for message with timeout to check shutdown
                    message = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=1.0,
                    )
                    await _print_tail_message(websocket, message, show_history)

                except asyncio.TimeoutError:
                    continue
                except Exception as e:  # pylint: disable=broad-exception-caught
                    print(f"[error] {e}")
                    break

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Connection error: {e}")


def cmd_tail(args: argparse.Namespace) -> int:
    """Connect to the debugger and print events until interrupted."""
    # Build server URL
    host = args.host
    port = args.port
    server_url = f"ws://{host}:{port}"

    # Run the async tail
    try:
        asyncio.run(_tail_events(args.run_id, server_url, args.show_history))
    except KeyboardInterrupt:
        print("\nInterrupted.")

    return 0


def main(args: Optional[list[str]] = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="reckon viz",
        description="Reckon Visualization Server CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Start server with fixtures
    reckon viz serve --load-fixtures

    # Import a run
    reckon viz import ./runs/my_run/

    # List all runs
    reckon viz list
        """,
    )

    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Override data directory",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start the visualization server")
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    serve_parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level",
    )
    serve_parser.add_argument(
        "--load-fixtures",
        action="store_true",
        help="Load fixture data on startup",
    )

    # import command
    import_parser = subparsers.add_parser("import", help="Import a run from local path")
    import_parser.add_argument(
        "path",
        type=str,
        help="Path to run directory or RunExport JSON",
    )
    import_parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Override run ID (default: directory name)",
    )
    import_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing run",
    )

    # list command
    list_parser = subparsers.add_parser("list", help="List all imported runs")
    list_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum runs to list",
    )

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a run")
    delete_parser.add_argument(
        "run_id",
        type=str,
        help="Run ID to delete",
    )
    delete_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation",
    )

    # tail command
    tail_parser = subparsers.add_parser("tail", help="Tail events from a run via WebSocket")
    tail_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="Run ID to tail events from",
    )
    tail_parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Viz server host (default: localhost)",
    )
    tail_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Viz server port (default: 8000)",
    )
    tail_parser.add_argument(
        "--show-history",
        action="store_true",
        help="Show existing events from snapshot",
    )

    parsed = parser.parse_args(args)

    if parsed.command is None:
        parser.print_help()
        return 0

    handlers = {
        "serve": cmd_serve,
        "import": cmd_import,
        "list": cmd_list,
        "delete": cmd_delete,
        "tail": cmd_tail,
    }
    handler = handlers.get(parsed.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(parsed)


if __name__ == "__main__":
    sys.exit(main())
