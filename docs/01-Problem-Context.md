# Problem and Context

A task gets a clue early and a reward much later. If it can keep only a few observations, which should it save? Reckon lets you change how a task keeps records and measure the consequences, including what it costs to find out which records helped.

## The failure mode

Consider the laboratory's [key-and-door task](./09-Tasks-Benchmarks.md). The agent sees a coloured key near the start, but needs its colour later to choose a door. The task writes the cue, retrieves it before choosing and reports the reward afterwards. A log can show that the cue was returned. Finding out whether it changed the outcome takes a comparison with the cue unavailable.

That example makes the memory path easy to follow. The supplied controller writes only one cue and uses it before writing another, so one slot is enough; it cannot tell you which retention rule handles competing clues better. Other [benchmark tasks](./09-Tasks-Benchmarks.md) put different demands on memory, such as keeping training examples to practise an earlier skill.

In reinforcement learning, continual learning and agent loops, the same kind of observation can arrive under different conditions. A record may become less useful as the agent's representation changes. Keeping everything eventually exhausts resources, while discarding the oldest record can lose a clue before it is needed. Delayed rewards make it harder to assign credit, and a successful run alone does not reveal which remembered thing made the difference.

Reckon's thesis connects these failures: memory, measurement and intervention are resource-bounded, but the system may not model those limits explicitly. The budget changes what the agent can know and test, not just how much storage it needs.

## The proposal

Describe a record together with what it costs to keep, and an intervention together with what it costs to perform. In the research model, the resource vector R includes memory in slots, tokens or bytes; bandwidth, latency and compute per step; the noise floor and precision of records; locality constraints; and whether logging is available at all. These limits govern both what the agent can do and what it can find out by doing it.

Under R, the agent can produce reliable records of only some events and perform only the allowed interventions. Causality is therefore relative to what that agent can record and do: which interventions produce a detectable change in a later record? The same resource limits shape how far back the agent can recover a past state and which records are worth their cost. The [framework overview](./02-Framework-Overview.md) links each question to the theory and the code.

## Success criteria

The research goal is better performance at a fixed budget on laptop-scale tasks, with the improvement surviving changes in the task. Use operation logs to locate the records a task retrieved, then compare outcomes when a record is removed or replaced. Count the extra trials and time spent measuring: a retention rule can improve the task's result while costing too much to be useful. The [benchmark account](./09-Tasks-Benchmarks.md) keeps the completed comparisons and their limits; the broader benefit remains a question to test.

## Implementation

To connect these ideas to your own task, [follow one delayed cue through the Python API](../src/reckon/README.md#connect-retrieval-to-an-outcome), from a write to a later retrieval and score update. Then read [how the memory manager works](./08-Causal-Memory-Manager-Design.md) to choose what survives when its allowance fills. The [memory module](../src/reckon/memory/README.md) leads to the exact types and implementation.
