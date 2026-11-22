"""A frontier must not replace an absent or zero outcome with another metric."""

from pathlib import Path
import sys

import pytest

from reckon.metrics.pareto import make_quality_vs_overhead_points

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "notebooks"))
from _utils.probe_integration import (  # noqa: E402
    BenchmarkResult,
    ProbeIntegration,
    compute_efficiency_metrics,
    generate_pareto_data,
)


def test_zero_outcome_survives_both_frontiers_and_efficiency_weighting():
    raw = {"probe_overhead_ratio": 0.5, "mean_accuracy": 0.0, "success_rate": 0.9}
    (point,) = make_quality_vs_overhead_points([raw], "mean_accuracy")
    assert (point.x, point.y) == (0.5, 0.0)
    assert (point.x_metric, point.y_metric) == ("probe_overhead_ratio", "mean_accuracy")

    result = BenchmarkResult(
        "measured", base_episodes=2, probe_episodes=2,
        success_rate=0.9, quality_metrics={"mean_accuracy": 0.0},
    )
    (notebook_point,) = generate_pareto_data([result], y_metric="mean_accuracy")
    assert (notebook_point.x, notebook_point.y) == (0.5, 0.0)
    assert notebook_point.to_dict()["y_metric"] == "mean_accuracy"
    efficiency = compute_efficiency_metrics(result, "mean_accuracy")
    assert efficiency["effective_quality"] == 0.0
    assert efficiency["quality_metric"] == "mean_accuracy"


def test_missing_requested_outcome_cannot_fall_back_to_success():
    with pytest.raises(ValueError, match="mean_accuracy"):
        make_quality_vs_overhead_points(
            [{"probe_overhead_ratio": 0.2, "success_rate": 0.9}], "mean_accuracy",
        )
    result = BenchmarkResult("candidate", success_rate=0.9)
    with pytest.raises(ValueError, match="mean_accuracy"):
        generate_pareto_data([result], y_metric="mean_accuracy")
    with pytest.raises(ValueError, match="mean_accuracy"):
        compute_efficiency_metrics(result, "mean_accuracy")


def test_absent_success_is_distinct_from_observed_zero():
    result = ProbeIntegration().get_result("candidate")
    assert result.to_dict()["success_rate"] is None
    with pytest.raises(ValueError, match="success_rate"):
        generate_pareto_data([result], y_metric="success_rate")
    result.success_rate = 0.0
    (point,) = generate_pareto_data([result], y_metric="success_rate")
    assert point.y == 0.0


@pytest.mark.parametrize("value", [None, True, "0.5", float("nan"), float("inf"), 10**400])
def test_invalid_coordinates_never_become_measured_zero(value):
    for key in ["mean_accuracy", "probe_overhead_ratio"]:
        raw = {"mean_accuracy": 0.7, "probe_overhead_ratio": 0.2, key: value}
        with pytest.raises(ValueError, match=key):
            make_quality_vs_overhead_points([raw], "mean_accuracy")
    result = BenchmarkResult("candidate", quality_metrics={"mean_accuracy": value})
    with pytest.raises(ValueError, match="mean_accuracy"):
        generate_pareto_data([result], y_metric="mean_accuracy")


def test_missing_or_misspelled_cost_cannot_become_free():
    with pytest.raises(ValueError, match="probe_overhead_ratio"):
        make_quality_vs_overhead_points([{"mean_accuracy": 0.7}], "mean_accuracy")
    with pytest.raises(ValueError, match="Unknown cost"):
        generate_pareto_data([], y_metric="success_rate", x_metric="probe_overhed_ratio")
    result = BenchmarkResult("candidate", probe_episodes=float("nan"), success_rate=0.5)
    with pytest.raises(ValueError, match="probe_episodes"):
        generate_pareto_data([result], y_metric="success_rate", x_metric="probe_episodes")


def test_callers_must_choose_the_outcome():
    with pytest.raises(TypeError):
        make_quality_vs_overhead_points([])
    with pytest.raises(TypeError):
        generate_pareto_data([])
    with pytest.raises(TypeError):
        compute_efficiency_metrics(BenchmarkResult("candidate"))
