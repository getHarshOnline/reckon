# Debugger data and views

Choose a debugger view by what your export contains. The application has a run selector, an event inspector and three views. Each needs different inputs.

For ordinary startup and import, use [Inspect an exported run](https://causality.in/reckon/inspect-an-exported-run/). This chapter explains the data an integration supplies, how the views interpret it and which parts of the broader debugger design remain unimplemented.

<a id="1-views"></a>

## Integrate the current views

| What you want to inspect | What to supply |
| --- | --- |
| When memory operations happened | Native kernel operations or debugger-shaped events with episode, step and sequence |
| How records are related | Record snapshots and any additional edges. Supply a probe tied to the pair for a measured edge. |
| How outcome varies with cost | Measured outcome and cost points. The application’s default frontier uses an operation-count ratio. |

The server maps native Rust operations into memory events and retains the complete source operation for inspection. It preserves event identity and sequence. Raw logs do not include full record snapshots, wall-clock times, task outcomes or paired probe evidence; those inputs remain absent. Keep the original event log and task result together.

::::tabs

:::tab "Timeline"

### (A) Timeline View (per episode)

Use `(episodeId, step, sequence)` to order debugger events when all three fields are present. Convert the producer’s snake-case fields without changing their meaning. See [Reproducibility](./12-Reproducibility.md).

If both events lack `sequence`, the comparator uses episode, step, wall time and then ID. Fully sequenced events use the sequence before the ID and leave wall time out. The server preserves sequence and converts all identities to strings, including zero and integers beyond JavaScript’s exact range. Decimal ID ties compare numerically. Kernel timestamps are logical steps; the timeline labels them as steps and the inspector says wall time was not recorded. Previous/next controls make operations at a shared step individually selectable.

A debugger-shaped event stream can supply a horizontal timeline with annotations for:

- store / read / prune events
- reward occurrences
- uncertainty spikes / TD-error spikes
- mode switches (if available)

The inspector can show the following when the selected event actually supplies them:

- record payload
- cost
- retention reason
- retrieval hits
- downstream usage

The shared server projection handles write, read, prune, score-update, compress and budget-check operations. It exposes retrieved IDs, prune reasons and score changes when supplied, and keeps the original operation under `kernelEvent`. It leaves snapshots empty. Logged slot/byte fields are retained in that source record rather than promoted to a complete usage measurement: the Python logger does not supply full usage for every operation. The graph and frontier need their own recorded inputs. Unsupported root fields and malformed input cause an explicit import error with a line number.

:::

:::tab "Relationship graph"

<a id="b-causal-link-view"></a>

### (B) Relationship graph

The graph draws directed provenance links between records present in its snapshots. The projection also accepts cycles in provenance or additional edges. Read a cycle as a description of the supplied relationships. Measuring mutual influence would require evidence for the corresponding pairs.

**Edge Types**:

| Type | Source | Visual | Description |
| --- | --- | --- | --- |
| **MEASURED** | Supplied probe evidence bound to the edge ID, source and target | Solid green | A direct probe assessed the pair. Read its result in the drawer. |
| **INFERRED** | Supplied by the caller | Dashed orange | Candidate reachability under a closure assumption, pending direct evidence |
| **PROXY** | Target record's `influence_proxy`, or zero if absent | Dotted blue | Provenance link with a heuristic display weight |

**UI Controls**:

| Control | Purpose | Default |
| --- | --- | --- |
| EdgeDisplayControl | Choose measured pairs, all supplied edges or measured pairs with probe-queue details | MEASURED_ONLY (direct probe evidence only) |
| TruthModeSwitch | Change the debugger's presentation | PRODUCT |
| EdgeLegend | Explains edge visual encoding | Shown in RESEARCH and available on demand in PRODUCT |

The graph collects one record per ID from the snapshots. It combines provenance links and supplied edges before applying the mode filter. Both endpoints must be present. Measured links take their width from the magnitude of the pair's probe effect size, and proxy links use the target's influence proxy when available.

The inspector labels the selected record’s **Attribution source** as **Measurement supplied** when either delta is present, **Proxy only** when only `influenceProxy` is present, or **Unscored** when the supplied score object has none of these values. A missing score object is **Not recorded**. **Record attribution** displays supplied ablation and counterfactual deltas and **Influence (proxy)**, including zero and negative deltas. These record-level values do not establish a measured link between two records or validate the experiment that supplied them.

**Proxy-only records in snapshot** counts distinct record IDs in the selected event’s snapshot. An empty snapshot is **Not recorded**, as in a raw kernel import; a snapshot with any missing score objects reports an incomplete count and the number identified. A fully supplied inventory with no proxy-only records reports zero. This is a snapshot count, not a whole-run count or a claim that every current record was exported. See [proxy-only reporting](./11-Evaluation-Metrics.md#distinguish-proxy-only-records) for the Python store summary and the same field-presence rule.

`MEASURED_ONLY`, `PROBE_STATUS` and `PRODUCT` show only pairs with supplied direct probe evidence. A measured edge means the pair was assessed. The probe may support or weaken the proposed relationship. `RESEARCH` with `INCLUDE_UNMEASURED` also shows supplied inferences and provenance proxies. `PROBE_STATUS` additionally shows any supplied pending-probe queue and its estimated cost; selecting it does not run a probe. The legend counts the visible edges, and changing the mode closes the drawer if its edge becomes hidden.

The application’s drawer reports that probe execution is unavailable because it has no probe or inference stream. Supply handlers to the reusable drawer only if your embedding can run the probes and record their results.

:::

:::tab "Cost and outcome"

### (C) Budget vs Performance Frontier

Plot a measured outcome against a resource cost to compare two runs. The [replay-budget task](https://causality.in/reckon/compare-replay-budgets/) supplies final classification accuracy and slot allowances. Use the task result for accuracy and the operation log for write counts.

The reusable `ParetoFrontier` component accepts precomputed `points`, which bypass event extraction. Supply finite coordinates with `xMetric` and `yMetric` names on every point and matching `axes` descriptions. Supplied axes display raw numbers by default; percentage formatting is an explicit choice and scales uncertainty with the coordinates. Extra current-run and selection markers must use the same quantities. Its frontier calculation treats lower x as better and higher y as better, so orient other metrics accordingly.

The application currently passes events to the component. Its default x value is final bytes divided by a positive byte allowance. The default y value is writes divided by writes plus prunes, labelled as an operation proxy. This counts operations, not task success. The net-writes ratio is likewise labelled as a proxy. The selectors name these quantities: `byteBudgetFraction` and `writeShare`, with `netWritesPerWrite` for the alternate y ratio. Counts use `byteCount`, `tokenCount`, `slotCount` or `writeCount`. Missing inputs remain unavailable; task outcomes and probe costs require supplied measurements. Use the task result for accuracy or reward and the [component reference](../viz-ui/packages/components/README.md#paretofrontier) to supply measured points.

Budget overruns retain their size and expand the plotted range beyond 100%. Frontier membership compares equal-cost points together and preserves exact duplicate candidates. A point is dominated only if another is at least as good on both axes and strictly better on one. The plot copies inputs before marking membership and refuses non-finite supplied coordinates. Repeated-trial aggregation and uncertainty remain the caller’s responsibility.

:::

::::

## Add a view to an embedding

The graph view also mounts the compute ledger and transitivity panel below. Their store inputs start at null, and the application has no diagnostic-report or compute-accounting stream to fill them. They show unavailable messages until an integration supplies those inputs. A custom embedding can use the same components with its own measurements.

### (D) Compute Ledger (HUD)

The reusable `ComputeLedger` component displays caller-supplied compute accounting. Its compact form sits below the debugger graph. A missing ledger leaves costs unavailable; it does not establish zero probe cost. An embedding supplies:

| Metric                    | Description                             |
| ------------------------- | --------------------------------------- |
| Base episodes             | Episodes spent on task execution        |
| Probe episodes            | Episodes spent on causal evaluation     |
| Overhead ratio            | `probe / (base + probe)`                |
| Reward per total episode  | Reward accounting for all compute       |
| Pending verification cost | Estimated cost to verify inferred edges |

Total compute includes both task episodes and probe episodes.

See [Evaluation Metrics](./11-Evaluation-Metrics.md) for details.

### (E) Violations Panel

The reusable `ViolationsPanel` sits beside the debugger graph. A missing report displays an unavailable message. A supplied report with zero violations instead shows zero alongside the number of triples checked; that result applies only to the supplied report.

The panel renders the report it receives for detected A→B and B→C paths with an unconfirmed A→C edge. Its input can distinguish an untested pair from one that was measured below threshold. The [Python diagnostic](./03-Math-Core.md#influence-diagnostics-and-ordering-limits) reports both under the same detection flag, with a null value for the missing pair. Richer fields in the debugger's report type are inputs to the view:

- Edge status (tested/untested, holds/fails)
- Statistical details (p, q, effect size, n)
- Category (measured_failure, untested, borderline, power_issue)
- Suggested action (verify edge, increase n)

### (F) Representation Drift Panel (optional)

This panel remains a proposed extension; it is not a current application view. A future embedding could:

- track chosen spectral stats over time/layers
- flag collapse/drift correlated with failure
- link drift events to memory decisions

<a id="2-debugging-questions-the-ui-must-answer"></a>

## Diagnose a task failure

Trace a suspected failure from the write to the read at the decision point, then check the task outcome. The timeline and provenance graph can tell you what to test. Run a properly timed intervention to measure the record’s contribution.

The retained [key-door demonstration](../notebooks/runs/2026-11-16/keydoor_export_demo/95585cb0799e/summary.md) provides a small example. Import its run directory, select it and use **Next event** to inspect all eleven operations, starting with event ID zero. For the first blue cue, write event 4 at step 24 and read event 5 at step 26 name the same record; event 6 at step 29 changes its utility from 0 to 0.1. Event 7 removes it at step 33. **Source operation** exposes each complete original log entry. The two operations at step 24 and the two at step 33 remain separately selectable in sequence order.

The imported result shows **3 episodes | 67% success**. The inspector reports wall time and snapshot attribution as **Not recorded** because the export supplies logical steps and no record snapshots. The two successful episodes establish this run’s outcome; the write/read sequence alone does not establish the cue’s causal contribution or rank retention policies.

Representation drift needs separately measured representation data. The proposed drift panel does not yet provide that diagnosis.

## 3. Output Artifacts

Callers preserve the task configuration, result and event log together. The [replay comparison](https://causality.in/reckon/compare-replay-budgets/) shows one complete layout. A notebook may separately save figures or a summary. The debugger application does not automatically export an HTML report or paper screenshots; the presence of those outputs is a property of the particular producer, not the import operation.

## Implementation

| Component | README |
| --- | --- |
| FastAPI server | [viz/README.md](../src/reckon/viz/README.md) |
| React debugger | [viz-ui/README.md](../viz-ui/README.md) |
| Timeline component | [viz-ui/packages/components/](../viz-ui/packages/components/README.md) |
| Causal graph component | [viz-ui/packages/components/](../viz-ui/packages/components/README.md) |
| Event data source | [memory/README.md](../src/reckon/memory/README.md): EventLogger |
