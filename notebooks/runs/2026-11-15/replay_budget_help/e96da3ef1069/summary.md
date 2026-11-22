# Replay budget worked example

Six one-episode continual-classifier runs from source `3d3aea6`, using the help page’s complete script with explicit FIFO. Each episode has three tasks, 60 training and 60 test samples per task, paired seeds 41–43 and two/sixteen slots with 50,000 bytes.

| Seed | Two slots | Sixteen slots | Difference (percentage points) |
| ---- | --------- | ------------- | ------------------------------ |
| 41   | 0.811111  | 0.827778      | +1.666667                      |
| 42   | 0.822222  | 0.800000      | -2.222222                      |
| 43   | 0.811111  | 0.838889      | +2.777778                      |

The three pairs are exploratory. They do not establish a policy ranking or general budget benefit. No probes run. All six configurations, results, summary metadata and raw event logs remain here, alongside [the CSV](comparison.csv), [executed script](runner.py), [source/environment identity](env_meta.json) and captured kernel lockfile. The two imports for seed 41 succeeded with 27 and 22 displayable events, respectively; the other raw logs contain 28/20 events for seed 42 and 38/35 for seed 43. The current server projection supports these numeric identities; this example did not repeat the separate browser qualification.
