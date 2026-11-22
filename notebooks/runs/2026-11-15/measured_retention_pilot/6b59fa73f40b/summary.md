# measured_retention_pilot Run Summary

**Mode:** demo
**Git:** 2c6b050
**Time:** 2026-11-15T13:51:36.546806+05:30
**Config Hash:** 6b59fa73f40b

## Configuration

- Seed: 100 (x5)
- Budget: 1 slots
- Task: four_builtin_tasks (3 episodes)
- Policy: matrix

## Key Metrics

- **matrix_rows:** 64
- **task_episodes:** 960
- **probe_episodes:** 4504
- **elapsed_s:** 24.3990

## Notes

This is an unpowered pilot for task variation, pruning and probe cost, not a policy-benefit claim. Four paired probe trials are deliberately small. The complete powered comparison and notebook adapters remain unfinished. Each JSONL row retains all five seed runs and their paired probe evidence. See [metrics](metrics.csv), [raw comparisons](comparison.jsonl), [source and environment](env_meta.json), and [configuration](config.json).

Run from the repository root to repeat the matrix:

```bash
python -m reckon.cli compare --config notebooks/runs/2026-11-15/measured_retention_pilot/6b59fa73f40b/keydoor.json --config notebooks/runs/2026-11-15/measured_retention_pilot/6b59fa73f40b/bandit.json --config notebooks/runs/2026-11-15/measured_retention_pilot/6b59fa73f40b/continual.json --config notebooks/runs/2026-11-15/measured_retention_pilot/6b59fa73f40b/tutor.json --policies none full fifo lru random importance utility diversity measured --budget-slots 1 2 --seeds 100 101 102 103 104 --output json
```