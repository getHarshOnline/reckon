"""Exercise generated RPC request and response codecs, then the optional daemon."""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import pytest

pytest.importorskip("betterproto2", reason="Install the rpc extra on Python 3.10+.")
pytest.importorskip("grpclib", reason="Install the rpc extra for the gRPC transport.")
from grpclib.client import Channel
from grpclib.const import Status
from grpclib.exceptions import GRPCError
from grpclib.testing import ChannelFor
from reckon.generated.reckon.core import v1 as rpc


def test_all_five_rpc_codecs():
    class Service(rpc.CausalMemoryServiceBase):
        async def write(self, message):
            assert message.payload == b"\x00payload"
            return rpc.WriteResponse(record_id="record-1", cost=rpc.RecordCost(bytes=8))

        async def retrieve(self, message):
            assert message.by_ids.ids == ["record-1"]
            return rpc.RetrieveResponse(
                records=[
                    rpc.Record(
                        id="record-1",
                        created_at_step=0,
                        causal_score=rpc.CausalScore(ablation_delta=0.0),
                    )
                ]
            )

        async def observe(self, message):
            assert message.outcome_value == -0.25
            return rpc.ObserveResponse(
                policy_used=rpc.CreditPolicy.SIMPLE,
                credits=[rpc.CreditAssignment(record_id="record-1", credit=-0.25)],
            )

        async def probe(self, message):
            assert message.record_ids == ["record-1"]
            return rpc.ProbeResponse(evidence=[rpc.Evidence(record_id="record-1", power=0.0)])

        async def export_run(self, message):
            assert message.run_id == "run-1"
            return rpc.ExportRunResponse(
                export=rpc.RunExport(
                    run_id="run-1",
                    metrics_csv_bytes=b"",
                    records_snapshot_json=None,
                )
            )

    async def exercise():
        async with ChannelFor([Service()]) as channel:
            client = rpc.CausalMemoryServiceStub(channel)
            assert (
                await client.write(rpc.WriteRequest(payload=b"\x00payload"))
            ).record_id == "record-1"
            record = (
                await client.retrieve(rpc.RetrieveRequest(by_ids=rpc.IdQuery(ids=["record-1"])))
            ).records[0]
            assert record.created_at_step == 0 and record.created_at_sequence is None
            assert record.causal_score.ablation_delta == 0.0
            assert record.causal_score.influence_proxy is None
            assert (await client.observe(rpc.ObserveRequest(outcome_value=-0.25))).credits[
                0
            ].credit == -0.25
            assert (await client.probe(rpc.ProbeRequest(record_ids=["record-1"]))).evidence[
                0
            ].power == 0.0
            exported = (await client.export_run(rpc.ExportRunRequest(run_id="run-1"))).export
            assert exported.metrics_csv_bytes == b"" and exported.records_snapshot_json is None

    asyncio.run(exercise())


def test_generated_client_reaches_rust_daemon(tmp_path):
    binary = os.environ.get("RECKON_DAEMON")
    if not binary:
        pytest.skip("Set RECKON_DAEMON to the built candidate daemon for the TCP check.")
    assert Path(binary).is_file(), "RECKON_DAEMON must name the built candidate executable."

    async def exercise(port):
        channel = Channel("127.0.0.1", port)
        try:
            client = rpc.CausalMemoryServiceStub(channel)
            tags = {
                "kind": rpc.TagValue(string_value="cue"),
                "ordered": rpc.TagValue(list_value=rpc.StringList(values=["b", "a", "b"])),
                "empty": rpc.TagValue(list_value=rpc.StringList(values=[])),
                "unset": rpc.TagValue(),
            }
            links = [
                rpc.Link(rel="derived_from", to_record_id="parent", meta_json=b'{ "n": 0 }'),
                rpc.Link(rel="caused_by", to_record_id="earlier", meta_json=b""),
            ]
            # betterproto2 decodes an empty map message value as None; the key
            # remains present, unlike a tag that was never supplied.
            decoded_tags = {**tags, "unset": None}
            written = await client.write(
                rpc.WriteRequest(
                    payload=b"actual-wire",
                    initial_utility=0.5,
                    run_id="qualification",
                    tags=tags,
                    links=links,
                )
            )
            assert written.cost.bytes == len(b"actual-wire")
            assert written.api_version.version == "1.0"
            retrieved = await client.retrieve(
                rpc.RetrieveRequest(
                    by_ids=rpc.IdQuery(ids=[written.record_id]), run_id="qualification"
                )
            )
            record = retrieved.records[0]
            assert record.id == written.record_id and record.payload == b"actual-wire"
            assert record.tags == decoded_tags and record.links == links
            assert record.created_at_step == 0 and record.created_at_sequence is None
            assert record.causal_score.ablation_delta is None
            observed = await client.observe(
                rpc.ObserveRequest(
                    episode_context_id=retrieved.episode_context_id,
                    outcome_value=-0.25,
                    credit_policy=rpc.CreditPolicy.SIMPLE,
                )
            )
            assert len(observed.credits) == 1
            assert observed.credits[0].record_id == written.record_id
            assert observed.policy_used == rpc.CreditPolicy.SIMPLE
            exported = (
                await client.export_run(
                    rpc.ExportRunRequest(
                        run_id="qualification",
                        record_scope=rpc.RecordScope.TOUCHED,
                    )
                )
            ).export
            assert exported.run_id == "qualification" and exported.source_revision == 3
            row = json.loads(exported.records_snapshot_json)[0]
            assert row["id"] == written.record_id
            assert row["tags"]["ordered"]["value"]["listValue"]["values"] == ["b", "a", "b"]
            assert row["tags"]["unset"] == {"value": None}
            assert row["links"] == [
                {"rel": link.rel, "toRecordId": link.to_record_id, "metaJson": list(link.meta_json)}
                for link in links
            ]
            await client.write(rpc.WriteRequest(tags={"kind": tags["kind"]}))
            for predicate in [tags, {"ordered": tags["ordered"]}]:
                found = await client.retrieve(
                    rpc.RetrieveRequest(by_tags=rpc.TagQuery(tags=predicate))
                )
                assert [item.id for item in found.records] == [written.record_id]
                assert found.records[0].tags == decoded_tags and found.records[0].links == links
            for value in [
                rpc.TagValue(list_value=rpc.StringList(values=["a", "b", "b"])),
                rpc.TagValue(list_value=rpc.StringList(values=["b", "a"])),
                rpc.TagValue(string_value="b"),
            ]:
                found = await client.retrieve(
                    rpc.RetrieveRequest(
                        by_tags=rpc.TagQuery(tags={"ordered": value, "kind": tags["kind"]})
                    )
                )
                assert found.records == []
            for method, request in [
                (client.probe, rpc.ProbeRequest(record_ids=[written.record_id])),
                (
                    client.export_run,
                    rpc.ExportRunRequest(run_id="qualification", include_events=True),
                ),
            ]:
                with pytest.raises(GRPCError) as error:
                    await method(request)
                assert error.value.status == Status.UNIMPLEMENTED
        finally:
            channel.close()

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    log_path = tmp_path / "daemon.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [binary, "--port", str(port), "--max-slots", "5"],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None, log_path.read_text()
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError("The owned daemon did not start listening.")
                    time.sleep(0.05)
            asyncio.run(exercise(port))
        finally:
            process.terminate()
            process.wait(timeout=10)
