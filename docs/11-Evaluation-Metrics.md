# Evaluation Metrics

Decide whether you are comparing policies, reporting memory activity or testing a record’s contribution. A policy comparison needs the task outcome and memory cost. For a record-removal test, also verify that the intervention ran during the task. Keep the producer and denominator with every metric because task counters, current-record summaries and intervention results answer different questions.

To run a complete comparison, follow [Compare two replay budgets](https://causality.in/reckon/compare-replay-budgets/). That task records classification accuracy and memory cost; it does not measure a record’s causal contribution.

## Task outcomes and diagnostics {#performance}

Read the task runner before interpreting its metrics. Each built-in task constructs its own values. The helper formulas in the next sections apply only when your code calls those helpers.

| Producer | Task outcome | Memory and contribution fields |
| --- | --- | --- |
| [`KeyDoorTask.run`](../src/reckon/tasks/task_a_keydoor.py) | Successful episodes divided by episodes; `mean_return` uses the same binary reward. | `successful_key_episodes_per_write` is useful writes divided by writes. `successful_stored_key_episode_fraction` is stored-key episodes with retrieval and success divided by stored-key episodes. Both use zero with an empty denominator. |
| [`BanditTask.run`](../src/reckon/tasks/task_b_bandit.py) | `mean_regret` is accumulated regret divided by steps; `mean_return` is reward divided by episodes. | `first_mode_detections_per_successful_read` is counted first detections divided by successful reads. `first_mode_detections_per_write` uses those detections divided by writes. Both use zero with an empty denominator. |
| [`ContinualTask.run`](../src/reckon/tasks/task_c_continual.py) | Final accuracy averaged over subtasks and episodes; forgetting averages positive diagonal-to-final drops for earlier subtasks. | `reads_per_write` is reads divided by `max(writes, 1)`. `mean_episode_accuracy_per_write` averages episode accuracy divided by `max(episode writes, 1)`. `one_minus_mean_forgetting` is one minus mean forgetting. |
| [`TutorTask.run`](../src/reckon/tasks/task_d_tutor.py) | Mean fraction of initial misconceptions cleared; an episode with none initially uses one. | `mean_episode_effective_hint_read_fraction` averages each episode's successful effective-hint reads divided by successful reads, using zero with no reads. `pooled_effective_hint_read_fraction` uses those useful reads divided by `max(total reads, 1)` across episodes; `mean_misconception_clearance` is the mean improvement fraction. |

Task-specific fields above live in `diagnostics`; Bandit, Continual and Tutor also report `memory.reads_per_write` as successful reads divided by `max(writes, 1)`. Key-Door instead reports `diagnostics.key_retrievals_per_query`: successful cue queries divided by all query attempts, including empty queries. These usage ratios and improvement measures are not record-ablation results. [Tasks and benchmarks](./09-Tasks-Benchmarks.md) explains the schedules and exact definitions. Saved runs from earlier revisions retain their original `causal` and memory keys; interpret those through their captured source, never as aliases for new results.

## Memory activity and cost {#memory-efficiency}

> [!CAUTION]
>
> **This helper drains the event buffer.** [`MemoryEfficiencyMetrics.from_cmm`](../src/reckon/metrics/memory.py) combines retained events, current memory and caller-supplied totals. It drains `get_event_log()`: preserve required run artifacts before calling it, and report how much of the run the buffer covers.

| Field | Calculation and scope |
| --- | --- |
| `reads_per_write` | Read count divided by write count. This can exceed one and does not measure relevance. |
| `useful_reads_per_read` | Caller-supplied useful reads divided by read count; an operation ratio, not a fraction of distinct records. |
| `peak_usage_bytes` | Largest `bytes_after` write sample, or current stored bytes when no write samples remain. |
| `average_usage_bytes` | Mean of those write samples, unavailable without samples; not a time-weighted average. |
| `total_reward_per_byte`, `total_reward_per_slot` | Supplied total reward divided by sampled peak/current bytes or current occupied slots respectively. |
| `mean_return_per_byte`, `mean_return_per_slot` | The same denominators with supplied mean return, only when total reward is absent. |

Read and write counts come from the [native logger](../kernel/src/logging.rs)'s `op_type` events, with task-supplied counts used when no events of that kind remain. A read event represents one retrieval call. The byte and slot denominators have different scopes; neither is automatically a whole-run peak. A supplied total reward of zero takes priority over mean return. Missing reward inputs or nonpositive denominators leave the affected ratios unavailable, omitted by `to_dict()`.

## Record usage and stored scores {#causal-quality-approximate}

[`RecordSummaryMetrics.from_cmm`](../src/reckon/metrics/record_summary.py) examines current records, caller-owned labels and already-stored deltas. It neither runs nor validates an intervention.

| Field | Calculation |
| --- | --- |
| `used_record_fraction` | Currently stored records with positive `use_count`, divided by stored records. No ground-truth labels are needed. |
| `necessary_cue_retention` | Retained necessary-cue IDs divided by positive `total_cues`, whose default is the number of supplied necessary IDs. |
| `useful_retrieval_fraction` | Supplied useful retrievals divided by retrievals, selected only when the necessary-cue denominator is nonpositive. |
| `max_abs_stored_ablation_delta` | Largest absolute finite stored `ablation_delta`. |
| `mean_stored_ablation_delta` | Signed mean of finite stored `ablation_delta` values. |

Missing positive denominators or finite scores leave the affected field unavailable. A retrieval fraction cannot stand in for cue retention, and a stored delta needs its original experiment before it can support a claim about contribution.

### Distinguish proxy-only records

Reports must flag a record as proxy-only when `influence_proxy` is present and both `ablation_delta` and `counterfactual_delta` are absent. A stored zero or negative delta is still present; a record with all three fields absent has no supplied attribution score. Preserve those distinctions when reporting record counts or interpreting a retention decision. Field presence describes the supplied score, while the original experiment establishes whether it is a valid measurement.

`CausalScore.is_proxy_only` computes the flag from those supplied fields. `RecordSummaryMetrics.from_cmm()` reports sorted `proxy_only_record_ids` and `proxy_only_record_count` for the current store without draining its event log. An examined empty store reports an empty list and zero; a summary constructed without an inventory leaves both unavailable. The flag is computed, so record serialization keeps the original score fields and their missing values without adding a wire field.

The [debugger inspector](./10-Debugger-Visualization.md#b-relationship-graph) labels each selected record’s supplied attribution source and counts proxy-only records in the selected event’s snapshot. Missing snapshots or score objects remain explicitly unavailable or incomplete. The experiment runner’s `retention_score_source` describes a whole run, and the graph’s measured, inferred and proxy edge labels describe relationships; neither replaces this record-by-record inventory. None of these reporting fields changes retention or validates a measurement.

## What a contribution measurement should establish {#causal-record-contract-v0}

The proposed record-contribution protocol asks whether removing a record or replacing it with random or null content, under the same budget and policy, causes a statistically significant performance drop at least as large as a declared threshold. Define the outcome, intervention, trial seeds and minimum useful difference before running it. The targets are:

| Target | Meaning |
| --- | --- |
| Causal precision | Fraction of stored records meeting that positive-usefulness test. |
| Causal recall | Fraction of ground-truth necessary records retained. |
| Counterfactual sensitivity | Outcome difference under the specified replacement or removal. |
| Useful memory rate | Fraction of stored items retrieved and shown to affect a decision. Access counts alone do not establish that effect. |

Only measured `ablation_delta` or `counterfactual_delta` values can supply intervention evidence; report `influence_proxy` separately. An identified causal effect also needs a declared estimand, identification assumptions, negative controls, repeated runs and an uncertainty interval. A metric name, the `ABLATION` credit policy, matched seeds or a p-value cannot supply those conditions.

The working evaluator below implements one removal test. Its aggregate denominators differ from these proposed whole-store targets, and replacement remains unsupported.

### Evaluation Protocol

`CausalRecordEvaluator` in [`src/reckon/metrics/evaluator.py`](../src/reckon/metrics/evaluator.py) runs paired task invocations with one actual record removal. Its defaults are 10 trials, an absolute delta threshold of 0.05 in the outcome’s units and alpha 0.05; the delta is not divided by the baseline. Trial independence still depends on the experiment. The procedure is:

1. **Setup**: Fix the task configuration, policy, budget, seed set and episodes per arm. Factories must return fresh instances. The evaluator snapshots declared task configuration, every budget field and policy configuration, then checks each arm against that snapshot. Tasks must derive their randomness from the supplied seed.
2. **Select the record**: An exact ID is accepted when it exists in both runs. For task-created records with fresh UUIDs, pass `record_selector` and use `record_id` as a stable report label. At the first read whose candidates match, the selector must identify exactly one record; multiple matches or a target that never reaches a read fail the evaluation.
3. **Apply the intervention**: The baseline retains the candidate. The other arm calls `prune` before access, logging or credit assignment, checks its success and verifies that the record is absent. The read then resolves again, so a ranked query can return its next candidate. An explicit-ID read returns no match for the removed ID.
4. **Verify the pair**: Both arms must reach the same read ordinal with matching selected payload, creation step, episode, cost, tags, source operation, utility, measured scores and metadata. Their digest excludes generated UUIDs and provenance input IDs; the selector supplies logical identity. A mismatch raises instead of returning a result. The report retains seeds, episodes per arm, both actual IDs, the shared target digest, removal status and both outcomes.
5. **Measure the difference**: Delta is baseline mean minus intervention mean, using a finite outcome where higher is better. A paired two-sided permutation test enumerates sign patterns up to 10,000; larger sets use 10,000 seeded draws. `is_significant` requires both the configured absolute effect threshold and p < alpha. `is_useful` additionally requires a strictly positive delta at or above the threshold.

Only `ABLATE` executes. `MASK` and `REPLACE` raise before task execution; their enum values do not imply support. The intervention removes one record instance at its first eligible read. A later replacement record is allowed, so this does not measure permanent suppression of the same fact. All four built-in tasks support this read-boundary intervention. Tutor reuses successful hints across episodes, so its comparison needs at least two episodes per arm; a one-episode run with no eligible record fails explicitly.

For example, evaluate a task-created key without pretending its UUID survives a fresh run:

```python
from reckon.core.resources import MemoryBudget
from reckon.memory.manager import CausalMemoryManager
from reckon.metrics import CausalRecordEvaluator
from reckon.tasks import KeyDoorTask

evaluator = CausalRecordEvaluator(
    KeyDoorTask,
    lambda: CausalMemoryManager(MemoryBudget(max_slots=16)),
    lambda result: result.performance.success_rate,
    n_trials=10,
)
result = evaluator.evaluate_record(
    "first key", record_selector=lambda record: "key" in record.tags
)
```

The report preserves per-record deltas, trial counts and permutation p-values. It does not compute per-record confidence intervals. `contract_precision` is the fraction of distinct evaluated target labels with `is_useful=True`, using zero when none are evaluated. With non-empty ground-truth labels, `contract_recall` is the useful overlap divided by that set’s size; absent or empty ground truth leaves recall unavailable. Harmful and zero effects remain in the signed results but enter neither numerator. These descriptive aggregates use unadjusted per-record tests and establish neither family-wise error nor false-discovery control.

### Supply your own paired runner

The separate [`Prober`](../src/reckon/metrics/probe.py) calls `run_fn(ablated_ids, seed)` twice per trial: `([], seed)` for the baseline and `([record_id], seed)` for removal. Each arm must start from the same task state; the caller owns removing the requested record after setup and before its use. Both arms must execute; precomputed unmatched baselines are refused. Replacement and shuffle requests raise before the runner is called. `probe_episodes` counts both arms, `probe_wall_time_s` measures the entire probe including statistics, and the returned configuration includes the actual first seed when one was generated.

Tests and intervals use the paired differences. The permutation test swaps labels within pairs ([paired permutation design](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html)); it enumerates all sign patterns when they fit the configured resample count and otherwise samples them. The t-test is a one-sample test of differences against zero, equivalent to the [paired t-test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_rel.html). Bootstrap resamples differences and centers its null draws at zero. Intervals are normal approximations for permutation, Student-t for t-tests and percentile bootstrap for bootstrap. Their assumptions and finite-sample limits still apply; a matched seed alone does not identify causation.

Fixed sampling uses `n_trials` pairs. Adaptive sampling applies only when both `adaptive_sampling` and `early_stopping` are true; otherwise the run uses `n_trials`. Adaptive sampling checks at `min_trials`, successive doublings, `n_trials` clipped to the allowed range, and `max_trials`. It stops for a significant difference or an interval wholly within `±delta_threshold`; otherwise it reaches the maximum. Before the across-record correction, p-values are multiplied by the number of scheduled looks and intervals use `alpha / looks`. This Bonferroni adjustment covers the planned repeated looks subject to each test’s assumptions; the approximate intervals are not exact confidence sequences. `Evidence.p_value` is therefore the look-adjusted value, while `p_value_adjusted` additionally applies the configured correction across records. Benjamini–Hochberg assumes independence or the appropriate positive dependence across tests; shared seeds do not establish that assumption. Choose Bonferroni when arbitrary dependence must be covered. Both significance flags are two-sided; usefulness still requires the signed outcome comparison. The [debugger graph](./10-Debugger-Visualization.md#b-relationship-graph) displays supplied evidence and does not execute these probes.

## Measure outcomes; do not optimise against a judge

Use the task outcome to test whether a record helped. A model's opinion that a record looks useful can be a labelled input, but should not replace the measured outcome. Validate a changed policy on held-out evidence before using it.

## Diagnostic goals

Time to diagnose a failure is a qualitative measure in early versions. A later diagnostic comparison should also count which failures it can detect automatically: a missing cue, wrong retrieval, budget waste or drift. These are evaluation goals, not fields computed by the helpers above.

## Probe Cost Accounting

Report task and probe episodes together, with their full elapsed time. [`ProbeCostTracker`](../src/reckon/metrics/probe_costs.py) measures the bracketed probe time; the caller supplies base costs and records calls, episode counts, environment steps and evaluated records. A tracking label does not execute an intervention or establish its benefit.

### Probe Cost Metrics

| Metric | Description | Unit |
| --- | --- | --- |
| `probe_episodes_total` | Total episodes used for probing | count |
| `probe_wall_time_total_ms` | Total wall time for all probes | milliseconds |
| `probe_calls_total` | Total `task.run` invocations for probing | count |
| `probe_env_steps_total` | Total environment steps for probing | count |
| `probe_records_evaluated` | Number of records evaluated | count |
| `probe_episodes_per_record` | Average episodes per record | episodes/record |
| `probe_wall_time_per_record_ms` | Average wall time per record | ms/record |
| `probe_overhead_ratio` | `probe_time / (base_time + probe_time)` | ratio (0-1) |

`ProbeCostSummary` aggregates these measurements. Per-record averages use zero when no records were evaluated; the overhead ratio uses zero when total elapsed time is zero.

### Efficiency Metrics

`EfficiencyMetrics.compute` combines supplied reward, utility improvement and the recorded costs. Missing positive denominators produce zero. These ratios help compare costs; the caller still has to measure any claimed improvement.

| Metric | Formula | Interpretation |
| --- | --- | --- |
| `reward_per_total_episode` | `reward / (base_episodes + probe_episodes)` | Performance accounting for all compute |
| `reward_per_total_wall_time` | `reward / (base_time_ms + probe_time_ms)` | Reward per millisecond, including probe overhead |
| `utility_gain_per_probe_episode` | `utility_improvement / probe_episodes` | Return on probing investment |

### Usage Example

Use this Key-Door example to check how the tracker reports invocations and their binary rewards. It runs two task invocations for accounting. To measure a contribution or utility improvement, supply a runner, intervention and comparison under the protocol above.

```python
from time import perf_counter

from reckon import CausalMemoryManager, MemoryBudget
from reckon.metrics import ProbeCostTracker, EfficiencyMetrics
from reckon.tasks.task_a_keydoor import KeyDoorTask

task = KeyDoorTask()
tracker = ProbeCostTracker()
base_episodes = 100
started = perf_counter()
baseline = task.run(
    CausalMemoryManager(MemoryBudget(max_slots=100, max_bytes=50_000)),
    num_episodes=base_episodes,
    seed=41,
)
tracker.set_base_costs(
    episodes=base_episodes,
    wall_time_ms=(perf_counter() - started) * 1000,
)

# Account for a second task run; no record-removal runner is invoked here.
with tracker.track_probe(probe_type="accounting-demo", seed=42):
    tracker.record_call(episodes=10)
    result = task.run(
        CausalMemoryManager(MemoryBudget(max_slots=100, max_bytes=50_000)),
        num_episodes=10,
        seed=42,
    )

summary = tracker.summarize()
print(f"Probe overhead: {summary.probe_overhead_ratio:.1%}")

# Key-Door awards one for a successful episode and zero otherwise.
total_reward = sum(
    episode["success"]
    for run in (baseline, result)
    for episode in run.raw_data["episodes"]
)
efficiency = EfficiencyMetrics.compute(
    total_reward=total_reward,
    probe_costs=summary,
)
print(f"Reward per total episode: {efficiency.reward_per_total_episode:.3f}")
```

### Proto Schema

Probe costs are defined in [`protos/reckon/events.proto`](../protos/reckon/events.proto):

- `ProbeCostEvent`: Per-probe operation costs
- `ProbeCostSummary`: Aggregated probe metrics

## Choose what a frontier compares

A frontier compares declared costs and outcomes. Choose the outcome explicitly and keep its producer, units and direction with the comparison. The [dictionary and notebook helpers](../src/reckon/metrics/README.md#selecting-a-frontier-outcome) retain the axis names and reject missing or nonfinite measurements. An observed zero stays zero; an absent accuracy value cannot become success rate or a measured zero. This prevents an incomplete row from appearing artificially cheap or successful.

The notebook efficiency helper also requires a named outcome. Its overhead-weighted value is that outcome multiplied by one minus the fraction of episodes spent probing. That arithmetic does not establish a causal effect or decide whether the measurement cost is worthwhile.

For helper inputs, serialization and integration with tasks, use the [metrics reference](../src/reckon/metrics/README.md). The future service that returns signed evaluation artifacts has a separate [planned contract](evaluation-contract.md).
