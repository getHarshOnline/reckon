"""Saved influence diagnostics must retain their meaning and byte identity."""

import os
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from reckon.core.causality import DirectInfluenceRecords, TransitivityReport
from reckon.core.resources import ResourceVector


def test_report_order_does_not_depend_on_hash_seed_or_insertion_order():
    source = """
import sys
from reckon.core.causality import DirectInfluenceRecords
from reckon.core.resources import ResourceVector
records = DirectInfluenceRecords(ResourceVector(memory_slots=10))
pairs = [("A", "B"), ("B", "C"), ("D", "E"), ("E", "F"),
         ("α", "β"), ("β", "γ"), ("e\\u0301", "é"), ("é", "終")]
if int(sys.argv[1]) % 2:
    pairs.reverse()
for source, target in pairs:
    records.add_relation(source, target, 0.5)
print(records.check_transitivity().to_json())
"""
    outputs = []
    for seed in [1, 2, 7, 19, 42, 101]:
        result = subprocess.run(
            [sys.executable, "-c", source, str(seed)],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(result.stdout)
    assert len(set(outputs)) == 1


def test_empty_report_has_the_versioned_exact_encoding():
    report = DirectInfluenceRecords(ResourceVector()).check_transitivity()
    assert report.to_canonical_json() == (
        '{"alpha":0.05,"multiple_testing_correction":"none",'
        '"schema_version":"reckon.transitivity-report/v1",'
        '"total_triples_tested":0,"violation_rate":0.0,"violations":[]}'
    )


def test_canonical_encoding_retains_duplicate_entries_and_does_not_mutate():
    records = DirectInfluenceRecords(ResourceVector())
    records.add_relation("é", "β", 0.5)
    records.add_relation("β", "終", 0.5)
    report = records.check_transitivity()
    missing = report.violations[0]
    measured = replace(missing, a_c_distinguishability=0.0, a_c_threshold=0.2)
    report.violations = [measured, missing, missing]
    before = report.to_dict()
    reordered = replace(report, violations=list(reversed(report.violations)))
    encoded = report.to_canonical_json()
    assert encoded == reordered.to_canonical_json()
    assert encoded.isascii() and not encoded.endswith("\n")
    assert report.to_dict() == before
    entries = json.loads(encoded)["violations"]
    assert len(entries) == 3
    assert sum(item["a_c_distinguishability"] is None for item in entries) == 2
    assert sum(item["a_c_distinguishability"] == 0.0 for item in entries) == 1
    assert all(item["triple"] == ["é", "β", "終"] for item in entries)


def test_metadata_changes_the_artifact_but_not_the_pair_decisions():
    records = DirectInfluenceRecords(ResourceVector())
    records.add_relation("A", "B", 0.5)
    records.add_relation("B", "C", 0.5)
    first = records.check_transitivity()
    second = records.check_transitivity(alpha=0.01, multiple_testing_correction="holm")
    assert first.violations == second.violations
    assert first.to_canonical_json() != second.to_canonical_json()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_encoding_refuses_nonfinite_values(value):
    report = TransitivityReport([], 0.0, 0, value, "none")
    with pytest.raises(ValueError, match="Out of range float"):
        report.to_canonical_json()
