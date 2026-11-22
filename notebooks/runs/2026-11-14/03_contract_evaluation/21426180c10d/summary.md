# 03_contract_evaluation Run Summary

**Mode:** demo
**Git:** 5bde868
**Time:** 2026-11-14T23:23:24.406304
**Config Hash:** 21426180c10d

## Configuration

- Seed: 42 (x1)
- Budget: 100 slots
- Task: seeded_record_decision (5 episodes)
- Policy: fifo

## Key Metrics

- **main_targets:** 6
- **useful_targets:** 1
- **key_delta:** 1.0000
- **key_p_value:** 0.0020
- **summary_delta:** 0.0000
- **hint_delta:** 0.7000
- **h1_supported:** True
- **h2_supported:** True
- **base_episodes:** 5
- **base_elapsed_s:** 0.0040
- **probe_episodes:** 220
- **probe_elapsed_s:** 0.1708
- **total_episodes:** 225
- **total_measured_s:** 0.1748
- **probe_episode_fraction:** 0.9778
- **probe_time_fraction:** 0.9771
- **evaluation_calls:** 14

## Figures

- [figures/ablation_deltas.png](figures/ablation_deltas.png)
- [figures/classification_vs_probe_episodes.png](figures/classification_vs_probe_episodes.png)

## Notes

Native evaluator; single-instance ablation. Per-record p-values are unadjusted. Counts include the main, additional trial-count, summary and hint evaluations once each. Figure/export time is outside measured task and probe time.