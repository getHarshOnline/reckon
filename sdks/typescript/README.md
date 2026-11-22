# @rtepl/reckon-client

The Node.js client calls Reckon's laboratory daemon over gRPC and HTTP/2. It generates its messages and five service methods from the same protocol sources as the daemon, preserving byte arrays, 64-bit integers and optional-field presence. The package is not published to npm.

## Build and run

Use Node.js 18 or later and pnpm. From this directory:

```bash
pnpm install --frozen-lockfile
pnpm build
```

The build runs both configured protocol generators before TypeScript compilation. Generated files stay in ignored `src/gen/` and compiled `dist/`; change the protocol sources or `buf.gen.yaml`, not those outputs. Node's ESM imports and both package entry points are included in the build.

Start the daemon from the repository root:

```bash
cargo run --manifest-path daemon/Cargo.toml -- --host 127.0.0.1
```

It keeps records in memory and has no caller authentication. Use a trusted local machine. Its state is separate from a Python memory manager's state. See the [repository guide](../../README.md#the-grpc-daemon-is-a-local-tool).

```typescript
import {
  createReckonClient,
  CreditPolicy,
  PayloadType,
} from "@rtepl/reckon-client";

const client = createReckonClient("http://127.0.0.1:50051");
const { recordId } = await client.write({
  payload: new TextEncoder().encode(
    JSON.stringify({ observation: "key found" }),
  ),
  payloadType: PayloadType.OBSERVATION,
  tags: { location: { value: { case: "stringValue", value: "room A" } } },
  initialUtility: 0.5,
});
const { records, episodeContextId } = await client.retrieve({
  query: { case: "byIds", value: { ids: [recordId] } },
});
const { credits } = await client.observe({
  episodeContextId,
  outcomeValue: 1.0,
  creditPolicy: CreditPolicy.SIMPLE,
});
```

## Calls and errors

`createReckonClient(baseUrl, options?)` and `new ReckonClient({ baseUrl, ...options })` create the same client. `timeout` sets a default deadline in milliseconds, initially 30,000; `headers` attaches caller metadata. Each method also accepts the generated client's call options, including `timeoutMs`, headers and an abort signal.

| Method | Laboratory behavior |
| --- | --- |
| `write(request)` | Store a new record and return its identity and cost |
| `retrieve(request)` | Query by tags, IDs or utility; return records and an episode context |
| `observe(request)` | Assign credit for an outcome in that context |
| `probe(request)` | Return `Code.Unimplemented` until a runner measures both arms |
| `exportRun(request)` | Export [named-run record snapshots](../../daemon/README.md); refuse unsupported attachments |

Failures retain their gRPC status in `ConnectError.code`. A deadline is `Code.DeadlineExceeded`; a missing episode context is `Code.NotFound`. `Code` and `ConnectError` are exported by both entry points. The Python laboratory's [paired probe](../../docs/11-Evaluation-Metrics.md) remains the current measured comparison route.

## Generated types

All messages and enums come from `protos/reckon/core/v1/types.proto` and `service.proto`, under the repository root. Responses are generated message instances. Requests accept partial message objects, with protobuf defaults for omitted fields.

This replaces the earlier handwritten interfaces and HTTP/JSON request body. Supply map fields as objects keyed by strings, not JavaScript `Map`; supply `TagValue` through its `value` oneof, as in the example. A list tag uses `{ value: { case: "listValue", value: { values: ["a", "b"] } } }`. The codec preserves that list, although the current Rust daemon stores only string-valued tags.

Byte fields use `Uint8Array`; `int64` fields use `bigint`. Optional fields distinguish `undefined` from an explicit `0`, `0n`, empty string or empty byte array. For example, `record.createdAtStep === 0n` is a present creation step. Use a generated message's `toJson()` or `toJsonString()` for protobuf JSON, and its class's `fromJson()` or `fromJsonString()` to read it; ordinary `JSON.stringify()` does not encode `bigint`.

The `ABLATION` credit enum normalizes positive measured ablation deltas; it does not establish a causal evidence profile. It retains wire number 4, while protobuf JSON uses `CREDIT_POLICY_ABLATION`. The former enum label has no alias; older saved JSON retains its original label and must be interpreted with its source revision. The [kernel credit implementation](../../kernel/src/credit.rs) defines the laboratory's shared rules.

## Supply another transport

The `@rtepl/reckon-client/connect` entry exports `createReckonClient(transport)`, the service descriptor and the same generated types, without importing Node's transport. It works with a caller-supplied Connect transport. For a browser, choose a web transport and a separately configured compatible gateway; the Rust daemon itself serves neither Connect nor gRPC-Web. No gateway is supplied by this package.

## Check the client

```bash
pnpm build
pnpm test
RECKON_DAEMON="$PWD/../../daemon/target/debug/reckon-daemon" pnpm test
```

Build that debug daemon first with `cargo build --manifest-path ../../daemon/Cargo.toml`. Without `RECKON_DAEMON`, its test is explicitly skipped. The HTTP/2 fixture exercises all five methods, bytes and large integers, present and absent optional values, caller metadata, a missing-context error and a deadline. The separate entry is checked with a caller-supplied transport. The daemon test starts its own loopback process, checks three successful methods and the two reserved refusals, then stops and joins it.

## Licence

The package metadata says Apache-2.0, but the repository's licensing is not settled; see the [repository README](../../README.md#licence).
