# Frequently Asked Questions

Use these answers when choosing a policy, connecting a task or diagnosing a run. For a first experiment, start with [Compare two replay budgets](https://causality.in/reckon/compare-replay-budgets/).

## Framework Questions

**Q: Does the laboratory require quantum mechanics?**

No. The framework is stated generally (arrow-neutral dynamics), but all benchmarks and implementations use classical systems. Quantum references are for theoretical completeness and future extensions.

**Q: Is this just another replay buffer?**

A replay buffer is one use of the memory manager. The same record API can hold cues, observations or reasoning traces, with a chosen retention policy and saved operation logs. The laboratory adds tasks and analysis tools for comparing those choices. Start with [the replay-budget comparison](https://causality.in/reckon/compare-replay-budgets/) for a complete learner example; it compares memory allowances, not causal effects of individual records.

**Q: Why "arrow-neutral"?**

The framework starts with dynamics that do not assume a preferred direction of time. Thermodynamic arrows need a coarse-graining and boundary conditions. This keeps those assumptions explicit instead of building them into the microscopic law.

## Implementation Questions

**Q: What if I don't know the causal scores?**

You can store and retrieve records without them. Use FIFO, LRU or a utility-based policy for the comparison you want to run. A supplied prediction-error score can guide retention, but it remains a heuristic. For a removal test, use a runner that removes the record at the point where the task would use it. Check the current evaluator’s limits in the [evaluation protocol](./11-Evaluation-Metrics.md#evaluation-protocol).

**Q: Can I use this with LLMs?**

The manager can store records for a custom agent loop, but it does not automatically manage a model's context window. Your adapter must decide what to write, how to retrieve it, how to assemble the prompt and which outcome updates utility. The conversation notebook can use a simulated backend or a local Ollama model. See the [notebook guide](../notebooks/README.md#backend-and-policy-toggles) for the switch. The software is for local research and has no public release or supported model integration.

**Q: How do I integrate with my RL framework?**

Start with [Connect retrieval to an outcome](../src/reckon/README.md#connect-retrieval-to-an-outcome). Your task supplies observations, actions and rewards; the manager supplies write, retrieval and retention. Keep retrievals for one decision in an `EpisodeContext` before assigning its outcome. `set_episode()` resets stores and the logger by default; `reset_memory=False` carries records, scores and retained events. Save needed events before a reset or before the finite buffer overwrites them. The [memory reference](../src/reckon/memory/README.md) covers the API and current budget limits.

## Debugging Questions

**Q: The agent failed. How do I know if it's a memory problem?**

Use the timeline view of [the debugger](./10-Debugger-Visualization.md) to inspect writes, reads and prunes around the failure, matching their record IDs to the cue records retained by your experiment. Minimal operation logs do not preserve full payloads or tags, so a timeline alone may not identify the cue. For an older `causal_precision` value, first identify its producer and source revision: those keys carried different usage and outcome summaries. Current task results name their `diagnostics` explicitly, including `one_minus_mean_forgetting` and the distinct episode and pooled hint-read fractions. The current record evaluator separately counts beneficial significant interventions. None alone diagnoses the cause of a failed task. The [metrics reference](./11-Evaluation-Metrics.md#causal-quality-approximate) explains those meanings and the intervention evidence needed for a causal interpretation.

**Q: What's "representation drift"?**

When the agent's internal embeddings change over time in ways that break previously learned associations. The [debugger design](./10-Debugger-Visualization.md#f-representation-drift-panel-optional) describes optional spectral tracking for this question. The current debugger application exposes Timeline, Relationship graph and Pareto Frontier views; it does not implement that drift panel.

## Implementation References

- [Memory Module README](../src/reckon/memory/README.md): CMM API (write, read, prune, update_score)
- [Debugger Server README](../src/reckon/viz/README.md): FastAPI backend
- [Debugger UI README](../viz-ui/README.md): React visualization components
