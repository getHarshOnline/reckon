"""Native operations survive imports, storage and both WebSocket paths."""

import argparse
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from reckon.core.episode_context import EpisodeContext
from reckon.core.resources import MemoryBudget
from reckon.memory import CausalMemoryManager, PayloadType
from reckon.viz.cli import cmd_import
from reckon.viz.projection import parse_events_jsonl, project_event
from reckon.viz.server import create_app
from reckon.viz.storage import RunIndex, RunMeta, RunStore, check_event_duplicates, create_storage
from reckon.viz.registry import register_cmm, unregister_cmm


def operation(event_id=0, op_type="write", **extra):
    return dict(
        event_id=event_id,
        op_type=op_type,
        timestamp=0,
        episode_id="episode",
        sequence=0,
        record_id=None,
        duration_us=0,
        slots_after=0,
        bytes_after=0,
        details=None,
        **extra,
    )


def encoded(events):
    return "\n".join(json.dumps(event) for event in events).encode()


def test_actual_manager_keeps_every_operation_and_source_field():
    manager = CausalMemoryManager(MemoryBudget(max_slots=2), episode_id="episode")
    record_id = manager.write({"cue": 7}, PayloadType.CUE)
    with EpisodeContext(episode_id="episode") as context:
        manager.retrieve(context=context)
        manager.observe(1, context=context)
    manager.prune(record_id, reason="fixture")
    raw = manager.get_event_log()
    projected = parse_events_jsonl(encoded(raw))
    assert len(projected) == len(raw)
    assert projected[0]["eventId"] == "0"
    assert {e["memoryEvents"][0]["opType"] for e in projected} == {1, 2, 3, 4}
    for source, event in zip(raw, projected):
        assert event["kernelEvent"] == source
        assert event["eventId"] == str(source["event_id"])
        assert event["sequence"] == source["sequence"]
        assert event["timeBasis"] == "step" and event["snapshot"] == []
        assert "usageAfter" not in event["memoryEvents"][0]
        assert project_event(event) == event
    read = next(e for e in projected if e["memoryEvents"][0]["opType"] == 2)
    assert read["memoryEvents"][0]["resultIds"] == [record_id]


def test_zero_large_ids_tied_keys_and_compress_are_preserved():
    events = [operation(0), operation(2**64 - 1, "compress"), operation(2)]
    assert [e["eventId"] for e in parse_events_jsonl(encoded(events))] == ["0", str(2**64 - 1), "2"]
    assert project_event(events[1])["kernelEvent"]["event_id"] == str(2**64 - 1)
    assert check_event_duplicates(events, b"") == events
    assert check_event_duplicates(events, encoded(events)) == []
    changed = dict(events[0], op_type="prune")
    with pytest.raises(ValueError, match="conflicting"):
        check_event_duplicates([changed], encoded(events))


@pytest.mark.parametrize(
    "event",
    [
        None,
        [],
        {},
        operation(op_type="invented"),
        dict(operation(), secret_extension=True),
        dict(operation(), details="bad json"),
        dict(operation(), sequence=True),
        dict(operation(), timestamp=2**54),
    ],
)
def test_unsupported_or_malformed_events_fail_with_the_line(event):
    with pytest.raises(ValueError, match="event line 2"):
        parse_events_jsonl(encoded([operation(), event]))


@pytest.mark.parametrize("run_id", ["", "../escape", "/tmp/escape", "a/b", ".", "..", "a\\b"])
def test_run_paths_cannot_escape_the_store(tmp_path, run_id):
    with pytest.raises(ValueError):
        RunStore(tmp_path).store_events(run_id, b"")


def test_symlink_run_cannot_escape_store(tmp_path):
    store = RunStore(tmp_path / "store")
    (tmp_path / "outside").mkdir()
    (tmp_path / "store" / "escape").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError):
        store.store_events("escape", b"")


def test_import_and_stream_share_the_projection(tmp_path, monkeypatch):
    monkeypatch.setenv("RECKON_VIZ_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RECKON_VIZ_LOAD_FIXTURES", raising=False)
    events = [operation(), operation(1, "compress")]
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/runs/import",
            json={"run_id": "test", "events_jsonl_bytes": encoded(events).decode()},
        )
        assert response.status_code == 200 and response.json()["events_count"] == 2
        expected = parse_events_jsonl(encoded(events))
        assert client.get("/v1/runs/test/events").json()["events"] == expected
        with client.websocket_connect("/v1/stream?run_id=test") as socket:
            snapshot = socket.receive_json()
            assert snapshot["type"] == "snapshot" and snapshot["events"] == expected
            assert (
                client.post("/v1/runs/test/events", json=[operation(2, "read")]).json()["appended"]
                == 1
            )
            message = socket.receive_json()
            assert message["events"] == [project_event(operation(2, "read"))]
        assert (
            client.post(
                "/v1/runs/import", json={"run_id": "test", "events_jsonl_bytes": ""}
            ).status_code
            == 409
        )
        assert len(client.get("/v1/runs/test/events").json()["events"]) == 3
        assert client.delete("/v1/runs/test").status_code == 405
        bad = client.post("/v1/runs/import", json={"run_id": "invalid", "events_jsonl_bytes": "{}"})
        assert bad.status_code == 400
        assert client.get("/v1/runs/invalid").status_code == 404


def test_cli_refuses_unrenderable_import_before_storage(tmp_path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    (source / "events.jsonl").write_text("{}")
    args = argparse.Namespace(
        path=str(source), data_dir=str(tmp_path / "data"), run_id="bad", force=False
    )
    assert cmd_import(args) == 1
    assert "Cannot display run" in capsys.readouterr().out
    assert not (tmp_path / "data" / "run_artifacts" / "bad").exists()


def test_cli_imports_original_and_named_copy_without_replacing_either(
    tmp_path, monkeypatch, capsys
):
    """Keep the walkthrough's two imports as a native, portable regression."""
    from reckon.viz.cli import main
    from reckon.viz.storage import create_storage

    manager = CausalMemoryManager(MemoryBudget(max_slots=2), episode_id="walkthrough")
    for step in range(6):
        manager.set_step(step)
        record_id = manager.write({"cue": step}, PayloadType.CUE)
        with EpisodeContext(episode_id="walkthrough") as context:
            manager.retrieve(context=context)
            manager.observe(1, context=context)
        manager.prune(record_id, reason="walkthrough step")
    events = manager.get_event_log()
    assert len(events) == 24
    original = encoded(events)
    source = tmp_path / "walkthrough-run"
    source.mkdir()
    (source / "events.jsonl").write_bytes(original)
    summary = {"task_name": "walkthrough", "budget_slots": 2, "num_episodes": 1}
    (source / "summary.json").write_text(json.dumps(summary))
    data = tmp_path / "data"
    command = ["--data-dir", str(data), "import", str(source)]
    assert main(command) == 0
    assert "Imported run: walkthrough-run" in capsys.readouterr().out
    assert main([*command, "--run-id", "inspected-copy"]) == 0
    output = capsys.readouterr().out
    assert "Imported run: inspected-copy" in output and "Events: 24" in output
    index, store = create_storage(data)
    for run_id in ("walkthrough-run", "inspected-copy"):
        assert store.get_events(run_id) == original
        assert json.loads(store.get_summary(run_id)) == summary
        assert index.get_run(run_id).task_name == "walkthrough"
    assert main(command) == 1
    assert "already exists" in capsys.readouterr().out
    assert (source / "events.jsonl").read_bytes() == original
    monkeypatch.setenv("RECKON_VIZ_DATA_DIR", str(data))
    monkeypatch.setenv("RECKON_VIZ_LOAD_FIXTURES", "0")
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        for run_id in ("walkthrough-run", "inspected-copy"):
            assert store.get_events(run_id) == original
            response = client.get(f"/v1/runs/{run_id}/events")
            assert response.status_code == 200
            assert response.json()["events"] == parse_events_jsonl(original)


def test_subscription_preserves_events_after_drain_and_separates_logger_resets():
    manager = CausalMemoryManager(MemoryBudget(max_slots=2))
    with manager.subscribe_events() as queue:
        manager.write({"cue": 1}, PayloadType.CUE)
        first_source, first = queue.get_nowait()
        assert first == manager.get_event_log()[0]
        manager.set_episode("reset", reset_memory=True)
        manager.write({"cue": 2}, PayloadType.CUE)
        second_source, second = queue.get_nowait()
        assert first_source != second_source
        assert first["event_id"] == second["event_id"] == 0
        assert queue.empty()
    manager.write({"cue": 3}, PayloadType.CUE)
    assert queue.empty()


def test_running_manager_is_persisted_and_fanned_out(tmp_path, monkeypatch):
    monkeypatch.setenv("RECKON_VIZ_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RECKON_VIZ_LOAD_FIXTURES", raising=False)
    manager = CausalMemoryManager(MemoryBudget(max_slots=2), episode_id="live")
    register_cmm(manager)
    try:
        with TestClient(create_app()) as client:
            manager.write({"cue": 1}, PayloadType.CUE)
            deadline = time.monotonic() + 5
            runs = []
            while not runs and time.monotonic() < deadline:
                runs = client.get("/v1/runs").json()["runs"]
                time.sleep(0.01)
            assert len(runs) == 1
            assert runs[0]["success_rate"] is None
            run_id = runs[0]["run_id"]
            with client.websocket_connect(f"/v1/stream?run_id={run_id}") as socket:
                snapshot = socket.receive_json()
                assert snapshot["events"][0]["eventId"] == "0"
                assert snapshot["success_rate"] is None
                manager.retrieve()
                event = socket.receive_json()["events"][0]
                assert event["memoryEvents"][0]["opType"] == 2
                assert len(client.get(f"/v1/runs/{run_id}/events").json()["events"]) == 2
            assert client.get("/health").json()["live_error"] is None
    finally:
        unregister_cmm()


def test_snapshot_and_concurrent_appends_leave_no_gap(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from reckon.viz.routes.ws import RunEventFanout, _send_run_snapshot
    from reckon.viz.storage import RunIndex, RunMeta

    async def exercise():
        store = RunStore(tmp_path / "runs")
        store.store_events("race", encoded([operation()]))
        index = RunIndex(tmp_path / "runs.db")
        index.add_run(RunMeta("race", "", "", "", 0, "race/events.jsonl"))
        fanout = RunEventFanout()
        entered, release = asyncio.Event(), asyncio.Event()
        messages = []

        class Socket:
            app = SimpleNamespace(state=SimpleNamespace(event_fanout=fanout))

            async def send_json(self, message):
                if message["type"] == "snapshot":
                    entered.set()
                    await release.wait()
                messages.append(message)

        socket = Socket()
        snapshot = asyncio.create_task(_send_run_snapshot(socket, "race", index, store))
        await entered.wait()
        first = asyncio.create_task(fanout.append_events(store, "race", [operation(1)]))
        duplicate = asyncio.create_task(fanout.append_events(store, "race", [operation(1)]))
        await asyncio.sleep(0)
        assert not first.done() and not duplicate.done()
        release.set()
        await asyncio.gather(snapshot, first, duplicate)
        assert [message["type"] for message in messages] == ["snapshot", "events"]
        assert [e["eventId"] for m in messages for e in m["events"]] == ["0", "1"]
        assert len(parse_events_jsonl(store.get_events("race"))) == 2

    asyncio.run(exercise())


def test_live_shutdown_flushes_last_queued_operations(tmp_path, monkeypatch):
    monkeypatch.setenv("RECKON_VIZ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECKON_VIZ_LOAD_FIXTURES", "0")
    manager = CausalMemoryManager(MemoryBudget(max_slots=2), episode_id="shutdown")
    register_cmm(manager)
    app = create_app()
    try:
        with TestClient(app) as client:
            manager.write({"cue": 1}, PayloadType.CUE)
            deadline = time.monotonic() + 5
            runs = []
            while not runs and time.monotonic() < deadline:
                runs = client.get("/v1/runs").json()["runs"]
                time.sleep(0.01)
            assert runs
            for _ in range(20):
                manager.retrieve()
        run_id = runs[0]["run_id"]
        events = parse_events_jsonl(app.state.run_store.get_events(run_id))
        assert len(events) == 21
        assert [event["eventId"] for event in events] == [str(i) for i in range(21)]
    finally:
        unregister_cmm()


def test_symlink_artifact_cannot_escape_run(tmp_path):
    store = RunStore(tmp_path / "store")
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"original")
    (tmp_path / "store" / "run").mkdir()
    (tmp_path / "store" / "run" / "events.jsonl").symlink_to(outside)
    with pytest.raises(ValueError):
        store.store_events("run", b"replacement")
    assert outside.read_bytes() == b"original"


def test_bundled_legacy_export_retains_snapshots_and_operations():
    from pathlib import Path
    from reckon.viz.storage import parse_run_export

    export = json.loads(
        (Path(__file__).parents[2] / "runs/_fixtures/golden_run_export.json").read_text()
    )
    _, raw = parse_run_export(export)
    source = [json.loads(line) for line in raw.splitlines()]
    events = parse_events_jsonl(raw)
    assert len(events) == 10
    for original, event in zip(source, events):
        assert event["snapshot"] == original["snapshot"]
        assert event["eventId"] == original["event_id"]
        assert event["wallTimeMs"] == original["wall_time_ms"]
        if original["event_type"] in {"WRITE", "READ", "PRUNE"}:
            assert event["memoryEvents"][0]["recordId"] == original["record_id"]


@pytest.mark.parametrize("route", ["bundle", "path-file", "path-directory"])
@pytest.mark.parametrize("existing", ["unindexed", "alias", "empty", "dangling"])
def test_http_import_never_replaces_existing_destinations(tmp_path, monkeypatch, route, existing):
    data = tmp_path / "data"
    monkeypatch.setenv("RECKON_VIZ_DATA_DIR", str(data))
    monkeypatch.setenv("RECKON_VIZ_LOAD_FIXTURES", "0")
    app = create_app()
    original = encoded([operation()])
    with TestClient(app) as client:
        store = app.state.run_store
        destination = data / "run_artifacts" / "target"
        if existing == "alias":
            assert (
                client.post(
                    "/v1/runs/import",
                    json={"run_id": "original", "events_jsonl_bytes": original.decode()},
                ).status_code
                == 200
            )
            destination.symlink_to(destination.parent / "original", target_is_directory=True)
        elif existing == "unindexed":
            store.store_events("target", original)
            store.store_summary("target", '{"keep": true}')
        elif existing == "empty":
            destination.mkdir()
        else:
            destination.symlink_to(destination.parent / "missing", target_is_directory=True)
        bundle = {"run_id": "target", "events_jsonl_bytes": ""}
        if route == "bundle":
            response = client.post("/v1/runs/import", json=bundle)
        else:
            source = tmp_path / "source"
            source.mkdir()
            if route == "path-file":
                source = source / "export.json"
                source.write_text(json.dumps(bundle))
            else:
                source = source / "target"
                source.mkdir()
                (source / "events.jsonl").write_bytes(b"")
            response = client.post("/v1/runs/import-path", json={"path": str(source)})
        assert response.status_code == (400 if existing in {"alias", "dangling"} else 409)
        assert app.state.run_index.get_run("target") is None
        if existing == "alias":
            assert store.get_events("original") == original
            assert destination.is_symlink()
        elif existing == "unindexed":
            assert store.get_events("target") == original
            assert store.get_summary("target") == '{"keep": true}'
        elif existing == "empty":
            assert list(destination.iterdir()) == []
        else:
            assert destination.is_symlink() and not destination.exists()


def test_create_run_reserves_destination_without_replacement(tmp_path):
    store = RunStore(tmp_path)
    store.create_run("new", b"original", '{"keep": true}')
    with pytest.raises(FileExistsError):
        store.create_run("new", b"replacement", "{}")
    assert store.get_events("new") == b"original"
    assert store.get_summary("new") == '{"keep": true}'


@pytest.mark.parametrize(
    "metrics, expected",
    [
        ({}, None),
        ({"success_rate": None}, None),
        ({"success_rate": 0.0}, 0.0),
        ({"success_rate": 0.625}, 0.625),
    ],
)
def test_success_measurement_survives_import_snapshot_and_append(
    tmp_path, monkeypatch, metrics, expected
):
    monkeypatch.setenv("RECKON_VIZ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECKON_VIZ_LOAD_FIXTURES", "0")
    summary = {"task_name": "measured task", "num_episodes": 8, "metrics": metrics}
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/runs/import",
            json={
                "run_id": "measurement",
                "summary": summary,
                "events_jsonl_bytes": encoded([operation()]).decode(),
            },
        )
        assert response.status_code == 200
        assert client.get("/v1/runs/measurement").json()["success_rate"] == expected
        assert client.get("/v1/runs").json()["runs"][0]["success_rate"] == expected
        with client.websocket_connect("/v1/stream?run_id=measurement") as socket:
            snapshot = socket.receive_json()
            assert snapshot["success_rate"] == expected
            assert snapshot["summary"] == summary
            assert (
                client.post("/v1/runs/measurement/events", json=[operation(1, "read")]).status_code
                == 200
            )
            assert socket.receive_json()["events"][0]["eventId"] == "1"
        assert client.get("/v1/runs/measurement").json()["success_rate"] == expected
    index, store = create_storage(tmp_path)
    assert index.get_run("measurement").success_rate == expected
    assert json.loads(store.get_summary("measurement")) == summary


@pytest.mark.parametrize("success", [None, 0.0, 0.625])
@pytest.mark.parametrize("source_kind", ["file", "directory"])
def test_cli_success_presence_does_not_rewrite_source(tmp_path, capsys, success, source_kind):
    summary = {"metrics": {} if success is None else {"success_rate": success}}
    events = encoded([operation()])
    source = tmp_path / "original"
    if source_kind == "file":
        source.write_text(
            json.dumps(
                {"run_id": "measured", "summary": summary, "events_jsonl_bytes": events.decode()}
            ),
            encoding="utf-8",
        )
        originals = {source: source.read_bytes()}
    else:
        source.mkdir()
        (source / "events.jsonl").write_bytes(events)
        (source / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        originals = {p: p.read_bytes() for p in source.iterdir()}
    data = tmp_path / "index"
    assert (
        cmd_import(
            argparse.Namespace(path=str(source), data_dir=str(data), run_id="measured", force=False)
        )
        == 0
    )
    capsys.readouterr()
    index, _ = create_storage(data)
    assert index.get_run("measured").success_rate == success
    assert all(path.read_bytes() == content for path, content in originals.items())


def test_legacy_success_defaults_migrate_once_without_changing_summaries(tmp_path):
    path = tmp_path / "legacy.db"
    summaries = {
        "absent": "{}",
        "zero": '{"metrics":{"success_rate":0}}',
        "positive": '{"metrics":{"success_rate":0.5}}',
        "malformed": "not json",
    }
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE runs (
            run_id TEXT PRIMARY KEY, config_id TEXT, notebook_name TEXT, task_name TEXT,
            created_at INTEGER, events_path TEXT, policy_name TEXT DEFAULT '',
            num_episodes INTEGER DEFAULT 0, budget_slots INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0, summary_json TEXT DEFAULT '')""")
        for run_id, summary in summaries.items():
            connection.execute(
                "INSERT INTO runs (run_id, config_id, notebook_name, task_name, created_at, events_path, success_rate, summary_json) VALUES (?, '', '', '', 0, ?, ?, ?)",
                (run_id, f"{run_id}/events.jsonl", 0.5 if run_id == "positive" else 0.0, summary),
            )
    index = RunIndex(path)
    assert index.get_run("absent").success_rate is None
    assert index.get_run("malformed").success_rate is None
    assert index.get_run("zero").success_rate == 0.0
    assert index.get_run("positive").success_rate == 0.5
    assert {name: index.get_run(name).summary_json for name in summaries} == summaries
    index.add_run(
        RunMeta("explicit-zero", "", "", "", 0, "explicit-zero/events.jsonl", success_rate=0.0)
    )
    reopened = RunIndex(path)
    assert reopened.get_run("explicit-zero").success_rate == 0.0
    assert reopened.get_run("absent").success_rate is None
