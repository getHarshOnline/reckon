# KeyDoor and Bandit are memory-path controls

The complete diagnostic follows the [fixed protocol](protocol.md) committed in `7a12e67`, with all 16 declared seeds 30,000–30,015, 32 task-policy-budget rows, 512 seed runs and 1,536 main episodes. Every retained-memory arm matches full memory for every seed in both tasks; this includes measured versus learned utility at both budgets. No memory averages 0.395833 success in KeyDoor versus 0.750000 for every retained-memory arm. Bandit return per episode averages 136.576672 without memory versus 159.510847 for every retained-memory arm. These descriptive differences do not establish a general benefit or a powered equivalence result.

Every fresh-task probe recorded zero reads of its initial retained records. All 2,740 paired outcomes match, and all 685 record estimates have zero contrast. The current episode uses its own newly written cue; the fresh probe starts without the live controller's cue ID. This explains why the experiment can show useful live memory while its historical-record probes show no effect. It cannot evaluate the value of removing that cue before the live controller's next decision.

KeyDoor uses each cue before the next write. Bandit replaces indicators itself and retires them at tracked mode switches. Bandit's one-slot arms each make 613 capacity-driven removals and 354 task-directed removals across these seeds. Full memory makes no capacity-driven removals and 963 task-directed removals. Two-slot arms generally make four capacity-driven and 963 task-directed removals; seeded random makes six and 961. Those different removals leave the observed task outcomes identical. The new indicator is admitted after room is made and is available at the next choice. The control therefore does not distinguish how policies rank competing useful records.

## Outcomes and full measurement cost

Every row covers 48 main episodes. Standard deviation describes the 16 seed-level means. Elapsed time includes probe time; neither column is a universal timing claim. Complete per-seed outcomes, sampled store costs, removals, paired differences and probe read counts are in [analysis.json](analysis.json). Each `seed-N.json.gz` retains the full comparison, source record snapshots and both arms of every probe. [complete.json](complete.json) identifies all completed seed files; [config.json](config.json), [environment](env_meta.json), [kernel lockfile](kernel.Cargo.lock) and [runner](runner.py) identify the inputs.

| Task | Policy | Slots | Mean | Seed SD | Probe episodes | Probe seconds | Inclusive seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| keydoor | none | control | 0.395833 | 0.250000 | 0 | 0.000000 | 0.005783 |
| keydoor | full | control | 0.750000 | 0.192450 | 0 | 0.000000 | 0.005001 |
| keydoor | fifo | 1 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.005084 |
| keydoor | fifo | 2 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.004042 |
| keydoor | lru | 1 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.004051 |
| keydoor | lru | 2 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.003912 |
| keydoor | random | 1 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.004609 |
| keydoor | random | 2 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.004343 |
| keydoor | importance | 1 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.004476 |
| keydoor | importance | 2 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.003958 |
| keydoor | utility | 1 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.004030 |
| keydoor | utility | 2 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.003881 |
| keydoor | diversity | 1 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.004066 |
| keydoor | diversity | 2 | 0.750000 | 0.192450 | 0 | 0.000000 | 0.004012 |
| keydoor | measured | 1 | 0.750000 | 0.192450 | 256 | 0.055966 | 0.060730 |
| keydoor | measured | 2 | 0.750000 | 0.192450 | 256 | 0.056563 | 0.060908 |
| bandit | none | control | 136.576672 | 7.137505 | 0 | 0.000000 | 0.111713 |
| bandit | full | control | 159.510847 | 4.832866 | 0 | 0.000000 | 0.181154 |
| bandit | fifo | 1 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.233949 |
| bandit | fifo | 2 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.179971 |
| bandit | lru | 1 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.189329 |
| bandit | lru | 2 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.173989 |
| bandit | random | 1 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.201810 |
| bandit | random | 2 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.177005 |
| bandit | importance | 1 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.183276 |
| bandit | importance | 2 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.175472 |
| bandit | utility | 1 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.190228 |
| bandit | utility | 2 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.178689 |
| bandit | diversity | 1 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.187084 |
| bandit | diversity | 2 | 159.510847 | 4.832866 | 0 | 0.000000 | 0.176448 |
| bandit | measured | 1 | 159.510847 | 4.832866 | 4904 | 37.455197 | 37.677866 |
| bandit | measured | 2 | 159.510847 | 4.832866 | 64 | 0.480988 | 0.658076 |

Measurement adds 5,480 probe episodes. KeyDoor's measured arms spend 256 each; Bandit spends 4,904 at one slot and 64 at two. The measured policy buys no observed outcome improvement here. Its zero contrasts are retained alongside the cost, not converted into a ranking claim. This completes the diagnostic, not RK-2/3 or the remaining retention comparisons. Keep these workloads as controls; a retention comparison needs reachable retained records that compete before they are used. The earlier pilot and completed Tutor confirmation remain unchanged under their own source revisions.
