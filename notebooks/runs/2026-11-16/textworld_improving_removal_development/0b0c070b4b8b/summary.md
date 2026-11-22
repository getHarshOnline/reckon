# TextWorld improving-removal development

The opt-in selector wins one of four fresh games at four slots, while default measured retention, FIFO and utility win none. Seeded random also wins that same game. At two slots every bounded policy scores zero. Full memory wins all four in three actions each. This is a small development result with a high probe cost, not a confirmation, a best-policy finding or an adoption decision.

## Declared scope and retained identity

The [protocol](protocol.md) and [declaration](declaration.json) fixed seeds 65000–65003, all nine existing controls plus `measured_improving`, two/four slots and the 30-step horizon before native execution. All 72 main arms and 5,408 replay episodes completed. The [completion marker](complete.json) and [environment identity](env_meta.json) bind source `c2de08f308e2f674545a276fa6e141bed6579330`, the unchanged `visible_ordered_instructions_v2` controller, adapter/runtime hashes, dependencies, extension and lockfile. The [analysis](analysis.json) retains every outcome vector, paired descriptive difference and per-seed cost.

Both measured arms used the same admissions, controller, signed effects and FIFO continuation. `measured` used `retention-score`; `measured_improving` used the explicit `improving-removal` rule. No cases were replaced or added and no source changed during execution. The original controller-development and sixteen-seed diagnostic results remain unchanged.

The separate [smoke](smoke-64999/complete.json), seed 64999, completed 18 main arms and 1,432 replays. Full memory won in three actions; all bounded arms scored zero. Its inclusive seed/preparation time was 387.118 seconds. The retained smoke copy matches every original source file byte for byte and is excluded from the four-seed totals below.

## Scores and controls

Vectors follow seed order 65000, 65001, 65002, 65003. These observed scores are binary, so their means also equal win fractions. SD is the sample standard deviation across the four outer seeds; it is descriptive, with no interval, significance test or power claim.

| Policy | Slots | Score vector | Wins | Mean | Sample SD |
| --- | --- | --- | --- | --- | --- |
| none | — | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| full | — | 1, 1, 1, 1 | 4/4 | 1.000000 | 0.000000 |
| fifo | 2 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| fifo | 4 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| lru | 2 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| lru | 4 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| random | 2 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| random | 4 | 0, 0, 0, 1 | 1/4 | 0.250000 | 0.500000 |
| importance | 2 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| importance | 4 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| utility | 2 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| utility | 4 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| diversity | 2 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| diversity | 4 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| measured | 2 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| measured | 4 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| measured, improving removal | 2 | 0, 0, 0, 0 | 0/4 | 0.000000 | 0.000000 |
| measured, improving removal | 4 | 0, 0, 0, 1 | 1/4 | 0.250000 | 0.500000 |

At four slots, improving-removal minus default measured, FIFO or utility is `[0, 0, 0, 1]`, mean 0.250000 and paired SD 0.500000. Its difference from random is zero in all four cases. All two-slot contrasts among bounded policies are zero. These equal observed outcomes do not establish policy equivalence. No-memory and full-memory controls are not budget-matched to the bounded arms.

Two slots remain a constrained control: the normal third instruction needs the goal and two earlier action records. Four slots admit those three records, with descriptions and inventory competing for the allowance. All four full-memory controls won in three actions; that observation does not change the realized two-action quests in the earlier diagnostic.

## The one improving selection still loses the goal later

In [seed 65003](seed-65003.json.gz), the first four-slot boundary occurs at pending write ordinal 4. Its existing records are goal description 0, initial inventory 1, `go east` action 2 and new description 3. Removing either 1 or 3 leads to a winning FIFO continuation, while the baseline removes goal 0 and fails. Both signed effects are −1: baseline outcome minus candidate-removal outcome.

The default measured rule removes goal 0 and fails. The opt-in rule chooses inventory 1, the earlier admission among the tied improving candidates. It retains the goal and first action for `take novel from chest`, but loses the goal before the third read. Its actual sequence is `go east`, `take novel from chest`, `close chest`, `drop loaf of bread`, `drop nest of toads`, `drop novel`, winning in six actions. Full memory instead follows `go east`, `take novel from chest`, `drop novel` and wins in three. Random at four slots also wins in six with the same command sequence, although its retained context differs.

The candidate therefore takes one measured improving removal and eventually wins through the subsequent fallback path. It does not establish continuous retention of the goal and progress through the instructed solution. The final-score/FIFO-horizon limitation remains.

| Measured rule | Slots | Positive effects | Negative effects | Zero effects | Replay episodes |
| --- | --- | --- | --- | --- | --- |
| Default retention score | 2 | 0 | 0 | 490 | 980 |
| Default retention score | 4 | 0 | 2 | 950 | 1,904 |
| Improving removal | 2 | 0 | 0 | 490 | 980 |
| Improving removal | 4 | 0 | 2 | 770 | 1,544 |

Across both rules there are 2,704 deterministic candidate pairs: four negative effects, 2,700 zero and none positive. The opt-in rule makes one strictly improving selection. Fewer later probes in its winning arm follow from ending that episode earlier. The pairs are conditional effects under FIFO, whose baseline can itself remove a target; they supply no independent inner trials or evidence that a zero-effect record is irrelevant under every continuation.

## Execution and storage costs

Inclusive arm time already contains replay time. Replay time includes prefix reconstruction and must not be added again. The following seconds sum four main arms per row. Other work shared the machine; these are recorded costs, not an isolated hardware benchmark.

| Policy | Slots | Replay episodes | Inclusive seconds | Replay seconds |
| --- | --- | --- | --- | --- |
| none | — | 0 | 1.442 | 0.000 |
| full | — | 0 | 0.645 | 0.000 |
| fifo | 2 | 0 | 1.033 | 0.000 |
| fifo | 4 | 0 | 1.141 | 0.000 |
| lru | 2 | 0 | 1.140 | 0.000 |
| lru | 4 | 0 | 1.061 | 0.000 |
| random | 2 | 0 | 1.152 | 0.000 |
| random | 4 | 0 | 0.974 | 0.000 |
| importance | 2 | 0 | 1.138 | 0.000 |
| importance | 4 | 0 | 1.059 | 0.000 |
| utility | 2 | 0 | 1.156 | 0.000 |
| utility | 4 | 0 | 1.098 | 0.000 |
| diversity | 2 | 0 | 1.111 | 0.000 |
| diversity | 4 | 0 | 1.058 | 0.000 |
| measured | 2 | 980 | 331.233 | 329.967 |
| measured | 4 | 1,904 | 694.822 | 693.470 |
| measured, improving removal | 2 | 980 | 323.868 | 322.670 |
| measured, improving removal | 4 | 1,544 | 516.189 | 515.009 |

Improving-removal takes 280.10× utility's recorded inclusive time at two slots and 470.22× at four. Random reaches the same four-slot score vector without probes. The four seeds' execution and preparation total 1887.077 seconds, including 5.530 seconds of game preparation. Artifact writing, final verification and other wall-clock overhead are additional.

| Seed | Inclusive seed/preparation seconds | Preparation seconds, already included |
| --- | --- | --- |
| 65000 | 458.114 | 1.825 |
| 65001 | 407.321 | 1.125 |
| 65002 | 700.665 | 1.084 |
| 65003 | 320.977 | 1.496 |

There is no byte cap. Bytes below are recorded payload costs, not process RAM. Counts sum all four main arms; ranges show the smallest and largest per-arm usage. No-memory prunes are immediate baseline discards, not retention selections. Full memory never prunes. The [analysis](analysis.json) retains every individual usage record.

| Policy | Slots | Writes | Prunes | Peak slots | Final slots | Peak bytes |
| --- | --- | --- | --- | --- | --- | --- |
| none | — | 253 | 253 | 1 | 0 | 1894–2401 |
| full | — | 45 | 0 | 9–12 | 9–12 | 4070–5131 |
| fifo | 2 | 253 | 245 | 2 | 2 | 2031–2495 |
| fifo | 4 | 254 | 238 | 4 | 4 | 2596–3453 |
| lru | 2 | 253 | 245 | 2 | 2 | 2031–3311 |
| lru | 4 | 254 | 238 | 4 | 4 | 2658–4007 |
| random | 2 | 253 | 245 | 2 | 2 | 2031–2495 |
| random | 4 | 211 | 195 | 4 | 4 | 2596–3544 |
| importance | 2 | 253 | 245 | 2 | 2 | 2031–2495 |
| importance | 4 | 254 | 238 | 4 | 4 | 2596–3453 |
| utility | 2 | 253 | 245 | 2 | 2 | 2031–2495 |
| utility | 4 | 254 | 238 | 4 | 4 | 2596–3453 |
| diversity | 2 | 253 | 245 | 2 | 2 | 2405–3311 |
| diversity | 4 | 254 | 238 | 4 | 4 | 2596–4041 |
| measured | 2 | 253 | 245 | 2 | 2 | 2031–2495 |
| measured | 4 | 254 | 238 | 4 | 4 | 2596–3453 |
| measured, improving removal | 2 | 253 | 245 | 2 | 2 | 2031–2495 |
| measured, improving removal | 4 | 209 | 193 | 4 | 4 | 2596–3453 |

## Verification and what remains

Retained checks matched all seed and generated-game hashes, the complete 72-arm matrix, actual live backend/controller and rule labels, no-memory discards, full-memory no-prune and bounded-slot invariants, replay episode accounting, actual main pruning events, signed effects and every opt-in improving selection. The stored means, sample SDs and paired vectors match the raw episodes. Native execution checked replay prefixes and pruning boundaries as it ran and required source/game identities to match at completion. Existing output directories are refused before evidence writes.

The opt-in rule now has one observed fresh-game improvement over the default rule, but only four development games, the same observed wins as random and a much larger cost. This closes the declared development execution, not the broader memory comparison or G33 research scope. Representation/admission changes, the FIFO continuation question, MiniGrid's ceiling, wider Causality research, a separately declared confirmation and any learned-policy promotion remain open. Preserve these outcomes and their source identities when choosing the next question.
