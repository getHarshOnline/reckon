# Reckon

<a id="the-reckon-laboratory-manual"></a>

Use this manual to build the `reckon` Python package, integrate its memory manager or send a run to the debugger. The build gives you a Python extension backed by Rust. Your task supplies the observations and outcomes.

For an introduction and experiments you can follow from start to finish, use [Reckon’s product guides](https://causality.in/reckon/understand-the-memory-laboratory/).

## Build and integrate the laboratory

::::card-group

:::card

[Build the Python extension](./01a-Installation.md)

Build the wheel against your interpreter and verify the Rust import.

:::

:::card

[Connect retrieval to an outcome](../src/reckon/README.md#connect-retrieval-to-an-outcome)

Wire writes, reads and an outcome into a task you own.

:::

:::card

[Understand memory decisions](./08-Causal-Memory-Manager-Design.md)

Find which limits apply when you write a record and how retrieval orders matches.

:::

:::card

[Supply debugger data](./10-Debugger-Visualization.md)

Supply the fields the timeline, graph and cost plot need.

:::

::::

Before you compare two runs, check which [task](./09-Tasks-Benchmarks.md) produced each [metric](./11-Evaluation-Metrics.md). Save the configuration, seeds, software versions and outputs together so someone can [repeat the run](./12-Reproducibility.md). The [notebooks](../notebooks/README.md) show how those inputs reach a figure.

If you came here to [compare replay budgets](https://causality.in/reckon/compare-replay-budgets/) or [inspect a saved run](https://causality.in/reckon/inspect-an-exported-run/), return to that task after installation.

## If you want to extend it or review the ideas

Read [the problem](./01-Problem-Context.md) and [framework](./02-Framework-Overview.md) first. The remaining chapters develop:

- [The mathematical core](./03-Math-Core.md): resource-indexed influence, its empirical estimate and retention under budgets.
- [Operational causality](./04-Operational-Causality.md) and [entropy and coarse-graining](./05-Entropy-CoarseGraining-Arrows.md): the definitions Reckon takes from MONAD.
- [Retrodiction bounds](./06-Retrodiction-Bounds.md): the assumptions limiting recovery of earlier states.
- [Learning](./07-Learning-Optimization-Specialization.md): training as an open reduction and representation geometry as an observable.

Use the [glossary](./13-Glossary.md), [FAQ](./14-FAQ.md) and [references](./99-References.md) for specific questions.

The [planned evaluation contract](evaluation-contract.md) specifies a future service for fixed experiments and signed results. It is separate from the laboratory's working evaluation helpers.

## Where the code is

| To change or understand | Read |
| --- | --- |
| System boundaries and data flow | [Architecture](../ARCHITECTURE.md) |
| Python integration | [Main API](../src/reckon/README.md) |
| Resources, channels and relation diagnostics | [Core reference](../src/reckon/core/README.md) |
| Records, queries and retention | [Memory reference](../src/reckon/memory/README.md) |
| Task runners | [Task interface](../src/reckon/tasks/README.md) |
| Measurement helpers | [Metrics reference](../src/reckon/metrics/README.md) |
| Run storage and streaming | [Debugger server](../src/reckon/viz/README.md) |
| Rust storage, logging and Python bindings | [Kernel](../kernel/README.md) |
| Browser application and reusable views | [Debugger interface](../viz-ui/README.md) |
| Test execution and new cases | [Run and extend the tests](../src/tests/README.md) |

> [!WARNING]
>
> **Keep the daemon on a trusted local machine.** It accepts loopback connections and uses plaintext without caller authentication. Its [record-only export](../daemon/README.md) returns the records a named run wrote or retrieved; event, metric and archive attachments remain unimplemented. This is separate from a complete debugger run bundle. See the [security policy](../SECURITY.md).
