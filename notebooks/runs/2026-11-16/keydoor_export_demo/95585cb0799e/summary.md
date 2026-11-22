# Key-door export demonstration

Three episodes executed once on 16 November 2026 from Reckon source `06e01a1c75d6879cc604e0b53307af954da38c95`, using the native `KeyDoorTask`, `CausalMemoryManager` and JSONL event exporter. Seed 42, FIFO, one slot and 50,000 bytes were chosen before execution. Memory and utility learning carry across episodes; no record probes or comparison arms run. The [configuration](config.json), [executed script](runner.py), [task result](result.json), [import metadata](summary.json), [source and environment identities](env_meta.json) and [kernel lockfile](kernel.Cargo.lock) retain the inputs and outputs.

| Episode       | Cue read back | Correct door    | Outcome |
| ------------- | ------------- | --------------- | ------- |
| `keydoor_ep0` | Green         | Right, `(3, 3)` | Failure |
| `keydoor_ep1` | Blue          | Right, `(3, 3)` | Success |
| `keydoor_ep2` | Blue          | Right, `(3, 3)` | Success |

Each episode wrote and retrieved its own cue once. The controller chooses right for a retrieved blue cue and otherwise guesses left; it does not try the other door after a failed guess. Green leaves the door random, so remembering green did not identify the right door in the first episode. Two successes out of three describe these episodes only. One slot holds the current cue until its read; the two FIFO removals replace earlier episodes’ records. This demonstration supplies no retention-policy ranking or causal comparison.

## Follow the saved events

The [native log](logs/events.jsonl) contains 11 events: three writes, three reads, three utility updates and two removals. Event IDs run from 0 through 10. For the first blue cue, write event 4 at logical step 24 names record `b4b5c6bb-df57-4f6f-ac60-da08406783e8`; read event 5 at step 26 returns that same ID, score-update event 6 records utility 0.1 after the successful episode, and removal event 7 replaces it during the next episode. The first removal and next write share step 24 with sequences 0 and 1; the following replacement uses step 33 in the same order. These are the logger’s logical steps, not wall-clock times.

The log records activity and partial counters, without full record payloads or a grid trajectory. Its zero `slots_after` fields do not measure an empty store. The separate [final record](final_records.json) retains the last surviving blue cue, ID `795ba66d-e0d1-44d8-868a-91e56b38011b`; it does not add snapshots to earlier events. Read the episode result for the observed cue and outcome, and the native task source for the controller’s movement rule.

## Environment

The run used Python 3.13.13, NumPy 2.4.2 and SciPy 1.17.0 with the existing importable Rust extension. Its binary and runtime source hashes match the [preceding retained laboratory run](../../textworld_improving_removal_development/0b0c070b4b8b/env_meta.json). This is execution evidence for that environment, not qualification of every supported interpreter. `wall_time_ms` in the import metadata measures the task call only, excluding setup and file writes.
