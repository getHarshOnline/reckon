# Continual comparison after the replay repair

This fixed calibration carries the [original Continual workload](../../notebooks/runs/2026-11-15/measured_retention_pilot/6b59fa73f40b/summary.md) forward after separating its data and replay randomness and allowing carried records to be read before the first new write. The completed KeyDoor and Bandit controls do not require a new workload. Continual already has competing replay samples; this run checks their actual use, policy outcomes and measurement cost on paired inputs. It leaves the completed Tutor result unchanged.

## Declared inputs and question

The [configuration](../../notebooks/experiments/continual_paired_calibration.json) retains three tasks, 40 training samples and 20 test samples per task, two features, replay probability 0.2 and learning rate 0.1. Each outer seed runs three episodes with carried memory and utility learning. Use fresh seeds 40,000–40,015 exactly, with 39,999 reserved for the runner check. Do not adjust the workload, policy or sample count after inspecting outcomes.

Compare no memory, full capacity, FIFO, LRU, seeded random, explicit importance, learned utility, Diversity and measured retention. The first two controls run once per seed; each limited policy uses one and two slots without a byte cap. This gives 16 rows, 256 seed runs and 768 main episodes. The outcome is final accuracy averaged over tasks and then the three episodes, with each outer seed as the observation. Keep forgetting, replay reads, writes and sampled storage with the result. The full-capacity arm is a reference at its measured cost, not an assumed upper bound on accuracy.

At each measured pruning decision, use four fixed paired trials per retained record, one fresh Continual episode per arm, non-probing FIFO, carried starting memory and utility learning. The existing equal-weight combination of utility and positive intervention delta per byte stays unchanged. Keep signed estimates even when the ranking uses only their positive part. The permutation test requests 256 resamples and enumerates all 16 sign combinations for four pairs; Bonferroni correction covers only the candidates at that decision, at alpha 0.05. Disable adaptive sampling and early stopping. These settings qualify the experiment and estimate its price; they are not a powered test of a small effect.

For outer seed index `i`, the probe stream starts at `3,000,000,000 + i * 100,000`. Each pruning decision advances by four. There are at most 360 writes across three main episodes, so the reservation is sufficient. The two budgets share each seed's probe stream. The reserved smoke seed uses 2,000,000,000 in a separate diagnostic, as the runner records; it is excluded from the calibration and inference. Main and calibration probe seeds are disjoint from the earlier experiments.

## Analysis and next comparison

Report all row means and sample spreads, exact paired differences from full capacity and learned utility, initial-record reads in both probe arms, nonzero record contrasts, unequal paired outcomes, and the full main/probe episode and elapsed-time costs. Retain null and adverse results. An initial-record read establishes that the measurement reached memory; an outcome contrast establishes a difference in that declared fresh task, not an identified causal effect or live-state continuation.

Use the observed paired spread and execution cost to plan the remaining confirmation on separate declared seeds, with its effect-size and power assumptions stated before execution. Do not reuse these calibration seeds in that confirmation or select a workload to make measured retention win. This run cannot establish a general policy advantage, equivalence or the whole Reckon hypothesis. No separately specified Beta-posterior retention rule is available, so no arm is invented under that name.

## Run and preserve

Use the existing runner: `python notebooks/experiments/workload_controls.py --config notebooks/experiments/continual_paired_calibration.json --plan`. After committing the declared inputs and source repair, use the same command with `--smoke OUTPUT_DIRECTORY`, then `--run`. The source identity, full declaration, runner, lockfile, complete compressed seed reports and accounting analysis stay under `notebooks/runs/`. The runner refuses an existing run instead of replacing completed observations. Preserve an interrupted run as incomplete until its completed seeds are reconciled. Earlier pilot artifacts remain tied to their original source and input-pairing limits.
