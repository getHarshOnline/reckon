# Paired Continual calibration

The [fixed declaration](protocol.md) completed all 16 seeds 40,000–40,015 under source `be3434e`: 16 rows, 256 seed runs, 768 main episodes and 4,776 probe episodes. The original three-task workload is unchanged; the source repair pairs data and replay opportunities and permits carried records to be read before any new write. This is a calibration, not the powered confirmation.

At one slot, every limited policy has the same outcome for every seed: admission must remove the only retained record, so ranking has no choice. At two slots, measured retention averages 0.839236 final accuracy versus 0.832986 for learned utility, a descriptive difference of 0.006250. Its per-seed differences include gains, losses and ties; their sample standard deviation is 0.023384. No memory averages 0.879167 and full capacity 0.862153, both above the measured mean. The calibration supplies no general policy advantage and does not discard the adverse comparison with no memory.

The fresh-task probes now reach carried memory. Their baseline and intervention arms record 9,985 initial-record reads at one slot and 46,894 at two. Across both budgets, 542 of 597 record estimates are nonzero and 1,265 of 2,388 paired outcomes differ. The four-pair probe differences have a maximum observed sample standard deviation of 0.055277; these small-sample spreads are planning evidence, not bounds on future variance. The measured arms consume 1,848 and 2,928 extra episodes. Their probe time is 3.777292 and 6.043469 seconds, within inclusive times 3.859280 and 6.125148; the corresponding utility arms take 0.074210 and 0.075970 seconds on this machine.

## All arms

Each row contains 48 main episodes. The standard deviation is across outer-seed means. Full per-seed differences, record reads, removals, store peaks and costs are in [analysis.json](analysis.json); the compressed seed reports preserve every paired intervention. [complete.json](complete.json) binds the completed seeds, while [config.json](config.json), [environment](env_meta.json), [lockfile](kernel.Cargo.lock) and [runner](runner.py) retain the exact inputs. Original pilot and Tutor outputs remain unchanged.

| Policy | Slots | Mean accuracy | Seed SD | Probe episodes | Probe seconds | Inclusive seconds |
| --- | --- | --- | --- | --- | --- | --- |
| none | control | 0.879167 | 0.023701 | 0 | 0.000000 | 0.072845 |
| full | control | 0.862153 | 0.024362 | 0 | 0.000000 | 0.070901 |
| fifo | 1 | 0.843403 | 0.019054 | 0 | 0.000000 | 0.075332 |
| fifo | 2 | 0.842014 | 0.024341 | 0 | 0.000000 | 0.073535 |
| lru | 1 | 0.843403 | 0.019054 | 0 | 0.000000 | 0.074884 |
| lru | 2 | 0.859028 | 0.026440 | 0 | 0.000000 | 0.074829 |
| random | 1 | 0.843403 | 0.019054 | 0 | 0.000000 | 0.076789 |
| random | 2 | 0.842708 | 0.024905 | 0 | 0.000000 | 0.075916 |
| importance | 1 | 0.843403 | 0.019054 | 0 | 0.000000 | 0.074401 |
| importance | 2 | 0.847917 | 0.018908 | 0 | 0.000000 | 0.074609 |
| utility | 1 | 0.843403 | 0.019054 | 0 | 0.000000 | 0.074210 |
| utility | 2 | 0.832986 | 0.025778 | 0 | 0.000000 | 0.075970 |
| diversity | 1 | 0.843403 | 0.019054 | 0 | 0.000000 | 0.073490 |
| diversity | 2 | 0.832986 | 0.025778 | 0 | 0.000000 | 0.075337 |
| measured | 1 | 0.843403 | 0.019054 | 1848 | 3.777292 | 3.859280 |
| measured | 2 | 0.839236 | 0.028722 | 2928 | 6.043469 | 6.125148 |

A confirmation must use separate declared seeds and report measured retention against both learned utility and no memory. Retain one slot as a control with no retention choice; the two-slot condition can compare rankings. Select its effect-size and variance assumptions before execution. This result establishes an executable comparison with reachable records; it does not close the laboratory comparison or justify promotion.
