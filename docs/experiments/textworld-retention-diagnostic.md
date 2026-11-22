# Diagnose TextWorld retention across all nine policies

This fixed calibration follows the [controller development](../../notebooks/runs/2026-11-16/textworld_controller_development/55a4ec2864b1/summary.md). The visible-instruction controller won all four development games with full memory, while no memory, utility and measured retention at two/four slots scored zero. One four-slot candidate removal produced a winning continuation that the unchanged ranking did not select. This supplies a useful full-memory control and a feasible bounded continuation; it does not establish a retention-policy benefit.

Commit this protocol and its [declaration](../../notebooks/experiments/textworld_retention_diagnostic.json) before executing the reserved smoke or calibration cases. Use the existing [comparison runner](../../notebooks/experiments/adapter_calibration.py). This is descriptive diagnostic calibration, with no primary hypothesis tests, confirmation claim or adoption decision. Preserve every zero, adverse outcome and failed execution; do not extend the seeds, replace a failed case or tune a rule to obtain a gain.

## Fixed cases, controller and arms

Use exactly sixteen fresh outer seeds, 64000–64015. Reserve 63999 for the separate smoke, excluded from the calibration summary. Generate the same three-room, five-object, three-command-quest games, with the 30-step horizon and default unblended house instructions. Generate once per seed and pin its executable and metadata hashes through every main/replay arm and completion. Preserve the original inputs and full transcripts.

Use the visible ordered-instruction controller from the source recorded in `notebooks/runs/2026-11-16/textworld_controller_development/55a4ec2864b1/env_meta.json`. It grounds the current instruction in admissible commands and reconstructs progress from retrieved action records. It permits required command repetition. Only the untried-command fallback avoids commands already present in retained history. The goal comes from the current observation or retained initial description; there is no hidden plan or action history, metadata solution, walkthrough, policy-command oracle, model call or prerecorded fallback. Unsupported prose and failed grounding retain their fallback outcomes.

> [!IMPORTANT]
>
> **Two slots are a constrained control.** The normal instructed path to the third action needs the goal record and two earlier action records. Two slots cannot retain all three; success there depends on fallback or current-observation information. Four slots admit those three records, and development already contains a successful four-slot removal path. Do not interpret a two-slot failure as evidence that an otherwise sufficient memory policy failed.

Run no memory and full memory once each, then FIFO, LRU, seeded random, explicit importance, learned utility, Diversity and measured retention at two and four slots. Nine policies give sixteen arms per seed, 256 main episodes in all. No memory immediately discards each admission. Full memory reserves six times the horizon plus sixteen slots and must perform no prunes. TextWorld remains slot-limited without a byte limit; record actual bytes and slots. Explicit importance freezes initial utility at admission, while learned utility remains its separate outcome-updated quantity. Random uses the outer seed independently of the environment.

## Preserve the measured policy and its limitations

Keep weight 0.5 and exactly one deterministic pair per candidate at each live pruning boundary. Reconstruct the same outer seed and all actual earlier prunes, matching the complete memory-call prefix, candidates and budget. The baseline uses FIFO at the pending write; the intervention removes the candidate first and uses FIFO for residual overflow. Both continue under FIFO. The signed effect is baseline outcome minus intervention outcome; the baseline may itself remove the target. Retain every negative, zero and positive effect. The existing ranking only bonuses beneficial retention effects; this diagnostic does not change it to penalise negative effects.

These are conditional effects under FIFO continuation. In development, a continuation could take a correct intermediate action yet later fail after another prune. A zero final-score difference therefore establishes neither record irrelevance nor policy equivalence. Identical fixed-seed inner continuations supply no independent trials, p-values or confidence intervals. The outer seeds supply the variation being calibrated.

## Complete evidence and costs

Save all main outcomes and baseline vectors, replay arms, memory-call journals, boundary hashes, ordinal-to-UUID mappings, actual selected removals and game identities under `notebooks/runs/`. Capture the committed protocol, declaration and runner, dependency versions, extension hash and Cargo lockfile. Require the input identity and retained game bytes to match again at completion. Existing outputs are never overwritten or silently resumed; a failure leaves its incomplete evidence intact.

Report every arm's score and win count, mean and sample SD, paired descriptive differences against no memory and utility, writes/prunes and peak/final usage. Report actual replay episode counts and inclusive per-arm elapsed time, with the replay portion separately identified but never added twice. Replay costs include prefix reconstruction. Report game preparation separately and the inclusive per-seed execution/preparation total. No confirmation power calculation belongs to these sixteen cases.

Run `python notebooks/experiments/adapter_calibration.py --config notebooks/experiments/textworld_retention_diagnostic.json --smoke .codex-tmp/textworld-retention-diagnostic-smoke-63999` for the reserved smoke, then use `--run` for all sixteen cases without changing the inputs.

## What follows from the answer

Review the complete diagnostic result before proposing anything further. If bounded policies again show only zero effects or an undifferentiated floor, diagnose the memory representation and FIFO continuation instead of scaling the same run. Any controller or scoring change requires its own declared development and fresh comparison; do not alter the completed cases. A later confirmation, if justified, needs a separate fixed protocol, fresh seeds, explicit contrasts and sample-size assumptions. This diagnostic authorises neither that confirmation nor policy adoption, and it does not resume paused Causality mathematics.
