# Reproducibility

Capture what ran before saving a result. Keep the task inputs, budget, policy, seeds, source revisions and resolved environment with the outputs. A later run needs the same task implementation, dependencies and intervention. The [replay-budget comparison](https://causality.in/reckon/compare-replay-budgets/) shows a complete small run bundle.

## Principles

1. **Deterministic Seeds**: All experiments use explicit random seeds
2. **Environment Versioning**: Record the resolved Python and Rust dependencies for each build and run
3. **Configuration as Code**: `reckon run --config` reads the YAML or JSON settings in `experiments/configs/`; explicit flags override them. Unknown fields and repeated keys are refused so an unused setting cannot appear to control a run.
4. **Logging**: Keep event rows, run configuration and results together. The current event-row producers are distinguished below.

## Determinism and Schema

### Event Schema Version

The intended versioned event-log contract requires a schema version field in the header:

```json
{ "schema_version": "1.0.0", "timestamp": "..." }
```

> [!NOTE]
>
> **Current logs have no version header.** Treat current `EventLogger.to_jsonl()` output as unversioned event rows. The notebook helper `RunManager.save_logs()` writes the dictionaries it receives and adds no header. Record the producer, schema and dependencies beside those files. Implement header emission and update the consumer before claiming either producer satisfies the versioned contract.

### Environment Capture

Record the Reckon revision and any working changes, Python interpreter, Rust and Cargo toolchain, and maturin and Protobuf versions. Older runs whose source required MONAD also need its recorded revision and working changes; the current kernel has no sibling-source dependency. `requirements.txt` gives Python minimums. Capture the versions you actually installed with `pip freeze` or `uv pip freeze`. The repository ignores `kernel/Cargo.lock`, so save and hash the lockfile used for the run. Supply it to `maturin build --locked` to repeat that resolution. For an offline replay, keep the locked dependencies available locally.

### Prepare a wheel's SBOM for delivery

Maturin's Cargo SBOM can contain local source directories in component identifiers and package URLs. Before selecting a wheel for delivery, use [the wheel preparation tool](../tools/portable_wheel.py) with the exact repository root used for its build. It writes a separate wheel and preserves the input:

```bash
python tools/portable_wheel.py prepare path/to/build/reckon-0.1.0-cp39-abi3-macosx_11_0_arm64.whl \
  --source-root "$PWD" \
  --output path/to/prepared/reckon-0.1.0-cp39-abi3-macosx_11_0_arm64.whl
python tools/portable_wheel.py check path/to/prepared/reckon-0.1.0-cp39-abi3-macosx_11_0_arm64.whl
```

Use the actual built filename and create the separate output directory first. The tool requires an existing CycloneDX 1.5 SBOM; use an SBOM-enabled Maturin build rather than treating its absence as a pass. It remaps local component identifiers and all their references together, preserving the dependency graph, scopes, licence declarations and hashes. Local package URLs become repository-relative source properties, including target source paths, without implying a registry publication. Registry and Git package URLs stay intact. Sources outside the supplied root, conflicting identities, signed wheels or SBOMs, invalid member hashes and existing output files are refused. The wheel's `RECORD` is updated for the changed SBOM bytes; other member contents stay unchanged.

This checks SBOM portability only. Native libraries can separately embed compiler, dependency-cache and toolchain paths. Check the complete wheel before delivery:

```bash
python tools/portable_wheel.py check path/to/prepared/reckon-0.1.0-cp39-abi3-macosx_11_0_arm64.whl \
  --source-root "$PWD" --all-members
```

The whole-wheel check also scans the payloads for local paths and file URLs, including encoded forms. A remaining native path needs a fresh compiler-remapped build; do not patch the binary bytes. For that build, add Rust’s `--remap-path-prefix=FROM=TO` options for the repository root, Cargo dependency-cache root and Rust toolchain root, using portable destinations such as `reckon`, `cargo` and `rust-toolchain`. Keep those options local to the build process and preserve any existing compiler flags. Use a separate target directory and wheel output so the original artifact remains available. Then prepare the new wheel’s SBOM and check the complete artifact again: compiler remapping and SBOM remapping address different embedded paths.

> [!IMPORTANT]
>
> **Portability checks do not clear a release.** Neither check establishes complete dependency coverage, rights clearance, reproducibility across platforms or release acceptance. Select and hash the prepared wheel only after the applicable release checks pass.

<a id="schema-changes-definition-of-done"></a>

### After changing a protocol

Regenerate the bindings and rebuild the extension after editing `protos/reckon/**/*.proto`. Otherwise persisted data and runtime types can disagree. The [Python wire guide](../protos/README.md) owns the pinned compiler/runtime pair, Python 3.10+ requirement and request-object API. Qualify absent, explicit-default and nondefault optional values in binary and JSON, along with all five RPC methods; a successful generator command alone does not establish compatibility.

::::steps

:::step "Regenerate the bindings"

From the repository root:

```bash
python -m pip install ".[dev,proto]"
python protos/generate_python.py
python protos/generate_python.py --check
```

:::

:::step "Rebuild the Python extension"

With the supported environment from [installation](./01a-Installation.md#set-up-the-environment) active:

```bash
maturin build --interpreter "$VIRTUAL_ENV/bin/python" --out "$VIRTUAL_ENV/wheels"
python -m pip install --force-reinstall --no-deps "$VIRTUAL_ENV"/wheels/*.whl
python -c "from reckon._rust import EventLogger, RecordStore"
```

See the [kernel build guide](../kernel/README.md#python-extension) for build prerequisites.

:::

:::step "Run the Python tests"

```bash
pytest src/tests/ -v
```

Review the generated changes together with any handwritten public types and conversions affected by the schema change. Historical v1 summary metrics use `HistoricalRunMetricsV1`; its original field names and numbers remain readable, including absent versus zero values. Follow the [historical metric decoding contract](../protos/README.md#read-historical-summary-metrics) when reading an older run.

:::

::::

### Deterministic Ordering

For reproducible ordering, use:

- Single-threaded logging path, or
- Sequence numbers for async paths
- No reliance on wall-clock ordering for correctness

## Canonical Event Ordering

Events are ordered by the **canonical key**:

```
(episode_id, step, sequence)
```

In the Rust logger and its Python drain, `timestamp` is the integer passed to `set_step()`. Their logical key is `(episode_id, timestamp, sequence)`. When projecting an event for the debugger, map that integer to `step`, preserve `sequence` and convert numeric `event_id` to a string ID. The shared server projection preserves those fields, including zero and large integer IDs. The [debugger data contract](./10-Debugger-Visualization.md#a-timeline-view-per-episode) explains ordering and the distinction between logical steps and wall time.

Use `wallTimeMs` or a producer’s wall-clock `timestamp` only in the cases below. The Rust logger’s `timestamp` is a logical step. Map it to `step` when converting Rust events.

### Canonical Key Components

| Field | Type | Description |
| --- | --- | --- |
| `episode_id` | string | Groups events by episode/run |
| `step` | int64 | Primary ordering within episode (logical causal time) |
| `sequence` | int64 | Monotonic tiebreaker within (episode_id, step) |

### Ordering Rules

1. **Canonical ordering**: When `episode_id`, `step`, and `sequence` are all present, events are ordered by `(episode_id, step, sequence)` ascending.

2. **Degraded ordering**: When `episode_id` and `step` exist but `sequence` is missing:
   - `sequence` is treated as 0
   - Compare `wallTimeMs` (then fall back to `timestamp`) only when both events lack a sequence and their episode and step match. If one event has a real sequence of 0 and the other lacks one, compare IDs.
   - **Warning**: Degraded ordering is deterministic _within_ a single log file, but is **NOT stable across runs**. Wall-clock timestamps depend on scheduling and system load, so replaying the same experiment may produce different `wallTimeMs` values and thus different ordering for degraded events.

3. **Mixed ordering**: Canonical/degraded items sort before non-canonical items.

4. **Fallback ordering**: If neither event has an episode and step, compare `timestamp` first, then fall back to `wallTimeMs`.

5. **Stable tiebreaker**: `id` (or `eventId`) is used as final tiebreaker when all else is equal.

### Sequence Generation

Generate sequence numbers with these properties:

- **Deterministic**: Same run produces same sequence
- **NOT derived from time**: No wall-clock dependency
- **Monotonically increasing**: Per (episode_id, step) key
- **Thread-safe**: Centralized counter with mutex/atomic for concurrent emission

A counter orders the events that reach it. Reproducing that order across concurrent runs additionally needs a deterministic scheduling or merge rule; a mutex alone does not make different thread schedules identical.

### Implementation

| Component | Location | Responsibility |
| --- | --- | --- |
| Rust EventLogger | `kernel/src/logging.rs` | Assigns a sequence in emission order |
| TypeScript comparator | `viz-ui/packages/components/src/utils/canonicalOrder.ts` | Single source of truth for sorting |
| Python EventLogger | (uses Rust binding) | Sequence assigned in Rust layer |

In TypeScript consumers, use `sortedCanonical()` before processing events:

```typescript
import { sortedCanonical } from "@rtepl/reckon-components";

const ordered = sortedCanonical(events);
```

### Degraded Mode Detection

Use `isDegradedOrdering()` to detect when events lack sequence numbers:

```typescript
import { isDegradedOrdering, analyzeOrdering } from "@rtepl/reckon-components";

if (isDegradedOrdering(event)) {
  console.warn("Event has degraded ordering (missing sequence)");
}

const analysis = analyzeOrdering(event);
// analysis.mode: 'canonical' | 'degraded' | 'fallback'
```

## Reproducing Results

Set up the environment first (see [installation](./01a-Installation.md)), then run a task with an explicit seed and budget:

```bash
reckon run --task keydoor --episodes 10 --seed 42 --budget-slots 10 --output json
```

`reckon list` shows the four available tasks. A configured run uses the same task, policy and budget constructors as a command assembled from flags:

```bash
reckon run --config experiments/configs/task_b_bandit.yaml --policy lru --episodes 2 --output json
reckon compare --tasks keydoor tutor --policies fifo lru utility --budget-slots 2 10 --seeds 42 43 44 --episodes 3 --output json
```

`run --output json` returns one object with `configuration`, `result`, `usage` and score-source fields. The task’s former top-level metrics are now under `result`. `compare` returns rows for the full task × policy × slot-budget matrix, with every seed’s run retained in its row. Each row names its task-specific outcome, mean, sample standard deviation, minimum, maximum, mean peak bytes/slots and measured elapsed time. A single seed leaves standard deviation unavailable. Peak storage is sampled after every successful write across episode resets, independently of the bounded event log; the run also reports final storage, writes and policy-directed removals. Bandit’s own removals remain in its task result.

Repeat `compare --config` to compare configured tasks. Use `--tasks` for default task configurations. Both commands accept `--budget-bytes`, `--episodes`, `--evidence-weight`, `--reset-memory` / `--no-reset-memory`, and `--learn-utility` / `--no-learn-utility`. Runs carry memory and learn utility by default. Comparison defaults include no memory, full memory, FIFO, LRU, seeded random removal, explicit importance and utility, with slot budgets 2 and 10 and seeds 42–44; `--seeds` supplies an explicit set, while `--seed` requests one seed. Comparison’s matrix overrides each file’s policy, slot budget and seed; task environment, byte limit, episode count and carry/learning settings remain from that file unless explicitly overridden.

Supported capacity-limited policies are `fifo`, `lru`, `random`, `importance`, `utility`, `evidence_per_byte`, `diversity` and the explicitly configured `measured` arm below. Their Python wrappers call the shared kernel rankings and budget selector. `random` supplies an order using the experiment seed and its pruning-round count independently of the task RNG. `importance` ranks finite `metadata.importance` per byte, defaulting to zero when absent; it does not substitute learned utility. Diversity removes low-utility surplus round-robin across payload types, then continues below its default one-record minimum per type when required by the budget. Current Continual and Tutor records supply explicit importance, while KeyDoor and Bandit do not invent weights. Selecting `evidence_per_byte` alone does not run a probe or establish a measured-effect arm: its built-in task runs use learned or initial utility and report zero probe episodes and time. Seed spread describes these runs; it is not a confidence interval or a general performance claim.

The `none` and `full` controls run once per configured task and seed, independent of the budget sweep. `none` physically writes and immediately discards each record before returning its ID, so no later read can retrieve it. Its transient write storage is measured rather than reported as zero; baseline discards are separate from policy removals. `full` reserves a finite upper bound on every possible write for the selected built-in task and episode count, removes the byte cap and verifies that capacity caused no pruning. Task-directed removals still occur in both controls. Their rows have no swept slot/byte budget; each run includes `effective_budget` for the capacity actually used. Both override the requested capacity limits explicitly.

Carry/reset and utility-learning choices remain visible in every comparison row. Repeat configurations with different `learn_utility` settings to compare fixed initial utility against updates from `observe`; explicit importance and random retention remain separate rankings in either setting.

An experiment file accepts `task`, optional `description`, `environment`, `budget`, `retention_policy`, `evidence_weight`, `experiment` and `retention_probe`. Budget accepts `max_slots` and `max_bytes`; token and rate limits are not offered by this runner. Experiment accepts `seed`, `num_episodes`, `reset_memory` and `learn_utility`. Environment fields must belong to the selected task’s configuration; KeyDoor has its fixed grid and accepts no environment fields. Continual’s sample generator is two-dimensional, so `feature_dim` must remain 2. The shipped examples use these executable fields rather than the earlier unimplemented agent and environment settings.

Current commands, configuration and notebook recipes use `evidence_per_byte` and `evidence_weight`; there are no aliases for the former policy and weight names. Saved runs, including their copied plans and runners, keep their original vocabulary and source revision. Use that revision to reproduce an earlier run rather than passing its old configuration to the current command.

For figures and further statistical comparisons, see the [notebooks guide](../notebooks/README.md). Its demo/paper modes change sample counts and analysis; the selected backend and independence of trials still determine what the result means. Use `reckon viz` for the implemented debugger commands; the old `debug` placeholder has been removed.

### Measure retained records before pruning

The `measured` arm needs an explicit `retention_probe` section. Start with the bounded [KeyDoor example](../experiments/configs/measured_keydoor.yaml):

```bash
reckon run --config experiments/configs/measured_keydoor.yaml --output json
reckon compare --config experiments/configs/measured_keydoor.yaml --policies fifo utility measured --budget-slots 1 2 --seeds 42 43 --output json
```

At each capacity-driven pruning decision, the runner copies the current memory and probes every retained candidate. Both arms start fresh instances of the configured task with the same seed and independent copies of that memory. The intervention physically removes its target before the task runs. Trials carry their initial memory across `episodes_per_arm`, use the declared non-probing `reference_policy`, and follow the main run’s `learn_utility` choice. Later task writes and task-directed removals remain possible. This measures the value of retaining that actual record for fresh task episodes under the reference policy; it does not resume the current environment or estimate the value of a different record. A record that those future episodes never use may correctly have a zero contrast.

The probe preserves the [paired sampling procedure](./11-Evaluation-Metrics.md#evaluation-protocol). `sampling` accepts the `ProbeConfig` fields, including the test, trial limits, resampling count, effect threshold, alpha, adaptive/early-stopping choices and across-record correction. Its explicit first seed advances by `max(n_trials, max_trials)` per decision; a range containing the main task seed is refused. Shared seed choices alone establish no statistical independence. The look adjustment and configured across-record correction apply to one decision’s candidate family, not all decisions in the adaptive policy run. Use separate evaluation seeds and an adequately powered design before claiming a policy benefit.

The existing measured-effect-per-byte rule consumes each signed point estimate: harmful effects add no retention bonus, utility keeps its separate weight, and the byte denominator and tie order stay unchanged. Statistical significance is reported alongside the effect rather than used as a retention pass mark. Probe trials and their score updates leave live memory untouched; the live manager validates the chosen IDs and costs before removing records. Probe estimates remain in the batch report and are recalculated at the next decision rather than silently written into the live record’s score history.

Each `retention_probes` batch includes the input records, budget and native admission costs with their digest, actual sampling configuration, reference policy, selected IDs and per-record evidence. Every effect keeps its uncertainty, paired seeds, both outcomes, removal identity, initial-record read counts, both-arm episode cost and measured trial time. A non-finite standardized effect is represented by `effect_size_d: null` with `effect_size_d_unavailable: non_finite`; the raw signed delta remains. The native event subscription covers each complete trial from its initial memory, even if the event ring is drained or fills. Its operation counts and byte peak cover trial operations; source history and total process RAM are not inferred from them. Copies and diagnostics consume memory outside the task’s retention allowance.

> [!IMPORTANT]
>
> **Count probe time once.** `usage.elapsed_s` already includes all probing. `probe_elapsed_s` includes copying, trials, statistics and measured selection; `task_elapsed_s` is the remainder, so adding probe time to total elapsed time would count it twice. Per-record `trial_elapsed_s` covers execution of its two arms; batch `probe_wall_time_s` also includes Prober’s inference, and batch `elapsed_s` includes the surrounding copy and selection work. `task_episodes`, `probe_episodes` and `total_episodes` keep both arms and every episode per arm in the cost. Comparison rows sum these costs across their seeds. A run with no pruning performs no probes and keeps `measured_retention_effects: false`.

The small example checks execution and accounting. It is not the full policy comparison or evidence of a performance advantage. The main run’s carry/reset choice remains separate from these explicitly carried-memory probe episodes.

## Artifact Storage

- `notebooks/runs/<date>/<notebook_name>/<config_hash>/`: Default output directory for `RunManager`. A caller can override its base directory; only explicitly saved artifacts are written.
- `experiments/runs/`: Repository location for retained experiment outputs; `reckon run` does not populate it automatically.
- `assets/demo_logs/`: A local folder for curated documentation examples. Git ignores it, so a fresh clone does not contain it.

Save stdout from `reckon run --output json` if you need the configuration, task result and measured usage bundle. Use a runner that also writes the event stream when you need a debugger import. The [notebook guide](../notebooks/README.md#opening-logs-in-debugger) shows where those saved logs live. An import needs the event rows in addition to any metrics or figures.

## Hardware Requirements

Target: laptop-scale experiments (no GPU required for core benchmarks)

## Implementation

- [Tasks Module README](../src/reckon/tasks/README.md) - Task execution and configuration
- [Main Module README](../src/reckon/README.md) - CLI integration (`reckon run`)
