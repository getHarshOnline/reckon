"""Decode v1 bytes captured before the metric type rename at e9be1ab."""

import json
from pathlib import Path

import pytest

pytest.importorskip("betterproto2", reason="Install the rpc extra on Python 3.10+.")
from reckon.generated.reckon.core import v1

FIXTURES = Path(__file__).parent / "fixtures/historical_run_metrics_v1.json"


@pytest.mark.parametrize("case", json.loads(FIXTURES.read_text()))
def test_historical_metrics_round_trip(case):
    wire = bytes.fromhex(case["metrics_hex"])
    summary_wire = bytes.fromhex(case["summary_hex"])
    metrics = v1.HistoricalRunMetricsV1.parse(wire)
    assert bytes(metrics) == wire
    assert json.loads(metrics.to_json()) == case["json"]
    assert bytes(v1.HistoricalRunMetricsV1.from_dict(case["json"])) == wire
    summary = v1.RunSummary.parse(summary_wire)
    assert bytes(summary.metrics) == wire
    assert bytes(summary) == summary_wire
    assert bytes(v1.RunSummary.from_json(summary.to_json())) == summary_wire
    assert metrics.causal_precision == case["json"].get("causalPrecision")
    assert metrics.useful_memory_rate == case["json"].get("usefulMemoryRate")


def test_original_saved_metric_keys_keep_their_values():
    source = Path(__file__).resolve().parents[2] / "runs/_fixtures/golden_run_export.json"
    saved = json.loads(source.read_text())["summary"]["metrics"]
    metrics = v1.HistoricalRunMetricsV1.from_dict(saved)
    assert metrics.causal_precision == saved["causal_precision"]
    assert metrics.success_rate == saved["success_rate"]
    assert metrics.useful_memory_rate is None
    assert not hasattr(v1, "RunMetrics")
