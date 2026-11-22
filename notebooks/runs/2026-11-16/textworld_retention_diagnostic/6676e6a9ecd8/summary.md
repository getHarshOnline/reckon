# TextWorld retention diagnostic

Measured retention wins one of sixteen games at two slots and three at four slots. It improves over utility by one seed at each budget, but matches FIFO’s complete score vectors and trails random retention at four slots. Full memory wins fifteen games; no memory wins none. These descriptive results preserve both the limited gains and the much larger probing cost, without establishing an overall best policy or a reason to adopt measured retention.

> [!NOTE]
>
> **Diagnostic evidence only.** The [protocol](protocol.md) and [declaration](declaration.json) fixed seeds 64000–64015, all nine policies, two/four slots and the 30-step horizon before execution. Source `dc90275b582db9cbb3d541f1948879cd30a110a0` contains the unchanged visible-instruction controller from `908870781c3a04adf31c50450b6c751eaaf41007`. All 256 main episodes and 10,672 replay episodes completed without replacing cases or tuning the controller, ranking or seeds. There are no primary tests, confidence intervals, power calculations or confirmation claims.

The [completion marker](complete.json) and [analysis](analysis.json) retain source identities, generated game hashes and full seed-level outcomes. The separately retained [smoke](smoke-63999/complete.json), seed 63999, has 16 main and 716 replay episodes; it is excluded from every sixteen-seed total below. It produced one full-memory win and zero scores in the other fifteen arms, with all 358 candidate effects zero.

## Scores and variation

Every row contains sixteen main episodes. Score is binary in these observed games, so its mean also equals the observed win fraction. The standard deviation is the sample SD across the sixteen outer seeds. Winning-seed suffixes below mean 64000 plus the listed number; the underlying vectors, including every zero, remain in the analysis.

| Policy | Slots | Mean score | Sample SD | Wins | Winning seed suffixes | Difference from utility, mean / paired SD |
| --- | --- | --- | --- | --- | --- | --- |
| none | — | 0.000000 | 0.000000 | 0/16 | None | Not budget-matched |
| full | — | 0.937500 | 0.250000 | 15/16 | 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15 | Not budget-matched |
| fifo | 2 | 0.062500 | 0.250000 | 1/16 | 13 | 0.062500 / 0.250000 |
| fifo | 4 | 0.187500 | 0.403113 | 3/16 | 6, 10, 13 | 0.062500 / 0.250000 |
| lru | 2 | 0.000000 | 0.000000 | 0/16 | None | 0.000000 / 0.000000 |
| lru | 4 | 0.062500 | 0.250000 | 1/16 | 10 | -0.062500 / 0.250000 |
| random | 2 | 0.062500 | 0.250000 | 1/16 | 13 | 0.062500 / 0.250000 |
| random | 4 | 0.250000 | 0.447214 | 4/16 | 3, 6, 10, 13 | 0.125000 / 0.341565 |
| importance | 2 | 0.000000 | 0.000000 | 0/16 | None | 0.000000 / 0.000000 |
| importance | 4 | 0.125000 | 0.341565 | 2/16 | 10, 13 | 0.000000 / 0.000000 |
| utility | 2 | 0.000000 | 0.000000 | 0/16 | None | 0.000000 / 0.000000 |
| utility | 4 | 0.125000 | 0.341565 | 2/16 | 10, 13 | 0.000000 / 0.000000 |
| diversity | 2 | 0.000000 | 0.000000 | 0/16 | None | 0.000000 / 0.000000 |
| diversity | 4 | 0.125000 | 0.341565 | 2/16 | 10, 13 | 0.000000 / 0.000000 |
| measured | 2 | 0.062500 | 0.250000 | 1/16 | 13 | 0.062500 / 0.250000 |
| measured | 4 | 0.187500 | 0.403113 | 3/16 | 6, 10, 13 | 0.062500 / 0.250000 |

No memory is zero in every seed, so each row’s mean and sample SD are also its paired mean and SD against no memory. Measured minus utility is +0.062500 at both budgets with paired SD 0.250000: one positive and fifteen zero differences, on seed 64013 at two slots and 64006 at four. FIFO has those same score vectors without probes. Random at four slots also wins seed 64003. Equal observed scores do not establish policy equivalence; for example, measured retention reaches the wins on 64006 and 64013 only at step 30, while FIFO reaches them earlier.

## Capacity and controller limits

> [!IMPORTANT]
>
> **Two slots remain a constrained control.** The normal instructed third action needs the goal and two earlier action records. Two slots cannot retain all three; fallback or current-observation information can still produce a win. Four slots can retain those records, but descriptions and inventory compete for the same allowance. The game generator was configured for a three-command quest; actual seeds 64003 and 64010 expose two-action quests and full memory wins each in two steps. Preserve that realized workload rather than describing every case as a three-action task.

Full memory wins thirteen other cases, including seed 64007 only after seventeen commands. The latter’s second instruction contains a prerequisite about an already opened chest before asking for the mop. The controller’s unordered verb matching sees the earlier opening word first, then falls back; its eventual win does not establish correct instruction parsing. Seed 64008 fails even with full memory: after travelling south and taking the coffee cup, it closes the cabinet instead of inserting the cup into the case. The instruction combines “get your hands on” with “put … inside”; the matcher treats the word “on” as a placement cue and misses the available insertion command. These diagnoses come from the saved visible prompts, admissible commands and source, without rerunning or changing the cases.

The controller reads visible instructions and retrieved action history, with an untried-command fallback when grounding fails. It has no hidden solution, cached plan, metadata walkthrough or model call. Its `fallback_count` field counts model-to-script fallback; zero there does not mean every scripted action followed an instruction. The separate environment and demo fields establish that these episodes used live games. These are narrow assisted games with admissible commands, not general text-game understanding.

## What the candidate removals show

The 5,336 deterministic candidate pairs contain 5 positive, 3 negative and 5,328 zero signed effects. At two slots there is one positive and 1,955 zero; at four there are four positive, three negative and 3,373 zero. A signed effect is FIFO-baseline outcome minus candidate-removal outcome; both continuations use FIFO. The baseline can itself remove the target. These are conditional effects from one pair each, not independent inner trials.

| Seed | Slots | Pending write ordinal | Candidate ordinal | Signed effect | Actual main removal |
| --- | --- | --- | --- | --- | --- |
| 64003 | 4 | 4 | 1 | −1 | 0 |
| 64003 | 4 | 4 | 3 | −1 | 0 |
| 64004 | 4 | 4 | 2 | −1 | 0 |
| 64006 | 4 | 56 | 55 | +1 | 54 |
| 64006 | 4 | 57 | 55 | +1 | 56 |
| 64006 | 4 | 58 | 55 | +1 | 1 |
| 64006 | 4 | 58 | 57 | +1 | 1 |
| 64013 | 2 | 58 | 57 | +1 | 4 |

At the three negative pairs, the candidate-removal continuation wins while the FIFO baseline fails. The main ranking instead removes ordinal 0, the original goal description. The current score gives negative measurements no retention bonus; it does not subtract their magnitude as a removal preference. The positive pairs occur late in the 30-step episodes and preserve records whose removal would prevent the FIFO continuation’s win. A zero final-score effect can hide differing intermediate actions or later losses under FIFO, as the earlier controller-development smoke demonstrated. It is not evidence that a record would be irrelevant under every continuation.

## Execution and storage costs

Inclusive seconds already contain replay seconds. Replay time includes prefix reconstruction and continuation and must not be added twice. Times below sum sixteen main arms per row. Early cases overlapped unrelated local archive encryption and copying; other machine activity was not controlled. These are recorded execution costs, not an isolated hardware benchmark.

| Policy     | Slots | Replay episodes | Inclusive seconds | Replay seconds |
| ---------- | ----- | --------------- | ----------------- | -------------- |
| none       | —     | 0               | 4.023858          | 0.000000       |
| full       | —     | 0               | 2.382703          | 0.000000       |
| fifo       | 2     | 0               | 3.624216          | 0.000000       |
| fifo       | 4     | 0               | 3.889698          | 0.000000       |
| lru        | 2     | 0               | 3.860734          | 0.000000       |
| lru        | 4     | 0               | 3.585131          | 0.000000       |
| random     | 2     | 0               | 3.880234          | 0.000000       |
| random     | 4     | 0               | 3.471407          | 0.000000       |
| importance | 2     | 0               | 3.788152          | 0.000000       |
| importance | 4     | 0               | 5.233292          | 0.000000       |
| utility    | 2     | 0               | 3.867073          | 0.000000       |
| utility    | 4     | 0               | 3.845218          | 0.000000       |
| diversity  | 2     | 0               | 3.766342          | 0.000000       |
| diversity  | 4     | 0               | 3.797014          | 0.000000       |
| measured   | 2     | 3,912           | 1028.318478       | 1024.377187    |
| measured   | 4     | 6,760           | 1803.517281       | 1799.583639    |

Measured retention takes 265.92× and 469.03× utility’s recorded inclusive time at two and four slots. Inclusive seed execution and game preparation total 2902.814708 seconds, including 17.706768 seconds of game preparation. Artifact writing and verification add further wall time. The reserved smoke separately records 195.265206 inclusive seed/preparation seconds and 1.955541 preparation seconds.

The following counts cover main-store events. No-memory prunes are immediate baseline discards, not retention-policy selections. Byte ranges are minima and maxima across the sixteen episode measurements; they are record payload costs, not process RAM. There is no byte cap. Limited arms peak and finish at their two/four-slot allowance; full memory peaks and finishes at 7–65 slots with no prunes; no memory transiently peaks at one slot and finishes empty.

| Policy | Slots | Writes | Prunes | Baseline discards | Peak bytes, min–max | Final bytes, min–max |
| --- | --- | --- | --- | --- | --- | --- |
| none | — | 1,009 | 1,009 | 1,009 | 1,781–2,591 | 0–0 |
| full | — | 257 | 0 | 0 | 3,645–20,589 | 3,645–20,589 |
| fifo | 2 | 960 | 928 | 0 | 1,900–2,671 | 337–681 |
| fifo | 4 | 861 | 797 | 0 | 2,360–3,345 | 685–1,621 |
| lru | 2 | 1,009 | 977 | 0 | 1,900–3,162 | 536–1,230 |
| lru | 4 | 957 | 893 | 0 | 2,382–3,627 | 805–2,460 |
| random | 2 | 966 | 934 | 0 | 1,963–2,792 | 365–1,042 |
| random | 4 | 817 | 753 | 0 | 2,360–4,109 | 627–3,454 |
| importance | 2 | 1,009 | 977 | 0 | 1,900–2,671 | 344–715 |
| importance | 4 | 908 | 844 | 0 | 2,360–3,345 | 489–1,152 |
| utility | 2 | 1,009 | 977 | 0 | 1,900–2,671 | 344–715 |
| utility | 4 | 908 | 844 | 0 | 2,360–3,345 | 219–1,152 |
| diversity | 2 | 1,009 | 977 | 0 | 2,214–3,162 | 536–1,230 |
| diversity | 4 | 908 | 844 | 0 | 2,360–3,667 | 681–1,373 |
| measured | 2 | 1,010 | 978 | 0 | 1,900–2,671 | 67–715 |
| measured | 4 | 909 | 845 | 0 | 2,360–3,345 | 219–1,152 |

## Verification and next work

Checks reproduced all sixteen seed-file hashes, input and game identities, the expected arm matrix, full-memory no-prune and immediate no-memory-discard invariants, every replay prefix and boundary digest, actual selected removals and complete aggregate accounting. The reserved smoke was copied into this result with every source byte unchanged. Original generated games, including their formatting, remain intact. No source code changed after declaration or during execution.

The bounded policies have some spread, but measured retention supplies no observed score advantage over FIFO and still pays for thousands of replays. The saved cases also expose remaining language-grounding errors, competition between repeated descriptions and task progress, and the limitations of final-score effects under FIFO continuation. Those are the next development questions to review before proposing a new comparison. Keep two-slot capacity constraints and realized two-action quests visible. Do not extend this sample or tune the completed cases to obtain a winner. A later controller, representation or ranking change needs its own declaration, development and fresh comparison; no confirmation, adoption or resumption of paused Causality mathematics follows from this diagnostic.
