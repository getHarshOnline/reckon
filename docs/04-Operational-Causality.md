# Operational Causality (Resource-Indexed Influence)

When a run succeeds after reading a record, test whether changing the record would change the outcome. First decide what counts as a readable record and how you will tell the intervention’s outcomes apart within the available resources. [MONAD’s formal reference](https://github.com/getHarshOnline/MONAD/blob/main/formal/README.md#notation-correspondence) locates the definitions of interventions and detectable influence, and the proofs about the relation. Reckon’s [mathematical core](./03-Math-Core.md#declare-the-comparison) explains what to declare for a laboratory comparison.

Influence defined this way is neither reflexive nor transitive in general, so it is a relation rather than a preorder; [When effects cancel along a path](https://causality.in/blog/when-effects-cancel/) explains the distinction with an exact example.

## Engineering implication

The memory manager keeps records within finite storage and operation budgets. To use a record as reliable evidence of an event, give the experiment a decision rule that distinguishes the event's two values within the allowed number of repeated trials. Each error probability must be at most $\delta$, where $0 \leq \delta < 1/2$. For a key-colour cue, that means testing whether the recorded observation lets the rule tell the two colours apart with the required error limit. A cue can remain in storage and still be too noisy to pass this test; keeping it only tells you that it persisted.

The contribution test asks a further question: does the outcome change when you remove or replace that cue? Ablation and counterfactual tests measure that change. Report the comparison, assumptions, controls and uncertainty when interpreting that change as causal. Check the [evaluation metrics](./11-Evaluation-Metrics.md) for the current probe methods and their limits before choosing a runner.

## Implementation

- [Core module README](../src/reckon/core/README.md): the `CausalRelation` and `DirectInfluenceRecords` classes in `causality.py`
- [Memory module README](../src/reckon/memory/README.md): storage, retrieval, retention and event logging for these experiments
