# Mathematical Core

[Home](./00-Index.md) | [Prev: Overview](./02-Framework-Overview.md) | [Next: Operational Causality](./04-Operational-Causality.md)

Use this chapter to interpret influence diagnostics, compare retention policies or design a test under resource limits. For method signatures and data types, see the [core Python reference](../src/reckon/core/README.md).

---

## Where the foundations live {#foundational-axioms-monad}

[MONAD](https://causality.in/monad/descriptions-and-repair/) owns the state space and measure-preserving evolution, invariant fine-grained entropy, observer interface, reliable-record criterion, detectable influence and information bounds. Its [formal reference](https://github.com/getHarshOnline/MONAD/blob/main/formal/README.md#notation-correspondence) locates the definitions and proofs; its [kernel reference](https://github.com/getHarshOnline/MONAD/blob/main/docs/kernel.md#compare-a-type-with-its-formal-reference) maps Rust types to those declarations or names a missing counterpart. Neither a resolved reference nor Reckon’s handwritten Python interfaces establishes implementation conformance. This chapter explains what a Reckon experiment must supply and what its diagnostics can report; the full paper remains private pending publication.

---

## Test influence under resource limits {#5-resource-indexed-causality-as-the-laboratory-applies-it}

### Declare the comparison

To investigate influence from A to B, declare the resources R, an allowed protocol and the two preparation operations that set A to zero or one. Record which outcome $`y`$ you observe for B, its two induced probability laws $`P_0`$ and $`P_1`$, the divergence $`D`$ (for example total variation, KL divergence or Hellinger distance) and the detection threshold $`\eta`$. The distributional comparison is:

```math
D(P_1, P_0) \geq \eta
```

To interpret this comparison under MONAD’s influence relation, establish the protocol’s reliable-record conditions for A and B as well. Reliability means repeatable discrimination within the declared trial and error limits, not persistence. A laboratory experiment may instead measure another downstream observable; specify that target and its interpretation rather than assuming it satisfies the reliable-record criterion for B.

MONAD's intervention notation selects allowed preparation operations that set A to zero or one. Those operations can also change other properties, so a detected difference establishes influence of the chosen intervention pair; isolating A's contribution needs additional assumptions or interventions matched outside A. This is not automatically the mechanism-replacement intervention of a structural causal model. The formal profile owns that distinction; a laboratory comparison must declare which operations it actually runs.

The observation model matters too. MONAD’s profile uses deterministic measurable coarse-graining followed by a separate noisy record channel. A stochastic coarse-graining would need its own induced-distribution definitions for fibers and events; the laboratory’s abstract channel interfaces do not establish that generalization.

> **Code**: See [`CausalRelation`](../src/reckon/core/causality.py) and [`DirectInfluenceRecords`](../src/reckon/core/causality.py).

### Current recorded-pair diagnostic

[`DirectInfluenceRecords`](../src/reckon/core/causality.py) stores supplied distinguishability values and thresholds. `causes()` compares each stored pair against its threshold; `check_transitivity()` scans the resulting decisions. It does not estimate the pair values or run significance tests.

Use the recorded thresholds to interpret the scan. The report echoes `alpha` and `multiple_testing_correction` as metadata. Passing either setting leaves the pair decisions unchanged.

> **Code**: See [`DirectInfluenceRecords.check_transitivity()`](../src/reckon/core/causality.py) for the recorded-pair scan.

These illustrative values produce one eligible path whose endpoint falls below its threshold. They exercise the recorded-pair scan; they are not measurements from an experiment:

```python
from reckon.core.causality import DirectInfluenceRecords
from reckon.core.resources import ResourceVector

pairs = DirectInfluenceRecords(ResourceVector(memory_slots=3))
pairs.add_relation("A", "B", distinguishability=0.5, threshold=0.1)
pairs.add_relation("B", "C", distinguishability=0.5, threshold=0.1)
pairs.add_relation("A", "C", distinguishability=0.08, threshold=0.1)
report = pairs.check_transitivity(alpha=0.05)
print(f"Violation rate: {report.violation_rate:.2%}")
print(f"Violations: {len(report.violations)}/{report.total_triples_tested}")
```

The report contains one tested path and one below-threshold endpoint:

```json
{
  "violations": [
    {
      "triple": ["A", "B", "C"],
      "a_b_detected": true,
      "b_c_detected": true,
      "a_c_detected": false,
      "a_b_distinguishability": 0.5,
      "b_c_distinguishability": 0.5,
      "a_c_distinguishability": 0.08,
      "a_c_threshold": 0.1
    }
  ],
  "violation_rate": 1.0,
  "total_triples_tested": 1,
  "alpha": 0.05,
  "multiple_testing_correction": "none"
}
```

#### Read the diagnostic’s counts {#influence-diagnostics-and-ordering-limits}

The Python diagnostic scans recorded two-edge paths through three distinct events. When the endpoint pair is missing or has a recorded value below threshold, it reports the path as a diagnostic. A missing pair has `a_c_distinguishability: null` and inherits the first edge's threshold for display. A tested pair below threshold carries its own value and threshold. `causes()` returns false in both cases. Use `get_relation()` to tell them apart. Both count toward `violation_rate`, whose denominator counts the eligible recorded paths. A two-event cycle alone produces a zero rate with no eligible paths.

### Interpret the recorded pairs {#5-2-interpret-the-recorded-pairs}

MONAD’s influence relation, written $`\preceq_R`$ in this manual, is resource-monotone when larger budgets admit every smaller-budget protocol, but is neither reflexive nor transitive in general. The [formal reference](https://github.com/getHarshOnline/MONAD/blob/main/formal/README.md#notation-correspondence) owns those results. [When effects cancel along a path](https://causality.in/blog/when-effects-cancel/) works through exact cancellation and a reliable channel whose total variation of 0.6 falls below a detection threshold of 0.9.

For Reckon, the consequences are concrete: `DirectInfluenceRecords` stores supplied pairs without assuming closure, and its current diagnostic does not test reflexivity. A missing A-to-C detection after detecting A-to-B and B-to-C need not be sampling error; the population relation itself can fail to compose. Finite samples add further uncertainty, and a larger resource budget need not produce more detected edges in the empirical graph, especially near the noise floor. Keep the population statement separate from that estimate.

#### Closure remains explicit {#5-3-4-system-policy-no-implicit-closure}

The library does not infer transitive closure from recorded pairs.

If downstream logic requires closure, it must be computed **explicitly** with an associated cost and uncertainty model. Closure computation is still planned. The [relationship graph](./10-Debugger-Visualization.md#b-relationship-graph) describes how the view filters snapshot edges and handles separately supplied edges.

**Planned closure modes** (not yet implemented in the library):

| Mode | Description | Trade-off |
| --- | --- | --- |
| **Optimistic** | Assume transitivity holds | Dangerous, low compute |
| **Verified** | Require direct evidence for implied edges | Expensive, high confidence |
| **Probabilistic** | Propagate posterior confidence along paths | Medium compute, uncertainty-aware |

> **Code**: See [`TransitivityReport`](../src/reckon/core/causality.py) for violation reports.

### Proposed empirical estimator {#5-3-empirical-influence-relation}

The estimator described here is a research proposal for pairwise tests. Today, `DirectInfluenceRecords` takes pair values you have already measured and compares them with their thresholds. You run the interventions and calculate significance separately.

#### Theoretical relation and proposed estimator {#5-3-1-notation-theoretical-vs-empirical}

The population relation describes detectability under the model. A finite experiment can only estimate it:

| Relation | Notation | Meaning |
| --- | --- | --- |
| Theoretical | $`\preceq_R`$ | Population/"true" detectability under resources $`R`$ |
| Empirical | $`\hat{\preceq}_{R,n,\alpha,M}`$ | Estimated from data with parameters below |

The empirical estimator is indexed by:

- $`n`$ = samples/episodes per pairwise test
- $`\alpha`$ = per-test significance level (default: 0.05)
- $`M`$ = number of hypotheses tested (for multiple testing)
- Plus implicit noise model and task stochasticity

#### Pairwise significance does not imply transitivity {#5-3-2-the-key-truth}

The proposed empirical estimate $`\hat{\preceq}_{R,n,\alpha,M}`$ adds noise and thresholds to the population relation. Detecting A→B and B→C at $`p < \alpha`$ does not imply A→C is detectable at $`p < \alpha`$.

#### Why empirical pairs can fail to compose {#5-3-3-why-transitivity-violations-occur}

Whether a finite test detects an effect depends on its size, the variance and the number of samples.

On top of the failures the relation itself allows, the empirical estimator can violate transitivity because of:

1. **Stochasticity / finite $`n`$**: Limited samples increase false negative rate
2. **Type I errors (false edges)**: Some detected edges are spurious
3. **Type II errors (missing edges)**: Some true edges fail detection
4. **Effect size dilution**: Causal effects often attenuate along paths ($`A \to B \to C`$ weaker than $`A \to B`$ or $`B \to C`$)
5. **Selection bias**: "We only tested some triples", so coverage is incomplete
6. **Multiple testing inflation**: Testing $`M`$ hypotheses without correction inflates false positives

#### Multiple testing {#5-3-6-multiple-testing}

The per-test $`\alpha = 0.05`$ is a **per-comparison** error rate.

When testing $`M`$ hypotheses, options include:

| Method | Control | Formula | Notes |
| --- | --- | --- | --- |
| **None** | Per-test | $`\alpha`$ | Fast, high false positive rate |
| **Bonferroni** | FWER | $`\alpha / M`$ | Conservative, low power |
| **Holm** | FWER | Sequential adjustment | Less conservative than Bonferroni |
| **Benjamini-Hochberg** | FDR | Ranks p-values | Controls expected false discovery rate |
| **q-values** | Estimated FDR or positive FDR at rejection thresholds | Minimum estimated rate over thresholds including the test | A thresholded-set quantity, not the test's posterior null probability |

A q-value describes the estimated false-discovery rate associated with calling a test significant. Local FDR instead estimates the probability that the test's null hypothesis is true, conditional on its observed statistic under the selected model. The [maintained qvalue package](https://www.bioconductor.org/packages/release/bioc/html/qvalue.html) distinguishes these two outputs. Neither is a causal probability, and neither is computed by the recorded-pair diagnostic.

**Planned options**: FWER control (Bonferroni/Holm), FDR control (Benjamini-Hochberg), q-values.

> [!NOTE]
>
> **Correction does not establish transitivity.** Correcting the error rate across tests does not make detected paths compose. The result is still a graph of pairwise decisions.

### Save a reproducible report

The scan orders event identifiers by Unicode code point, so the resulting triples have the same order across insertion orders and Python hash seeds. `to_json(indent=2)` gives a readable report. For a saved identity, use `to_canonical_json()` and hash its UTF-8 bytes without adding a newline:

```python
import hashlib

artifact = report.to_canonical_json().encode("utf-8")
digest = hashlib.sha256(artifact).hexdigest()
```

The canonical profile adds `schema_version: "reckon.transitivity-report/v1"` to the report. It sorts violations by the event triple, breaks repeated-triple ties by the complete encoded entry and retains duplicate entries. Object keys sort lexically; Python JSON uses compact separators, ASCII string escapes and its finite-number spelling. Event identifiers keep their exact Unicode sequences, and numeric representations such as `1` and `1.0` remain distinct. NaN and either infinity are refused. Serialization leaves the original report unchanged.

The digest covers the report's supplied fields, including significance and correction metadata. Those labels still do not change the pair decisions or perform statistical correction. Keep the source records, resource configuration and implementation revision with the artifact when another run must reproduce it. Missing endpoint values remain `null`, distinct from a measured zero or a value below threshold.

---

## Use scores to choose what survives {#6-utility-and-retention}

### Read the stored signals {#6-1-stored-signals}

Each record $r$ carries:

- `utility.value`: accumulated utility estimate (updated via `update_score()`)
- `utility.last_used`: timestep of last access
- `causal_score.ablation_delta`: performance change when record removed (**MEASURED**)
- `causal_score.counterfactual_delta`: change under hypothetical intervention (**MEASURED**)
- `causal_score.influence_proxy`: heuristic proxy (e.g., gradient magnitude) (**PROXY**)

These labels describe the intended source of each score. A populated field alone does not establish that its intervention ran or was valid; keep the experiment with the value and follow the [proxy-only reporting rule](./11-Evaluation-Metrics.md#distinguish-proxy-only-records).

### Policy Score for Retention

When the Python memory manager prunes, it calls its configured [retention policy](../src/reckon/memory/policies.py). `EvidencePerBytePolicy` prefers the non-negative part of an ablation result, then the non-negative part of a counterfactual result, then a separate proxy. Deltas use outcome with the record minus outcome without it: a negative value means removal helped, so that effect gives zero retention credit. The stored measurement keeps its sign:

```math
C_m(r) = \begin{cases}
\max(\Delta_a, 0) & \text{if ablation measured} \\
\max(\Delta_c, 0) & \text{else if counterfactual measured} \\
\bot & \text{otherwise}
\end{cases}
```

```math
C_p(r) = |\phi|
```

Combined score:

```math
S(r) = (1 - \alpha) \cdot U(r) + \alpha \cdot C(r)
```

where:

- $C_m(r)$ = beneficial part of the measured attribution (from `ablation_delta` or `counterfactual_delta`)
- $C_p(r)$ = proxy magnitude (from `influence_proxy`)
- $C(r) = C_m(r)$ if defined, else $C_p(r)$ as fallback. If the record has neither a measured value nor a proxy, the causal term is zero.
- A negative or zero measured result remains the selected measured branch; it does not fall through to a positive proxy. The proxy is separately labelled and is not evidence of benefit.
- $U(r)$ = utility estimate
- $\alpha$ = evidence weight (0-1)

To free bytes, slots and tokens, the Python policy removes the records with the lowest combined score divided by `max(record.cost.bytes, 1)` first.

**Design note**: The Python policy selects the kernel's `EvidencePerByte` rule above. The Rust `WeightedEvidencePolicy` wrapper selects `WeightedEvidence`, which adds non-negative ablation and counterfactual contributions and the absolute proxy with weights 1, 0.5 and 0.25, then mixes that sum with utility. It ranks the combined score without dividing by cost. Both rules live in the [kernel](../kernel/src/policies.rs), and they remain different policies; a comparison must name the rule and revision it uses.

The [store’s priority index](../kernel/src/store.rs) is a third ranking: utility plus $0.5[\max(\Delta_a, 0) + \max(\Delta_c, 0)]$, with missing measurements contributing zero. The daemon calls the same function for capacity pruning. It uses neither the proxy nor cost division. NaN measurements contribute zero; a NaN total has the lowest priority. Both stores break equal scores by record ID.

> **Code**: [Kernel retention rules](../kernel/src/policies.rs) implement the rankings and byte/slot selection; [Python policy objects](../src/reckon/memory/policies.py) select the laboratory rules.

To interpret `ablation_delta` or `counterfactual_delta`, report what you changed, what you compared, how you identified the effect, the controls and the uncertainty. Keep proxy scores separate. See [evaluation metrics](./11-Evaluation-Metrics.md) for what each method tests.

### Account for time since access {#6-3-recency}

Define recency as $\tau(r) := t_{now} - t_{last}$, measuring steps since last access (not since creation).

A policy could weight utility by a decay function $f(\tau)$, for example $\exp(-\tau/T)$ with task-configurable $T$. The current FIFO policy sorts by creation time, and LRU sorts by `last_used` with creation time breaking ties. Neither applies this decay.

### Keep every storage limit {#6-4-budget-constraint}

Given budget $B = (M_s, M_b, M_t)$ where $M_s$ = max slots, $M_b$ = max bytes, $M_t$ = max tokens:

```math
\sum_{r \in \mathcal{R}} 1 \leq M_s, \quad \sum_{r \in \mathcal{R}} |r|_b \leq M_b, \quad \sum_{r \in \mathcal{R}} |r|_t \leq M_t
```

> **Code**: See [`MemoryBudget`](../src/reckon/core/resources.py).

### Choose which records to remove {#6-5-optimal-pruning}

Select records to prune by solving:

```math
\arg\min_{S \subseteq \mathcal{R}} \sum_{r \in S} U(r) \quad \text{s.t.} \quad \sum_{r \in S} |r|_b \geq \delta
```

where $\delta$ = overflow amount to free.

This is a knapsack-style optimization and is NP-hard in general. The [Python `UtilityPolicy`](../src/reckon/memory/policies.py) selects the kernel's greedy utility-per-cost heuristic. The [Rust `UtilityPolicy`](../kernel/src/policies.rs) selects its raw-utility rule instead. Neither policy solves the general optimization problem, and sharing the kernel does not make those two rankings equivalent.

> **Code**: See [`RetentionPolicy`](../src/reckon/memory/policies.py) and Rust implementation in [`kernel/src/policies.rs`](../kernel/src/policies.rs).

---

## Apply information bounds with their assumptions {#7-information-theoretic-bounds}

MONAD (§6) defines a single-letter channel-capacity functional. Its interpretation as a reliable coding rate requires a declared channel class, repeated-use model, block code, error criterion and block-cost constraint, with converse and achievability results under those assumptions. The MONAD profile does not establish the general coding theorem. Check the hypotheses of any coding result you apply to an experiment. Rates use nats per channel use; a record slot is not automatically one channel use.

For two probability laws on a finite alphabet, independent identically distributed observations and fixed strictly positive priors, the profile's Chernoff result gives the asymptotic exponent of optimal weighted Bayes error. A sample budget or detectability threshold also needs the hypothesis family, statistic, sampling model and Type-I/Type-II error requirements. These results inform memory experiments only after the experiment supplies that model; they do not by themselves give a per-slot storage guarantee or an individual causal-test guarantee.

The full foundational formalism is in MONAD’s “Information-theoretic bounds” section.

---

## Find the corresponding interface {#summary}

| Concept | Mathematical Object | Code Reference |
| --- | --- | --- |
| State Space | $`\mathcal{X}^{(N)}`$ | Implicit in record payloads |
| Resources | $`R = (M, B, \varepsilon)`$ | [`ResourceVector`](../src/reckon/core/resources.py) |
| Coarse-Graining | $`\Pi_s : \mathcal{X} \to \mathcal{M}_s`$ in MONAD’s deterministic profile | [`CoarseGraining`](../src/reckon/core/channels.py), an abstract laboratory interface |
| Record Channel | $`\mathcal{C}_R : \mathcal{M}_s \to \Delta(\mathcal{Y}_R)`$ | [`RecordChannel`](../src/reckon/core/channels.py) |
| Recorded influence pairs | Supplied values and thresholds, interpreted against $`\preceq_R`$ | [`DirectInfluenceRecords`](../src/reckon/core/causality.py) |
| Utility | $`U(r)`$ | [`UtilityEstimate`](../src/reckon/memory/record.py) |
| Budget | $B = (M_s, M_b, M_t)$ | [`MemoryBudget`](../src/reckon/core/resources.py) |

---

[Home](./00-Index.md) | [Prev: Overview](./02-Framework-Overview.md) | [Next: Operational Causality](./04-Operational-Causality.md)
