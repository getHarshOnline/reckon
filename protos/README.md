# Python wire messages and RPC

The protocol sources define laboratory records, budgets and events in `reckon`, and the daemon's five-method API in `reckon.core.v1`. These historical wire messages are separate from the [Rust-owned laboratory model](../kernel/src/record.rs), its PyO3 public-record adapters and the Python resource configuration. Changing a wire declaration does not migrate those adapters automatically. Laboratory scalar token counts retain their original numeric meaning: new nullable counts use the Rust JSON snapshot model, and exporting an unknown count to the historical wire is refused.

The [reference build](../docs/reference/README.md#protocol-and-http-references) compiles these schemas into a field and RPC reference for documentation assembly. Change the protocol source and its comments; generated reference stays outside Git.

## Record origin

`RecordOrigin` holds the operation that created a record, its input record IDs and its content hash. `MemoryRecord.provenance` remains field 10, with `source_op`, repeated `input_ids` and `hash` at nested fields 1–3. The field names, repeated-value order and embedded bytes are unchanged. The new type name has no `Provenance` alias: reflection and any `Any` type URLs must select `reckon.RecordOrigin`. A content hash and input list do not establish authorship, rights or a measured causal link.

## Read historical summary metrics

`reckon.core.v1.RunSummary.metrics` uses `HistoricalRunMetricsV1`. This is the historical v1 summary shape: its field numbers, optional presence, JSON keys and values stay intact. In particular, `causal_precision` at field 4 and `useful_memory_rate` at field 5 keep their original labels. Their formulas depend on the producer and source revision; the decoder does not translate them into current task diagnostics or record summaries. Current task and helper metrics are documented in the [metrics reference](../docs/11-Evaluation-Metrics.md).

The former `RunMetrics` type has no alias. The qualified descriptor name is now `reckon.core.v1.HistoricalRunMetricsV1`, so reflection lookups and any external `Any` type URLs must select that name explicitly; unchanged embedded bytes do not imply type-name compatibility. The historical JSON keys remain camelCase or their original protobuf snake_case inputs. Saved run files are not rewritten. The daemon’s [record-only export](../daemon/README.md) leaves historical summary metrics absent; it does not synthesize a producer for them.

## Install the optional tools

The core library supports CPython 3.9–3.12. Python wire messages, RPC and generation require Python 3.10 or later. The `rpc` extra pins `betterproto2[grpclib]` 0.10.0; `proto` adds compiler 0.10.1, `grpcio-tools` 1.78.0 and Ruff 0.17.5, which the compiler uses to format its output. These dependencies are unconditional inside their extras: requesting either extra on Python 3.9 fails dependency resolution rather than installing incomplete RPC support. The `full` extra includes `proto` and also requires Python 3.10+. Importing the core library does not import these tools.

After [building the required extension](../docs/01a-Installation.md#set-up-the-environment), use the same environment from the repository root:

```bash
python -m pip install ".[rpc]"
# For schema changes and the independent presence tests:
python -m pip install ".[dev,proto]"
```

## Call the local daemon

Start the daemon as described in the [repository guide](../README.md#the-grpc-daemon-is-a-local-tool). The generated asynchronous client uses gRPC directly:

```python
import asyncio
from grpclib.client import Channel
from reckon.generated.reckon.core.v1 import (
    CausalMemoryServiceStub, CreditPolicy, IdQuery, ObserveRequest,
    RetrieveRequest, WriteRequest,
)

async def main():
    channel = Channel("127.0.0.1", 50051)
    try:
        client = CausalMemoryServiceStub(channel)
        written = await client.write(WriteRequest(payload=b"observation"))
        retrieved = await client.retrieve(
            RetrieveRequest(by_ids=IdQuery(ids=[written.record_id]))
        )
        observed = await client.observe(ObserveRequest(
            episode_context_id=retrieved.episode_context_id,
            outcome_value=1.0,
            credit_policy=CreditPolicy.SIMPLE,
        ))
        print(observed.credits)
    finally:
        channel.close()

asyncio.run(main())
```

`Probe` returns `UNIMPLEMENTED` until its runner exists. `ExportRun` returns [scoped run observations](../daemon/README.md); set the same `run_id` on writes and retrievals, then request an explicit scope. Events, metrics and archive flags remain unsupported. Its state is separate from a Python memory manager's state. Use only a trusted local machine; the daemon has no caller authentication.

## Generate and check the Python files

With the `proto` extra installed, activate that environment so the compiler can find Ruff, then run from the repository root:

```bash
python protos/generate_python.py
python protos/generate_python.py --check
```

The script reads the Python plugin options from `buf.gen.yaml`, compiles all schemas together with the packaged compiler and writes `src/reckon/generated/`. It refuses to overwrite a layout containing obsolete Python files; review their retirement first. `--check` compares the complete generated Python file set and bytes without changing the source. Buf can also run the same plugin through `(cd protos && buf generate)` when both configured Python and TypeScript plugins are installed; that command also regenerates debugger TypeScript output.

The compiler uses packages named by the schemas: `reckon.generated.reckon` for laboratory messages and `reckon.generated.reckon.core.v1` for the daemon API. It also generates a shared message pool. Do not edit generated types by hand.

The migration from the old betterproto output changes Python calls while preserving the protobuf field numbers and RPC paths:

- Pass a request object, such as `client.write(WriteRequest(payload=...))`, instead of keyword fields directly to the method.
- Use enum members such as `CreditPolicy.SIMPLE` and `RecordScope.RETRIEVED`, without repeating the enum name as a prefix.
- Use class methods such as `RunExport.parse(data)` and `RunExport.from_json(text)` to construct decoded messages.
- Optional fields use `None` for absence. Explicit `0`, `0.0`, `""` and `b""` remain present through binary and JSON serialization.

Run the protocol checks after regeneration:

```bash
python -m pytest src/tests/test_proto_conformance.py src/tests/test_proto_presence.py src/tests/test_proto_rpc.py
cargo build --manifest-path daemon/Cargo.toml
RECKON_DAEMON="$PWD/daemon/target/debug/reckon-daemon" python -m pytest src/tests/test_proto_rpc.py
```

The presence test walks every optional field in the actual compiled schemas and checks its wire presence with Google's independent protobuf runtime. The RPC suite exercises all five generated client/server methods over HTTP/2. The opt-in daemon case checks writes, retrieval, observation and scoped export, plus refused probes and unsupported export attachments over loopback TCP, then stops its own daemon. Without `RECKON_DAEMON`, that case is reported as skipped. Without the optional dependencies, the protocol modules are reported as skipped so the base-library suite remains usable on Python 3.9.

## Retention-policy names

`MemoryManagerConfig` names the per-byte rule with `EVIDENCE_PER_BYTE` (enum number 4) and `evidence_weight` (field 3). The rule uses a supplied ablation effect, then a counterfactual effect, then a proxy only when neither measurement is present. The renamed enum and field preserve protobuf wire numbers and bytes; protobuf JSON now uses `RETENTION_POLICY_TYPE_EVIDENCE_PER_BYTE` and `evidenceWeight`. Earlier saved JSON retains its names and must be read with its source revision. The type and field names have no compatibility aliases.
