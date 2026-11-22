# Notebook retention calibration

The fixed comparison completed all sixteen declared seeds. Conversation measured retention recalls 5.208 percentage points more than learned utility at both budgets, but each average gain comes from only two of sixteen seeds. MiniGrid measured retention matches the perfect success of utility and explicit importance. Every TextWorld main episode scores zero and loses. These are calibration observations, not confirmation tests, evidence of equivalence or grounds for adoption.

The run uses committed source `9f2383f12a22d2d4590024ecb8bc221a4fb8d04b`, seeds 61000–61015, one main episode per arm and the [fixed declaration](declaration.json). There are 768 main episodes and 14,232 replay episodes. The [protocol](protocol.md), [runner](runner.py), [environment and source identities](env_meta.json), [complete marker](complete.json) and [analysis with all seed vectors](analysis.json) are retained alongside sixteen compressed seed files. Each seed file contains every main transcript and replay arm, including the memory-call journal, boundary digest, record-ID mapping, target removal and game identity. The reserved smoke seed 60001 is excluded.

## Outcomes across outer episodes

Each cell is mean (sample standard deviation), with sixteen independent outer seeds. Conversation measures literal constraint recall, MiniGrid measures success and TextWorld measures final game score. None and full run once per seed; limited policies run at two and four slots. Full memory had no prunes in any episode. No memory discarded every admission before a controller could read it.

| Policy | Slots | Conversation recall | MiniGrid success | TextWorld score |
| --- | --: | --: | --: | --: |
| none | — | 0.000000 (0.000000) | 0.500000 (0.516398) | 0.000000 (0.000000) |
| full | — | 1.000000 (0.000000) | 1.000000 (0.000000) | 0.000000 (0.000000) |
| fifo | 2 | 0.166667 (0.201843) | 0.500000 (0.516398) | 0.000000 (0.000000) |
| fifo | 4 | 0.312500 (0.209718) | 0.562500 (0.512348) | 0.000000 (0.000000) |
| lru | 2 | 0.239583 (0.227456) | 0.500000 (0.516398) | 0.000000 (0.000000) |
| lru | 4 | 0.666667 (0.291865) | 0.562500 (0.512348) | 0.000000 (0.000000) |
| random | 2 | 0.093750 (0.171796) | 0.562500 (0.512348) | 0.000000 (0.000000) |
| random | 4 | 0.385417 (0.283619) | 0.750000 (0.447214) | 0.000000 (0.000000) |
| importance | 2 | 0.072917 (0.160655) | 1.000000 (0.000000) | 0.000000 (0.000000) |
| importance | 4 | 0.677083 (0.281982) | 1.000000 (0.000000) | 0.000000 (0.000000) |
| utility | 2 | 0.125000 (0.197203) | 1.000000 (0.000000) | 0.000000 (0.000000) |
| utility | 4 | 0.697917 (0.293250) | 1.000000 (0.000000) | 0.000000 (0.000000) |
| diversity | 2 | 0.000000 (0.000000) | 0.500000 (0.516398) | 0.000000 (0.000000) |
| diversity | 4 | 0.291667 (0.187577) | 1.000000 (0.000000) | 0.000000 (0.000000) |
| measured | 2 | 0.177083 (0.214897) | 1.000000 (0.000000) | 0.000000 (0.000000) |
| measured | 4 | 0.750000 (0.304290) | 1.000000 (0.000000) | 0.000000 (0.000000) |

Conversation measured minus utility is 0.052083 at both budgets, with paired SD 0.145535. At two slots, seeds 61002 and 61006 improve by 0.333333 and 0.5; at four slots, seeds 61001 and 61002 improve by 0.5 and 0.333333. The other fourteen seed differences at each budget are zero. At two slots, LRU has higher observed recall (0.239583) than measured retention (0.177083); the gain over utility is not a best-policy claim. The two budget comparisons share episode seeds and are not independent replications. No confidence interval, p-value or post-hoc power claim is assigned to this calibration.

MiniGrid measured, utility and explicit importance each succeed in all sixteen seeds at both budgets. Their equality is consistent with the controller retaining its explicitly prioritised initial cue, while the declared branch fallback without memory succeeds in eight seeds. This checks retention in a known corridor, not learned navigation or general policy equivalence.

All 256 TextWorld main episodes have zero score and zero wins, including full memory. Its 5,620 candidate comparisons use 11,240 replay episodes and all have zero outcome differences. The limited scripted selector therefore supplies no useful game-performance comparison here. These zeros do not establish that the records are irrelevant or that the policies are equivalent. A useful game-solving comparator remains open.

## The price of selecting a prune

Each measured row has sixteen main episodes. Inclusive seconds already contain all replay work; do not add probe seconds to them again. The ratios compare inclusive measured-arm time with utility at the same budget on this machine during this run, rather than asserting a portable speed factor.

| Adapter | Slots | Replay episodes | Replay seconds | Inclusive seconds | Times utility |
| --- | --: | --: | --: | --: | --: |
| conversation | 2 | 664 | 1.324284 | 1.347108 | 89.33 |
| conversation | 4 | 1,072 | 2.128729 | 2.155672 | 123.01 |
| minigrid | 2 | 504 | 0.849396 | 0.873345 | 44.33 |
| minigrid | 4 | 752 | 1.332346 | 1.356205 | 66.87 |
| textworld | 2 | 3,832 | 1147.501898 | 1151.964171 | 265.43 |
| textworld | 4 | 7,408 | 2143.982391 | 2148.226640 | 446.62 |

Inclusive episode execution and game preparation total 3,391.832261 seconds, about 56.5 minutes. Shared game preparation accounts for 20.840309 seconds within that total. Per-seed costs remain in the analysis. Conversation and MiniGrid keep the declared 500 bytes per slot; TextWorld has no byte limit. Actual peak slots, bytes, writes, prunes and immediate discards are retained for each main episode.

## What the removal effect means

The live controller is paused at a pending write. Each arm reconstructs the same deterministic episode and its actual earlier pruning choices, then verifies the memory calls, credit context and candidate state. The baseline uses FIFO at that write; the intervention removes its candidate first, then uses FIFO for any remaining overflow. Both continue under FIFO. The signed difference is baseline outcome minus intervention outcome. A FIFO baseline may itself discard the target, and forced removal can change which other record survives. This is conditional removal under a bounded continuation policy, not guaranteed retention versus removal.

Each candidate receives one exact deterministic pair. Repeating it would not produce independent evidence. The method needs a replayable simulator and its fixed seed or game; it does not establish that an arbitrary live conversation or external service can be resumed or previewed this way. All reconstruction and continuation episodes are charged.

Across 7,116 record estimates, 26 differences are positive, 66 negative and 7,024 zero. Conversation has 7 positive / 2 negative at two slots and 19 positive / 35 negative at four. MiniGrid has 8 and 21 negative differences respectively, with no positive differences: forcing out a different record can preserve the cue that FIFO would otherwise discard. None of those tested MiniGrid candidates is itself retrieved after the intervention boundary. TextWorld has 1,916 and 3,704 zero differences. Signed outcomes remain in the evidence even though the ranking grants a bonus only to beneficial retention effects.

## Verification and next question

The runner verified unchanged source inputs and all sixteen executable/metadata pairs before writing completion. A subsequent read of every compressed seed file matched its saved hash, recomputed all 48 means and sample spreads, checked every replay prefix and boundary, matched actual target-prune events and confirmed the shared TextWorld identity across all arms. Counts match 768 main and 14,232 replay episodes. The full-memory and immediate-discard controls hold for every seed.

The current comparison is complete as declared. It leaves a separate confirmation question for the small conversation gain, retains MiniGrid’s ceiling under its supplied controller and leaves TextWorld’s game-solving comparator unfinished. Confirmation must declare fresh seeds, planning assumptions and its contrast family before outcomes. These results do not close the broader research hypothesis, deployment contracts or promotion requirements. Earlier native comparisons and read-boundary ablations remain separate evidence.
