# Reckon Notebooks

Notebooks for exploring memory management under resource budgets, from small demonstrations to configurable experiments. Choose a notebook for your question, then check which backend and outcome it uses.

## Quick Start

Complete [installation](../docs/01a-Installation.md#set-up-the-environment) first, including the explicit CPython 3.11 environment and extension import check. The commands below assume that environment is active and start from the repository root.

Install the notebook runner, table and plotting dependencies:

```bash
python -m pip install ".[notebooks]"
(cd notebooks && jupyter lab 00_quickstart_demo.ipynb)
```

Install optional environment integrations only for the notebook you plan to run; see [Optional dependencies](#optional-dependencies). They are not needed to build the memory kernel. If the extension import fails, follow the [kernel build procedure](../kernel/README.md#python-extension). The convenience [setup helper](../setup.sh) always targets its own `.venv`, even when another environment is active; see the [installation note](../docs/01a-Installation.md#set-up-the-environment) before using it.

:::accordion "Try the notebook adapters from a terminal"

## Small command-line demonstrations

Try the notebooks' core functionality from the repository root with the project environment active. Each subshell returns to that root before the next example:

```bash
# Demo 1: Reckon memory basics
(cd notebooks && python -c "
from reckon.memory import CausalMemoryManager, PayloadType
from reckon.core.resources import MemoryBudget

cmm = CausalMemoryManager(MemoryBudget(max_slots=10, max_bytes=1000), episode_id='demo')
cmm.write({'obs': 'key in room A'}, PayloadType.OBSERVATION, tags=['key'])
cmm.write({'obs': 'door locked'}, PayloadType.OBSERVATION, tags=['door'])
print(f'Stored {cmm.current_usage_slots} records')
print(f'Key records: {len(cmm.retrieve(query={\"tags\": [\"key\"]}))}')
")

# Demo 2: Tool-using conversation (notebook 04 core)
(cd notebooks && python -c "
from _utils.adapters import ToolEnv, get_demo_episodes
env = ToolEnv()
obs, info = env.reset(seed=42)
print(f'Episode constraints: {info[\"constraints\"]}')
print(f'First user message: {obs[:100]}...')
response = {'tool': None, 'final': 'I understand.', 'memory_write': []}
obs, reward, done, _, _ = env.step(response)
print(f'Reward: {reward}, Done: {done}')
")

# Demo 3: Optional environment-registry adapter
(cd notebooks && python -c "
from _utils.adapters import get_env, check_env_available
print(f'MiniGrid available: {check_env_available(\"minigrid_memory\")}')
env, is_real = get_env('minigrid_memory', fallback=True, verbose=True)
obs, info = env.reset(seed=42)
print(f'Observation type: {type(obs).__name__}')
")

# Demo 4: Ollama check (notebook 04 LLM backend)
(cd notebooks && python -c "
from _utils.adapters import ollama_healthcheck, OLLAMA_AVAILABLE
if OLLAMA_AVAILABLE:
    print('Ollama is running and ready!')
else:
    print('Ollama not running - notebooks will use simulated backend')
    print('Start ollama serve, then run ollama pull llama3.2 in another terminal')
")
```

:::

## Run Modes

Every notebook has a `RUN_MODE` variable at the top:

| Mode | Purpose | Runtime | Dependencies |
| --- | --- | --- | --- |
| `"demo"` | Smaller demonstrations and experiments | 1-5 min estimate | Project environment; extras depend on the selected backend |
| `"paper"` | Larger configured samples and available comparison routines | 10-60 min estimate | Same core environment; extras depend on the selected backend |

The mode changes configured sample counts and selected analysis branches; it does not certify a result. A repeated fixed trace, scripted response or generated score remains that kind of demonstration in either mode. Live episodes, pairing, independence, sample size and the measured outcome must support any statistical interpretation. Notebook 05 requires the real MiniGrid environment. Notebook 06 labels its fixed trace when TextWorld is absent and does not treat that replay as independent game trials.

## Notebook Index

Unlinked source paths below are relative to the repository root. Open those original notebooks, experiment accounts and saved run summaries from your checkout; they have not yet been published with this manual. Public source links will follow publication of the reviewed files. Each run’s complete evidence stays beside its summary.

| # | Notebook | Purpose | Key Features | Estimated runtime (demo/paper) |
| --- | --- | --- | --- | --- |
| 00 | `notebooks/00_quickstart_demo.ipynb` | One episode and its recorded outputs | Single run, debugger integration | 2m / 5m |
| 01 | [01_system_overview_math_to_code.ipynb](01_system_overview_math_to_code.ipynb) | Math to code mapping, architecture | Theory walkthrough, diagrams | 3m / 3m |
| 02 | [02_policy_bakeoff_keydoor_scaled.ipynb](02_policy_bakeoff_keydoor_scaled.ipynb) | Four rules with fixed oracle utility | Synthetic key retention; no learned utility or measured effects | 5m / 30m |
| 03 | [03_contract_evaluation_executable.ipynb](03_contract_evaluation_executable.ipynb) | Verify a record removal | Native evaluator, paired evidence, measured episode/time cost | Under 1m locally / under 1m locally |
| 04 | [04_agentic_conversation_simulator.ipynb](04_agentic_conversation_simulator.ipynb) | Dialogue memory demo | Ollama integration, tool-use env | 3m / 15m |
| 05 | [05_rl_env_adapter_minigrid.ipynb](05_rl_env_adapter_minigrid.ipynb) | Memory at the final fork | Live corridor controller, masked cue, read controls | 3m / 20m |
| 06 | [06_text_env_adapter_textworld.ipynb](06_text_env_adapter_textworld.ipynb) | Memory at command selection | Live game identity, retrieved context, score increments | 3m / 15m |
| 07 | [07_scaling_and_perf_envelope.ipynb](07_scaling_and_perf_envelope.ipynb) | Performance benchmarks | Synthetic workloads; configured scales to 100k records | 10m / 60m |

## Read the saved experiments

Live notebook source and recipes use `EvidencePerBytePolicy` and `evidence_weight`. Retained cell outputs and saved runs keep their original policy names, configuration hashes and source revisions; the source rename does not re-execute those results. Use the saved revision and its copied plan for historical reproduction. New configuration hashes reflect the current field names.

### 03: A record-removal fixture

Notebook 03 uses `CausalRecordEvaluator` on a seeded synthetic task. The key colour is generated anew for each paired seed, and the manager physically removes the selected record at its read boundary. Key, distractor, retrieved-but-ignored summary and hint cases retain native trial evidence. The trial-count plot measures classification against the fixture’s known labels and counts both probe arms; the curve comes from executed trials, with base episodes counted only when run. The 14 November demo (`notebooks/runs/2026-11-14/03_contract_evaluation/21426180c10d/summary.md`) retains the actual results, figures and source digest. Its 5 base episodes and 220 probe episodes are execution evidence for that fixture, not a performance claim about another task. The paper-mode run (`notebooks/runs/2026-11-14/03_contract_evaluation/45232de57285/summary.md`), executed with `RUN_MODE="paper"`, retains 20 base and 1,220 probe episodes under the same fixture. Per-record tests are unadjusted. The [evaluation protocol](../docs/11-Evaluation-Metrics.md#evaluation-protocol) defines the single-instance intervention and its limits.

### 04: Literal recall in conversation

Notebook 04 answers from the current message and retrieved records. Its scripted backend recognizes the generated templates and quotes remembered requirements; the score measures literal recall in the final answer, not prose compliance. The demo run (`notebooks/runs/2026-11-14/04_conversation_simulator/ecd23fabae26/summary.md`) has 80 policy-comparison episodes and 10 context controls; the paper run (`notebooks/runs/2026-11-14/04_conversation_simulator/3ccd39a9de41/summary.md`) has 320 comparison episodes and 40 controls. Both also execute three inspection episodes. Context controls use fresh memory for each arm: supplying retained context recalls every requirement, while withholding it recalls none. Transcripts include retrieved IDs and the actual memory prompt. Policy scores remain assigned priorities and learned utility, with no measured retention effects. The optional live Ollama path has only been checked with a stubbed model call.

### 05: Remembering the object at a fork

Notebook 05 reads the actual step-zero object record at the fork of a real MiniGrid MemoryS7 episode. Its controller knows the corridor geometry and masks the starting object from every later controller observation. The demo (`notebooks/runs/2026-11-14/05_minigrid_adapter/a6ad14486cda/summary.md`) has 160 comparison and 20 control episodes; paper mode (`notebooks/runs/2026-11-14/05_minigrid_adapter/55c842051d20/summary.md`) has 480 and 60. Both also execute one inspection episode. All control episodes with retrieval succeed; withholding retrieval produces 50% success under the declared seeded branch fallback. The result tests retention at that decision, not learned navigation. Policy scores are assigned priorities; final outcome credit arrives after the decision.

### 06: TextWorld command selection

Notebook 06 retrieves descriptions, inventory and retained action history before each command. The current scripted selector follows visible ordered instructions and permits a command to repeat when the task requires it. Only its untried-command fallback avoids commands found in retained history; the optional model receives the same context. The TextWorld adapter uses the documented Filter interface, seeds game generation and credits changes in cumulative score. Comparisons reuse one generated game per seed, with executable and metadata digests retained. These are slot-limited text experiments; results report their absent byte limit and actual final bytes. The following saved runs use the earlier untried-command selector. The 15 November demo (`notebooks/runs/2026-11-15/06_textworld_adapter/50c6690d52af/summary.md`) records 80 live comparisons, two context controls, one live inspection and one labelled fixed-trace inspection. All live comparisons and controls record zero wins. The controls use the same game and retain all writes: context changes the command sequence without producing a win. The paper run (`notebooks/runs/2026-11-15/06_textworld_adapter/f2d0ee019e56/summary.md`) records 240 comparisons with the same two controls and two inspections, also with zero wins. Live model use remains unverified.

## Probe one record in a notebook episode

Notebooks 04–06 also run a separate paired ablation through the native evaluator. Each arm starts a fresh episode under FIFO with 100 slots. The experiment removes the first matching constraint record in the simulated conversation, the initial MiniGrid cue, or the first TextWorld action record immediately before its first eligible read. Matched record digests and read ordinals verify the target; a missing or ambiguous target fails. Later replacements remain allowed. TextWorld additionally checks matching game and metadata hashes between arms.

```python
from _utils.adapters.record_probe import AdapterProbeConfig, evaluate_adapter_record

result = evaluate_adapter_record(
    AdapterProbeConfig("minigrid", budget_slots=100, max_steps=100),
    "initial_object",
    lambda record: "initial_cue" in record.tags,
    n_trials=20,
    seed_base=1000,
)
print(result["evaluation"]["delta"], result["confidence_interval"])
print(result["probe_episodes"], result["probe_elapsed_s"])
```

Run this from the notebooks directory or add that directory to the Python import path as the notebooks do. The same entry accepts `conversation` and `textworld`. Conversation uses the simulator and literal final-answer recall, MiniGrid uses its declared corridor controller and success, and TextWorld uses the scripted selector and final game score. Live game dependencies are required; prerecorded traces and model fallbacks cannot supply paired evidence.

The reference policy must choose records without running further episodes. `MeasuredRetentionPolicy` and its subclasses are refused before an episode starts. A custom policy supplied through `policy_factory` must follow the same requirement; arbitrary caller code can conceal nested work that this runner cannot count. The reported episode total counts the adapter arms, so it does not account for hidden episodes in a custom policy that breaks this contract. The notebooks use FIFO.

Each `record_probe.json` contains the protocol, policy configuration, both arms' outcomes and transcripts, record-removal evidence, peak record bytes and slots, and all executed episode/time costs. The normal-approximation interval and paired sign-permutation test are across episode seeds, with no correction across record labels. Demo mode runs four pairs and paper mode twenty; neither name implies a powered experiment. These probes measure removal at a read, separately from the policy comparison. They do not set online retention scores, and a zero game-score difference with a controller that never wins does not establish memory equivalence. Adapter callers can supply fresh, empty memory through the keyword-only `memory` argument; a mismatched budget or policy is refused without replacing that manager or its hooks. The repository carries each run's summary, protocol and environment. Per-seed results, transcripts and record probes are written beside them when you run an experiment and are not committed.

The complete 15 November executions below used the source recorded in each run's `env_meta.json`, with the probe settings described above. Each saved run includes the original policy comparisons and context controls as well as its separate record-removal experiment. Source hashes and the paired TextWorld game hashes match the retained files.

| Notebook | Demo run | Paper-mode run | Mean removal effect in paper mode |
| --- | --- | --- | --- |
| Conversation | 4 pairs (`notebooks/runs/2026-11-15/04_conversation_simulator/045229537dbf/summary.md`) | 20 pairs (`notebooks/runs/2026-11-15/04_conversation_simulator/0d152b9a4b6e/summary.md`) | 0.3917 less literal constraint recall |
| MiniGrid | 4 pairs (`notebooks/runs/2026-11-15/05_minigrid_adapter/a9e2b54ca058/summary.md`) | 20 pairs (`notebooks/runs/2026-11-15/05_minigrid_adapter/88f3e6cdedb8/summary.md`) | 0.7000 less success |
| TextWorld | 4 pairs (`notebooks/runs/2026-11-15/06_textworld_adapter/b1549049532d/summary.md`) | 20 pairs (`notebooks/runs/2026-11-15/06_textworld_adapter/e3ce4299c21f/summary.md`) | 0.0000 change; both arms average 0.05, with one win each |

The effect is the baseline outcome minus the outcome after removing one record. Together these runs execute 144 probe episodes, with their time charged separately from the main comparisons. The two positive differences concern the named records and controllers. TextWorld's demo probe scores are all zero; its larger probe set includes a game both arms win, while their outcomes still match within every pair. This does not establish equivalence. These are the declared four- and twenty-pair experiments, not the still-open powered policy comparison or live-pruning integration.

Dictionary metrics export through the standard CSV writer, so notebooks 03–06 do not import pandas. Other notebooks still use it for their tables. Game adapters load only when requested; an installed MiniGrid or TextWorld integration cannot block an unrelated conversation import.

## Select a live prune with an episode replay

The [live retention runner](_utils/adapters/live_retention.py) measures a candidate removal from the current episode. It restarts the same deterministic controller and environment seed, repeats the actual earlier pruning choices, and verifies the memory-call history and candidate state at the pending write. This reconstructs the controller's local variables, random stream and credit context through execution. It does not transplant records into a new task. The recorder compares writes, reads, returned records, credit inputs, logical steps, budgets and candidate metadata; record IDs are matched by admission order. A differing prefix or missing boundary fails the run.

```python
from _utils.adapters.live_retention import run_replay_retention_episode
from _utils.adapters.record_probe import AdapterProbeConfig

result = run_replay_retention_episode(
    AdapterProbeConfig("minigrid", budget_slots=2, max_steps=100),
    seed=60001,
)
print(result["outcome"], result["probe_episodes"])
```

At the pending write, the baseline follows FIFO. The intervention removes the named candidate first and then uses FIFO if more capacity is needed; both continuations use FIFO afterward. The difference is baseline outcome minus intervention outcome. The baseline may itself remove the candidate, so this is an effect under a bounded continuation policy, not guaranteed retention versus removal. The evidence-per-byte rule mixes learned utility with the beneficial part of that difference at weight 0.5; signed differences remain in the evidence, including zero and adverse results. Each live decision ranks the actual candidates and removes only the selected records in the main store. Probe stores cannot change it.

Conversation uses the scripted literal-recall controller, MiniGrid uses its known-corridor controller, and TextWorld uses the scripted command selector. TextWorld additionally requires an existing generated `game_file`, with executable and metadata hashes checked for every arm. A comparison passes the identity pinned at generation through `expected_game_identity`, so separate policy arms cannot silently accept changed game bytes. Model calls and prerecorded fallback episodes are refused. This route does not establish a game-solving improvement for TextWorld's limited selector.

Each candidate executes one deterministic pair. Repeating that pair would repeat the same fixed future; it cannot supply independent samples, a p-value or a within-episode confidence interval. A policy comparison still needs a declared sample of independent outer episodes and appropriate uncertainty across those episodes. The result retains every arm's transcript, memory-call journal, boundary digest, chosen removals, outcome and elapsed time. Probe counts and time include full prefix reconstruction as well as continuation. The main elapsed time already includes the probes and must not be added to them again. The 60001 examples and integration checks are development fixtures, excluded from later comparisons. Saved native comparisons and the separate read-boundary ablations above remain unchanged; the Conversation confirmation (`docs/experiments/conversation-retention-confirmation.md`) declares its fresh outer seeds separately.

The fixed sixteen-seed calibration (`notebooks/runs/2026-11-16/adapter_retention_calibration/b4ec292d870a/summary.md`) completes nine policies, giving sixteen arms per adapter and seed, with 768 main and 14,232 replay episodes. Conversation gains 0.052083 literal recall over utility at both budgets, from two improving seeds each, with paired SD 0.145535 and 89×/123× inclusive time. LRU has higher observed recall than measured retention at two slots. MiniGrid measured, utility and importance all succeed in every seed; TextWorld records zero score and wins in every main arm, with zero differences in all 5,620 candidate comparisons. This calibration measures variation and cost; it establishes neither a confirmed conversation gain nor policy equivalence. That calibration left the controller repair to the separate development below. The fixed Conversation confirmation (`notebooks/runs/2026-11-16/conversation_retention_confirmation/df3d0053c39f/summary.md`) completes all 256 fresh seeds: 4,096 main and 26,972 replay episodes. Measured minus utility is 0.061849 at two slots and 0.048828 at four, with 97.5% intervals [0.040447, 0.083251] and [0.030164, 0.067492] and Bonferroni-adjusted p-values 7.67e-10 and 2.32e-8. These confirm the declared literal-recall comparisons. LRU still has higher observed recall at two slots, while measured retention takes 74.11×/116.82× utility time. The result establishes neither an overall best policy nor an adoption decision, and the wider research hypothesis remains open.

The TextWorld controller development (`docs/experiments/textworld-controller-development.md`) separately repairs the scripted selector’s failure to follow the visible quest. It grounds the default generated instructions in admissible commands and reconstructs progress only from retrieved action records; losing the original description also loses the remembered task. Its four declared development games and reserved smoke are separate from the completed experiments above. The completed development cases (`notebooks/runs/2026-11-16/textworld_controller_development/55a4ec2864b1/summary.md`) produce four full-memory wins in three actions each, while no memory, utility and measured retention at two/four slots remain at zero. They retain 2,872 replay episodes, one negative candidate effect and no positive effects; the one winning removal seen in a replay was not selected by the unchanged main ranking.

> [!NOTE]
>
> **A working controller is not a policy gain.** These four games establish successful full-memory controls for the declared grammar, with bounded-memory failures and full costs preserved. The all-policy diagnostic calibration (`docs/experiments/textworld-retention-diagnostic.md`) uses fresh seeds and treats two slots as a constrained control. These development cases supply no confirmation or adoption claim.

The completed TextWorld diagnostic (`notebooks/runs/2026-11-16/textworld_retention_diagnostic/6676e6a9ecd8/summary.md`) retains all sixteen fresh seeds, 256 main episodes and 10,672 replays. Full memory wins 15/16; measured retention wins 1/16 at two slots and 3/16 at four, matching FIFO’s complete score vectors. Random wins 4/16 at four slots. Measured minus utility is +0.062500 at each budget, from one improved seed each with paired SD 0.250000, at 265.92×/469.03× utility’s recorded inclusive time. Early timings overlap unrelated local archive work. Five candidate effects are positive, three negative and 5,328 zero. The saved prompts also expose a full-memory parsing failure and a seventeen-step fallback win; two generated quests need only two actions despite the three-command generation setting. These are descriptive results with controller, capacity and continuation limits, not a confirmation or adoption decision. Review those limits before declaring further development or a fresh comparison.

The current selector, `visible_ordered_instructions_v2`, addresses those two parsing defects by matching only the action clause after the final comma in the default unblended house grammar. Completed prerequisites no longer supply verbs, placement cues or entity names to the next action. The follow-up regressions (`docs/experiments/textworld-controller-development.md#follow-up-instruction-regressions`) use saved visible prompts and synthetic instructions, with progress still requiring retrieved action records. They are parser checks, not new game results. All completed runs above retain their original controller identities and outcomes; the capacity, description competition and FIFO continuation limits remain open.

The isolated selector development (`docs/experiments/textworld-controller-development.md#isolated-development-of-an-improving-removal-selector`) adds an explicit `selection_rule="improving-removal"` option to `run_replay_retention_episode`. It chooses a single removal whose measured continuation outcome improves on FIFO, with ties by admission order; without an improvement it uses the existing score rule. It refuses pressure requiring multiple slots, bytes or tokens and inconsistent repeated baselines. The default remains `retention-score`; the comparison runner selects the opt-in rule only for an explicitly declared `measured_improving` arm. New evidence names the selected rule. The synthetic checks keep the FIFO-horizon limitation visible; these fixtures supply no game-performance or adoption evidence.

The four-game native development (`notebooks/runs/2026-11-16/textworld_improving_removal_development/0b0c070b4b8b/summary.md`) completes all 72 declared main arms and 5,408 replays. Full memory wins 4/4. At four slots the opt-in rule wins 1/4, versus zero for default measured retention, FIFO and utility; seeded random wins the same game. Every bounded arm scores zero at two slots. The candidate takes one measured improving removal, then loses the goal before the third action and wins through fallback in six actions, while full memory wins that game in three. Its recorded inclusive time is 280.10× utility at two slots and 470.22× at four on the shared machine. All four seeds, controls, costs and signed effects remain in the result. This completes the declared development execution, not confirmation, adoption or the broader comparison.

## Optional Dependencies

Install only the integrations you want to run. These are optional; the Python environment and Rust extension are still required.

::::tabs

:::tab "Ollama"

### Ollama (Local LLM)

For notebooks 04 (conversation) with real LLM inference:

```bash
# Install Ollama (macOS)
brew install ollama

# Or download from https://ollama.ai

# Start Ollama server
ollama serve

# Pull a model (in another terminal)
ollama pull llama3.2:1b   # Lightweight model
ollama pull qwen2.5:3b    # Better quality
```

**Without Ollama:** Notebooks use `SimulatedOllamaBackend` for deterministic demo mode.

:::

:::tab "Gymnasium"

### Gymnasium (RL Foundation)

Needed when selecting an actual Gymnasium-backed environment. The fallback demonstrations do not establish that this optional backend ran:

```bash
pip install gymnasium
```

:::

:::tab "MiniGrid"

### MiniGrid (Memory RL)

For notebook 05 with real MiniGrid environments:

```bash
pip install minigrid gymnasium
```

**Without MiniGrid:** Notebook 05 stops with installation instructions. The separate environment-registry examples can still replay traces, but those are not notebook 05’s experiment.

:::

:::tab "Memory Gym"

### Memory Gym (Advanced Memory RL)

Optional benchmark suite for memory-critical tasks:

```bash
pip install memory-gym
```

:::

:::tab "TextWorld"

### TextWorld (Text Adventures)

For notebook 06 with real text game environments:

```bash
pip install textworld
```

**Without TextWorld:** Notebook 06 labels a fixed prerecorded trace. It preserves that trace’s supplied rewards and never labels them live-game outcomes.

:::

::::

### All Optional Dependencies

```bash
# Install these optional environment integrations when you intend to use them
pip install minigrid gymnasium textworld memory-gym

# Verify installation
python -c "import gymnasium; import minigrid; print('OK')"
```

## Backend and Policy Toggles

Several notebooks support backend switching:

| Notebook | Variable         | Options                  | Default      |
| -------- | ---------------- | ------------------------ | ------------ |
| 04       | `BACKEND`        | `"sim"`, `"ollama"`      | `"sim"`      |
| 06       | `POLICY_BACKEND` | `"scripted"`, `"ollama"` | `"scripted"` |

Set to `"ollama"` to use local LLM inference (requires Ollama running).

## Artifact Layout

`RunManager` saves a notebook’s outputs under `runs/YYYY-MM-DD/<notebook_name>/<config_hash>/`. Check that directory for the files the notebook wrote.

| Path                | What you can inspect                |
| ------------------- | ----------------------------------- |
| `config.json`       | Run settings                        |
| `metrics.csv`       | Tabular results                     |
| `figures/`          | PNG plots such as `fig1_pareto.png` |
| `logs/events.jsonl` | Recorded events for debugger import |
| `summary.md`        | Generated run summary               |

The directory layout does not guarantee that every file was produced. `save_logs()` writes the supplied event dictionaries; a metrics table or configuration alone is not a debugger event stream.

## Opening Logs in Debugger

Notebook output goes under `notebooks/runs/` by default. To open a run that has `logs/events.jsonl`, follow [Inspect an exported run](https://causality.in/reckon/inspect-an-exported-run/). If the file is missing, check which outputs the notebook actually saved. A metrics table cannot supply the events.

The [visualization module](../src/reckon/viz/README.md) owns the REST API, WebSocket streaming and opt-in fixture loading instructions.

## Notebook Structure

The notebooks use a header followed by ten numbered sections:

```
0. Header (title, purpose, inputs/outputs, runtime, git hash)
1. Setup (imports, seed, config)
2. Problem + Hypotheses
3. Minimal Theory (2-3 equations, linked to docs)
4. System Mapping (architecture diagram)
5. Experiment Design (metrics, seeds, tests)
6. Demo Run (lite)
7. Full Run (paper mode)
8. Results (tables + plots with captions)
9. Debugger Walkthrough
10. Limitations + Next Steps
Appendix (optional)
```

## Creating New Notebooks

1. Copy `_template/NOTEBOOK_TEMPLATE.ipynb`
2. Update the header section
3. Follow the standard structure
4. Use `_utils` modules for common operations
5. Export artifacts using the [RunManager example](README.md#artifact-helpers).

## Module Reference

### `_utils.config`

```python
from _utils.config import NotebookConfig, hash_config

config = NotebookConfig(
    notebook_name="my_notebook",
    run_mode="demo",
    seed=42,
)
config_hash = hash_config(config)
```

### `_utils.seeds`

```python
from _utils.seeds import set_all_seeds
set_all_seeds(42)  # Sets Python, NumPy, random
```

### Artifact helpers

Use `_utils.artifacts.RunManager` to save the outputs actually produced by a notebook.

```python
from _utils.artifacts import RunManager

run = RunManager(config)
run.save_config()
run.save_metrics(df)
run.save_figure(fig, "pareto")
run.save_logs(events)
run.write_summary(key_metrics)
```

### `_utils.stats`

```python
from _utils.stats import paired_permutation_test, bootstrap_ci

p_value = paired_permutation_test(baseline, treatment)
ci_low, ci_high = bootstrap_ci(deltas, confidence=0.95)
```

### `_utils.plots`

```python
from _utils.plots import setup_plotting, add_caption

setup_plotting()  # Consistent style
fig, ax = plt.subplots()
# ... plot ...
add_caption(ax, "Description", n=100, seeds="42-51", test="permutation")
```

### `_utils.adapters`

Environment adapters for external integrations:

```python
from _utils.adapters import (
    # Tool-Using Conversation Environment (no deps)
    ToolEnv, ToolEnvConfig, get_demo_episodes,

    # Ollama LLM Client
    OllamaConfig, ollama_healthcheck, ollama_chat, OLLAMA_AVAILABLE,

    # Gymnasium Wrapper
    GymEnvWrapper, GymEnvConfig, obs_to_record, GYMNASIUM_AVAILABLE,

    # Environment Registry
    get_env, list_envs, check_env_available, print_env_status,
)

# Check what's available
print_env_status()

# Get an environment with automatic fallback
env, is_real = get_env("minigrid_memory", fallback=True)
```

## Environment Registry

Available environments with fallback support:

| Name                   | Package    | Memory-Critical | Fallback          |
| ---------------------- | ---------- | --------------- | ----------------- |
| `minigrid_memory`      | minigrid   | Yes             | ReplayTraceEnv    |
| `minigrid_keycorridor` | minigrid   | Yes             | ReplayTraceEnv    |
| `minigrid_unlock`      | minigrid   | Yes             | ReplayTraceEnv    |
| `memory_gym_mortar`    | memory_gym | Yes             | ReplayTraceEnv    |
| `memory_gym_mystery`   | memory_gym | Yes             | ReplayTraceEnv    |
| `taxi`                 | gymnasium  | No              | ReplayTraceEnv    |
| `frozen_lake`          | gymnasium  | No              | ReplayTraceEnv    |
| `cliff_walking`        | gymnasium  | No              | ReplayTraceEnv    |
| `textworld`            | textworld  | Yes             | Scripted episodes |

## Troubleshooting

**Import errors?**

```bash
# From the repository root with the project environment active
(cd notebooks && python -c "from _utils import config")
```

**Rust extension not found?** Follow the [kernel Python extension procedure](../kernel/README.md#python-extension) from the repository root, then verify the required import. A completed setup message alone does not establish readiness.

**Viz dependencies missing?**

```bash
# From the repository root with the project environment active
pip install -e ".[dev,viz]"
```

**Ollama not responding?**

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if needed
ollama serve
```

**MiniGrid import error?**

```bash
pip install minigrid gymnasium
python -c "import minigrid; print('OK')"
```

<a id="graceful-degradation"></a>

## When an optional backend is missing

The adapters can use these fallbacks when an optional integration is unavailable:

1. **No Ollama**: Uses `SimulatedOllamaBackend` with deterministic responses
2. **No MiniGrid/Gymnasium**: The registry can return `ReplayTraceEnv`; notebook 05 instead requires the live environment
3. **No TextWorld**: Notebook 06 replays its fixed trace and reports that backend

Record whether a result came from a live, replayed, scripted or simulated backend. A fallback does not test the missing integration. It also does not replace the required Rust extension or the project environment.
