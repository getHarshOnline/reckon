# How the memory manager works

<a id="causal-memory-manager-cmm-system-design"></a>

Your task decides what to remember and when to use it. Reckon's memory manager keeps those records within an allowance and chooses which ones to remove when another write needs room. This guide follows those decisions, then explains the checks and storage details you need when integrating or extending the manager.

<a id="1-purpose"></a>

## Follow a cue through memory

In the [delayed-cue example](../src/reckon/README.md#connect-retrieval-to-an-outcome), the task writes the location of a key, retrieves it later and reports an outcome. `retrieve()` remembers which records it returned in an episode context. `observe()` shares credit among those records and updates their utility through a moving average. The task supplies the outcome and the decisions that led to it.

Writing another record may force a choice. With room for two records, a third admissible write needs to remove at least one of the first two. FIFO removes the oldest; a utility policy removes records with the lowest utility per byte. The same task can therefore keep different memories under the same allowance. A score affects that choice only when the retention policy uses it.

The manager retains native record values through PyO3, with the caller’s payload and mutable containers kept by reference. Rust also keeps fixed admission costs, priorities and the event buffer. Writes and reads also have separate operation-rate allowances. Before a write removes anything, the manager checks those limits and whether the new record can fit at all. If you limit tokens, your task must supply its token count. The [budget rules](#budget-enforcement) explain refusals and what remains unchanged.

<a id="2-core-abstractions"></a>

## What a record carries

### MemoryRecord

The payload holds the observation itself, raw or compressed. Its ID lets you retrieve that particular record; its step and episode identify when it was written. Tags describe its role, such as a cue, reward, trace or representation. Origin fields keep the creating operation, input record IDs and content hash.

The record also carries its cost in bytes, tokens and slots, its utility estimate and uncertainty, and when it was last used. Optional fields hold later ablation, counterfactual or proxy scores. Those stored signals are inputs to a policy: the [mathematical core](./03-Math-Core.md#policy-score-for-retention) explains how a policy turns them into a ranking.

### MemoryBudget

Use `max_slots` to limit the number of records, `max_bytes` to limit their byte cost and `max_tokens` when your task counts tokens. The manager enforces all active storage limits together. Reads and writes can also have independent `max_read_ops_per_window` and `max_write_ops_per_window` allowances over logical steps. Even an empty read counts as a successful call. The [rate-limit rules](#read-and-write-rate-limits) explain expiry, calls in progress, failures and setting changes; the [token rules](#supply-token-counts-explicitly) keep a missing count distinct from zero.

A record larger than its byte or token allowance is refused before existing records or logs change. For an admissible write, the selected policy frees enough bytes, slots and tokens before insertion. See the [Python memory implementation](../src/reckon/memory/manager.py).

### Episode boundaries

`set_episode(id, reset_memory=False)` carries records, learned scores, retained events and operation windows into the next episode. `set_step()` remains relative to that episode; the manager offsets it beyond the previous episode’s last step so FIFO and LRU can compare old and new records correctly. With operation limits enabled, the timeline cannot move backwards. An explicit reset clears records, scores, the event buffer, operation windows and the time offset. The default API call still resets; callers choose carry explicitly. Task or environment state has its own lifetime.

<a id="policy-retention-retrieval"></a>

### Choose what to keep

Pass a `RetentionPolicy` when creating the manager; the default is `FIFOPolicy`. FIFO removes the oldest records, while LRU removes those least recently accessed. Other built-in choices use utility per byte, caller-supplied importance, measured effects, a seeded random order or diversity of payload types. Choose the comparison that answers your task's question rather than assuming the more elaborate rule will do better.

The kernel follows the chosen removal order until enough bytes, slots and tokens are freed. Python supplies the random policy's seeded order. Before removing anything, the manager checks that the selection contains distinct existing records and frees enough space. The diversity rule protects a minimum number of each payload type while capacity permits. The wider design also considers avoiding redundancy in replay; protecting type counts alone does not implement that behaviour.

### Ask for a record

To retrieve a known cue, pass its `record_ids`. To search the retained records, filter by `tags`, `payload_type` or `min_utility`; matches are ordered by utility and capped by `limit`. The [memory module](../src/reckon/memory/README.md) leads to the current API.

The intended retrieval design is broader: symbolic keys, similarity search and reads triggered by uncertainty or prediction error. The manager currently supports explicit IDs and the filters above. Your task must supply similarity search or decide when uncertainty warrants a read.

<a id="3-online-knapsack-framing-implementation-agnostic"></a>

## Why compare utility with cost?

Suppose each candidate record at time t has an estimated value v_i and a resource cost c_i. We want a subset whose total value ∑ v_i is as large as possible while its total cost stays within C_max. This is the knapsack view of retention; value here estimates downstream utility or influence, and cost describes the resource being limited.

New observations arrive before all their consequences are known. An online approximation is to remove the lowest utility per unit of cost when the allowance fills. Python's utility policy uses bytes as that cost, even when a slot or token limit triggers removal. It is a greedy rule to compare against the alternatives, rather than a guarantee of the best possible retained set.

<a id="4-causal-scoring-optional-but-important"></a>

## Use measured effects in a retention decision

An outcome update shares credit among retrieved records. To ask what difference a particular record made, you need another experiment. An ablation removes it and measures the change in performance; a counterfactual probe replaces it with an alternative. The manager can also accept an influence proxy, such as a gradient or TD-error signal, when no such measurement is available.

Keep the comparison, assumptions, controls and uncertainty with a measured delta before interpreting it causally. A proxy supplies a heuristic for retention. The manager stores these inputs and uses the selected rule; the experiment has to justify what each input means.

Python's `EvidencePerBytePolicy` mixes utility with an effect score and divides by byte cost, using the kernel's `EvidencePerByte` rule. For the effect score, it takes the positive part of an ablation measurement if present, otherwise the positive part of a counterfactual measurement, otherwise the proxy magnitude. A harmful or zero measurement gives zero effect credit; it does not fall through to the proxy. The [mathematical core](03-Math-Core.md#policy-score-for-retention) gives the formulas and distinguishes this rule from Rust's weighted aggregation and the store's priority index.

<a id="design-guardrail-priority-fallback-as-product-choice"></a>

### Why the policy uses the first available score

The fallback lets the policy work with a proxy alone. Choosing that fallback is a product choice, not a theoretical claim about causality. Downstream reports must [flag proxy-only records](./11-Evaluation-Metrics.md#distinguish-proxy-only-records) so a heuristic cannot appear to be an intervention result. To decide whether a score supports a causal claim, check how the caller obtained it. Keep the measurement’s context with its [evaluation](./11-Evaluation-Metrics.md) or [graph](./10-Debugger-Visualization.md).

An alternative policy could combine scores or keep separate tiers. Changing that rule changes the retention algorithm and needs its own comparison.

<a id="5-outputs-for-debugger"></a>

## Keep the history needed to explain a run

The current Python manager emits Rust logger events for these operations:

- Successful writes: record ID and the current total stored bytes in `bytes_after`.
- Reads: the returned hit IDs in `details`, not the original query predicates.
- Prunes: record ID and the emitted reason label.
- Supported score updates on an existing record: record ID, score type, old/new values and signal source.

> [!CAUTION]
>
> **Collect the run before events are lost.** These minimal operation events do not preserve full record payloads, tags, utility snapshots or query context, and a score-update event is not pair-bound graph evidence. The manager's in-memory ring holds 10,000 events and can overwrite older entries; `get_event_log()` drains the retained buffer. Saving a complete run requires explicit collection and export, as described in [Reproducibility](./12-Reproducibility.md).

The kernel's [future storage and performance choices](../kernel/README.md#future-storage-and-performance-choices) describe the conditions for a durable laboratory store and replay, batch numerics, shared arena mechanics and a Linux I/O adapter.

## Integrate the Python manager

The [Rust laboratory model](../kernel/src/record.rs) owns record fields and their TypeScript and JSON Schema descriptions. The public [Python adapters](../src/reckon/memory/record.py) preserve mutable references, dataclass helpers, copying and pickling around native fields. [Resource configuration](../src/reckon/core/resources.py) remains a Python dataclass. Protocol declarations for [records](../protos/reckon/record.proto), [budgets](../protos/reckon/budget.proto), [influence](../protos/reckon/causality.proto) and [events](../protos/reckon/events.proto) define separate historical wire models; check their adapters when changing an interface.

A write encodes the payload for admission, checks the budget, selects and verifies removals, retains the native object with its admission costs, and logs the operation before returning its record ID. A query filters those live objects and sorts matches by utility; explicit IDs retain caller order. After applying the limit, a read updates access statistics through the native store, logs the operation and returns the records. Python filtering scans the retained objects, so a workload needing indexed queries requires its own implementation and measurements.

All policies implement `select_for_pruning(records, overflow_bytes, overflow_slots=0, overflow_tokens=0)`. Custom policies must accept the trailing token pressure and satisfy all three dimensions; the manager rejects an insufficient selection before removal.

These Python objects select rules implemented in the [Rust kernel](../kernel/src/policies.rs). Ranking inputs cross the binding; payloads stay with the caller. The kernel handles byte, slot and token pressure, preserves input order for equal keys and rejects invalid ranking inputs before the manager prunes or logs. The random arm retains Python's seeded permutation and passes that order to the kernel.

The laboratory’s explicit `measured` arm obtains deltas through paired trials from independent copies of retained memory before pruning. Each pair starts fresh task episodes under a declared reference policy, removing the target in one arm. Its point estimate enters the existing measured-effect-per-byte ranking. The [probe configuration and cost report](./12-Reproducibility.md#measure-retained-records-before-pruning) distinguish this experiment from continuing the live task, and preserve signed estimates, uncertainty and the full probe cost rather than turning significance into a pass mark.

Ordinary reads follow the query path described above. During `before_read(callback)`, the callback sees the limited candidate list before access counts, logging or context tracking. It may prune a candidate; the query then resolves again so the returned IDs and later credit describe the changed memory. The scope holds the manager lock, survives episode resets and removes its callback after success or failure. Nested scopes are refused, and callbacks must not initiate another read. The [evaluator](../src/reckon/metrics/evaluator.py) uses this boundary for verified ablation.

For shaped credit, `observe()` records `observe:shaped:softplus:scale=1.0` as the signal source on each score update. A bare `observe:shaped` in an older trace needs the run's source revision to identify its formula.

Credit weights and the utility update come from the [shared kernel implementation](../kernel/src/credit.rs), also called by the daemon. The manager validates every proposed utility update before changing either store. ABLATION gives measured non-positive effects zero credit, including an all-non-positive set; equal fallback is reserved for a set with no measurements.

Utility updates synchronize the native priority index; attribution and proxy updates remain in the live native records. Writes and prunes must keep both representations aligned. Tasks own the decisions and outcomes that drive these operations, and compute their metrics from the relevant task state. The [kernel guide](../kernel/README.md#components) explains storage mechanics, while the [architecture guide](../ARCHITECTURE.md) owns performance targets; those targets are not measured guarantees.

## Thread Safety

Manager operations use a reentrant `RLock`. `retrieve()` also updates a caller-supplied or current episode context outside the locked `read()` call. Returned `MemoryRecord` objects are mutable references, not isolated snapshots. A lock around storage does not make the whole context, caller mutation and observation sequence atomic.

Key points:

- The lock is reentrant to support nested method calls (e.g., `write()` calling `_enforce_budget_combined()`)
- Internal state (`_records`, `_store`, `_logger`) should not be accessed directly without holding the lock
- Callers coordinate context lifetime and mutation of returned records separately; copy a returned record if you need a stable snapshot

## JSON Encoding

The `ReckonJSONEncoder` class handles serialization of complex types:

```python
from reckon.memory.manager import ReckonJSONEncoder
import json

# Serialize payload with custom encoder
json.dumps(complex_payload, cls=ReckonJSONEncoder)
```

Supported types:

- `datetime`: Converted to ISO format string
- Dataclasses: Converted to dict via `asdict()`
- Objects with `__dict__`: Converted to their `__dict__`
- NumPy arrays: Converted to list via `tolist()`

## Numeric Safety

The memory module includes several safeguards for numeric stability:

| Safeguard | Location | Purpose |
| --- | --- | --- |
| `MAX_DELTA = 1000.0` | `UtilityEstimate.update_utility()` | Clamps that helper's additive delta |
| `NORMALIZATION_THRESHOLD = 1e6` | `UtilityEstimate.update_utility()` | Returns a flag when the resulting magnitude exceeds the threshold; does not normalize it |
| Minimum cost floor | `utility_per_cost()` | Uses `max(cost.bytes, 1)` to prevent division by zero |

The update path matters. `CMM.update_score()` assigns the supplied value directly. `MemoryRecord.update_utility()` adds its delta directly. `observe()` instead uses the [credit utility helper](../src/reckon/core/credit.py), whose moving average has its own bounds. The first helper's safeguards do not apply automatically to every path, and writing a score does not validate its measurement.

## Subscribe to recorded operations

`subscribe_events()` is a context manager yielding a queue of `(source_id, event)` pairs. Attachment copies the retained kernel log and registers the queue under the manager lock. Later write, read, prune and score-update operations copy the actual logged record before a caller can drain it. Resetting memory creates a new source ID; the subscription survives the reset and distinguishes repeated numeric event IDs by source.

Attachment refuses known prior ring overflow. Previously drained events are unavailable. The queue is diagnostic memory outside the task's budget and must be consumed; it has no fixed memory bound. Leaving the context detaches under the lock. The [visualization server](../src/reckon/viz/README.md#with-causalmemorymanager-process-local-registration) consumes this interface for its process-local live runs.

## Budget Enforcement

### Copy retained memory for a trial

`fork_for_trial(retention_policy)` copies the live native records, their admitted costs and priorities, cost totals and episode timeline into an independent manager. Supply a fresh policy for the trial. Mutable payloads and metadata are copied too. The trial starts with empty operation windows and an empty event log, and receives no callbacks, subscriptions or episode-context retrieval history. Its writes, reads, score updates and removals leave the original manager unchanged. This copies retained memory for a new experiment; it does not snapshot a running task or its environment.

### Admit a write under all storage limits

The Python `write()` path computes byte, slot and token overflow together while holding its lock:

1. Validate byte and declared token counts against the kernel’s signed 64-bit range, keeping the one-byte floor for integer byte costs below one. A token limit requires a count for every retained record and the new write. Reject a record that alone exceeds either allowance, leaving existing records and logs unchanged.
2. Calculate all three overflows, then ask the selected policy for the shortest prefix of its existing ranking that satisfies every active dimension. Token pressure does not change a per-byte score into a per-token score.
3. Verify that the policy chose distinct existing records and freed enough space, that both final retained totals fit the kernel's signed 64-bit range, and that the pruning reason is valid text before removing any. Insert the new record only after those checks.

The total before pruning may exceed that integer range if the selected removals make the final total fit. A fractional byte count raises `TypeError`; an unrepresentable byte count or retained total raises `OverflowError` before records or removal logs change. `set_step()` and a carried episode's next step use the same integer range. Episode IDs and pruning reasons must be UTF-8-encodable strings; invalid episode changes and pruning reasons are refused before their state changes.

Byte, slot and token limits are enforced together, and a policy that cannot satisfy them raises an error instead of silently changing rankings. Admission uses the original native costs, so editing returned Python cost metadata cannot change the stored totals or pretend that a removal frees more space. The [memory-manager design](#2-core-abstractions) owns the intended constraints and current limits.

### Supply token counts explicitly

Set `MemoryBudget(max_tokens=...)` and pass `cost_tokens=` to every `write()`. The caller owns the tokenizer and counting convention; Reckon does not estimate tokens from bytes or choose a tokenizer. Counts must be non-negative integers, including an explicit zero. A missing, fractional, negative, Boolean, oversized or unrepresentable count is refused before pruning. A limit itself must be a positive integer.

```python
memory = CausalMemoryManager(MemoryBudget(max_slots=3, max_tokens=10))
first = memory.write("first cue", PayloadType.CUE, cost_tokens=6)
second = memory.write("second cue", PayloadType.CUE, cost_tokens=5)
assert memory.get_record(first) is None  # FIFO frees six tokens.
assert memory.current_usage_tokens == 5
```

Without a token limit, callers may omit the count. `RecordCost.tokens` then holds `None`. The existing `to_dict()` representation omits `cost.tokens`; the typed `snapshot_json()` representation instead uses an explicit null, with counted tokens represented as decimal strings. `current_usage_tokens` is unavailable (`None`) while any retained record lacks a count; it returns zero for an empty store or an explicitly zero-cost set. Enabling a token limit with uncounted records still retained refuses the next write; remove those records or start an empty episode first. Editing their returned metadata does not supply a missing count to the store.

Carried episodes preserve counts; full resets clear them with the store. The native store tracks declared token totals alongside byte totals, validates replacements before mutation and deducts both costs on removal. Its low-level `Record` and `insert()` retain an explicit zero-token default. Native admission budgets stay with their caller. The command-line comparison runner still offers byte and slot budgets only, and the daemon has its own limits.

### Read and write rate limits

`MemoryBudget.max_read_ops_per_window` and `max_write_ops_per_window` independently limit successful calls over the last `window_size` logical steps. At step `t`, calls with `t - window_size < call_step <= t` count, including repeated calls at the same step. For example, with a three-step window, a call at step zero stops counting at step three. Counts and window size must be positive integers; `None` leaves that operation unlimited.

Each `read()` or `retrieve()` consumes one read, even when it returns no records; `retrieve()` does not count twice. Each successful `write()` consumes one write. Reaching a limit raises `RuntimeError` before serialization, pruning, read interventions, access counts or native event logging. Calls in progress reserve capacity under the manager’s lock, so concurrent or nested calls cannot overspend it. A failed call releases its reservation. This accounting does not roll back changes made by a caller’s failing intervention or policy.

With either limit enabled, steps cannot move backwards. Carried episodes keep the windows on the continuous timeline. A full episode reset starts fresh windows together with the empty store; it also accepts validated changes to the rate settings. Changing those settings otherwise raises `ValueError` on the next read or write, because a larger window cannot recover discarded history. A call in progress cannot move or reset its timeline. These are Python manager limits on reads and writes, not wall-clock throttles, token limits or daemon limits.

## Implementation

| Component | README |
| --- | --- |
| Python CMM API | [memory/README.md](../src/reckon/memory/README.md) |
| Rust RecordStore + EventLogger | [kernel/README.md](../kernel/README.md) |
| Debugger backend | [viz/README.md](../src/reckon/viz/README.md) |
| Debugger UI | [viz-ui/README.md](../viz-ui/README.md) |
