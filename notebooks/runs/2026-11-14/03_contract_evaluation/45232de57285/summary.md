# 03_contract_evaluation Run Summary

**Mode:** paper
**Git:** 5bde868
**Time:** 2026-11-14T23:24:38.108420
**Config Hash:** 45232de57285

## Configuration

- Seed: 42 (x1)
- Budget: 100 slots
- Task: seeded_record_decision (20 episodes)
- Policy: fifo

## Key Metrics

- **main_targets:** 6
- **useful_targets:** 1
- **key_delta:** 1.0000
- **key_p_value:** 0.0001
- **summary_delta:** 0.0000
- **hint_delta:** 0.6800
- **h1_supported:** True
- **h2_supported:** True
- **base_episodes:** 20
- **base_elapsed_s:** 0.0139
- **probe_episodes:** 1220
- **probe_elapsed_s:** 1.9251
- **total_episodes:** 1240
- **total_measured_s:** 1.9390
- **probe_episode_fraction:** 0.9839
- **probe_time_fraction:** 0.9928
- **evaluation_calls:** 26

## Figures

- [figures/ablation_deltas.png](figures/ablation_deltas.png)
- [figures/classification_vs_probe_episodes.png](figures/classification_vs_probe_episodes.png)

## Notes

Native evaluator; single-instance ablation. Per-record p-values are unadjusted. Counts include the main, additional trial-count, summary and hint evaluations once each. Figure/export time is outside measured task and probe time.