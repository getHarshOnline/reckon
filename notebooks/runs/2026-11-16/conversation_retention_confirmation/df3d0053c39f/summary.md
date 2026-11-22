# Conversation retention confirmation

Measured retention improves literal recall over learned utility in both predeclared comparisons across 256 fresh outer seeds. The gains are 0.061849 at two slots and 0.048828 at four slots, with both adjusted intervals above zero. This establishes a gain for the fixed scripted controller and comparisons. It does not establish an overall best policy or justify adoption: LRU has higher observed recall at two slots, full memory recalls everything, and measured retention takes much more time.

The [fixed protocol](protocol.md) and [declaration](declaration.json) were committed before outcomes at source `e60a4a2072cd21e30c89103770b2fbd86f109b89`. The reserved smoke seed 61999 passed its structural and accounting checks and is excluded. All 256 declared seeds 62000–62255 completed without replacement or tuning: nine policies, sixteen arms per seed, 4,096 main episodes and 26,972 replay episodes. The eight-step controller, two/four-slot budgets, 500 bytes per slot and causal weight 0.5 remained fixed. The [completion marker](complete.json) identifies the inputs and hashes every compressed seed report.

## Primary comparisons

Each contrast pairs outcomes by seed. The two-sided paired t tests use Bonferroni adjustment for the declared family of two; each reported interval is 97.5%. Planning used difference 0.05 and paired SD 0.20, giving conditional power 0.958968776 per contrast under independent normal paired differences. That planning quantity is neither the probability of success on both contrasts nor an adoption threshold.

| Slots | Measured − utility | Paired SD | 97.5% interval | Adjusted p | Improving / equal / adverse seeds |
| --- | --- | --- | --- | --- | --- |
| 2 | 0.061849 | 0.151875 | [0.040447, 0.083251] | 7.67365141e-10 | 38 / 218 / 0 |
| 4 | 0.048828 | 0.132443 | [0.030164, 0.067492] | 2.31812079e-08 | 32 / 224 / 0 |

The [analysis](analysis.json) retains both complete difference vectors and every baseline outcome vector. Other policy comparisons are descriptive. LRU at two slots averages 0.243490, compared with measured retention at 0.169271. The tests above compare measured retention only with utility; they do not test superiority over LRU or every alternative. No memory scores zero and full memory scores one in every episode.

## All arms and measured costs

Each row contains 256 main episodes. SD is the sample standard deviation across outer seeds. Inclusive elapsed time includes all replay work. The replay column measures the portion spent reconstructing prefixes and executing continuations; it must not be added to the inclusive column. These are observed times on this machine, not a portable performance guarantee.

| Policy | Slots | Mean recall | SD | Replay episodes | Inclusive seconds | Replay seconds |
| --- | --- | --- | --- | --- | --- | --- |
| none | — | 0.000000 | 0.000000 | 0 | 0.229867 | 0.000000 |
| full | — | 1.000000 | 0.000000 | 0 | 0.210076 | 0.000000 |
| fifo | 2 | 0.126953 | 0.194271 | 0 | 0.224882 | 0.000000 |
| fifo | 4 | 0.298828 | 0.266509 | 0 | 0.246079 | 0.000000 |
| lru | 2 | 0.243490 | 0.216329 | 0 | 0.223493 | 0.000000 |
| lru | 4 | 0.717448 | 0.269397 | 0 | 0.260662 | 0.000000 |
| random | 2 | 0.085938 | 0.172745 | 0 | 0.232803 | 0.000000 |
| random | 4 | 0.318359 | 0.282560 | 0 | 0.260619 | 0.000000 |
| importance | 2 | 0.118490 | 0.194871 | 0 | 0.227007 | 0.000000 |
| importance | 4 | 0.734375 | 0.288439 | 0 | 0.262435 | 0.000000 |
| utility | 2 | 0.107422 | 0.187476 | 0 | 0.229388 | 0.000000 |
| utility | 4 | 0.727214 | 0.295429 | 0 | 0.263999 | 0.000000 |
| diversity | 2 | 0.000000 | 0.000000 | 0 | 0.209973 | 0.000000 |
| diversity | 4 | 0.218750 | 0.219179 | 0 | 0.248829 | 0.000000 |
| measured | 2 | 0.169271 | 0.211833 | 10,356 | 16.999988 | 16.672769 |
| measured | 4 | 0.776042 | 0.246490 | 16,616 | 30.840436 | 30.464010 |

Measured retention takes 74.11× utility time at two slots and 116.82× at four slots. Inclusive seed execution totals 51.248483 seconds; no game preparation is needed. This total covers episode execution, while saving and checking artifacts adds further wall time. Peak slots and bytes, writes, prunes and baseline discards remain available per arm and seed in the analysis and original reports. Full memory performed no prunes; no memory immediately discarded each admission.

## Replay evidence and scope

The 13,486 candidate pairs contain 392 positive, 627 negative and 12,467 zero signed effects. At two slots the counts are 58 positive, 68 negative and 5,052 zero; at four slots they are 334 positive, 559 negative and 7,415 zero. Negative candidate effects are retained even though the ranking grants a bonus only to beneficial retention effects. Candidate effects and outer policy gains answer different questions.

Every candidate uses one deterministic pair after reconstructing the actual earlier removals. The baseline uses FIFO at the pending write; the intervention removes the named candidate first, then FIFO handles any residual overflow. Both continue under FIFO. The baseline may remove the same target. These are effects of conditional removal under that continuation, with no inner p-values, confidence intervals or independent repeated-trial claim.

The retained reports preserve every main and replay transcript, memory-call journal, boundary hash, ordinal-to-UUID map, selected removal, signed outcome and cost. Verification checked all 256 saved hashes, the committed input identity at completion, all 4,096 main arms, immediate no-memory discards, absence of full-memory prunes, replay prefix and boundary digests, named actual removals, aggregate accounting and both paired comparisons.

This result concerns literal constraint recall by the unchanged scripted controller. It does not test an arbitrary agent, model-dependent continuation or real-world memory system. MiniGrid’s calibration ceiling and TextWorld’s all-zero main outcomes remain separate findings. A useful TextWorld game-solving comparator, wider research comparisons and a practical adoption decision remain open. The [earlier calibration](../../adapter_retention_calibration/b4ec292d870a/summary.md) and native experiments retain their own scope.
