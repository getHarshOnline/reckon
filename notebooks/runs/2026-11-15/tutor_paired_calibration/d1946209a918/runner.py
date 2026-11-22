"""Repeat the declared exploratory Tutor condition with repaired random streams."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / 'notebooks'))
from _utils.artifacts import RunManager
from _utils.config import NotebookConfig
from reckon.experiments import load_experiment, compare_experiments
from reckon import _rust

old_path = Path('notebooks/runs/2026-11-15/tutor_retention_calibration/24a235e37516/config.json')
old = json.loads((root / old_path).read_text())
source_paths = sorted(old['custom']['source_sha256'])
source_hashes = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in source_paths}
commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
assert commit.startswith('b9c2809')
assert not subprocess.check_output(['git', '-C', str(root), 'diff', 'HEAD', '--', *source_paths])
config = NotebookConfig(
    notebook_name='tutor_paired_calibration', seed=100, seed_count=5,
    budget_slots=2, budget_bytes=None, task_name='tutor', num_episodes=5,
    policy_name='matrix', eval_n_trials=4, git_hash=commit,
    custom={
        'purpose': 'Repeat the exploratory condition after input-pairing repair; not a powered test or a new held-out sample.',
        'earlier_configuration': old_path.as_posix(),
        'earlier_configuration_sha256': hashlib.sha256((root / old_path).read_bytes()).hexdigest(),
        'declaration': old['custom']['declaration'],
        'policies': old['custom']['policies'], 'budgets': old['custom']['budgets'],
        'source_sha256': source_hashes,
    },
)
run = RunManager(config, root / 'notebooks/runs')
assert not (run.run_dir / 'comparison.json').exists()
run.save_config()
(run.run_dir / 'experiment.json').write_text(json.dumps(config.custom['declaration'], indent=2)+'\n')
shutil.copy2(__file__, run.run_dir / 'runner.py')
shutil.copy2(root / 'kernel/Cargo.lock', run.run_dir / 'kernel.Cargo.lock')
report = compare_experiments(
    [load_experiment(str(run.run_dir / 'experiment.json'))],
    config.custom['policies'], config.custom['budgets'], list(range(100,105)),
)
(run.run_dir / 'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
rows = [{k:v for k,v in row.items() if k != 'runs'} for row in report['rows']]
run.save_metrics(rows)
env = {
    'python': platform.python_version(), 'platform': platform.platform(),
    'dependencies': {name:importlib.metadata.version(name) for name in ['numpy','scipy','PyYAML','reckon']},
    'extension_sha256': hashlib.sha256(Path(_rust.__file__).read_bytes()).hexdigest(),
    'source_commit': commit, 'uncommitted_source': False,
    'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}
(run.run_dir / 'env_meta.json').write_text(json.dumps(env,indent=2)+'\n')
task_episodes = sum(row['task_episodes'] for row in rows)
probe_episodes = sum(row['probe_episodes'] for row in rows)
notes = (
    'The source separates student, per-question response, concept-choice and hint-choice streams. '
    'All workload, policy, budget and probe settings match the earlier declared calibration. '
    'Seeds 100–104 are reused exploratory seeds, not a held-out confirmation. '
    'The comparison remains a fresh-task retention probe, not live-state continuation. '
    'All old runs remain unchanged. See [raw runs and paired probe outcomes](comparison.json), '
    '[complete configuration](config.json), [metrics](metrics.csv), [environment](env_meta.json), '
    '[captured kernel lockfile](kernel.Cargo.lock) and [runner](runner.py).\n\n'
    '| Policy | Slots | Mean improvement | Seed standard deviation | Probe episodes |\n'
    '| --- | --- | --- | --- | --- |\n' + '\n'.join(
        f"| {r['policy']} | {r['budget_slots'] if r['budget_slots'] is not None else 'control'} | {r['mean']:.6f} | {r['stdev']:.6f} | {r['probe_episodes']} |" for r in rows
    )
)
run.write_summary({'rows':len(rows),'seed_runs':sum(len(r['runs']) for r in report['rows']),
                   'task_episodes':task_episodes,'probe_episodes':probe_episodes,
                   'elapsed_s':sum(r['elapsed_s'] for r in rows)}, notes)
print(run.run_dir)
print(json.dumps(rows,indent=2))
