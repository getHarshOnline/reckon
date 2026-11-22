# Reckon core module

Configure resources, implement a channel or inspect supplied influence pairs with these core types. The [mathematical framework](../../../docs/03-Math-Core.md) explains their interpretation. A type or stored threshold alone does not demonstrate record reliability or a causal effect.

The [generated core API](https://docs.causality.in/reckon/python-api/core) reads fields, signatures and method documentation from resources, channels, recorded influence, credit and episode-context code. [Build it from the selected checkout](../../../docs/reference/README.md); keep the explanations below beside the generated reference.

## Credit assignment in Python

[`compute_credit`](credit.py) attaches record IDs to weights calculated by the [Rust kernel](../../../kernel/src/credit.rs). The same kernel supplies the moving-average update to Python and the daemon. SHAPED normalizes stable softplus weights, with a laboratory default scale of 1.0 and utility 0.5 for a missing record. Empty retrieval and NONE yield no assignment. Non-finite outcomes or invalid weights fail before an observation changes utility; finite negative outcomes use the same weights.

ABLATION normalizes only positive measured ablation deltas. If no record has a measurement, it falls back to equal credit. If measurements exist but none is positive, every weight is zero; a harmful measured effect does not earn fallback credit. The signed measurements remain unchanged. Supply them as `ablation_deltas` to `compute_credit`. Python policy values and new observation tags use `ablation`; serialized assignments use that spelling too. The former `CAUSAL` member and `causal` string have no aliases. Existing saved records keep their original labels and source revision. The utility update requires finite inputs, credit in [0, 1], a learning rate in (0, 1] and ordered finite bounds, then clamps its result to those bounds.

## Resource and channel boundaries

`ResourceVector` contains optional slot, byte, token, bandwidth and compute limits plus a noise floor. Its `is_satisfied()` method checks only slots, bytes and tokens, and only where both compared values are present. It does not enforce bandwidth, compute, noise or MONAD's full protocol order.

Implement `CoarseGraining` and `RecordChannel` for your observation and storage model. MONAD uses a deterministic measurable coarse-graining map followed by a noisy record channel. Your implementation must satisfy the assumptions needed by the result you use; the abstract interfaces do not check them.

`MemoryBudget.to_resource_vector()` copies the slot, byte and token configuration, not a complete formal protocol budget. The [memory-manager guide](../../../docs/08-Causal-Memory-Manager-Design.md#budget-enforcement) owns write-time admission and operation limits. Resource and relation dataclasses are mutable; copy or serialize a configuration before changing it when a saved result needs its original settings.

## Interpret recorded pairs

`add_relation()` stores the supplied pair values. `causes()` checks the stored distinguishability against its threshold with the implementation's floating-point tolerance. Run the intervention and check whether it can reliably distinguish the outcomes before passing your measurement to this type. The [operational causality chapter](../../../docs/04-Operational-Causality.md) owns the stronger protocol criterion; new evidence remains an intervention contrast unless its causal assumptions are established.

Influence can fail to be transitive even in the theoretical relation. MONAD gives a finite counterexample, and measurement noise can create further violations in recorded results. Run `DirectInfluenceRecords.check_transitivity()` to find eligible stored paths that violate the relation. See [docs/03-Math-Core.md](../../../docs/03-Math-Core.md) for details.

The scan orders triples consistently across insertion orders and Python hash seeds. Use `TransitivityReport.to_canonical_json()` for the versioned finite-value encoding to save or hash. The [serialization contract](../../../docs/03-Math-Core.md#influence-diagnostics-and-ordering-limits) defines its byte spelling, duplicate handling and preserved distinction between missing and measured endpoint values.

The default stored-pair threshold is 0.1, compared as `distinguishability >= threshold - EPSILON` with `EPSILON = 1e-9`. Changing it changes classifications, not the statistical detectability of the upstream experiment. An eligible path with a missing endpoint pair remains untested; the diagnostic never infers an A-to-C effect from A-to-B and B-to-C.

Change `resources.py` for budget types, `channels.py` for abstract observation/storage interfaces and `causality.py` for recorded-pair diagnostics. The [kernel credit module](../../../kernel/src/credit.rs) owns weights and moving-average updates; Python’s `credit.py` attaches record IDs and translates policy names. The [protocol sources](../../../protos/README.md) declare separate resource, budget, relation and divergence wire types; those do not make the Python objects generated or enforce the formal model.

Part of the [Python library](../README.md).
