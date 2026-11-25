# Reckon

<a id="reckon-laboratory"></a>

Reckon, a laboratory for causal records under resource budgets, measures what an agent with limited memory should keep: what changes outcomes for what it costs, with the uncertainty shown. This repository holds its working laboratory: the Python package and command `reckon`, the Rust crate `reckon-kernel`, benchmark tasks and a debugger. Reckon belongs to [Causality](https://causality.in), a research programme of RawThoughts Enterprises Private Limited, and Harsh Joshi is its author.

The laboratory is research software under Apache-2.0. It is not published to any package registry.

## The problem

Agents have finite memory. What should they remember? Reckon's starting problem is that memory, measurement and intervention are resource-bounded, yet an agent design can leave those limits implicit. What the agent can reliably record and what it can change determine which causal relationships it can detect. The [problem and context](docs/01-Problem-Context.md) develops that argument.

The task writes an observation, retrieves records when it needs them and reports an outcome. Reckon tracks which records were returned, assigns them credit and updates their utility through a moving average. When memory fills, the selected retention policy chooses what to discard under byte and slot limits. Learned utility per byte is one policy; oldest first and least recently used supply simple comparisons. The [memory manager design](docs/08-Causal-Memory-Manager-Design.md) explains the choices and the other resource limits still to enforce.

But finding out what caused a difference is not free. A probe runs matched trials with and without a record, reports the difference and its uncertainty, and counts both arms’ episodes and elapsed time. Ablation attribution and influence proxies do not by themselves identify causal effects; every causal interpretation needs its stated intervention, assumptions and controls. The [benchmark account](docs/09-Tasks-Benchmarks.md) keeps the completed comparisons, including a small Tutor gain over learned utility at substantial probing cost. Whether the measurement earns its cost remains a question to test.

## A quick example

```python
from reckon import CausalMemoryManager, MemoryBudget, PayloadType, UtilityPolicy
from reckon.core.episode_context import EpisodeContext

# Configure byte and slot allowances
memory = CausalMemoryManager(
    MemoryBudget(max_slots=100, max_bytes=50_000),
    retention_policy=UtilityPolicy(),
)

# Store an observation
record_id = memory.write(
    payload={"observation": "key is in room A"},
    payload_type=PayloadType.OBSERVATION,
    tags=["key", "location"],
)

# Connect these retrieved records to one supplied outcome
with EpisodeContext(episode_id="key-door"):
    hits = memory.retrieve(query={"tags": ["key"]})
    print(hits[0].payload["observation"])
    memory.observe(outcome=1.0)

print(f"Utility: {memory.get_record(record_id).utility.value:.3f}")
# The selected policy removes the lowest utility per byte when space runs out.
```

This prints `key is in room A` and `Utility: 0.100`: one returned record receives all the credit, and the default update blends 10% of its credited outcome with 90% of its previous utility. The outcome is supplied here; the example demonstrates the update, not an agent opening a door or proof that the record helped. A real task supplies its observed outcome. The [complete integration guide](src/reckon/README.md#connect-retrieval-to-an-outcome) explains context lifetime, empty retrievals and carrying memory between episodes. Direct `update_score()` calls can still supply a score explicitly; compare those separately from learned utility. See [budget enforcement](docs/08-Causal-Memory-Manager-Design.md#budget-enforcement) for write validation and resource limits.

## The core idea

The framework studies resource-relative detectable influence: which allowed interventions produce a detectable outcome difference under a memory budget, compute limit and noise floor. A scorer's label or observed difference alone does not establish that relation. This connects information theory (channel capacity) with engineering (memory budgets).

## What you get

| Component | Description |
| --- | --- |
| **Causal Memory Manager** | Write, read, score and prune records under budget constraints |
| **Four benchmark tasks** | Key and door, a hidden-mode bandit, continual classification and a tutoring loop |
| **Debugger** | Event timeline, attribution graph and budget-versus-performance frontier |
| **Framework** | The ideas and the design, in [`docs/`](docs/00-Index.md) |

`reckon compare` runs declared tasks, policies, budgets and seeds and saves outcomes, spread, storage and elapsed time. The [reproducibility guide](docs/12-Reproducibility.md) owns its configuration and the [eight notebooks](notebooks/README.md) provide worked experiments. The debugger shows saved or live laboratory events; it does not decide which policy to adopt.

## Beyond the laboratory

The laboratory runs today for Causality’s research; the problem in front is making Reckon the shared instrument for RTEPL’s agent tools: a way to turn a correction from ordinary work, with permission for that use, into a fixed case, compare a proposed model, skill or policy change against it, and show the outcome, cost and uncertainty to the person who decides. This repository holds the local laboratory and its memory experiments; the services for shared cases, evaluations and decisions are not part of this code. [Cases, evaluations and decisions](https://causality.in/reckon/cases-evaluations-and-decisions/) explains them, and the [evaluation contract](docs/evaluation-contract.md) specifies the evaluator.

In the design that path is a learning loop, and in it Reckon has nothing to add without Pale's genealogy, the git history of context: an append-only map of references that shows where work came from, what it relied on and what followed, while each record stays with its owner. Scope writes back to it a pointer to the context it gave each agent, so the chain runs from what an agent was given to what it did and what followed. From that chain Reckon builds interventional and counterfactual traces for Counsel's and SkillOpt's training, each an intervention contrast and not an identified causal effect. None of that path is in this repository, whose memory laboratory runs without genealogy.

## Getting started

The library and daemon build from this checkout. MONAD supplies the theoretical definitions described in the manual; the implemented kernel does not call its types or require its source. The commands below assume access to the Reckon repository. Reproducible builds require the selected Reckon revision and dependency lockfiles. The [installation guide](docs/01a-Installation.md#set-up-the-environment) selects CPython 3.11 explicitly, builds the wheel and checks the extension. The documented CPython range is 3.9–3.12. The PyO3 build targets the `abi3-py39` ABI. If you build with a newer interpreter, run the extension import check before relying on it.

```bash
git clone https://github.com/getHarshOnline/reckon.git
cd reckon
```

After completing that installation with its environment active:

```bash
# Run a benchmark task
reckon run --task keydoor --episodes 10
```

Run these commands from the repository root with the supported environment active. For contributor dependencies and pytest, follow [Run and extend the tests](src/tests/README.md). Notebook use additionally needs the packages in the [notebook guide](notebooks/README.md). For the debugger's separate server and interface terminals, follow [Open the debugger](docs/01a-Installation.md#open-the-debugger). The [memory manager chapter](docs/08-Causal-Memory-Manager-Design.md) explains budgets and retention policies.

## The gRPC daemon is a local tool

The `daemon/` folder holds a Rust gRPC service, with a TypeScript client in `sdks/`. It keeps its state in memory and uses plaintext without caller authentication. It defaults to `127.0.0.1` and accepts only loopback addresses. `Probe` returns `UNIMPLEMENTED` until an episode runner can measure baseline and intervention trials; `ExportRun` returns [scoped observations from named runs](daemon/README.md), with explicit refusals for unsupported attachments. Run it on a trusted machine:

```bash
(cd daemon && cargo run --release -- --host 127.0.0.1)
```

`--max-slots` must be positive. Writes serialize capacity admission and byte accounting; replacing an existing record in the state store uses its existing slot and subtracts its old byte cost. The public `Write` operation creates a fresh record ID each time. These controls limit the in-memory record count; they do not supply a daemon byte budget or persistence.

`--max-contexts` also must be positive and defaults to 10,000. A context expires five minutes after creation; reuse does not extend it. Retrieval reclaims expired contexts before admission and returns `RESOURCE_EXHAUSTED` when every context slot is still live, without touching records or evicting active attribution. Retrievals sharing a live context merge their returned IDs once. Missing or expired retrieval IDs start a fresh context, whose ID is returned to the caller. Observation refuses expired contexts with `FAILED_PRECONDITION`, or `NOT_FOUND` if cleanup already removed them. An observation admitted before expiry keeps its attribution snapshot. The daemon also sweeps expired contexts every 30 seconds while the server runs. These limits bound context count, not total attribution bytes.

Never expose it to a network. See [SECURITY.md](SECURITY.md).

The [Python wire guide](protos/README.md) shows the optional asynchronous gRPC client and its generated request types. That path requires Python 3.10+; the core library keeps its documented Python 3.9 support.

## Repository structure

- To change a memory rule, start in the Python library at `src/reckon/`. The Rust `kernel/` builds through PyO3 and maturin, and `protos/` defines the messages shared by those layers.
- To inspect a run, open the React debugger in `viz-ui/` or use the examples in `notebooks/`. For local daemon clients, use `sdks/` with the gRPC service in `daemon/`.
- For setup, use the installation guide or the optional `setup.sh` helper. `docs/` contains the developer manual, `ARCHITECTURE.md` explains how the parts connect, and `paper/` contains the LaTeX source.

## Design goals

1. Make memory decisions **explicit and measurable**.
2. Provide tasks where **selective retention is necessary**.
3. Make failures **debuggable**: what was stored, what mattered, what broke.
4. Stay **laptop-scale**: no cloud infrastructure required.

## Documentation

| Looking for | Read |
| --- | --- |
| Where to start | [The manual's front page](docs/00-Index.md) |
| An introduction and experiments to follow | [Reckon's product guide](https://causality.in/reckon/) |
| System architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| The memory manager | [docs/08-Causal-Memory-Manager-Design.md](docs/08-Causal-Memory-Manager-Design.md) |
| Benchmark tasks | [docs/09-Tasks-Benchmarks.md](docs/09-Tasks-Benchmarks.md) |
| Notebooks and demos | [notebooks/README.md](notebooks/README.md) |
| Glossary | [docs/13-Glossary.md](docs/13-Glossary.md) |

## Citation

See [CITATION.cff](CITATION.cff) and [docs/99-References.md](docs/99-References.md).

## Product version

The product version is set in [kernel/Cargo.toml](kernel/Cargo.toml). Maturin reads it for Python package metadata, and the required native extension supplies Python's runtime version. The CLI and debugger reuse that runtime value; the daemon reads its own projected Cargo package version.

From a complete checkout, after changing the kernel version, run `python tools/sync_version.py --write` with Python 3.11 or newer to update the daemon and npm manifests. Run `python tools/sync_version.py` before building to refuse version drift without changing files. Rebuild the extension when checking the new runtime version. Schema versions and saved runs keep their own identities.

## Licence

Reckon is licensed under [Apache-2.0](LICENSE): the kernel, the daemon, the Python package, the SDKs and the debugger. Third-party material keeps its own licence and notices.

## Related repositories

| Repository | Relationship |
| --- | --- |
| [MONAD](https://causality.in/monad/) | The formal definitions used by the laboratory manual |
| [HENA](https://causality.in/hena/) | The swarm; its kernel depends on this one, and its store may speak this laboratory's record protocol |
| [Q-HENA](https://causality.in/q-hena/) | The quantum swarm; its kernel depends on this one |
