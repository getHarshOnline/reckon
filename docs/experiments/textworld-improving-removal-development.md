# Develop selection from measured removal outcomes

The [synthetic development](textworld-controller-development.md#isolated-development-of-an-improving-removal-selector) separates an ignored improving removal from later goal loss under FIFO. The opt-in selector completes two immediate-completion fixtures, while both it and the default fail the fixture whose useful next read is followed by another FIFO loss. This declaration asks whether that isolated selection change produces useful paths in fresh games and records its full cost. It is development, not confirmation, a best-policy claim or adoption.

Review and commit the candidate, this protocol, its [declaration](../../notebooks/experiments/textworld_improving_removal_development.json) and [runner](../../notebooks/experiments/adapter_calibration.py) before native execution. Preserve all completed comparisons and their source identities. Do not extend these seeds, replace a failure or adjust the rule after observing a game to obtain a win.

## Fixed inputs and arms

Reserve seed 64999 for a separate smoke. Use exactly four further development seeds, 65000–65003, excluded from future confirmation. Generate once per seed with the existing three-room, five-object, three-command-quest settings and default unblended house instructions. Retain executable and metadata hashes through every main and replay arm. Record the realized quest, including any two-action quest, rather than assuming the configured length was realized.

Use the `visible_ordered_instructions_v2` controller, the existing description/inventory/action admissions and a 30-step horizon. Reconstruct progress only from actually retrieved records; no hidden plan, metadata solution, walkthrough, model call or prerecorded fallback is allowed. This comparison isolates the ranking change within that controller; it does not estimate a change from the older controller used by the completed diagnostic.

Run no memory and full memory once each. Run FIFO, LRU, seeded random, explicit importance, learned utility, Diversity, default measured retention and the opt-in `measured_improving` arm at two and four slots. This gives eighteen main arms per seed, seventy-two across the four development seeds; the smoke's eighteen are separate. Keep no-memory admission discards, full-memory no-prune checks and the existing importance/random semantics. There is no byte cap; record the actual byte and slot use. Two slots remain a constrained control because the goal and two earlier action records require three slots. Four slots permit those records but still compete with descriptions and inventory.

## Change only the selection rule

Both measured arms use weight 0.5, one deterministic pair per candidate, the same verified main prefix and FIFO continuation in both probe arms. The baseline uses FIFO at the pending write; the intervention removes its candidate first. The signed effect remains baseline outcome minus intervention outcome. Repeated baseline outcomes must agree for the opt-in rule. The baseline can itself remove the candidate; a zero final-score effect can conceal different next actions or later losses under FIFO.

`measured` selects `retention-score`, preserving the existing ranking. `measured_improving` selects `improving-removal`: if an intervention has a strictly higher final outcome than the common baseline, select the candidate with the highest intervention outcome, ties by earliest admission ordinal. Otherwise use the existing ranking. It handles exactly one slot of pressure, with no simultaneous byte or token pressure, and refuses other pressure before probing. No joint-removal benefit is inferred from separate single-record trials. Retain the selected rule in both result evidence levels.

## Keep every outcome and the cost of obtaining it

Retain every main and replay transcript, memory-call journal, boundary digest, candidate ordinal, actual selected removal, all signed effects and source/dependency/extension identities. Pin the committed protocol, declaration, runner, adapters and lockfile. Refuse completion if an input or retained game changes. Preserve incomplete attempts and never overwrite or silently resume one.

Report all ten policies, including zero and adverse outcomes: seed-level scores and wins, mean and sample SD, writes, prunes, bytes and slots. Include descriptive paired vectors against no memory, utility, FIFO and default measured retention where budgets match. Report replay counts, main-inclusive elapsed time and the replay portion, without adding that portion twice; report preparation separately. Shared-machine timings are recorded costs, not isolated hardware performance. No p-values, confidence intervals, power calculation or policy-equivalence claim belong to these four cases.

The synthetic checks establish the refusal paths. The smoke checks native execution, declared rule labels, complete accounting and stable inputs; it need not show a candidate win. After a valid smoke, execute all four declared seeds without changing inputs. Use the runner's `--config notebooks/experiments/textworld_improving_removal_development.json` with `--smoke .codex-tmp/textworld-improving-removal-smoke-64999`, then `--run`. Retain the smoke separately from the four-seed totals.

## What this can settle

Review which measured improvements become actual selections, which survive later writes, and which fail under the unchanged FIFO horizon. Preserve the complete controls even if the candidate does worse. A failure can guide a separately declared development change; it cannot justify replacing a case here. Any later confirmation needs fresh seeds, explicit contrasts and sample-size assumptions. Representation changes, different continuation models, MiniGrid's ceiling, wider Causality research and learned-policy promotion remain separate.
