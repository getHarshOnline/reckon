"""CSV exports preserve observations without loading optional table packages."""

import builtins
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "notebooks"))
from _utils.artifacts import RunManager
from _utils.config import NotebookConfig


def test_current_notebook_weight_round_trips_without_silently_defaulting_old_input():
    current = NotebookConfig(
        notebook_name="weight-round-trip", policy_name="evidence_per_byte", evidence_weight=0.75
    )
    assert NotebookConfig.from_dict(current.to_dict()) == current
    for old in [{"causal_weight": 0.75}, {"policy_name": "causal"}]:
        with pytest.raises(ValueError, match="original source revision"):
            NotebookConfig.from_dict(old)


def test_dictionary_export_preserves_csv_values_without_pandas(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name != "pandas", "Dictionary export must not load pandas"
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    run = RunManager(NotebookConfig(notebook_name="csv-test"), base_dir=tmp_path)
    path = run.save_metrics(
        [
            {"text": 'a, b\n"quoted"', "value": 0.5},
            {"text": "second", "value": 1, "extra": "new column"},
        ]
    )
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {"text": 'a, b\n"quoted"', "value": "0.5", "extra": ""},
        {"text": "second", "value": "1", "extra": "new column"},
    ]


@pytest.mark.parametrize("completed", [False, True])
def test_exclusive_run_creation_preserves_incomplete_and_completed_evidence(tmp_path, completed):
    config = NotebookConfig(notebook_name="preserved-experiment")
    run = RunManager(config, base_dir=tmp_path, require_new=True)
    (run.run_dir / "config.json").write_bytes(b"original configuration")
    (run.run_dir / "seed.json.gz").write_bytes(b"original seed evidence")
    if completed:
        (run.run_dir / "complete.json").write_bytes(b"original completion")
    before = {p.relative_to(run.run_dir): p.read_bytes() for p in run.run_dir.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        RunManager(config, base_dir=tmp_path, require_new=True)
    assert {p.relative_to(run.run_dir): p.read_bytes() for p in run.run_dir.rglob("*") if p.is_file()} == before
    assert RunManager(config, base_dir=tmp_path).run_dir == run.run_dir
