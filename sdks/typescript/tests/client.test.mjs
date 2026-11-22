import assert from "node:assert/strict";
import { once } from "node:events";
import { createServer } from "node:http2";
import { createServer as createSocketServer } from "node:net";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";
import { connectNodeAdapter } from "@connectrpc/connect-node";
import {
  createReckonClient,
  Code,
  ConnectError,
  CreditPolicy,
  PayloadType,
  Record,
  RecordScope,
  RunExport,
} from "@rtepl/reckon-client";
import {
  CausalMemoryService,
  createReckonClient as withTransport,
} from "@rtepl/reckon-client/connect";
import { createRouterTransport } from "@connectrpc/connect";

test("all five methods preserve protobuf values over HTTP/2", async (t) => {
  const seen = [];
  const large = 9007199254740993n;
  const server = createServer(
    connectNodeAdapter({
      routes(router) {
        router.service(CausalMemoryService, {
          async write(request, context) {
            seen.push("write");
            assert.equal(
              context.requestHeader.get("x-reckon-test"),
              "metadata",
            );
            if (request.payload[0] === 255) {
              await delay(100);
              return {};
            }
            assert.deepEqual(request.payload, new Uint8Array([0, 128, 255]));
            assert.equal(request.tags.group.value.case, "listValue");
            assert.deepEqual(request.tags.group.value.value.values, ["a", "b"]);
            return {
              recordId: "r1",
              timestamp: large,
              cost: { bytes: 3n },
              apiVersion: { version: "1.0" },
            };
          },
          retrieve(request) {
            seen.push("retrieve");
            assert.deepEqual(request.query.value.ids, ["r1"]);
            assert.equal(request.context, undefined);
            return {
              records: [
                {
                  id: "r1",
                  createdAtStep: 0n,
                  causalScore: { ablationDelta: 0 },
                },
              ],
              episodeContextId: "c1",
            };
          },
          observe(request) {
            seen.push("observe");
            if (request.episodeContextId === "missing")
              throw new ConnectError("context absent", Code.NotFound);
            assert.equal(request.creditPolicy, CreditPolicy.SIMPLE);
            return {
              credits: [{ recordId: "r1", credit: -0.25 }],
              policyUsed: CreditPolicy.SIMPLE,
            };
          },
          probe(request) {
            seen.push("probe");
            assert.deepEqual(request.recordIds, ["r1"]);
            return { evidence: [{ recordId: "r1", power: 0 }] };
          },
          exportRun(request) {
            seen.push("exportRun");
            assert.equal(request.runId, "run1");
            return {
              export: { runId: "run1", metricsCsvBytes: new Uint8Array() },
            };
          },
        });
      },
    }),
  );
  const sessions = new Set();
  server.on("session", (session) => {
    sessions.add(session);
    session.on("close", () => sessions.delete(session));
  });
  t.after(async () => {
    for (const session of sessions) session.destroy();
    await new Promise((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const client = createReckonClient(
    `http://127.0.0.1:${server.address().port}`,
    {
      timeout: 2_000,
      headers: { "x-reckon-test": "metadata" },
    },
  );
  const written = await client.write({
    payload: new Uint8Array([0, 128, 255]),
    tags: {
      group: { value: { case: "listValue", value: { values: ["a", "b"] } } },
    },
  });
  assert.equal(written.timestamp, large);
  assert.equal(written.apiVersion.version, "1.0");
  const retrieved = await client.retrieve({
    query: { case: "byIds", value: { ids: ["r1"] } },
  });
  const record = retrieved.records[0];
  assert.equal(record.createdAtStep, 0n);
  assert.equal(record.createdAtSequence, undefined);
  assert.equal(record.causalScore.ablationDelta, 0);
  assert.equal(record.causalScore.influenceProxy, undefined);
  const jsonRecord = Record.fromJson(record.toJson());
  assert.equal(jsonRecord.createdAtStep, 0n);
  assert.equal(jsonRecord.causalScore.ablationDelta, 0);
  assert.equal(
    (
      await client.observe({
        episodeContextId: "c1",
        creditPolicy: CreditPolicy.SIMPLE,
      })
    ).credits[0].credit,
    -0.25,
  );
  assert.equal(
    (await client.probe({ recordIds: ["r1"] })).evidence[0].power,
    0,
  );
  const exported = (await client.exportRun({ runId: "run1" })).export;
  assert.deepEqual(exported.metricsCsvBytes, new Uint8Array());
  assert.equal(exported.recordsSnapshotJson, undefined);
  assert.deepEqual(
    RunExport.fromJson(exported.toJson()).metricsCsvBytes,
    new Uint8Array(),
  );
  assert.deepEqual(seen, [
    "write",
    "retrieve",
    "observe",
    "probe",
    "exportRun",
  ]);
  await assert.rejects(
    client.observe({ episodeContextId: "missing" }),
    (error) => error.code === Code.NotFound,
  );
  await assert.rejects(
    client.write({ payload: new Uint8Array([255]) }, { timeoutMs: 10 }),
    (error) => error.code === Code.DeadlineExceeded,
  );
});

test("the connect entry uses a caller-supplied transport", async () => {
  const client = withTransport(
    createRouterTransport((router) => {
      router.rpc(
        CausalMemoryService,
        CausalMemoryService.methods.write,
        () => ({ recordId: "custom" }),
      );
    }),
  );
  assert.equal((await client.write({})).recordId, "custom");
});

test(
  "the generated Node client reaches all five Rust daemon methods",
  {
    skip: !process.env.RECKON_DAEMON,
    timeout: 20_000,
  },
  async (t) => {
    const reservation = createSocketServer();
    reservation.listen(0, "127.0.0.1");
    await once(reservation, "listening");
    const port = reservation.address().port;
    await new Promise((resolve) => reservation.close(resolve));
    const daemon = spawn(
      process.env.RECKON_DAEMON,
      ["--port", String(port), "--max-slots", "5"],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let output = "";
    daemon.stdout.on("data", (data) => {
      output += data;
    });
    daemon.stderr.on("data", (data) => {
      output += data;
    });
    const exited = once(daemon, "exit");
    t.after(async () => {
      daemon.kill("SIGTERM");
      await exited;
    });
    const client = createReckonClient(`http://127.0.0.1:${port}`, {
      timeout: 1_000,
    });
    let written;
    for (let attempt = 0; attempt < 100; attempt++) {
      assert.equal(daemon.exitCode, null, output);
      try {
        written = await client.write({
          payload: new Uint8Array([0, 128, 255]),
          payloadType: PayloadType.OBSERVATION,
          runId: "qualification",
        });
        break;
      } catch (error) {
        if (error.code !== Code.Unavailable) throw error;
        await delay(25);
      }
    }
    assert.ok(written, output);
    assert.equal(written.cost.bytes, 3n);
    const retrieved = await client.retrieve({
      query: { case: "byIds", value: { ids: [written.recordId] } },
      runId: "qualification",
    });
    assert.deepEqual(
      retrieved.records[0].payload,
      new Uint8Array([0, 128, 255]),
    );
    assert.equal(retrieved.records[0].createdAtStep, 0n);
    assert.equal(retrieved.records[0].createdAtSequence, undefined);
    const observed = await client.observe({
      episodeContextId: retrieved.episodeContextId,
      outcomeValue: -0.25,
      creditPolicy: CreditPolicy.SIMPLE,
    });
    assert.equal(observed.credits[0].recordId, written.recordId);
    const exported = (
      await client.exportRun({
        runId: "qualification",
        recordScope: RecordScope.TOUCHED,
      })
    ).export;
    assert.equal(exported.runId, "qualification");
    assert.equal(exported.sourceRevision, 3n);
    assert.equal(
      JSON.parse(new TextDecoder().decode(exported.recordsSnapshotJson))[0].id,
      written.recordId,
    );
    await assert.rejects(
      client.probe({ recordIds: [written.recordId] }),
      (error) => error.code === Code.Unimplemented,
    );
    await assert.rejects(
      client.exportRun({ runId: "qualification", includeEvents: true }),
      (error) => error.code === Code.Unimplemented,
    );
  },
);
