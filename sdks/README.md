# Reckon SDKs

The laboratory daemon serves gRPC on loopback. The Python and Node.js clients use that protocol with messages generated from the shared schemas.

## Available SDKs

| Language | Package | Status |
| --- | --- | --- |
| Python | `reckon.generated.reckon.core.v1` | Asynchronous gRPC client; install the `rpc` extra on Python 3.10+ |
| TypeScript | `@rtepl/reckon-client` | Generated client over gRPC and HTTP/2 on Node.js 18+; not published to npm |

## Python client

The [wire guide](../protos/README.md) gives installation, request-object calls, generation and tests against the daemon. The core memory manager remains independent of this optional client.

## TypeScript SDK

The [TypeScript guide](typescript/README.md) carries a complete write, retrieve and observe example, generated field shapes, deadlines and status errors. The separate `@rtepl/reckon-client/connect` entry accepts a caller-supplied transport; browser use needs a compatible gateway, which the daemon and SDK do not provide.

`Probe` remains unimplemented. [Run export](../daemon/README.md) supports scoped record snapshots from named operations; events, metrics and archive requests return `UNIMPLEMENTED`.

## Running the Daemon

SDKs require the Reckon daemon to be running:

```bash
cd daemon && cargo run --release -- --host 127.0.0.1
# Listens on 127.0.0.1:50051 in plaintext without caller authentication.
```

## Generating SDKs

For Python, install the `proto` extra and run from the repository root:

```bash
python protos/generate_python.py
python protos/generate_python.py --check
```

Python output goes to `src/reckon/generated/`. The TypeScript SDK's own `pnpm generate` command uses its separate configuration and writes `sdks/typescript/src/gen/`. The root Buf configuration also has a debugger TypeScript output; it does not generate every SDK into a common folder.

## Protocol

The daemon serves gRPC, with no HTTP/JSON or browser gRPC-Web gateway. Its protocol is defined in:

- `protos/reckon/core/v1/types.proto` - Data types
- `protos/reckon/core/v1/service.proto` - 5-verb RPC API
