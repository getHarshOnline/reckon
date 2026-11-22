# tutor_paired_calibration Run Summary

**Mode:** demo
**Git:** b9c28099a60f408d05af167610d898d7b6b5be1c
**Time:** 2026-11-15T14:35:21.152647
**Config Hash:** d1946209a918

## Configuration

- Seed: 100 (x5)
- Budget: 2 slots
- Task: tutor (5 episodes)
- Policy: matrix

## Key Metrics

- **rows:** 16
- **seed_runs:** 80
- **task_episodes:** 400
- **probe_episodes:** 2144
- **elapsed_s:** 3.3620

## Notes

The source separates student, per-question response, concept-choice and hint-choice streams. All workload, policy, budget and probe settings match the earlier declared calibration. Seeds 100–104 are reused exploratory seeds, not a held-out confirmation. The comparison remains a fresh-task retention probe, not live-state continuation. All old runs remain unchanged. See [raw runs and paired probe outcomes](comparison.json), [complete configuration](config.json), [metrics](metrics.csv), [environment](env_meta.json), [captured kernel lockfile](kernel.Cargo.lock) and [runner](runner.py).

| Policy | Slots | Mean improvement | Seed standard deviation | Probe episodes |
| --- | --- | --- | --- | --- |
| none | control | 0.360000 | 0.136219 | 0 |
| full | control | 0.446667 | 0.128236 | 0 |
| fifo | 2 | 0.386667 | 0.130384 | 0 |
| fifo | 4 | 0.433333 | 0.117851 | 0 |
| lru | 2 | 0.386667 | 0.132497 | 0 |
| lru | 4 | 0.406667 | 0.103816 | 0 |
| random | 2 | 0.400000 | 0.102740 | 0 |
| random | 4 | 0.433333 | 0.117851 | 0 |
| importance | 2 | 0.413333 | 0.128236 | 0 |
| importance | 4 | 0.433333 | 0.124722 | 0 |
| utility | 2 | 0.386667 | 0.130384 | 0 |
| utility | 4 | 0.433333 | 0.117851 | 0 |
| diversity | 2 | 0.386667 | 0.130384 | 0 |
| diversity | 4 | 0.433333 | 0.117851 | 0 |
| measured | 2 | 0.386667 | 0.112052 | 768 |
| measured | 4 | 0.420000 | 0.106979 | 1376 |