# Installation and a first run

Build a wheel for your Python interpreter, then import the Rust extension and run a task to check the build. The library and daemon build from this checkout without a sibling repository.

## Before you begin

Install these tools before building:

| Tool | Requirement |
| --- | --- |
| Shell | Bash for the activation commands |
| Python | CPython 3.9–3.12 with virtual-environment support; this guide uses 3.11 |
| Rust and Cargo | Use a toolchain supported by the resolved dependencies. The kernel declares Rust 1.75; the dependency versions you build can require a newer release. |
| System tools | A linker; Cargo supplies the Protocol Buffers compiler |
| Git | Access to the Reckon source repository |

Use CPython 3.11 for the steps below. The extension builds with PyO3 0.20.3 and targets the `abi3-py39` ABI. The package metadata allows `>=3.9`. If you use a Python version outside the documented range, run the import check on your machine before starting an experiment.

The optional Python wire messages and gRPC client require Python 3.10+ through the `rpc` extra; generation uses `proto`. Python 3.9 remains supported for the core library. See the [wire guide](../protos/README.md) for installation and calls.

When repeating an experiment, check out the Reckon revision and dependency lockfiles recorded with that run. Older revisions that declared a MONAD dependency still need the matching MONAD source captured with their evidence.

The Rust builds use the [pinned compiler](../kernel/README.md#protocol-buffers-compiler) unless `PROTOC` selects another executable. A separately installed `protoc` is optional. Offline builds need the packaged compiler dependencies in Cargo's cache along with the other dependencies.

## Set up the environment

::::steps

:::step "Check out Reckon"

Clone the selected source:

```bash
git clone https://github.com/getHarshOnline/reckon.git
cd reckon
```

:::

:::step "Create the Python environment"

Use an installed CPython 3.11 explicitly. Choose an unused environment directory; if `.venv-311` already exists, choose another name rather than replacing it.

```bash
python3.11 -m venv .venv-311
source .venv-311/bin/activate
python --version
python -m pip install "maturin>=1.4,<2.0"
```

Check that the reported version is 3.11. Activating an existing environment does not change the interpreter that created it.

:::

:::step "Build and install the package"

From the Reckon repository root, build a wheel with that interpreter:

```bash
maturin build --interpreter "$VIRTUAL_ENV/bin/python" --out "$VIRTUAL_ENV/wheels"
python -m pip install "$VIRTUAL_ENV"/wheels/*.whl
```

The wheel and its base dependencies supply the Python package, NumPy and SciPy. Install optional debugger, test or notebook dependencies for the workflow that needs them. To build with a recorded `kernel/Cargo.lock`, supply that lockfile and add `--locked`. See [what to capture for a repeatable build](./12-Reproducibility.md#environment-capture).

:::

:::step "Verify the extension"

```bash
python -c "from reckon._rust import EventLogger, RecordStore"
```

The command exits silently when Python can load the compiled extension. If it fails, check that the active interpreter matches the wheel and follow the [kernel build procedure](../kernel/README.md#python-extension). The package requires the extension.

:::

::::

Keep this environment active for the commands below. Install the notebook runner, table and plotting packages with `python -m pip install ".[notebooks]"`. The [notebook guide](../notebooks/README.md) covers optional environment integrations.

The optional `setup.sh` helper uses the repository’s `.venv` and installs the `dev,viz` extras. If the directory is missing, the script creates it using the `python3` on your path. Create an unused environment with a supported interpreter first or check the interpreter in an existing `.venv`. Use a fresh directory if you need to switch interpreters.

> [!WARNING]
>
> **Verify the extension import.** The helper can finish after a failed extension build, so verify the import before using the environment.

If you came from [Compare replay budgets](https://causality.in/reckon/compare-replay-budgets/), return there with this environment active. For [Inspect an exported run](https://causality.in/reckon/inspect-an-exported-run/), add the Python visualization dependencies with `python -m pip install ".[viz]"`, then install Node.js 18 or later and pnpm 9 for the interface. Neither task needs the daemon.

## Check that it works

List the available tasks, then run ten Key-Door episodes:

```bash
reckon list
reckon run --task keydoor --episodes 10
```

Look for a task result after `reckon list` reports the available runners. The command checks that the task and extension can run together. For changes to the implementation, [run its tests](../src/tests/README.md).

## Use the memory manager

Use the following to check the Python integration after the build. It stores an observation, retrieves it by tag and updates the stored record’s utility.

```python
from reckon import CausalMemoryManager, MemoryBudget, PayloadType

memory = CausalMemoryManager(MemoryBudget(max_slots=100, max_bytes=50_000))
record_id = memory.write(
    payload={"observation": "key is in room A"},
    payload_type=PayloadType.OBSERVATION,
    tags=["key", "location"],
)
hits = memory.retrieve(query={"tags": ["key"]})
memory.update_score(record_id, "utility", value=10.0, signal_source="reward")
```

For a complete integration with expected output, [connect retrieval to an outcome](../src/reckon/README.md#connect-retrieval-to-an-outcome). The [memory manager chapter](./08-Causal-Memory-Manager-Design.md) explains retention and how the selected policy enforces byte, slot and declared-token limits together.

## Open the debugger

For the startup and import walkthrough, follow [Inspect an exported run](https://causality.in/reckon/inspect-an-exported-run/). To produce debugger-compatible data or embed a view, use the [debugger data contract](./10-Debugger-Visualization.md) and [server API](../src/reckon/viz/README.md).

## The daemon is for your own machine only

The gRPC daemon keeps its own in-memory store. It defaults to `127.0.0.1`, rejects non-loopback addresses and uses plaintext without caller authentication:

```bash
(cd daemon && cargo run --release -- --host 127.0.0.1)
```

> [!WARNING]
>
> **Use it only on a trusted local machine.** It is separate from the Python manager and debugger. Its [record-only `ExportRun`](../daemon/README.md) selects records written or retrieved by a named run; event, metric and archive attachments remain unimplemented. It does not yet produce a complete debugger run bundle.
