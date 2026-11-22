# Framework overview

<a id="framework-overview-arrow-neutral-core-operational-causality-memory-manager"></a>

Reckon uses a research model to ask which observations an agent can keep and test under resource limits. Start here to see how those questions relate to the memory manager, evaluation code and debugger.

## Layers

The model distinguishes the underlying dynamics, the observations an agent can make and the conclusions it can draw from them.

### Layer 1: Microdynamics (arrow-neutral)

Assume closed evolution is reversible and measure-preserving (classical) or unitary (quantum). Fine-grained entropy is invariant here. No arrow is assumed in the micro-law.

### Layer 2: Observer interface (where arrows enter)

For scale s and resources R, the interface has three parts. The coarse-graining Π_s determines what the agent observes. The record channel C_R determines what it can store and read back under noise. The allowed operations Op_R determine what it can change in an experiment.

Thermodynamic arrows arise only after:

- choosing Π_s and resolution,
- adding boundary conditions (e.g., Past Hypothesis),
- invoking typicality arguments.

### Layer 3: Operational causality and retrodiction

Use [operational causality](./04-Operational-Causality.md) to ask whether an intervention changes what can be reliably observed under R. The resulting relation can fail reflexivity and transitivity. Use [retrodiction](./06-Retrodiction-Bounds.md) to ask whether you can recover an earlier state from later records, given what the observation map preserves, how inverse errors grow and how noisy the records are.

## The engineering translation

The memory manager stores typed records and decides when to remove them. Evaluation helpers summarize outcomes and test supplied comparisons. The debugger shows activity from a run you saved.

> [!NOTE]
>
> **Abstract interfaces do not establish the model.** The [channel interfaces](../src/reckon/core/README.md#resource-and-channel-boundaries) are abstract classes, not concrete implementations of mathematical coarse-graining or reliable recording. The [memory manager](./08-Causal-Memory-Manager-Design.md) explains current budget enforcement and retrieval. The [evaluation protocol](./11-Evaluation-Metrics.md#evaluation-protocol) describes the intervention-timing limits; the [debugger guide](./10-Debugger-Visualization.md) distinguishes recorded operations from snapshots and measured contribution evidence.

## Implementation

| Component | Design Doc | Implementation |
| --- | --- | --- |
| Core abstractions | [03-Math-Core.md](./03-Math-Core.md) | [core/README.md](../src/reckon/core/README.md) |
| Causal Memory Manager | [08-Causal-Memory-Manager-Design.md](./08-Causal-Memory-Manager-Design.md) | [memory/README.md](../src/reckon/memory/README.md) |
| Debugger | [10-Debugger-Visualization.md](./10-Debugger-Visualization.md) | [viz/README.md](../src/reckon/viz/README.md), [viz-ui/README.md](../viz-ui/README.md) |
| Performance layer | none | [kernel/README.md](../kernel/README.md) |
