# TextWorld controller development

The repaired scripted controller wins all four declared development games with full memory, each in three actions. The separate smoke also wins with full memory. No memory, utility and measured retention at two and four slots still score zero in every main episode. The repair establishes a working control on these cases; it does not establish a measured-retention benefit.

> [!NOTE]
>
> **Development evidence.** These cases test a narrow controller for the generated game’s visible, unblended instructions. They are not a confirmation sample or an arbitrary text-game benchmark. Keep their seeds out of any later confirmation, and preserve the bounded-memory failures when designing the next comparison.

The [protocol](protocol.md), [declaration](declaration.json) and controller were committed at `908870781c3a04adf31c50450b6c751eaaf41007` before these outcomes. Seeds 63000–63003 completed exactly as declared: six arms per seed, 24 main episodes and 2,872 replay episodes. The [smoke evidence](smoke-62999/complete.json) retains the separate seed 62999: six main episodes and 728 replay episodes. No case was replaced, no controller or policy changed during either run, and no model or prerecorded fallback supplied an episode. The [completion marker](complete.json) and [analysis](analysis.json) preserve the input identities, seed hashes and complete vectors.

## What changed in the controller

The former selector ignored the printed quest and chose the first admissible command it had not retained as tried. Saved calibration episodes show examinations, dropped objects and wandering even with full memory. Once available commands were exhausted it repeated the first one; its global tried set also prevented intentional reuse. Those completed results remain tied to their original source and are unchanged.

The current selector grounds each visible instruction’s verb and object names in the admissible commands, and reconstructs instruction progress from the retrieved action records in timestamp order. It can reuse a command when a later instruction calls for it. The initial description supplies the goal; pruning it removes the remembered goal. There is no hidden cached plan, solution walkthrough, metadata-derived action sequence, policy-command oracle or intermediate-reward advice. The old untried-command fallback remains when grounding fails, so unsupported prose can still loop. This is the default unblended house grammar, not general language understanding.

The normal instructed path to the third action requires the goal record and two earlier action records. Two slots cannot retain all three, so that arm is a constrained control; success there depends on fallback or current-observation information. Four slots can hold those three records, and the retained winning removal below establishes a successful four-slot continuation on one development game.

| Development seed | Full-memory commands | Outcome |
| --- | --- | --- |
| 63000 | go south; go east; take broom | Win in 3 steps |
| 63001 | go east; take type B keycard from bed stand; lock type B box with type B keycard | Win in 3 steps |
| 63002 | take broom from rack; go east; put broom on mantelpiece | Win in 3 steps |
| 63003 | take latchkey from coffer; go east; unlock box with latchkey | Win in 3 steps |

## All arms and costs

Each development row has four main episodes. Times include all four episodes on this machine. Replay time is already inside inclusive time and must not be added again; it includes both prefix reconstruction and continuation. These are development observations, with no p-values, confidence intervals or power claim.

| Policy | Slots | Mean score | Wins | Replay episodes | Inclusive seconds | Replay seconds |
| --- | --- | --- | --- | --- | --- | --- |
| none | — | 0.0 | 0/4 | 0 | 1.305031 | 0.000000 |
| full | — | 1.0 | 4/4 | 0 | 0.774245 | 0.000000 |
| utility | 2 | 0.0 | 0/4 | 0 | 1.511018 | 0.000000 |
| utility | 4 | 0.0 | 0/4 | 0 | 1.436162 | 0.000000 |
| measured | 2 | 0.0 | 0/4 | 976 | 418.114550 | 416.551624 |
| measured | 4 | 0.0 | 0/4 | 1,896 | 728.051102 | 726.622467 |

Measured retention takes 276.71× and 506.94× utility time at two and four slots, with no main-score gain here. Inclusive seed execution and game preparation total 1158.739135 seconds, including 7.116039 seconds of game preparation. Artifact saving and checking add further wall time. All baseline costs, usage counts and raw outcomes remain in the analysis.

## What the retained replays show

The four development games contain 1,436 candidate pairs: 1,435 zero effects, one negative effect and no positive effects. In seed 63000 at four slots, pending write ordinal 4, removing description record ordinal 2 produces the winning command sequence while the FIFO baseline scores zero. Its signed effect is therefore −1. The main policy instead removes ordinal 0, the original task description. The current ranking rewards beneficial retention effects and does not subtract a penalty for a negative effect, so this observed winning removal is not selected. The controller repair leaves that policy rule unchanged; changing it would require a separately declared candidate and comparison.

The smoke illustrates a second limit. At four slots, the first actual prune discards the task description. Removing another candidate in a replay preserves that description long enough to take the correct second action, but the later FIFO continuation still prevents the final win. All 364 smoke effects are therefore zero, although the intermediate actions differ. A zero conditional effect does not establish that the record is irrelevant under other future retention choices.

Every arm uses the same generated game executable and metadata for its seed. Verification reproduced all saved seed and game hashes, input identities, main-arm counts, full-memory no-prune and immediate no-memory discard invariants, every replay prefix and boundary digest, selected actual removals, and the complete cost and outcome aggregation. The original game inputs remain byte-for-byte records, including generated formatting. The source checks passed 36 focused tests, Pyright with no errors and locked offline Cargo checking.

## Proposed next comparison

> [!IMPORTANT]
>
> **Keep the next step a calibration.** A successful full-memory control now exists on these development cases, but bounded-memory performance and policy spread still need measurement. A confirmation sample must be declared separately after that evidence is reviewed.

Propose fresh calibration seeds 64000–64015 with reserved smoke 63999, unchanged three-room/five-object/three-command games, 30-step horizon and two/four-slot budgets. Treat two slots as the constrained control described above, not a capacity sufficient for the normal third-instruction path. Run all nine policies: no memory and full memory once each, then FIFO, LRU, random, importance, utility, Diversity and measured retention at both budgets, giving 16 arms per seed and 256 main episodes. Keep the controller and current weight-0.5, one-pair FIFO-continuation rule fixed, retain every generated game and paired outcome, and report full probe costs. The additional baselines may expose limitations that utility alone cannot distinguish; do not tune the budget or ranking to obtain a win.

That calibration would estimate outer-seed variation and reveal whether the bounded arms remain at a floor. Preserve a null or adverse answer. If the bounded task still cannot distinguish the policies, diagnose its workload or continuation limits before proposing a larger confirmation. Neither these development results nor that proposed calibration settle adoption, MiniGrid’s ceiling or the wider research hypothesis. No new calibration or confirmation has run as part of this development.
