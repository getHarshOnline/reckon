# Continual confirmation: a gain over utility, a loss against no memory

The [fixed protocol](protocol.md) completed all 64 declared seeds 50,000–50,063 under source `adad858`: 16 rows, 1,024 seed runs, 3,072 main episodes and 360,320 additional probe episodes. Its source, extension and configuration identities matched at completion. The task and retention formula stayed fixed. The measured policy used 64 paired probes per record, as declared before the run, rather than the calibration's four-pair diagnostic.

At two slots, measured retention averages 0.855556 accuracy, learned utility 0.831076 and no memory 0.871354. Measured retention improves on learned utility by 0.024479, or 2.448 percentage points, but loses 0.015799, or 1.580 points, against no memory. Both contrasts exclude zero under the declared correction. The positive contrast's interval lies wholly below the 0.05 planning target. That analyst-selected detectability target is not an adoption threshold.

| Declared paired contrast | Mean difference | Paired SD | 97.5% interval | Bonferroni-adjusted p |
| --- | --- | --- | --- | --- |
| Measured, two slots minus utility | 0.024479 | 0.024681 | [0.017395, 0.031563] | 9.2914427e-11 |
| Measured, two slots minus none | -0.015799 | 0.021350 | [-0.021927, -0.009670] | 2.9048171e-07 |

The unit is a seed's mean over three carried episodes, not an episode or a probe. The two 97.5% intervals and adjusted p-values implement the declared two-comparison family. Normal-difference assumptions and the finite workload still limit inference. The actual paired spreads are below the planned 0.10 assumption; no retrospective power calculation replaces the declaration. All one-slot limited policies have identical outcomes for each seed because there is only one retained record available for removal.

## Cost and reach of measurement

Each row contains 192 main episodes. The measured one-slot arm adds 113,792 probe episodes and 301.022178 probe seconds within 301.467103 inclusive seconds. The two-slot arm adds 246,528 episodes and 617.818656 probe seconds within 618.281687 inclusive seconds. Utility takes 0.392478 and 0.439060 seconds respectively: approximately 768 and 1,408 times less inclusive elapsed time on this machine. Timings are observations of this run, not universal performance ratios. Inclusive time already contains probe time.

Probe arms record 622,721 initial-record reads at one slot and 3,969,852 at two. The 2,815 record estimates include 979 positive, 1,831 negative and five zero contrasts; 92,843 of 180,160 paired outcomes differ. The 64-pair sample standard deviations average 0.021979 and reach 0.043565, below the 0.10 planning assumption in this run, not a bound on future variation. This establishes that probes reached carried memory and measured task-outcome changes. It does not establish identified causal effects, live-classifier continuation or that the measurement's price is justified. The fresh-task experiment and its reference policy remain exactly those in the protocol.

## All policies

| Policy | Slots | Mean accuracy | Seed SD | Probe episodes | Probe seconds | Inclusive seconds |
| --- | --- | --- | --- | --- | --- | --- |
| none | control | 0.871354 | 0.022271 | 0 | 0.000000 | 0.402589 |
| full | control | 0.855990 | 0.025281 | 0 | 0.000000 | 0.419738 |
| fifo | 1 | 0.839063 | 0.020334 | 0 | 0.000000 | 0.555552 |
| fifo | 2 | 0.841406 | 0.022787 | 0 | 0.000000 | 0.545188 |
| lru | 1 | 0.839063 | 0.020334 | 0 | 0.000000 | 0.446503 |
| lru | 2 | 0.854948 | 0.025928 | 0 | 0.000000 | 0.450970 |
| random | 1 | 0.839063 | 0.020334 | 0 | 0.000000 | 0.443248 |
| random | 2 | 0.842448 | 0.021808 | 0 | 0.000000 | 0.454111 |
| importance | 1 | 0.839063 | 0.020334 | 0 | 0.000000 | 0.455876 |
| importance | 2 | 0.839844 | 0.024836 | 0 | 0.000000 | 0.434000 |
| utility | 1 | 0.839063 | 0.020334 | 0 | 0.000000 | 0.392478 |
| utility | 2 | 0.831076 | 0.022172 | 0 | 0.000000 | 0.439060 |
| diversity | 1 | 0.839063 | 0.020334 | 0 | 0.000000 | 0.405353 |
| diversity | 2 | 0.831076 | 0.022172 | 0 | 0.000000 | 0.378157 |
| measured | 1 | 0.839063 | 0.020334 | 113792 | 301.022178 | 301.467103 |
| measured | 2 | 0.855556 | 0.024627 | 246528 | 617.818656 | 618.281687 |

Full capacity and LRU at two slots have means close to measured retention, but no additional significance or equivalence claim is assigned to these descriptive comparisons. No memory has the highest observed mean. Every positive, negative and zero seed-level difference remains in [analysis.json](analysis.json) and the complete compressed seed reports.

## What this result establishes

The repaired laboratory can keep data and replay opportunities paired, consult carried records, execute isolated removals, preserve signed outcomes and account for measurement cost. In this workload, its measured rule improves over learned utility while remaining worse than no memory and expensive to execute. Under the declared statistical assumptions, the corrected interval excludes a five-percentage-point gain over utility and excludes any positive mean gain over no memory. It does not establish a practical retention advantage over the simple controls, generalize to other workloads or justify adoption.

Keep this conclusion alongside the Tutor confirmation's smaller positive gains and large probe price, and the KeyDoor/Bandit control limits. Do not tune or add seeds to obtain a preferred winner. Notebook 04–06 retention comparisons, live-context experiments and the remaining product contracts stay open; this result alone does not close RK-2/3.

## Retained inputs

[complete.json](complete.json) binds all 64 completed seed files. [config.json](config.json), [declaration](declaration.json), [environment](env_meta.json), [kernel lockfile](kernel.Cargo.lock) and the captured [runner](runner.py) identify what executed. Each `seed-N.json.gz` contains all 16 policy rows and complete probe evidence. The notebook envelope retains its generic `run_mode: demo` label; this runner takes sample size from the separately committed declaration, and the completed 64-seed list establishes the full confirmation. The reserved smoke seed is excluded. Calibration, control and earlier Tutor files remain unchanged.
