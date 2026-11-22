# Tasks and benchmarks

<a id="tasks-and-benchmarks-right-problems"></a>

Choose a task by the behavior you want to measure. The experiments ask when selective retention beats having no memory and whether a limited store can do useful work without an unlimited allowance. Compare runs to check those aims. Each `run()` builds its own `TaskResult`, so read the producer and denominator before comparing a shared field name. See [evaluation metrics](./11-Evaluation-Metrics.md) for the difference between usage counts, oracle labels and intervention results.

All four runners use `retrieve()` inside an `EpisodeContext` and report an outcome through `observe()`. By default they retain records, learned scores and buffered events across episodes; `reset_memory=True` starts each episode empty. `learn_utility=False` disables outcome updates for fixed-score comparisons. Both settings are recorded in `raw_data`. The [task guide](../src/reckon/tasks/README.md#outcome-credit) states each outcome and distinguishes labelled importance from learned utility.

Current task results keep outcome fields in `performance`, shared memory activity in `memory`, and named task summaries in `diagnostics`. These diagnostics describe counters and outcomes; none executes a record intervention. Earlier saved runs retain their original keys and source revision.

## Task A: Key–Door Delayed Credit Gridworld

- The current grid uses a colored key as an early cue for the policy's later door choice.
- Reward is sparse and delayed.
- Agent has an explicit "store cue" operation with a budget.

The door row is a wall except at its two doors. Red opens the left door and blue the right; green opens a seeded random door that its color does not identify. The supplied controller reads the current episode's key once before approaching the door, chooses right for a retrieved blue cue, and otherwise chooses left. It does not explore a second door after a failed guess. Without retrieval it therefore succeeds on left-door episodes; with retrieval it also solves blue episodes. Green remains partly unpredictable for this controller. This distinguishes cue use under a declared controller from a claim that no other controller could solve the grid without memory.

> [!NOTE]
>
> **This workload controls the memory path.** Only one cue is written per episode and it is used before the next write. A store with one slot can therefore hold everything this controller needs. Across-episode pruning of old cues does not itself make this task distinguish retention rankings; use it as a memory-path control unless a separate workload introduces competing records before the decision.

Metrics:

- `success_rate` and `mean_return`: successful episodes divided by episodes, with binary reward.
- `successful_stored_key_episode_fraction`: episodes with a stored key that was retrieved and followed by success, divided by episodes with a stored key; zero when no key was stored. This is a task-specific usage/outcome association, not a necessity test.
- `successful_key_episodes_per_write`: useful writes divided by writes, or zero with no writes; `key_retrievals_per_query`: successful cue queries divided by query attempts, or zero with no attempts. Empty queries count in `raw_data.total_reads` and each episode's `reads`.

Producer: [`KeyDoorTask.run()`](../src/reckon/tasks/task_a_keydoor.py). A memory-budget comparison must also account for the agent policy and the grid's allowed paths; this metric does not establish that a stored cue was indispensable.

## Task B: Hidden-Mode Contextual Bandit (Nonstationary)

- Environment switches hidden modes.
- Only occasional observations reveal mode.
- The memory challenge is to retain useful mode indicators under budget.

Metrics:

- `mean_regret`: accumulated optimal expected reward minus sampled reward, divided by total steps; `mean_return`: reward divided by episodes.
- `raw_data.mean_detection_lag`: mean recorded delay after a tracked mode switch, falling back to the configured switch interval when no lag is recorded.
- `first_mode_detections_per_successful_read`: counted first detections divided by successful reads. Its `first_mode_detections_per_write` uses those detections divided by writes. Both use zero for an empty denominator. These are different usage ratios. `memory.reads_per_write` is successful reads divided by `max(writes, 1)`.

Producer: [`BanditTask.run()`](../src/reckon/tasks/task_b_bandit.py). The runner retrieves the retained indicator before each arm choice, then reports the reward through `observe()`. It explicitly prunes indicators at tracked switches and when replacing them with newer ones; `raw_data.episodes[].task_prunes` reports these task-directed removals. Include that schedule when comparing memory policies. A seed now spawns separate environment and arm-choice streams. The environment’s reward table, mode sequence, indicator arrivals and reward noise remain paired when missing memory changes exploration frequency; chosen arms and their rewards can differ.

## Task C: Continual Classification with Replay Budget

- Sequence of tasks or drifting distributions.
- Replay buffer budget is the constrained memory.
- The task writes misclassified examples; the selected CMM retention policy determines which remain under budget.

Metrics:

- `mean_accuracy`: final accuracy averaged over subtasks, then episodes.
- `forgetting`: the mean positive drop from each earlier subtask's immediately post-training accuracy to its final accuracy, averaged over episodes.
- `mean_episode_accuracy_per_write`: the mean across episodes of final episode accuracy divided by `max(episode writes, 1)`; it does not use current occupied slots.
- `reads_per_write`: reads divided by `max(writes, 1)`; `one_minus_mean_forgetting`: one minus mean forgetting. Neither is a record-ablation result.

Producer: [`ContinualTask.run()`](../src/reckon/tasks/task_c_continual.py). Report the accuracy matrix and write/read counts alongside these quantities. The [product walkthrough](https://causality.in/reckon/compare-replay-budgets/) runs paired comparisons at two slot allowances.

The current runner generates training and test data from a stream separate from replay choices, with one replay opportunity per training position. A retained sample is eligible from the start of the episode, even before a new sample is written. This keeps data and replay opportunities paired when policy outcomes differ and lets a fresh-task probe consult carried records. Earlier runs shared the data and conditional-replay stream and delayed replay until the first new write; their numbers retain that source meaning. A new comparison must identify the repaired source rather than present old outcomes as matched-input evidence.

## Task D: Small "Tutor Loop" Simulation

- Multi-session student interaction.
- Later questions depend on specific past misconceptions/hints.
- The agent stores associations between concepts and effective hints for later retrieval.

Metrics:

- `success_rate` and `mean_return`: mean fraction of initial misconceptions cleared; an episode with none initially uses one.
- `mean_episode_effective_hint_read_fraction`: mean episode ratio of successful previously effective hint reads to successful reads, using zero when there are no reads.
- `pooled_effective_hint_read_fraction`: successful previously effective hint reads divided by `max(total reads, 1)` across episodes. `mean_misconception_clearance` carries the mean improvement fraction, not necessary-record recall. `memory.reads_per_write` is successful reads divided by `max(writes, 1)`.

Producer: [`TutorTask.run()`](../src/reckon/tasks/task_d_tutor.py). These are simulated hint-use and improvement quantities; interpreting them as causal effects requires a separate intervention comparison. Each episode seed spawns independent streams for the starting student, responses, concept choices and hint choices. Response seeds are assigned by question index before execution. Comparisons therefore share starting students and response randomness at a given question while allowing learned state, concept selection and hint success to differ.

Baselines:

- no memory
- full memory reference, with its resource cost reported
- FIFO/LRU
- random retention
- importance-only retention (no causal probes)

Arrange these comparison arms yourself. Each `BaseTask.run()` executes the task with the manager you pass. Record each runner, stored and task-local state, budget, policy, seeds and cost. Use the full-memory arm as a reference at its measured cost, and check its performance against the other arms.

## KeyDoor and Bandit serve as memory-path controls

The fixed control diagnostic (`notebooks/runs/2026-11-16/workload_controls/8eac11d1cbb9/summary.md`) uses the repaired source recorded in its `env_meta.json`, fresh seeds 30,000–30,015 and the pilot's unchanged workloads. All retained-memory arms match full memory in every seed at one and two slots. KeyDoor averages 0.750000 success with memory versus 0.395833 without; Bandit averages 159.510847 return per episode with memory versus 136.576672 without. These are descriptive results under the supplied controllers, not a powered equivalence finding.

All 2,740 fresh-task probe pairs have equal outcomes and no reads of their initial retained records. The live controller uses its new cue, while a fresh probe starts without that controller's cue ID. Measurement adds 5,480 episodes without an observed policy gain. Bandit's task-directed replacements and capacity-driven removals are counted separately in the result. Keep these tasks as memory-path controls: changing retention rankings cannot test their value when no competing useful record must survive until a later read. A live continuation experiment would answer a different question from these fresh-task probes.

## The first measured-retention pilot exposes workload limits

The 15 November 2026 pilot (`notebooks/runs/2026-11-15/measured_retention_pilot/6b59fa73f40b/summary.md`) ran the source recorded in its `env_meta.json`, before the KeyDoor wall repair. Its 64 rows contain 320 seed runs, 960 task episodes and 4,504 probe episodes. Each row uses seeds 100–104 and three main episodes per seed, with one or two slots for limited policies. The controls and seven retention policies, complete task settings, raw paired trials and source hashes are retained with the run. Probes use four fixed pairs per record, one fresh episode per arm, FIFO as reference and Bonferroni correction within each pruning decision. This is an exploratory pilot; its sample size was not chosen to detect a declared smallest useful effect.

| Task and outcome | No memory | Full memory | Utility, one / two slots | Measured, one / two slots |
| --- | --- | --- | --- | --- |
| KeyDoor success fraction, before wall repair | 1.0000 | 0.9333 | 0.9333 / 0.9333 | 0.9333 / 0.9333 |
| Bandit return per episode | 131.5000 | 159.5028 | 159.5028 / 159.5028 | 159.5028 / 159.5028 |
| Continual final mean accuracy | 0.8878 | 0.8733 | 0.8533 / 0.8433 | 0.8533 / 0.8433 |
| Tutor improvement fraction | 1.0000 | 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 |

These are means across five seeds, with seed-level results and spread in the raw rows. Measured and utility outcomes match within every seed in these conditions. That observation supplies no evidence of equivalence or general policy benefit. Continual at two slots does distinguish some other policies, but no memory has the highest mean in this small sample. Bandit reports different outcomes with and without memory while its task-directed replacement schedule leaves these retention arms indistinguishable. That source also shared environment and action randomness: equal seeds did not guarantee equal mode, indicator or reward-noise sequences when exploration differed. The current runner separates those streams; the earlier numerical difference is not a matched-environment estimate. Tutor saturates. KeyDoor's no-memory advantage came from an unintended path through the gaps between doors; the current environment blocks that path. Repeating the saved configuration against current code therefore answers a different question from reproducing the original source revision.

The measured arm pays 80 / 80 extra episodes on KeyDoor, 1,616 / 16 on Bandit, 632 / 1,200 on Continual and 320 / 560 on Tutor at one / two slots, each against 15 main episodes. Probe-policy time occupies about 69–99% of the measured runs' inclusive elapsed time on this machine. Positive and negative record estimates in the two-slot Continual runs still lead to the same final outcomes as utility here. A powered comparison needs a declared effect size, suitable workloads and disjoint comparison seeds; it cannot turn these exploratory choices into a confirmatory result after seeing the outcomes.

### Continual with paired inputs and reachable carried records

The paired Continual calibration (`notebooks/runs/2026-11-16/continual_paired_calibration/53df3560dc14/summary.md`) retains the original workload on the repaired source recorded in its `env_meta.json` and fresh seeds 40,000–40,015. At two slots, measured retention averages 0.839236 accuracy versus utility's 0.832986, with positive, negative and zero seed-level differences. No memory averages 0.879167 and full capacity 0.862153, both higher than measured retention. All one-slot policies match because admission must remove the sole retained record. Probes now read carried records and produce nonzero contrasts, while adding 4,776 episodes across the measured arms. This calibration establishes a working comparison and its cost; it does not establish policy benefit or replace the separate confirmation.

### Confirm the Continual comparison

The completed Continual confirmation (`notebooks/runs/2026-11-16/continual_confirmation/7e2728490cc1/summary.md`) follows its [fixed protocol](experiments/continual-confirmation.md), with 64 fresh seeds, 3,072 main episodes and 360,320 probe episodes. At two slots, measured retention averages 0.855556 accuracy versus utility's 0.831076 and no memory's 0.871354. The measured-minus-utility difference is 0.024479, with a 97.5% interval [0.017395, 0.031563] and adjusted p-value 9.2914e-11. Measured minus no memory is -0.015799, with interval [-0.021927, -0.009670] and adjusted p-value 2.9048e-7. Both comparisons exclude zero under the declared correction, but in opposite directions; the gain over utility is below the five-percentage-point planning target. That target is not an adoption threshold.

At two slots, the measured arm adds 246,528 probe episodes and takes 618.281687 inclusive seconds versus utility's 0.439060, approximately 1,408 times as long on this machine. The one-slot arm pays for measurement without a ranking choice. The result establishes working paired inputs, reachable carried records and costed intervention comparisons; it does not establish a practical retention advantage over no memory or close the remaining notebook and product work. Preserve the adverse conclusion alongside the gain over utility instead of tuning the workload for a winner.

### A Tutor condition below the ceiling

The Tutor calibration (`notebooks/runs/2026-11-15/tutor_retention_calibration/24a235e37516/summary.md`), also on 15 November, changes one declared workload: six concepts, one session of six questions, all concepts initially misunderstood, base hint success 0.3 and the existing remembered-hint boost of 0.2. It carries memory across five episodes per seed, uses two and four slots and retains exploratory seeds 100–104 and four probe pairs. The relevant task and kernel source is the source recorded in its `env_meta.json`. Its 16 rows contain 400 main episodes and 1,744 probe episodes.

This condition avoids saturation: no memory averages 0.2733 improvement and full memory 0.3867. At two / four slots, utility averages 0.3267 / 0.3733 and measured retention 0.3667 / 0.3467. The measured arm is higher at two slots and lower at four in this sample, paying 720 / 1,024 probe episodes against 25 main episodes per row. This single calibration supplies a workable varying outcome, not a powered comparison or a reason to discard the adverse result. Its original configurations and same-seed outcomes stay with the run. That source shared student, response and action randomness, so different hint use could shift later draws. The current runner pairs starting students by episode and responses by question, independently of concept and hint selection. The saved calibration remains exploratory evidence under its original source, not a comparison rerun under that repair.

### Repeat the declared condition with matched inputs

The paired-input calibration (`notebooks/runs/2026-11-15/tutor_paired_calibration/d1946209a918/summary.md`) uses the repaired source recorded in its `env_meta.json` with the same workload, policies, two/four-slot budgets, probe settings and exploratory seeds 100–104. Its 16 rows contain 400 main episodes and 2,144 probe episodes. The run retains the complete comparison, source hashes, kernel lockfile, extension hash and runner.

No memory averages 0.3600 improvement and full memory 0.4467. Utility averages 0.3867 / 0.4333 at two / four slots; measured retention averages 0.3867 / 0.4200. The equal two-slot means hide one positive and one negative seed-level difference, each 0.0333. At four slots, one seed is 0.0667 worse and the other four match. The measured arm pays 768 / 1,376 probe episodes against 25 main episodes per row. This repeat preserves the adverse result and the cost; its reused exploratory seeds and small sample do not establish benefit, equivalence or a powered comparison.

### Confirm the declared Tutor comparison

The completed confirmation (`notebooks/runs/2026-11-15/tutor_confirmation/eef872b88357/summary.md`) follows the [predeclared protocol](experiments/tutor-confirmation.md) under the source recorded in its `env_meta.json`, with all 256 fresh seeds, 20,480 main episodes and 5,790,720 probe episodes. Measured minus learned utility is 0.003385 at two slots and 0.007552 at four: gains of 0.339 and 0.755 percentage points. The respective 97.5% intervals are [0.000366, 0.006405] and [0.004213, 0.010891], with Bonferroni-adjusted p-values 0.02415 and 0.000001330. Both contrasts reject zero under the declared t test, and both intervals lie wholly below the analyst-selected 0.05 planning target. That target is not an adoption threshold.

Each measured row contains 1,280 main episodes. At two / four slots, measurement adds 2,096,128 / 3,694,592 probe episodes and 2,086.37 / 4,252.78 probe seconds; inclusive elapsed time is 2,087.33 / 4,253.78 seconds, compared with 0.77 / 0.85 seconds for utility on this machine. The saved summary includes all 16 policy means, seed spreads, costs, sampled store peaks and the exact input identities. This is a small positive result for this implemented policy and Tutor condition, with a large measurement cost. It does not establish equivalence, general policy benefit, the broader hypothesis or promotion readiness. The remaining tasks and notebook policy comparisons still need their own results.

## Implementation

- [Tasks Module README](../src/reckon/tasks/README.md): `BaseTask` interface and task implementations (A–D)
- [Metrics Module README](../src/reckon/metrics/README.md): Performance, memory efficiency, and causal quality metrics
