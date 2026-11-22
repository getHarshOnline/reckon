# Tutor confirmation: small gains with a large measurement cost

Measured retention improved the mean fraction of misconceptions cleared over learned utility in this declared Tutor workload. The gains were 0.339 percentage points at two slots and 0.755 points at four slots. Both family-adjusted comparisons reject zero, but both intervals lie wholly below the predeclared five-percentage-point planning target. Measurement required 5,790,720 additional episodes. This establishes a small positive difference for this workload and implementation; it does not establish a generally useful policy or justify promotion.

## Fixed comparison and saved evidence

The run completed on 15 November 2026 under source commit `3d3aea69834f00f8ab514880cff6ab903acfb8db`, with all 256 declared seeds, 20,000–20,255. Each seed supplied five carried-memory episodes for each of 16 policy/budget groups: 1,280 main episodes per row and 20,480 altogether. The outcome is the fraction of six initial misconceptions cleared, averaged across those five episodes. The independent analysis unit is the outer seed. No seed was added, replaced or removed after outcomes were seen.

The [captured protocol](tutor-confirmation.md), [configuration](tutor_confirmation.json), [runner](tutor_confirmation.py) and [kernel lockfile](Cargo.lock) retain the predeclared inputs. The [manifest](manifest.json) contains the complete seed-file index and hashes, 137 source hashes, source revision, Python and dependency versions, extension hash and start/end times. Every indexed compressed seed file retains its main runs, record snapshots, paired probe outcomes and selected removals. [Analysis](analysis.json) retains both primary paired vectors; [metrics](metrics.csv) retains all policy means, spreads and costs.

The complete-run check matched every file hash and input identity, verified the 16 groups in each of 256 seeds, reconciled all main and probe episode counts, checked paired probe seeds and disjoint outer-seed reservations, and independently recalculated every reported mean, spread, interval and primary p-value. The CSV agrees with that analysis. The original source, configuration and protocol remained unchanged through completion.

## Primary contrasts

Differences below are in fractions cleared, not percentage points. Each contrast uses a paired t test across 256 outer-seed means. The two 97.5% intervals and Bonferroni-adjusted p-values use the declared family alpha of 0.05.

| Slots | Measured minus utility | Paired standard deviation | 97.5% interval | Adjusted p-value |
| --- | --- | --- | --- | --- |
| 2 | 0.00338542 | 0.02142620 | [0.00036604, 0.00640479] | 0.024148186 |
| 4 | 0.00755208 | 0.02369554 | [0.00421291, 0.01089125] | 1.3301559e-06 |

The observed paired standard deviations, 0.02143 and 0.02370, were much smaller than the planning assumption of 0.25. Interval widths were 0.00604 and 0.00668. The planning target of 0.05 was an analyst-selected effect for sample planning, not Harsh’s acceptance threshold. These intervals support positive effects smaller than that target under the declared t approximation. They do not establish equivalence between policies, a universal performance ranking or the broader Reckon hypothesis. No retrospective observed-effect power is substituted for the planning calculation.

At two slots, measured retention was higher in 50 seeds, equal in 180 and lower in 26. At four slots it was higher in 74, equal in 157 and lower in 25. These are descriptive counts from the same paired vectors, not additional significance tests.

## All policy outcomes

These are descriptive 95% t intervals for each policy mean, not simultaneous intervals for ranking all policies. Every row contains 256 independent seed means. The no-memory and full-capacity controls run once per seed, without a two/four-slot label.

| Policy | Slots | Mean fraction cleared | Seed standard deviation | 95% interval |
| --- | --- | --- | --- | --- |
| none | control | 0.303385 | 0.080990 | [0.293417, 0.313354] |
| full | control | 0.392708 | 0.104657 | [0.379827, 0.405590] |
| fifo | 2 | 0.330208 | 0.079862 | [0.320379, 0.340038] |
| fifo | 4 | 0.363281 | 0.086252 | [0.352665, 0.373897] |
| lru | 2 | 0.332292 | 0.082175 | [0.322177, 0.342406] |
| lru | 4 | 0.363021 | 0.089951 | [0.351949, 0.374092] |
| random | 2 | 0.334245 | 0.080218 | [0.324371, 0.344118] |
| random | 4 | 0.361458 | 0.086414 | [0.350822, 0.372094] |
| importance | 2 | 0.331901 | 0.080698 | [0.321969, 0.341833] |
| importance | 4 | 0.360026 | 0.089317 | [0.349033, 0.371019] |
| utility | 2 | 0.329818 | 0.079982 | [0.319973, 0.339662] |
| utility | 4 | 0.360677 | 0.088309 | [0.349808, 0.371546] |
| diversity | 2 | 0.329818 | 0.079982 | [0.319973, 0.339662] |
| diversity | 4 | 0.360677 | 0.088309 | [0.349808, 0.371546] |
| measured | 2 | 0.333203 | 0.080602 | [0.323282, 0.343124] |
| measured | 4 | 0.368229 | 0.091833 | [0.356926, 0.379532] |

## Cost and storage

Each row below has 1,280 main episodes. Probe time is included in elapsed time; task time is the measured remainder after subtracting probe time. The measured rows alone used 2,096,128 and 3,694,592 probe episodes, or 1,637.6 and 2,886.4 extra episodes per main episode. Their inclusive elapsed times were 2,087.33 and 4,253.78 seconds, compared with 0.77 and 0.85 seconds for utility. These timings describe this machine and run. The runner also spent time saving and analysing evidence outside the per-policy timers.

| Policy | Slots | Probe episodes | Task seconds | Probe seconds | Inclusive seconds |
| --- | --- | --- | --- | --- | --- |
| none | control | 0 | 0.852 | 0.000 | 0.852 |
| full | control | 0 | 0.879 | 0.000 | 0.879 |
| fifo | 2 | 0 | 0.837 | 0.000 | 0.837 |
| fifo | 4 | 0 | 0.802 | 0.000 | 0.802 |
| lru | 2 | 0 | 0.780 | 0.000 | 0.780 |
| lru | 4 | 0 | 0.839 | 0.000 | 0.839 |
| random | 2 | 0 | 0.787 | 0.000 | 0.787 |
| random | 4 | 0 | 0.844 | 0.000 | 0.844 |
| importance | 2 | 0 | 0.815 | 0.000 | 0.815 |
| importance | 4 | 0 | 0.840 | 0.000 | 0.840 |
| utility | 2 | 0 | 0.772 | 0.000 | 0.772 |
| utility | 4 | 0 | 0.846 | 0.000 | 0.846 |
| diversity | 2 | 0 | 0.764 | 0.000 | 0.764 |
| diversity | 4 | 0 | 0.815 | 0.000 | 0.815 |
| measured | 2 | 2,096,128 | 0.959 | 2086.370 | 2087.329 |
| measured | 4 | 3,694,592 | 0.995 | 4252.780 | 4253.775 |

Peak bytes and slots below are the mean of each seed’s sampled main-store peak after successful writes. They measure record accounting, not process memory or the combined memory used by probe trials. The no-memory control discards each write immediately after that observation, which explains its sampled one-slot peak. Writes and policy prunes are totals across main runs; the control’s immediate discards are separate from policy prunes.

| Policy | Slots | Mean peak bytes | Mean peak slots | Writes | Policy prunes |
| --- | --- | --- | --- | --- | --- |
| none | control | 60.477 | 1.000 | 2,330 | 0 |
| full | control | 670.340 | 11.781 | 3,016 | 0 |
| fifo | 2 | 118.160 | 2.000 | 2,536 | 2,024 |
| fifo | 4 | 231.742 | 4.000 | 2,790 | 1,766 |
| lru | 2 | 117.852 | 2.000 | 2,552 | 2,040 |
| lru | 4 | 231.324 | 4.000 | 2,788 | 1,764 |
| random | 2 | 117.953 | 2.000 | 2,567 | 2,055 |
| random | 4 | 231.625 | 4.000 | 2,776 | 1,752 |
| importance | 2 | 115.980 | 2.000 | 2,549 | 2,037 |
| importance | 4 | 228.707 | 4.000 | 2,765 | 1,741 |
| utility | 2 | 117.938 | 2.000 | 2,533 | 2,021 |
| utility | 4 | 231.562 | 4.000 | 2,770 | 1,746 |
| diversity | 2 | 117.938 | 2.000 | 2,533 | 2,021 |
| diversity | 4 | 231.562 | 4.000 | 2,770 | 1,746 |
| measured | 2 | 117.770 | 2.000 | 2,559 | 2,047 |
| measured | 4 | 231.074 | 4.000 | 2,828 | 1,804 |

## What this result leaves open

The retained policy mixes learned utility with positive measured effect per byte. Each prune measures record removal in fresh FIFO-reference Tutor episodes with copied memory; it does not continue the live student. Inner probe intervals are pointwise 95% intervals, while per-decision p-values use Bonferroni correction across candidate records. Neither that correction nor this outer comparison claims simultaneous error control over all adaptively reached pruning decisions.

This result applies to six concepts, six questions, the declared hint probabilities, five carried episodes and the two tested slot budgets. It does not identify which part of the scoring mixture produced the gain, establish transfer to other tasks, or show that the gain is worth its measurement cost. Other workloads, compute-budget comparisons and a distinct posterior-based retention rule remain separate work. The earlier exploratory null and adverse results remain unchanged in their original bundles.
